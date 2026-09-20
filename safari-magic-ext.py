#!/usr/bin/env python3
"""Safari Magic Extensions Manager CLI & GUI.

Community sharing & distribution platform for Apple Safari AI-generated Magic Extensions.
Features:
  1. List active & unlinked Safari Magic Extensions with AI prompts and SF Symbols.
  2. Pack extensions into shareable single-file `.magicext` bundles with AI metadata.
  3. Install extensions from local `.magicext` files, direct URLs, or Community Registry.
  4. Explore curated community AI extensions, inspect prompts, and 1-click install.
  5. Export/Backup extensions to Downloads as folder or ZIP.
  6. Update existing extensions and sync source modifications.
  7. Dual-tab native macOS GUI (My Extensions + Community Hub) via tkinter.

Runs on the Python that ships with macOS (3.9.6). The `from __future__` import
below keeps the `X | None` annotations lazy so they do not need Python 3.10.
"""

# Must precede every other statement. Without it, the PEP 604 annotations in
# this file are evaluated at import time and raise TypeError on Python 3.9.
from __future__ import annotations

__version__ = "1.1.1"

import argparse
import base64
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

MAGIC_EXTENSIONS_DIR = (
    Path.home()
    / "Library/Containers/com.apple.Safari/Data/Library/Safari/MagicExtensions"
)
DB_PATH = MAGIC_EXTENSIONS_DIR / "Extensions.db"
MAC_ABSOLUTE_TIME_OFFSET = 978307200.0  # 2001-01-01 00:00:00 UTC

# Published community catalog, shared with the web gallery.
DEFAULT_REGISTRY_URL = (
    "https://vatsal057.github.io/safari-magic-extensions/community_registry.json"
)

# Base used to resolve relative `download_url` values from the registry.
REGISTRY_BASE_URL = DEFAULT_REGISTRY_URL.rsplit("/", 1)[0] + "/"

# When running from a repository checkout the catalog and packages are on disk.
# Once `install-cli.sh` copies this script to ~/.local/bin there is no adjacent
# `web/` directory, so the remote catalog above becomes the only source.
_SCRIPT_DIR = Path(__file__).resolve().parent
LOCAL_REGISTRY_PATH = _SCRIPT_DIR / "web" / "community_registry.json"
LOCAL_REGISTRY_CANDIDATES = (
    LOCAL_REGISTRY_PATH,
    _SCRIPT_DIR / "community_registry.json",
)
CACHE_DIR = Path.home() / "Library/Caches/safari-magic-ext"
CACHED_REGISTRY_PATH = CACHE_DIR / "community_registry.json"
USER_AGENT = "SafariMagicExtensionsManager/1.0"


def get_db_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open connection to the SQLite database with WAL awareness."""
    if not db_path.exists():
        raise FileNotFoundError(
            f"Safari Magic Extensions database not found at:\n{db_path}\n"
            "Please ensure Safari has been launched at least once."
        )
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.OperationalError as exc:
        _prompt_for_full_disk_access(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _prompt_for_full_disk_access(db_path: Path) -> None:
    """Open FDA settings and print exact fix steps, then exit."""
    # $TERM_PROGRAM is set by Terminal.app, iTerm2, Warp, Hyper, etc.
    terminal_name = Path(os.getenv("TERM_PROGRAM", "Terminal")).stem or "Terminal"

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║         Full Disk Access required: opening settings…         ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print("macOS is blocking access to Safari's extension database.")
    print(f"  {db_path}")
    print()
    print(f"Fix (one-time, ~30 seconds):")
    print(f"  1. In System Settings (opening now) → find '{terminal_name}'")
    print( "       If it's listed but OFF, toggle it ON.")
    print( "       If it's not listed, click '+' and select your terminal app.")
    print( "  2. Quit and reopen Terminal.")
    print( "  3. Re-run your command.")
    print()

    # Open directly to the Full Disk Access pane. Works without FDA.
    subprocess.run(
        ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"],
        check=False,
    )

    sys.exit(1)


def invocation_name() -> str:
    """How the user invoked this tool, for copy-pasteable hints.

    Reads as `safari-magic-ext` once installed, or `python3 safari-magic-ext.py`
    when run from a repository checkout.
    """
    name = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "safari-magic-ext"
    if name.endswith(".py"):
        return f"python3 {name}"
    return name or "safari-magic-ext"


def slugify(value: str) -> str:
    """Convert a name into a lowercase, dash-separated catalog identifier.

    Registry IDs are slugs (e.g. "night-meadow-new-tab") so that
    `safari-magic-ext install <id>` is memorable and copy-pasteable.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug or "extension"


def clean_target_folder_name(name: str) -> str:
    """Ensure destination directory name matches Safari's convention (CamelCase-HEX)."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", name)
    if not cleaned:
        cleaned = "CustomExtension"
    if not re.search(r"-[0-9A-Fa-f]{4}$", cleaned):
        suffix = uuid.uuid4().hex[:4].upper()
        cleaned = f"{cleaned}-{suffix}"
    return cleaned


def synthesize_manifest_if_missing(extension_dir: Path) -> None:
    """Create a default manifest.json if one doesn't exist."""
    manifest_path = extension_dir / "manifest.json"
    if manifest_path.exists():
        return

    html_files = list(extension_dir.glob("*.html"))
    entry_html = (
        "index.html"
        if (extension_dir / "index.html").exists()
        else (html_files[0].name if html_files else "newtab.html")
    )

    data = {
        "manifest_version": 3,
        "name": extension_dir.name.replace("-", " ").title(),
        "version": "1.0",
        "description": f"{extension_dir.name.replace('-', ' ').title()} Safari Extension",
        "browser_url_overrides": {"newtab": entry_html},
        "browser_specific_settings": {
            "safari": {
                "prompt": f"Create {extension_dir.name.replace('-', ' ').title()}"
            }
        },
        "icon_variants": [{"any": "symbol:moon.stars.fill"}],
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"-> Generated default manifest.json using entry point '{entry_html}'")


def apply_metadata_to_manifest(
    extension_dir: Path, name: str | None = None, prompt: str | None = None
) -> None:
    """Write name/prompt into an extension's manifest.json, if it has one.

    Safari reads the AI prompt from `browser_specific_settings.safari.prompt`,
    so packages and installs keep it in sync with magic.json / the database.
    """
    manifest_path = extension_dir / "manifest.json"
    if not manifest_path.exists():
        return

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if prompt:
            settings = data.setdefault("browser_specific_settings", {})
            safari = settings.setdefault("safari", {})
            safari["prompt"] = prompt
        if name:
            data["name"] = name

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[Warning] Could not update manifest.json: {e}")


def normalize_manifest(extension_dir: Path) -> dict:
    """Inspect and adapt manifest.json so Safari Magic Extensions engine accepts it."""
    synthesize_manifest_if_missing(extension_dir)
    manifest_path = extension_dir / "manifest.json"

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    name = data.get("name") or extension_dir.name
    description = data.get("description", "")

    if "browser_specific_settings" not in data:
        data["browser_specific_settings"] = {}
    if "safari" not in data["browser_specific_settings"]:
        data["browser_specific_settings"]["safari"] = {}

    safari_settings = data["browser_specific_settings"]["safari"]
    prompt = safari_settings.get("prompt")
    if not prompt:
        prompt = description or name
        safari_settings["prompt"] = prompt

    icon_variants = data.get("icon_variants", [])
    selected_symbol = "puzzlepiece.extension"
    if icon_variants and isinstance(icon_variants, list):
        first_icon = icon_variants[0].get("any", "")
        if isinstance(first_icon, str) and first_icon.startswith("symbol:"):
            selected_symbol = first_icon.replace("symbol:", "", 1)
        else:
            data["icon_variants"] = [{"any": f"symbol:{selected_symbol}"}]
    else:
        data["icon_variants"] = [{"any": f"symbol:{selected_symbol}"}]

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return {
        "name": name,
        "description": description,
        "prompt": prompt,
        "selected_symbol": selected_symbol,
    }


def get_installed_extensions(conn: sqlite3.Connection | None = None) -> list[dict]:
    """Retrieve all registered Safari Magic extensions."""
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, directory_name, selected_symbol, symbol_color_name,
                   prompt, description, creation_date, modified_date
            FROM magic_extensions
            WHERE name != ''
            ORDER BY modified_date DESC
            """
        )
        rows = cursor.fetchall()
        results = []
        for r in rows:
            dir_path = MAGIC_EXTENSIONS_DIR / r["directory_name"]
            results.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "directory_name": r["directory_name"],
                    "folder_path": str(dir_path),
                    "exists_on_disk": dir_path.exists(),
                    "selected_symbol": r["selected_symbol"],
                    "symbol_color_name": r["symbol_color_name"],
                    "prompt": r["prompt"],
                    "description": r["description"],
                    "creation_date": r["creation_date"] + MAC_ABSOLUTE_TIME_OFFSET,
                    "modified_date": r["modified_date"] + MAC_ABSOLUTE_TIME_OFFSET,
                }
            )
        return results
    finally:
        if close_conn:
            conn.close()


# =========================================================================
#  Package Standard (.magicext) & Packaging
# =========================================================================

# Never shipped inside a .magicext bundle.
IGNORE_NAMES = (
    ".git",
    ".vscode",
    ".tmp",
    "node_modules",
    ".DS_Store",
    "Thumbs.db",
    "magic.json",
)


def _detect_author() -> str:
    """Best-effort author detection: git config > $USER > 'Anonymous'."""
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        name = result.stdout.strip()
        if name:
            return name
    except Exception:
        pass
    return os.getenv("USER") or "Anonymous"


def interactive_select_extension(
    conn: sqlite3.Connection | None = None,
    prompt_text: str = "Select an extension",
) -> dict:
    """Display a numbered list of installed extensions and return the chosen one.

    Raises SystemExit if no extensions are found or the user cancels.
    Auto-selects when only one extension is installed.
    """
    extensions = get_installed_extensions(conn)
    if not extensions:
        print("[Error] No Safari Magic Extensions found on this Mac.")
        print("  Open Safari, use 'Describe an Extension', and create one first.")
        sys.exit(1)

    if len(extensions) == 1:
        ext = extensions[0]
        print(f"\n🪄 Found 1 extension: '{ext['name']}'")
        short = (ext["prompt"] or "")[:70]
        if short:
            print(f"   Prompt: \"{short}{'...' if len(ext['prompt']) > 70 else ''}\"")
        answer = input("Use this extension? [Y/n]: ").strip().lower()
        if answer in ("", "y", "yes"):
            return ext
        print("Cancelled.")
        sys.exit(0)

    print(f"\n🪄 Found {len(extensions)} Safari Magic Extensions:\n")
    for i, ext in enumerate(extensions, 1):
        short = (ext["prompt"] or "")[:60]
        if len(ext["prompt"] or "") > 60:
            short += "..."
        print(f"  [{i}] {ext['name']}")
        if short:
            print(f"       {short}")

    print()
    while True:
        raw = input(f"{prompt_text} [1-{len(extensions)}] (or 'q' to quit): ").strip()
        if raw.lower() in ("q", "quit", "exit"):
            print("Cancelled.")
            sys.exit(0)
        try:
            idx = int(raw)
            if 1 <= idx <= len(extensions):
                return extensions[idx - 1]
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(extensions)}.")


def find_installed_extension(
    target_identifier: str, conn: sqlite3.Connection | None = None
) -> dict | None:
    """Find an installed extension by ID, directory name, or name.

    Exact matches (ID, directory, full name) win. A partial name match is only
    accepted when exactly one extension matches, so a vague target like "night"
    reports the ambiguity instead of silently picking the first hit.
    """
    extensions = get_installed_extensions(conn)
    needle = target_identifier.strip().lower()

    for ext in extensions:
        if needle in (
            ext["id"].lower(),
            ext["directory_name"].lower(),
            (ext["name"] or "").lower(),
        ):
            return ext

    partial = [ext for ext in extensions if needle and needle in (ext["name"] or "").lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        names = ", ".join(f"'{e['name']}'" for e in partial)
        raise ValueError(
            f"'{target_identifier}' matches {len(partial)} extensions: {names}. "
            "Use the full name or the extension ID."
        )
    return None


def pack_extension(
    target_identifier: str,
    output_dir: Path | str | None = None,
    author: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> Path:
    """Package an extension into a shareable single-file .magicext bundle.

    Embeds magic.json containing the exact AI prompt, SF Symbol, badge tint color,
    author handle, and description.
    """
    candidate = Path(target_identifier).expanduser()
    is_folder_target = candidate.is_dir()

    matched: dict | None = None
    if is_folder_target:
        # Packaging a plain folder needs no database access, so `convert` works
        # even on a machine where Safari has never created Extensions.db.
        source_dir = candidate.resolve()
    else:
        close_conn = False
        if conn is None:
            conn = get_db_connection()
            close_conn = True
        try:
            matched = find_installed_extension(target_identifier, conn)
        finally:
            if close_conn:
                conn.close()

        if not matched:
            raise ValueError(
                f"No active extension or valid folder found matching '{target_identifier}'."
            )
        source_dir = Path(matched["folder_path"])

    if not source_dir.exists():
        raise FileNotFoundError(f"Extension files not found at: {source_dir}")

    dest_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir
        else (Path.home() / "Downloads")
    )
    dest_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="safari_ext_pack_") as tmp_dir:
        # Stage a copy so normalizing the manifest never edits the user's files.
        # Keep the original folder name: normalize_manifest derives a default
        # extension name from it when the folder has no manifest.json.
        staging = Path(tmp_dir) / source_dir.name
        shutil.copytree(
            source_dir, staging, ignore=shutil.ignore_patterns(*IGNORE_NAMES)
        )

        manifest_meta = normalize_manifest(staging)

        if matched is None:
            matched = {
                "id": str(uuid.uuid4()).upper(),
                "name": manifest_meta["name"],
                "directory_name": source_dir.name,
                "selected_symbol": manifest_meta["selected_symbol"],
                "symbol_color_name": "blue",
                "prompt": manifest_meta["prompt"],
                "description": manifest_meta["description"],
            }
        else:
            # The database is authoritative for installed extensions; make the
            # packaged manifest agree with it.
            apply_metadata_to_manifest(
                staging, name=matched["name"], prompt=matched["prompt"]
            )

        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", matched["name"]).strip("_")
        if not safe_name:
            safe_name = "SafariExtension"
        output_file = dest_dir / f"{safe_name}.magicext"

        package_meta = {
            "magic_format_version": 1,
            "id": matched["id"],
            "name": matched["name"],
            "author": author or _detect_author(),
            "version": "1.0",
            "description": matched["description"],
            "prompt": matched["prompt"],
            "selected_symbol": matched["selected_symbol"],
            "symbol_color_name": matched["symbol_color_name"],
            "packaged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zf:
            # magic.json lives at the archive root.
            zf.writestr("magic.json", json.dumps(package_meta, indent=2))

            for root, dirs, files in os.walk(staging):
                dirs[:] = [d for d in dirs if d not in IGNORE_NAMES]
                for file in files:
                    if file in IGNORE_NAMES:
                        continue
                    full_path = Path(root) / file
                    zf.write(full_path, arcname=str(full_path.relative_to(staging)))

    print(f"✓ Packaged '{matched['name']}' into .magicext:")
    print(f"  Bundle: {output_file}")
    print(f"  Prompt: {matched['prompt']}")
    print(f"  Symbol: {matched['selected_symbol']} ({matched['symbol_color_name']})")
    return output_file


# =========================================================================
#  Community Registry
# =========================================================================

class CommunityRegistry:
    """Manages browsing and resolving extensions from the community catalog."""

    def __init__(self, local_path: Path | None = None):
        # An explicit path wins; otherwise prefer a repo checkout beside this
        # script, falling back to the last successful remote download.
        if local_path is not None:
            self.local_candidates: tuple[Path, ...] = (Path(local_path),)
        else:
            self.local_candidates = LOCAL_REGISTRY_CANDIDATES + (CACHED_REGISTRY_PATH,)
        self._cache: dict | None = None

    @property
    def local_path(self) -> Path:
        """First on-disk catalog that actually exists (else the preferred path)."""
        for candidate in self.local_candidates:
            if candidate.exists():
                return candidate
        return self.local_candidates[0]

    def _read_local(self) -> dict | None:
        for candidate in self.local_candidates:
            if not candidate.exists():
                continue
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as err:
                print(f"[Warning] Failed to read local registry {candidate}: {err}")
        return None

    def fetch_catalog(self) -> dict:
        """Load the catalog from the published URL, falling back to local copies.

        Resolution order:
          1. $SAFARI_MAGIC_REGISTRY_URL (override, useful for testing a fork)
          2. The published GitHub Pages catalog
          3. A `web/community_registry.json` next to this script (repo checkout)
          4. The cached copy from the last successful download
        """
        if self._cache is not None:
            return self._cache

        remote_url = os.getenv("SAFARI_MAGIC_REGISTRY_URL") or DEFAULT_REGISTRY_URL
        data = None

        try:
            req = urllib.request.Request(
                remote_url, headers={"User-Agent": USER_AGENT}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self._write_cache(data)
        except Exception as err:
            print(f"[Notice] Remote registry unavailable ({err}). Using local catalog.")

        if not data:
            data = self._read_local()

        if not data:
            data = {"version": 1, "extensions": []}

        self._cache = data
        return data

    @staticmethod
    def _write_cache(data: dict) -> None:
        """Persist the downloaded catalog so offline runs still work."""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(CACHED_REGISTRY_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass  # A warm cache is a convenience, never a requirement.

    def list_all(self) -> list[dict]:
        """Return all catalog extensions."""
        catalog = self.fetch_catalog()
        return catalog.get("extensions", [])

    def search(self, query: str = "") -> list[dict]:
        """Search catalog by name, prompt, description, or tags."""
        extensions = self.list_all()
        if not query:
            return extensions
        q = query.lower()
        matches = []
        for item in extensions:
            tags = " ".join(item.get("tags", []))
            # `id` is included so that searching for the slug shown on the
            # website and in `install <id>` finds the extension.
            haystack = (
                f"{item.get('id', '')} {item.get('name', '')} "
                f"{item.get('description', '')} {item.get('prompt', '')} "
                f"{item.get('author', '')} {tags} {item.get('category', '')}"
            ).lower()
            if q in haystack:
                matches.append(item)
        return matches

    def get(self, item_id: str) -> dict | None:
        """Find a catalog item by ID, slug, or name (all case-insensitive)."""
        needle = item_id.strip().lower()
        needle_slug = slugify(item_id)
        for item in self.list_all():
            candidates = {
                item.get("id", "").lower(),
                slugify(item.get("id", "")),
                item.get("name", "").lower(),
                slugify(item.get("name", "")),
            }
            if needle in candidates or needle_slug in candidates:
                return item
        return None


# =========================================================================
#  Package Installation & Security
# =========================================================================

def assert_archive_is_safe(archive_path: Path) -> None:
    """Reject archives that could write outside their extraction directory.

    Guards against three separate tricks:
      * absolute member paths ("/etc/passwd")
      * parent traversal ("../../etc/passwd"), including Windows separators
      * symlink members, which extract harmlessly but redirect later writes
    """
    with zipfile.ZipFile(archive_path, "r") as zf:
        for member in zf.infolist():
            name = member.filename
            normalized = name.replace("\\", "/")

            if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
                raise ValueError(
                    f"Security Exception: absolute path in archive member '{name}'"
                )

            if any(part == ".." for part in PurePosixPath(normalized).parts):
                raise ValueError(
                    f"Security Exception: path traversal in archive member '{name}'"
                )

            # Upper 16 bits of external_attr hold the Unix mode for zips
            # created on POSIX systems.
            mode = member.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                raise ValueError(
                    f"Security Exception: symbolic link in archive member '{name}'"
                )


def safe_extract_archive(archive_path: Path, dest_dir: Path) -> dict:
    """Extract a .magicext/.zip archive, refusing anything that escapes dest_dir."""
    dest_dir = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    assert_archive_is_safe(archive_path)

    with zipfile.ZipFile(archive_path, "r") as zf:
        # Re-verify each resolved destination, which also catches members that
        # would land outside dest_dir via an intermediate symlink.
        for member in zf.infolist():
            member_path = (dest_dir / member.filename).resolve()
            if member_path != dest_dir and not member_path.is_relative_to(dest_dir):
                raise ValueError(
                    f"Security Exception: Zip traversal attempt detected in '{member.filename}'"
                )

        zf.extractall(dest_dir)

    magic_meta = {}
    magic_file = dest_dir / "magic.json"
    if magic_file.exists():
        try:
            with open(magic_file, "r", encoding="utf-8") as f:
                magic_meta = json.load(f)
            # Remove magic.json from Safari extension folder so Safari isn't confused
            magic_file.unlink()
        except Exception as e:
            print(f"[Warning] Could not parse magic.json: {e}")

    return magic_meta


def resolve_source_to_package(source: str, temp_workspace: Path) -> tuple[Path, dict]:
    """Resolve a source (local file, URL, or community registry ID) into a local archive."""
    source_str = str(source).strip()

    # 1. Direct Web URL (HTTP/HTTPS)
    if source_str.startswith("http://") or source_str.startswith("https://"):
        parsed = urllib.parse.urlparse(source_str)
        filename = Path(parsed.path).name or "package.magicext"
        if not filename.endswith((".magicext", ".zip")):
            filename += ".magicext"
        download_target = temp_workspace / filename
        print(f"-> Downloading extension package from:\n   {source_str}")
        req = urllib.request.Request(
            source_str, headers={"User-Agent": "SafariMagicExtensionsManager/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            with open(download_target, "wb") as f:
                shutil.copyfileobj(resp, f)
        return download_target, {}

    # 2. Local File (.magicext or .zip)
    local_path = Path(source_str).expanduser().resolve()
    if local_path.is_file():
        return local_path, {}

    # 3. Community Registry Item
    registry = CommunityRegistry()
    catalog_item = registry.get(source_str)
    if catalog_item:
        url = catalog_item.get("download_url", "")
        if not url:
            raise ValueError(
                f"Community extension '{catalog_item.get('name', source_str)}' has no "
                "download_url in the catalog."
            )

        # Check if it references a local extension already on disk
        if url.startswith("local:"):
            folder_ref = url.replace("local:", "", 1)
            candidate_dir = MAGIC_EXTENSIONS_DIR / folder_ref
            if not candidate_dir.exists():
                raise FileNotFoundError(
                    f"Catalog entry '{catalog_item.get('name', source_str)}' points at the "
                    f"local folder '{folder_ref}', which is not installed in Safari."
                )
            print(f"-> Packing local showcase extension '{catalog_item['name']}'...")
            pkg = pack_extension(
                target_identifier=folder_ref,
                output_dir=temp_workspace,
                author=catalog_item.get("author"),
            )
            return pkg, catalog_item

        # Check if URL is a relative or local package file path
        rel_candidate = (registry.local_path.parent / url).resolve()
        if rel_candidate.is_file():
            return rel_candidate, catalog_item

        cwd_candidate = Path(url).expanduser().resolve()
        if cwd_candidate.is_file():
            return cwd_candidate, catalog_item

        # Relative URLs in the catalog are published alongside it, so resolve
        # them against the registry base rather than giving up.
        download_url = (
            url
            if url.startswith(("http://", "https://"))
            else urllib.parse.urljoin(REGISTRY_BASE_URL, url)
        )
        download_target = temp_workspace / f"{slugify(catalog_item['id'])}.magicext"
        print(f"-> Downloading '{catalog_item['name']}' from registry...")
        req = urllib.request.Request(download_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(download_target, "wb") as f:
                shutil.copyfileobj(resp, f)
        return download_target, catalog_item

    # 4. Local Folder (direct sideload)
    if local_path.is_dir():
        return local_path, {}

    raise FileNotFoundError(
        f"Unable to resolve source '{source_str}'. It is not a valid file, URL, or community registry item."
    )


def install_package(
    source: str | Path,
    color: str | None = None,
    symbol: str | None = None,
    name: str | None = None,
    relaunch: bool = True,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Install a .magicext, .zip, directory, or community extension into Safari."""
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True

    with tempfile.TemporaryDirectory(prefix="safari_ext_install_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        resolved_path, registry_info = resolve_source_to_package(str(source), tmp_path)

        # If it's a directory, install directly
        if resolved_path.is_dir():
            try:
                return add_extension(
                    conn=conn,
                    source_path=resolved_path,
                    color=color or "blue",
                    symbol=symbol,
                    name=name,
                    relaunch=relaunch,
                )
            finally:
                if close_conn:
                    conn.close()

        # It's an archive (.magicext or .zip)
        extract_dir = tmp_path / "extracted"
        package_meta = safe_extract_archive(resolved_path, extract_dir)

        # Merge metadata with explicit overrides
        effective_name = (
            name
            or package_meta.get("name")
            or registry_info.get("name")
            or resolved_path.stem
        )
        effective_symbol = (
            symbol
            or package_meta.get("selected_symbol")
            or registry_info.get("selected_symbol")
        )
        effective_color = (
            color
            or package_meta.get("symbol_color_name")
            or registry_info.get("symbol_color_name")
            or "blue"
        )
        effective_prompt = (
            package_meta.get("prompt")
            or registry_info.get("prompt")
        )

        # If prompt is present in magic.json, sync it into manifest.json
        if effective_prompt:
            apply_metadata_to_manifest(
                extract_dir, name=effective_name, prompt=effective_prompt
            )

        # Rename extract_dir to match effective name so Safari directory is descriptive
        clean_ext_name = re.sub(r"[^a-zA-Z0-9_-]", "", effective_name) or "MagicExtension"
        named_extract_dir = tmp_path / clean_ext_name
        if named_extract_dir != extract_dir:
            extract_dir.rename(named_extract_dir)
            extract_dir = named_extract_dir

        try:
            ext_id = add_extension(
                conn=conn,
                source_path=extract_dir,
                color=effective_color,
                symbol=effective_symbol,
                name=effective_name,
                relaunch=relaunch,
            )

            # Ensure prompt is preserved in SQLite if package provided it
            if effective_prompt:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE magic_extensions SET prompt = ? WHERE id = ?",
                    (effective_prompt, ext_id),
                )
                conn.commit()

            print(f"✓ Installed package: '{effective_name}' [{ext_id}]")
            return ext_id
        finally:
            if close_conn:
                conn.close()


# =========================================================================
#  Exporting & Existing Core
# =========================================================================

def export_extension(
    target_identifier: str,
    output_dir: Path | str | None = None,
    as_zip: bool = False,
    conn: sqlite3.Connection | None = None,
) -> Path:
    """Export an installed Safari Magic Extension to a target directory (defaults to ~/Downloads)."""
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True

    try:
        matched = find_installed_extension(target_identifier, conn)
        if not matched:
            raise ValueError(f"No extension found matching '{target_identifier}'.")

        src_folder = Path(matched["folder_path"])
        if not src_folder.exists():
            raise FileNotFoundError(f"Extension files not found on disk at {src_folder}")

        dest_root = (
            Path(output_dir).expanduser().resolve()
            if output_dir
            else (Path.home() / "Downloads")
        )
        dest_root.mkdir(parents=True, exist_ok=True)

        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", matched["name"])
        ignore_patterns = shutil.ignore_patterns(
            ".git", ".vscode", ".tmp", "node_modules", ".DS_Store"
        )

        if as_zip:
            zip_base = dest_root / safe_name
            archive_path = Path(
                shutil.make_archive(
                    str(zip_base), "zip", root_dir=src_folder
                )
            )
            print(f"✓ Exported '{matched['name']}' as ZIP to:\n  {archive_path}")
            return archive_path
        else:
            dest_folder = dest_root / safe_name
            if dest_folder.exists():
                shutil.rmtree(dest_folder)
            shutil.copytree(src_folder, dest_folder, ignore=ignore_patterns)
            print(f"✓ Exported '{matched['name']}' folder to:\n  {dest_folder}")
            return dest_folder
    finally:
        if close_conn:
            conn.close()


def export_all_extensions(
    output_dir: Path | str | None = None, as_zip: bool = False
) -> list[Path]:
    """Export all installed extensions."""
    conn = get_db_connection()
    try:
        extensions = get_installed_extensions(conn)
        exported = []
        for ext in extensions:
            path = export_extension(ext["id"], output_dir=output_dir, as_zip=as_zip, conn=conn)
            exported.append(path)
        return exported
    finally:
        conn.close()


def list_extensions(conn: sqlite3.Connection) -> None:
    """Print registered and unregistered extensions."""
    extensions = get_installed_extensions(conn)
    reg_dirs = {ext["directory_name"] for ext in extensions}

    print("\n==========================================")
    print("      Safari Magic Extensions Status      ")
    print("==========================================")

    print("\n[Active in Safari]")
    if not extensions:
        print("  (None)")
    for ext in extensions:
        print(f"  • {ext['name']}")
        print(f"      Folder: {ext['directory_name']}")
        print(f"      Symbol: {ext['selected_symbol']} ({ext['symbol_color_name']})")
        print(f"      ID:     {ext['id']}")
        if ext["prompt"]:
            short_prompt = ext["prompt"][:80] + ("..." if len(ext["prompt"]) > 80 else "")
            print(f"      Prompt: {short_prompt}")

    unregistered = []
    if MAGIC_EXTENSIONS_DIR.exists():
        for item in sorted(MAGIC_EXTENSIONS_DIR.iterdir()):
            if item.is_dir() and (item / "manifest.json").exists():
                if item.name not in reg_dirs:
                    unregistered.append(item.name)

    print("\n[Unlinked Folders in Safari Storage]")
    if not unregistered:
        print("  (None)")
    for u in unregistered:
        print(f"  • {u}")
    if unregistered:
        print(f"\n  Tip: Run 'python3 safari-magic-ext.py sync' to register all {len(unregistered)} unlinked folder(s) in Safari.")
    print()


def sync_unlinked_extensions(
    conn: sqlite3.Connection | None = None, relaunch: bool = True
) -> list[str]:
    """Scan Safari MagicExtensions storage for unlinked folders and register them in Extensions.db."""
    close_conn = False
    if conn is None:
        conn = get_db_connection(DB_PATH)
        close_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT directory_name FROM magic_extensions WHERE name != ''")
        registered_dirs = {row["directory_name"] for row in cursor.fetchall()}

        synced = []
        if MAGIC_EXTENSIONS_DIR.exists():
            for item in sorted(MAGIC_EXTENSIONS_DIR.iterdir()):
                if (
                    item.is_dir()
                    and not item.name.startswith(".")
                    and not item.name.endswith(".app")
                    and item.name != "chrome-to-safari-8a9210f8262ad887ad0836bca385444cae8089eb"
                ):
                    if item.name not in registered_dirs:
                        print(f"-> Found unlinked folder: {item.name}, registering in database...")
                        try:
                            add_extension(
                                conn=conn,
                                source_path=item,
                                relaunch=False,
                            )
                            synced.append(item.name)
                        except Exception as e:
                            print(f"[Warning] Failed to register '{item.name}': {e}")

        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(FULL);")

        if synced:
            print(f"\n✓ Successfully registered {len(synced)} unlinked extension(s) in Safari database!")
            if relaunch:
                relaunch_safari()
        else:
            print("\nAll extension folders in Safari storage are already registered in the database.")

        return synced
    finally:
        if close_conn:
            conn.close()


def explore_community(query: str = "") -> None:
    """Print community catalog items matching query."""
    registry = CommunityRegistry()
    items = registry.search(query)

    print("\n==========================================")
    print("   Safari Magic Extensions Community Hub  ")
    print("==========================================")
    if not items:
        print(f"No community extensions found matching '{query}'.")
        return

    print(f"Found {len(items)} community extension(s):\n")
    for item in items:
        tags = ", ".join(item.get("tags", []))
        print(f"  ★ {item.get('name')} (by {item.get('author')})")
        print(f"      ID:     {item.get('id')}")
        print(f"      Symbol: {item.get('selected_symbol')} ({item.get('symbol_color_name')})")
        print(f"      Tags:   {tags}")
        print(f"      Prompt: \"{item.get('prompt')}\"")
        print(f"      Desc:   {item.get('description')}")
        print(f"      Install command: {invocation_name()} install {item.get('id')}\n")


def add_extension(
    conn: sqlite3.Connection,
    source_path: Path,
    color: str = "blue",
    symbol: str | None = None,
    name: str | None = None,
    relaunch: bool = True,
) -> str:
    """Copy folder if necessary, adapt manifest, and register in database."""
    source_path = source_path.expanduser().resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"Directory does not exist: {source_path}")
    if not source_path.is_dir():
        raise NotADirectoryError(f"Provided path is not a folder: {source_path}")

    MAGIC_EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True)

    if source_path.parent.resolve() == MAGIC_EXTENSIONS_DIR.resolve():
        target_dir = source_path
        dir_name = source_path.name
        print(f"-> Folder is already in Safari extensions folder: {dir_name}")
    else:
        clean_name = clean_target_folder_name(source_path.name)
        target_dir = MAGIC_EXTENSIONS_DIR / clean_name
        print(f"-> Copying extension from:\n   {source_path}\n   to:\n   {target_dir}")
        if target_dir.exists():
            shutil.rmtree(target_dir)
        ignore_patterns = shutil.ignore_patterns(
            ".git", ".vscode", ".tmp", "node_modules", ".DS_Store"
        )
        shutil.copytree(source_path, target_dir, ignore=ignore_patterns)
        dir_name = clean_name

    meta = normalize_manifest(target_dir)
    final_name = name or meta["name"]
    final_symbol = symbol or meta["selected_symbol"]
    description = meta["description"]
    prompt = meta["prompt"]

    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name FROM magic_extensions WHERE directory_name = ?",
        (dir_name,),
    )
    existing = cursor.fetchone()
    if existing:
        print(
            f"\n[Notice] '{dir_name}' is already registered as '{existing['name']}'. Updating files & metadata..."
        )
        return update_extension(
            conn=conn,
            target_identifier=dir_name,
            source_path=source_path if source_path != target_dir else None,
            color=color if color != "blue" else None,
            symbol=symbol,
            name=name,
            relaunch=relaunch,
        )
    else:
        cursor.execute("SELECT value FROM metadata WHERE key = 'next_sync_generation'")
        row = cursor.fetchone()
        next_gen = int(row["value"]) if row and row["value"] is not None else 1

        ext_id = str(uuid.uuid4()).upper()
        now_apple = time.time() - MAC_ABSOLUTE_TIME_OFFSET

        cursor.execute(
            """
            INSERT INTO magic_extensions (
                id, version, creation_date, modified_date, name, description,
                selected_symbol, prompt, directory_name, symbol_color_name,
                sync_state, sync_generation
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """,
            (
                ext_id,
                now_apple,
                now_apple,
                final_name,
                description,
                final_symbol,
                prompt,
                dir_name,
                color,
                next_gen,
            ),
        )

        cursor.execute(
            "UPDATE metadata SET value = ? WHERE key = 'next_sync_generation'",
            (next_gen + 1,),
        )
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(FULL);")

        print(f"\n✓ Successfully installed & activated '{final_name}'")
        print(f"    ID:     {ext_id}")
        print(f"    Folder: {dir_name}")
        print(f"    Symbol: {final_symbol} ({color})")

    if relaunch:
        relaunch_safari()

    return ext_id


def update_extension(
    conn: sqlite3.Connection,
    target_identifier: str,
    source_path: Path | None = None,
    color: str | None = None,
    symbol: str | None = None,
    name: str | None = None,
    relaunch: bool = True,
) -> str:
    """Update an existing extension's files and/or metadata."""
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, directory_name, selected_symbol, symbol_color_name, prompt, description
        FROM magic_extensions
        WHERE id = ? OR directory_name = ? OR name = ?
        COLLATE NOCASE
    """,
        (target_identifier, target_identifier, target_identifier),
    )
    row = cursor.fetchone()

    if not row:
        cursor.execute(
            """
            SELECT id, name, directory_name, selected_symbol, symbol_color_name, prompt, description
            FROM magic_extensions
            WHERE directory_name LIKE ? OR name LIKE ?
            COLLATE NOCASE
        """,
            (f"{target_identifier}%", f"%{target_identifier}%"),
        )
        row = cursor.fetchone()

    if not row:
        raise ValueError(
            f"No extension found matching '{target_identifier}'. Run 'list' to see installed extensions."
        )

    ext_id = row["id"]
    dir_name = row["directory_name"]
    target_dir = MAGIC_EXTENSIONS_DIR / dir_name

    print(f"Updating extension: '{row['name']}' [{dir_name}]...")

    if source_path:
        source_path = source_path.expanduser().resolve()
        if source_path != target_dir:
            print(f"-> Syncing files from:\n   {source_path}\n   to:\n   {target_dir}")
            ignore_patterns = shutil.ignore_patterns(
                ".git", ".vscode", ".tmp", "node_modules", ".DS_Store"
            )
            shutil.copytree(
                source_path, target_dir, dirs_exist_ok=True, ignore=ignore_patterns
            )

    meta = {}
    if target_dir.exists():
        meta = normalize_manifest(target_dir)

    new_name = name or row["name"] or meta.get("name")
    new_symbol = symbol or meta.get("selected_symbol") or row["selected_symbol"]
    new_color = color or row["symbol_color_name"]
    new_desc = meta.get("description") or row["description"]
    new_prompt = meta.get("prompt") or row["prompt"]
    now_apple = time.time() - MAC_ABSOLUTE_TIME_OFFSET

    cursor.execute("SELECT value FROM metadata WHERE key = 'next_sync_generation'")
    sync_row = cursor.fetchone()
    next_gen = (
        int(sync_row["value"]) if sync_row and sync_row["value"] is not None else 1
    )

    cursor.execute(
        """
        UPDATE magic_extensions
        SET modified_date = ?,
            name = ?,
            description = ?,
            selected_symbol = ?,
            prompt = ?,
            symbol_color_name = ?,
            sync_generation = ?
        WHERE id = ?
    """,
        (
            now_apple,
            new_name,
            new_desc,
            new_symbol,
            new_prompt,
            new_color,
            next_gen,
            ext_id,
        ),
    )

    cursor.execute(
        "UPDATE metadata SET value = ? WHERE key = 'next_sync_generation'",
        (next_gen + 1,),
    )
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(FULL);")

    print(f"\n✓ Extension '{new_name}' updated successfully!")
    print(f"    ID:     {ext_id}")
    print(f"    Folder: {dir_name}")
    print(f"    Symbol: {new_symbol} ({new_color})")

    if relaunch:
        relaunch_safari()

    return ext_id


def relaunch_safari() -> None:
    """Relaunch Safari to reload SQLite state."""
    try:
        check = subprocess.run(
            ["pgrep", "-x", "Safari"], capture_output=True, text=True
        )
        if check.returncode == 0:
            print("\nRestarting Safari to apply changes...")
            subprocess.run(["killall", "Safari"], check=False)
            time.sleep(1)
            subprocess.run(["open", "-a", "Safari"], check=False)
            print("✓ Safari restarted successfully!")
        else:
            print(
                "\nSafari is currently closed. It will show the new extension when you open it."
            )
    except Exception as e:
        print(f"[Warning] Could not restart Safari automatically: {e}")


# =========================================================================
#  GUI (Dual-Tab Tkinter Native macOS UI)
# =========================================================================

def launch_gui() -> None:
    """Launch modern native graphical user interface with My Extensions & Community Hub."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Safari Magic Extensions: Community Manager")
    root.geometry("880x660")
    root.minsize(760, 520)

    # Style configuration
    style = ttk.Style()
    style.theme_use("clam")

    # Dark theme palette
    BG = "#18181b"
    PANEL_BG = "#27272a"
    CARD_BG = "#212124"
    ACCENT = "#3b82f6"
    ACCENT_HOVER = "#2563eb"
    FG = "#f4f4f5"
    FG_MUTED = "#a1a1aa"
    SUCCESS = "#10b981"
    BORDER = "#3f3f46"

    root.configure(bg=BG)

    # Header
    header = tk.Frame(root, bg=BG, padx=20, pady=14)
    header.pack(fill=tk.X)

    title_label = tk.Label(
        header,
        text="Safari Magic Extensions",
        font=("system-ui", 18, "bold"),
        fg=FG,
        bg=BG,
    )
    title_label.pack(anchor="w")

    subtitle = tk.Label(
        header,
        text="Package, share, discover, and 1-click install AI-generated extensions directly in Safari.",
        font=("system-ui", 11),
        fg=FG_MUTED,
        bg=BG,
    )
    subtitle.pack(anchor="w", pady=(2, 0))

    # Notebook Tabs Style
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background=PANEL_BG,
        foreground=FG_MUTED,
        padding=[14, 8],
        font=("system-ui", 11, "bold"),
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", ACCENT)],
        foreground=[("selected", "#ffffff")],
    )

    notebook = ttk.Notebook(root)
    notebook.pack(fill=tk.BOTH, expand=True, padx=16, pady=4)

    # Treeview Styles
    style.configure(
        "Treeview",
        background=PANEL_BG,
        foreground=FG,
        fieldbackground=PANEL_BG,
        rowheight=32,
        font=("system-ui", 11),
        borderwidth=0,
    )
    style.configure(
        "Treeview.Heading",
        background="#32323a",
        foreground=FG,
        font=("system-ui", 11, "bold"),
        relief="flat",
    )
    style.map(
        "Treeview",
        background=[("selected", ACCENT)],
        foreground=[("selected", "#ffffff")],
    )

    # =====================================================================
    #  TAB 1: Installed Extensions
    # =====================================================================
    tab_installed = tk.Frame(notebook, bg=BG)
    notebook.add(tab_installed, text="  My Extensions  ")

    inst_main = tk.Frame(tab_installed, bg=BG, padx=10, pady=10)
    inst_main.pack(fill=tk.BOTH, expand=True)

    tree_frame = tk.Frame(inst_main, bg=BORDER, bd=1)
    tree_frame.pack(fill=tk.BOTH, expand=True)

    inst_cols = ("name", "folder", "badge", "id")
    tree = ttk.Treeview(
        tree_frame, columns=inst_cols, show="headings", selectmode="browse"
    )
    tree.heading("name", text="Extension Name", anchor="w")
    tree.heading("folder", text="Folder Name", anchor="w")
    tree.heading("badge", text="SF Symbol & Tint", anchor="w")
    tree.heading("id", text="UUID", anchor="w")

    tree.column("name", width=220, minwidth=140)
    tree.column("folder", width=160, minwidth=120)
    tree.column("badge", width=160, minwidth=120)
    tree.column("id", width=200, minwidth=140)

    scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # Details Area
    inst_details = tk.Frame(
        inst_main, bg=CARD_BG, padx=12, pady=10, bd=1, relief="solid"
    )
    inst_details.pack(fill=tk.X, pady=(10, 0))

    prompt_var = tk.StringVar(
        value="Select an extension above to inspect its Safari AI prompt and details."
    )
    tk.Label(
        inst_details,
        text="Original AI Generation Prompt:",
        font=("system-ui", 10, "bold"),
        fg=ACCENT,
        bg=CARD_BG,
    ).pack(anchor="w")

    prompt_label = tk.Label(
        inst_details,
        textvariable=prompt_var,
        font=("system-ui", 11),
        fg=FG,
        bg=CARD_BG,
        wraplength=800,
        justify="left",
    )
    prompt_label.pack(anchor="w", pady=(3, 0))

    # =====================================================================
    #  TAB 2: Community Hub
    # =====================================================================
    tab_community = tk.Frame(notebook, bg=BG)
    notebook.add(tab_community, text="  Community Hub  ")

    comm_main = tk.Frame(tab_community, bg=BG, padx=10, pady=10)
    comm_main.pack(fill=tk.BOTH, expand=True)

    # Search Bar
    search_bar = tk.Frame(comm_main, bg=BG)
    search_bar.pack(fill=tk.X, pady=(0, 8))

    tk.Label(
        search_bar,
        text="Search Catalog:",
        font=("system-ui", 11, "bold"),
        fg=FG,
        bg=BG,
    ).pack(side=tk.LEFT, padx=(0, 8))

    search_var = tk.StringVar()
    search_entry = tk.Entry(
        search_bar,
        textvariable=search_var,
        font=("system-ui", 11),
        bg=PANEL_BG,
        fg=FG,
        insertbackground=FG,
        relief="flat",
        bd=1,
    )
    search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=4)

    comm_tree_frame = tk.Frame(comm_main, bg=BORDER, bd=1)
    comm_tree_frame.pack(fill=tk.BOTH, expand=True)

    comm_cols = ("name", "author", "badge", "tags", "id")
    comm_tree = ttk.Treeview(
        comm_tree_frame, columns=comm_cols, show="headings", selectmode="browse"
    )
    comm_tree.heading("name", text="Extension", anchor="w")
    comm_tree.heading("author", text="Creator", anchor="w")
    comm_tree.heading("badge", text="SF Symbol", anchor="w")
    comm_tree.heading("tags", text="Tags", anchor="w")
    comm_tree.heading("id", text="Package ID", anchor="w")

    comm_tree.column("name", width=200, minwidth=140)
    comm_tree.column("author", width=110, minwidth=80)
    comm_tree.column("badge", width=150, minwidth=110)
    comm_tree.column("tags", width=150, minwidth=100)
    comm_tree.column("id", width=140, minwidth=100)

    comm_scroll = ttk.Scrollbar(
        comm_tree_frame, orient=tk.VERTICAL, command=comm_tree.yview
    )
    comm_tree.configure(yscrollcommand=comm_scroll.set)
    comm_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    comm_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    # Community Details
    comm_details = tk.Frame(
        comm_main, bg=CARD_BG, padx=12, pady=10, bd=1, relief="solid"
    )
    comm_details.pack(fill=tk.X, pady=(10, 0))

    comm_prompt_var = tk.StringVar(
        value="Select a community extension to view prompt, description, and 1-click install."
    )
    tk.Label(
        comm_details,
        text="Community AI Prompt & Details:",
        font=("system-ui", 10, "bold"),
        fg=SUCCESS,
        bg=CARD_BG,
    ).pack(anchor="w")

    comm_prompt_label = tk.Label(
        comm_details,
        textvariable=comm_prompt_var,
        font=("system-ui", 11),
        fg=FG,
        bg=CARD_BG,
        wraplength=800,
        justify="left",
    )
    comm_prompt_label.pack(anchor="w", pady=(3, 0))

    # Shared Bottom Status Bar
    status_bar = tk.Frame(root, bg=BG, padx=18, pady=10)
    status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    status_var = tk.StringVar(value="Ready")
    status_label = tk.Label(
        status_bar, textvariable=status_var, font=("system-ui", 11), fg=FG_MUTED, bg=BG
    )
    status_label.pack(side=tk.LEFT)

    current_installed = []
    current_catalog = []
    registry = CommunityRegistry()

    # Helpers
    def make_btn(parent, text, cmd, primary=False, success=False):
        bg_col = SUCCESS if success else (ACCENT if primary else PANEL_BG)
        fg_col = "#ffffff" if (primary or success) else FG
        b = tk.Button(
            parent,
            text=text,
            command=cmd,
            bg=bg_col,
            fg=fg_col,
            activebackground=ACCENT_HOVER,
            activeforeground="#ffffff",
            relief="flat",
            padx=10,
            pady=5,
            font=("system-ui", 10, "bold" if (primary or success) else "normal"),
            cursor="pointinghand",
        )
        b.pack(side=tk.LEFT, padx=3)
        return b

    # =====================================================================
    #  Actions & Handlers
    # =====================================================================
    def refresh_installed() -> None:
        nonlocal current_installed
        for item in tree.get_children():
            tree.delete(item)
        try:
            conn = get_db_connection()
            current_installed = get_installed_extensions(conn)
            conn.close()

            for ext in current_installed:
                tree.insert(
                    "",
                    tk.END,
                    iid=ext["id"],
                    values=(
                        ext["name"],
                        ext["directory_name"],
                        f"{ext['selected_symbol']} ({ext['symbol_color_name']})",
                        ext["id"],
                    ),
                )
            status_var.set(f"Loaded {len(current_installed)} active extension(s).")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load extensions:\n{e}")

    def on_installed_select(event) -> None:
        selected = tree.selection()
        if not selected:
            prompt_var.set("Select an extension above to inspect details.")
            return
        ext_id = selected[0]
        for ext in current_installed:
            if ext["id"] == ext_id:
                p = ext["prompt"] or "(No prompt recorded)"
                d = ext["description"] or ""
                prompt_var.set(f"Prompt: \"{p}\"\nDescription: {d}")
                break

    tree.bind("<<TreeviewSelect>>", on_installed_select)

    def refresh_community() -> None:
        nonlocal current_catalog
        for item in comm_tree.get_children():
            comm_tree.delete(item)
        query = search_var.get().strip()
        current_catalog = registry.search(query)
        for item in current_catalog:
            tags = ", ".join(item.get("tags", []))
            comm_tree.insert(
                "",
                tk.END,
                iid=item["id"],
                values=(
                    item["name"],
                    item.get("author", "community"),
                    f"{item.get('selected_symbol')} ({item.get('symbol_color_name')})",
                    tags,
                    item["id"],
                ),
            )
        status_var.set(f"Community Catalog: {len(current_catalog)} item(s) found.")

    def on_community_select(event) -> None:
        selected = comm_tree.selection()
        if not selected:
            comm_prompt_var.set("Select a community extension to view details.")
            return
        ext_id = selected[0]
        for item in current_catalog:
            if item["id"] == ext_id:
                p = item.get("prompt", "")
                d = item.get("description", "")
                a = item.get("author", "")
                comm_prompt_var.set(f"Author: {a}\nPrompt: \"{p}\"\nDescription: {d}")
                break

    comm_tree.bind("<<TreeviewSelect>>", on_community_select)
    search_entry.bind("<KeyRelease>", lambda e: refresh_community())

    # Tab 1 Buttons
    inst_btn_bar = tk.Frame(inst_main, bg=BG)
    inst_btn_bar.pack(fill=tk.X, pady=(10, 0))

    def pack_action() -> None:
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Notice", "Select an extension to pack for sharing.")
            return
        ext_id = selected[0]
        dest = filedialog.askdirectory(
            title="Select Destination Folder for .magicext Package",
            initialdir=str(Path.home() / "Downloads"),
        )
        if not dest:
            return
        try:
            out = pack_extension(ext_id, output_dir=dest)
            status_var.set(f"Packaged: {out.name}")
            subprocess.run(["open", "-R", str(out)], check=False)
            messagebox.showinfo(
                "Package Ready to Share",
                f"Successfully created shareable package:\n{out}\n\nRevealed in Finder.",
            )
        except Exception as e:
            messagebox.showerror("Packaging Failed", str(e))

    def export_zip_action() -> None:
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Notice", "Select an extension first.")
            return
        dest = filedialog.askdirectory(initialdir=str(Path.home() / "Downloads"))
        if not dest:
            return
        try:
            out = export_extension(selected[0], output_dir=dest, as_zip=True)
            status_var.set(f"Exported {out.name}")
            subprocess.run(["open", "-R", str(out)], check=False)
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    def install_from_file_or_url_action() -> None:
        file_path = filedialog.askopenfilename(
            title="Select .magicext or Extension Zip",
            filetypes=[
                ("Magic Extension Package", "*.magicext"),
                ("ZIP Archives", "*.zip"),
                ("All Files", "*.*"),
            ],
        )
        if not file_path:
            return
        try:
            ext_id = install_package(file_path, relaunch=True)
            refresh_installed()
            messagebox.showinfo(
                "Installed Successfully",
                f"Extension installed and activated in Safari!\nID: {ext_id}",
            )
        except Exception as e:
            messagebox.showerror("Installation Failed", str(e))

    def import_folder_action() -> None:
        folder = filedialog.askdirectory(title="Select Extension Folder (Chrome or Safari)")
        if not folder:
            return
        try:
            conn = get_db_connection()
            ext_id = add_extension(conn, Path(folder), relaunch=True)
            conn.close()
            refresh_installed()
            messagebox.showinfo(
                "Folder Sideloaded",
                f"Extension imported and activated in Safari!\nID: {ext_id}",
            )
        except Exception as e:
            messagebox.showerror("Import Failed", str(e))

    def submit_action() -> None:
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Notice", "Select an extension to submit to the Hub.")
            return
        ext_id = selected[0]
        try:
            pkg_path = pack_extension(ext_id)
            with zipfile.ZipFile(pkg_path, "r") as zf:
                meta = json.loads(zf.read("magic.json").decode("utf-8"))

            name = meta.get("name", "")
            prompt = meta.get("prompt", "")
            desc = meta.get("description", "")
            author = meta.get("author", "")
            symbol = meta.get("selected_symbol", "")
            color = meta.get("symbol_color_name", "blue")

            slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'extension'
            with open(pkg_path, "rb") as f:
                pkg_bytes = f.read()
            b64_payload = base64.b64encode(pkg_bytes).decode("utf-8")

            status_var.set("Preparing submission package...")
            root.update()

            def upload_tmpfiles(filepath, name_slug):
                import urllib.request, json, os, uuid
                boundary = uuid.uuid4().hex
                with open(filepath, 'rb') as f:
                    file_data = f.read()
                zip_filename = f"{name_slug}.zip"
                body = (
                    f"--{boundary}\r\n"
                    f"Content-Disposition: form-data; name=\"file\"; filename=\"{zip_filename}\"\r\n"
                    "Content-Type: application/zip\r\n\r\n".encode('utf-8')
                    + file_data +
                    f"\r\n--{boundary}--\r\n".encode('utf-8')
                )
                req = urllib.request.Request("https://tmpfiles.org/api/v1/upload", data=body)
                req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
                req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15)')
                try:
                    with urllib.request.urlopen(req) as resp:
                        res = json.loads(resp.read().decode())
                        return res["data"]["url"]
                except Exception:
                    return None

            upload_url = upload_tmpfiles(pkg_path, slug)

            repo = os.getenv("SAFARI_MAGIC_HUB_REPO", "Vatsal057/safari-magic-extensions")
            issue_body = f"""### Extension Name
{name}

### Author Name / GitHub Handle
{author}

### Original AI Generation Prompt
{prompt}

### Extension Description
{desc}

### SF Symbol Tint Color
{color}

### SF Symbol Name
{symbol}

### Automated Package Data
<!-- MAGICEXT_BASE64_START -->
{b64_payload}
<!-- MAGICEXT_BASE64_END -->
"""
            # Prepare pre-filled browser form
            pkg_field = ""
            if upload_url:
                pkg_field = f"Download link: {upload_url}\n\n"
            if len(b64_payload) < 2500:
                pkg_field += f"<!-- MAGICEXT_BASE64_START -->\n{b64_payload}\n<!-- MAGICEXT_BASE64_END -->"

            query_params = urllib.parse.urlencode({
                "template": "extension_submission.yml",
                "title": f"[Extension Submission]: {name}",
                "extension_name": name,
                "author_handle": author,
                "ai_prompt": prompt,
                "description": desc,
                "selected_symbol": symbol,
                "symbol_color": color,
                "package_upload": pkg_field,
            })
            issue_url = f"https://github.com/{repo}/issues/new?{query_params}"
            status_var.set("Opening browser submission form...")
            subprocess.run(["open", issue_url], check=False)
            messagebox.showinfo(
                "Submission Prepared",
                f"Opening GitHub submission form in your browser.\n\nPackage data is pre-filled. Just click 'Submit new issue'!",
            )
        except Exception as e:
            messagebox.showerror("Submission Error", str(e))

    inst_btn_box = tk.Frame(inst_btn_bar, bg=BG)
    inst_btn_box.pack(side=tk.RIGHT)

    make_btn(inst_btn_box, "↻ Refresh", refresh_installed)
    make_btn(inst_btn_box, "Export ZIP", export_zip_action)
    make_btn(inst_btn_box, "＋ Sideload Folder", import_folder_action)
    make_btn(inst_btn_box, "Install .magicext", install_from_file_or_url_action)
    make_btn(inst_btn_box, "★ Pack (.magicext)", pack_action)
    make_btn(inst_btn_box, "🚀 Submit to Hub", submit_action, success=True)

    # Tab 2 Buttons
    comm_btn_bar = tk.Frame(comm_main, bg=BG)
    comm_btn_bar.pack(fill=tk.X, pady=(10, 0))

    def community_install_action() -> None:
        selected = comm_tree.selection()
        if not selected:
            messagebox.showwarning("Notice", "Select an extension from the Community Hub.")
            return
        item_id = selected[0]
        status_var.set(f"Installing community extension '{item_id}'...")
        root.update()
        try:
            ext_id = install_package(item_id, relaunch=True)
            refresh_installed()
            messagebox.showinfo(
                "Installation Complete",
                f"Successfully installed and activated community extension!\nID: {ext_id}\n\nSafari restarted.",
            )
            notebook.select(tab_installed)
        except Exception as e:
            messagebox.showerror("Community Install Failed", str(e))
        finally:
            status_var.set("Ready")

    def copy_prompt_action() -> None:
        selected = comm_tree.selection()
        if not selected:
            messagebox.showwarning("Notice", "Select an extension to copy its prompt.")
            return
        item_id = selected[0]
        for item in current_catalog:
            if item["id"] == item_id:
                p = item.get("prompt", "")
                root.clipboard_clear()
                root.clipboard_append(p)
                status_var.set("Copied prompt to clipboard!")
                messagebox.showinfo(
                    "Prompt Copied",
                    f"Copied AI Prompt to clipboard:\n\n\"{p}\"\n\nYou can paste this into Safari to generate variations!",
                )
                break

    comm_btn_box = tk.Frame(comm_btn_bar, bg=BG)
    comm_btn_box.pack(side=tk.RIGHT)

    make_btn(comm_btn_box, "↻ Refresh Catalog", refresh_community)
    make_btn(comm_btn_box, "📋 Copy AI Prompt", copy_prompt_action)
    make_btn(comm_btn_box, "⚡ Install into Safari", community_install_action, success=True)

    # Initial loads
    refresh_installed()
    refresh_community()

    root.mainloop()


# =========================================================================
#  CLI Entry Point
# =========================================================================

def main() -> None:
    # If launched with no arguments, open the GUI!
    if len(sys.argv) == 1:
        launch_gui()
        return

    parser = argparse.ArgumentParser(
        prog="safari-magic-ext",
        description="Share, package, install, and manage Safari Magic Extensions easily.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"safari-magic-ext {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Command: gui
    subparsers.add_parser("gui", help="Open the graphical user interface")

    # Command: list
    subparsers.add_parser("list", help="List all Safari Magic extensions")

    # Command: explore
    explore_parser = subparsers.add_parser(
        "explore", help="Explore curated community AI extensions"
    )
    explore_parser.add_argument(
        "query", nargs="?", default="", help="Optional search query"
    )

    # Command: pack
    pack_parser = subparsers.add_parser(
        "pack", help="Package an extension into a shareable .magicext bundle"
    )
    pack_parser.add_argument(
        "target",
        nargs="?",
        default=None,
        type=str,
        help="Name, directory name, or ID of extension to pack (interactive picker if omitted)",
    )
    pack_parser.add_argument(
        "--to",
        dest="output_dir",
        type=str,
        default=None,
        help="Destination directory (defaults to ~/Downloads)",
    )
    pack_parser.add_argument(
        "--author",
        type=str,
        default=None,
        help="Creator name/handle to embed in package (auto-detected if omitted)",
    )

    # Command: convert
    convert_parser = subparsers.add_parser(
        "convert", help="Convert any local extension folder into a .magicext bundle"
    )
    convert_parser.add_argument(
        "path",
        type=str,
        help="Path to local extension folder",
    )
    convert_parser.add_argument(
        "--to",
        dest="output_dir",
        type=str,
        default=None,
        help="Destination directory (defaults to ~/Downloads)",
    )
    convert_parser.add_argument(
        "--author",
        type=str,
        default=None,
        help="Creator name/handle to embed in package",
    )

    # Command: submit
    submit_parser = subparsers.add_parser(
        "submit", help="Package an extension and open GitHub submission form"
    )
    submit_parser.add_argument(
        "target",
        nargs="?",
        default=None,
        type=str,
        help="Name, directory name, or ID of extension to submit (interactive picker if omitted)",
    )
    submit_parser.add_argument(
        "--repo",
        type=str,
        default="Vatsal057/safari-magic-extensions",
        help="Target GitHub repository (user/repo)",
    )
    submit_parser.add_argument(
        "--author",
        type=str,
        default=None,
        help="Creator name/handle to embed in package (auto-detected if omitted)",
    )
    submit_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate package and URL without opening browser",
    )

    # Command: install
    install_parser = subparsers.add_parser(
        "install",
        help="Install a .magicext package from file path, URL, or community registry",
    )
    install_parser.add_argument(
        "source",
        type=str,
        help="Path to .magicext file, URL, or community registry ID (e.g. nightlife-wild)",
    )
    install_parser.add_argument(
        "--name", type=str, default=None, help="Custom extension display name"
    )
    install_parser.add_argument(
        "--color", type=str, default=None, help="SF Symbol badge color"
    )
    install_parser.add_argument(
        "--symbol", type=str, default=None, help="SF Symbol name"
    )
    install_parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Do not restart Safari automatically",
    )

    # Command: export
    export_parser = subparsers.add_parser(
        "export", help="Export/backup an extension to Downloads or specified directory"
    )
    export_parser.add_argument(
        "target",
        type=str,
        help="Name, directory name, or ID of extension (or 'all' for all)",
    )
    export_parser.add_argument(
        "--to",
        dest="output_dir",
        type=str,
        default=None,
        help="Destination directory (defaults to ~/Downloads)",
    )
    export_parser.add_argument(
        "--zip",
        action="store_true",
        help="Export as a compressed .zip file instead of folder",
    )

    # Command: add
    add_parser = subparsers.add_parser(
        "add", help="Add an extension folder from anywhere"
    )
    add_parser.add_argument(
        "path",
        type=str,
        help="Path to extension folder (or folder name if already in Safari)",
    )
    add_parser.add_argument(
        "--color",
        type=str,
        default="blue",
        help="SF Symbol badge color (blue, purple, orange, green, etc.)",
    )
    add_parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="SF Symbol name (e.g. sparkles, star.fill)",
    )
    add_parser.add_argument(
        "--name", type=str, default=None, help="Custom extension display name"
    )
    add_parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Do not restart Safari automatically",
    )

    # Command: update
    update_parser = subparsers.add_parser(
        "update", help="Update files or metadata of an existing extension"
    )
    update_parser.add_argument(
        "target",
        type=str,
        help="Name, directory name, or ID of the extension to update",
    )
    update_parser.add_argument(
        "--from",
        dest="source_path",
        type=str,
        default=None,
        help="Source directory with updated code to sync into Safari",
    )
    update_parser.add_argument(
        "--color",
        type=str,
        default=None,
        help="Change SF Symbol badge color",
    )
    update_parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Change SF Symbol icon",
    )
    update_parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Change display name",
    )
    update_parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Do not restart Safari automatically",
    )

    # Command: sync
    sync_parser = subparsers.add_parser(
        "sync", help="Scan storage and register all unlinked extension folders into Safari database"
    )
    sync_parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Do not restart Safari automatically",
    )

    args = parser.parse_args()

    if args.command == "gui":
        launch_gui()
    elif args.command == "explore":
        explore_community(args.query)
    elif args.command == "pack":
        conn = get_db_connection(DB_PATH)
        try:
            target = args.target
            if not target:
                ext = interactive_select_extension(conn, prompt_text="Select extension to pack")
                target = ext["id"]
            pack_extension(
                target_identifier=target,
                output_dir=args.output_dir,
                author=args.author,
                conn=conn,
            )
        finally:
            conn.close()
    elif args.command == "convert":
        # Converting a folder is a pure file operation: no Safari database needed.
        try:
            pkg = pack_extension(
                target_identifier=args.path,
                output_dir=args.output_dir,
                author=args.author,
            )
            print(f"\n✓ Successfully converted folder '{args.path}' into .magicext bundle!")
            print(f"  Package: {pkg}")
        except Exception as e:
            print(f"\n[Error] {e}")
            sys.exit(1)
    elif args.command == "submit":
        conn = get_db_connection(DB_PATH)
        try:
            target = args.target
            if not target:
                ext = interactive_select_extension(conn, prompt_text="Select extension to submit")
                target = ext["id"]
            author = args.author or _detect_author()
            pkg_path = pack_extension(
                target_identifier=target,
                author=author,
                conn=conn,
            )
            with zipfile.ZipFile(pkg_path, "r") as zf:
                meta = json.loads(zf.read("magic.json").decode("utf-8"))

            name = meta.get("name", "")
            prompt = meta.get("prompt", "")
            desc = meta.get("description", "")
            author = meta.get("author", "")
            symbol = meta.get("selected_symbol", "")
            color = meta.get("symbol_color_name", "blue")

            slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'extension'
            with open(pkg_path, "rb") as f:
                pkg_bytes = f.read()
            b64_payload = base64.b64encode(pkg_bytes).decode("utf-8")

            def upload_tmpfiles(filepath, name_slug):
                import urllib.request, json, os, uuid
                boundary = uuid.uuid4().hex
                with open(filepath, 'rb') as f:
                    file_data = f.read()
                # Use .zip filename so tmpfiles.org does not reject with 422 Invalid file extension
                zip_filename = f"{name_slug}.zip"
                body = (
                    f"--{boundary}\r\n"
                    f"Content-Disposition: form-data; name=\"file\"; filename=\"{zip_filename}\"\r\n"
                    "Content-Type: application/zip\r\n\r\n".encode('utf-8')
                    + file_data +
                    f"\r\n--{boundary}--\r\n".encode('utf-8')
                )
                req = urllib.request.Request("https://tmpfiles.org/api/v1/upload", data=body)
                req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
                req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15)')
                try:
                    with urllib.request.urlopen(req) as resp:
                        res = json.loads(resp.read().decode())
                        return res["data"]["url"]
                except Exception:
                    return None

            upload_url = upload_tmpfiles(pkg_path, slug)
            pkg_field = ""
            if upload_url:
                pkg_field = f"Download link: {upload_url}\n\n"
            if len(b64_payload) < 2500:
                pkg_field += f"<!-- MAGICEXT_BASE64_START -->\n{b64_payload}\n<!-- MAGICEXT_BASE64_END -->"

            query_params = urllib.parse.urlencode({
                "template": "extension_submission.yml",
                "title": f"[Extension Submission]: {name}",
                "extension_name": name,
                "author_handle": author,
                "ai_prompt": prompt,
                "description": desc,
                "selected_symbol": symbol,
                "symbol_color": color,
                "package_upload": pkg_field,
            })
            issue_url = f"https://github.com/{args.repo}/issues/new?{query_params}"

            print(f"\n==========================================")
            print(f"      Extension Submission Ready!         ")
            print(f"==========================================")
            print(f"Package: {pkg_path}")
            print(f"GitHub:  {issue_url}")
            print(f"\nNext steps:")
            print(f"1. Opening submission form in your browser.")
            print(f"2. Package payload is pre-attached. Click 'Submit new issue'.")

            if not args.dry_run:
                subprocess.run(["open", issue_url], check=False)
        finally:
            conn.close()
    elif args.command == "install":
        conn = get_db_connection(DB_PATH)
        try:
            install_package(
                source=args.source,
                color=args.color,
                symbol=args.symbol,
                name=args.name,
                relaunch=not args.no_restart,
                conn=conn,
            )
        except Exception as e:
            print(f"\n[Error] {e}")
            sys.exit(1)
        finally:
            conn.close()
    elif args.command == "list":
        conn = get_db_connection(DB_PATH)
        try:
            list_extensions(conn)
        finally:
            conn.close()
    elif args.command == "export":
        conn = get_db_connection(DB_PATH)
        try:
            if args.target.lower() == "all":
                export_all_extensions(output_dir=args.output_dir, as_zip=args.zip)
            else:
                export_extension(
                    target_identifier=args.target,
                    output_dir=args.output_dir,
                    as_zip=args.zip,
                    conn=conn,
                )
        finally:
            conn.close()
    elif args.command == "add":
        conn = get_db_connection(DB_PATH)
        target = Path(args.path)
        if not target.is_absolute():
            if not target.exists() and (MAGIC_EXTENSIONS_DIR / args.path).exists():
                target = MAGIC_EXTENSIONS_DIR / args.path
        try:
            add_extension(
                conn=conn,
                source_path=target,
                color=args.color,
                symbol=args.symbol,
                name=args.name,
                relaunch=not args.no_restart,
            )
        except Exception as e:
            print(f"\n[Error] {e}")
            sys.exit(1)
        finally:
            conn.close()
    elif args.command == "update":
        conn = get_db_connection(DB_PATH)
        src = Path(args.source_path) if args.source_path else None
        try:
            update_extension(
                conn=conn,
                target_identifier=args.target,
                source_path=src,
                color=args.color,
                symbol=args.symbol,
                name=args.name,
                relaunch=not args.no_restart,
            )
        except Exception as e:
            print(f"\n[Error] {e}")
            sys.exit(1)
        finally:
            conn.close()
    elif args.command == "sync":
        conn = get_db_connection(DB_PATH)
        try:
            sync_unlinked_extensions(conn=conn, relaunch=not args.no_restart)
        except Exception as e:
            print(f"\n[Error] {e}")
            sys.exit(1)
        finally:
            conn.close()


if __name__ == "__main__":
    main()
