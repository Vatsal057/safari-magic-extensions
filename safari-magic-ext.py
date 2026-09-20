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
"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
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
LOCAL_REGISTRY_PATH = Path(__file__).resolve().parent / "community_registry.json"


def get_db_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open connection to the SQLite database with WAL awareness."""
    if not db_path.exists():
        raise FileNotFoundError(
            f"Safari Magic Extensions database not found at:\n{db_path}\n"
            "Please ensure Safari has been launched at least once."
        )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


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
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True

    try:
        extensions = get_installed_extensions(conn)
        matched = None
        for ext in extensions:
            if (
                target_identifier.lower() == ext["id"].lower()
                or target_identifier.lower() == ext["directory_name"].lower()
                or target_identifier.lower() in ext["name"].lower()
            ):
                matched = ext
                break

        # Check if user passed an unlinked local folder directly
        source_dir = None
        if not matched:
            candidate = Path(target_identifier).expanduser().resolve()
            if not candidate.is_dir() and (MAGIC_EXTENSIONS_DIR / target_identifier).is_dir():
                candidate = (MAGIC_EXTENSIONS_DIR / target_identifier).resolve()

            if candidate.is_dir() and (candidate / "manifest.json").exists():
                meta = normalize_manifest(candidate)
                source_dir = candidate
                matched = {
                    "id": str(uuid.uuid4()).upper(),
                    "name": meta["name"],
                    "directory_name": candidate.name,
                    "selected_symbol": meta["selected_symbol"],
                    "symbol_color_name": "blue",
                    "prompt": meta["prompt"],
                    "description": meta["description"],
                }
            else:
                raise ValueError(
                    f"No active extension or valid folder found matching '{target_identifier}'."
                )
        else:
            source_dir = Path(matched["folder_path"])

        if not source_dir or not source_dir.exists():
            raise FileNotFoundError(f"Extension files not found at: {source_dir}")

        dest_dir = (
            Path(output_dir).expanduser().resolve()
            if output_dir
            else (Path.home() / "Downloads")
        )
        dest_dir.mkdir(parents=True, exist_ok=True)

        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", matched["name"]).strip("_")
        if not safe_name:
            safe_name = "SafariExtension"
        output_file = dest_dir / f"{safe_name}.magicext"

        # Construct package metadata (magic.json)
        package_meta = {
            "magic_format_version": 1,
            "id": matched["id"],
            "name": matched["name"],
            "author": author or os.getenv("USER") or "Anonymous",
            "version": "1.0",
            "description": matched["description"],
            "prompt": matched["prompt"],
            "selected_symbol": matched["selected_symbol"],
            "symbol_color_name": matched["symbol_color_name"],
            "packaged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        # Build ZIP archive with .magicext extension
        ignore_names = {
            ".git",
            ".vscode",
            ".tmp",
            "node_modules",
            ".DS_Store",
            "Thumbs.db",
        }

        with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zf:
            # Store magic.json at archive root
            zf.writestr("magic.json", json.dumps(package_meta, indent=2))

            for root, dirs, files in os.walk(source_dir):
                dirs[:] = [d for d in dirs if d not in ignore_names]
                for file in files:
                    if file in ignore_names or file == "magic.json":
                        continue
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(source_dir)
                    zf.write(full_path, arcname=str(rel_path))

        print(f"✓ Packaged '{matched['name']}' into .magicext:")
        print(f"  Bundle: {output_file}")
        print(f"  Prompt: {matched['prompt']}")
        print(f"  Symbol: {matched['selected_symbol']} ({matched['symbol_color_name']})")
        return output_file
    finally:
        if close_conn:
            conn.close()


# =========================================================================
#  Community Registry
# =========================================================================

class CommunityRegistry:
    """Manages browsing and resolving extensions from the community catalog."""

    def __init__(self, local_path: Path = LOCAL_REGISTRY_PATH):
        self.local_path = local_path
        self._cache = None

    def fetch_catalog(self) -> dict:
        """Load registry from remote URL if configured, or bundled fallback."""
        if self._cache is not None:
            return self._cache

        remote_url = os.getenv("SAFARI_MAGIC_REGISTRY_URL")
        data = None

        if remote_url:
            try:
                req = urllib.request.Request(
                    remote_url,
                    headers={"User-Agent": "SafariMagicExtensionsManager/1.0"},
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except Exception as err:
                print(f"[Notice] Remote registry unavailable ({err}). Using local catalog.")

        if not data and self.local_path.exists():
            try:
                with open(self.local_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as err:
                print(f"[Warning] Failed to read local registry: {err}")

        if not data:
            data = {"version": 1, "extensions": []}

        self._cache = data
        return data

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
            haystack = (
                f"{item.get('name', '')} {item.get('description', '')} "
                f"{item.get('prompt', '')} {item.get('author', '')} {tags}"
            ).lower()
            if q in haystack:
                matches.append(item)
        return matches

    def get(self, item_id: str) -> dict | None:
        """Find catalog item by ID or name."""
        for item in self.list_all():
            if (
                item.get("id", "").lower() == item_id.lower()
                or item.get("name", "").lower() == item_id.lower()
            ):
                return item
        return None


# =========================================================================
#  Package Installation & Security
# =========================================================================

def safe_extract_archive(archive_path: Path, dest_dir: Path) -> dict:
    """Extract zip/.magicext archive safely protecting against zip-slip directory traversal."""
    dest_dir = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "r") as zf:
        for member in zf.infolist():
            member_path = (dest_dir / member.filename).resolve()
            # Prevent Zip Slip directory traversal vulnerability
            if not str(member_path).startswith(str(dest_dir)):
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
        # Check if it references a local extension already on disk
        if url.startswith("local:"):
            folder_ref = url.replace("local:", "", 1)
            candidate_dir = MAGIC_EXTENSIONS_DIR / folder_ref
            if candidate_dir.exists():
                print(f"-> Packing local showcase extension '{catalog_item['name']}'...")
                pkg = pack_extension(
                    target_identifier=folder_ref,
                    output_dir=temp_workspace,
                    author=catalog_item.get("author"),
                )
                return pkg, catalog_item

        # Check if URL is a relative or local package file path
        rel_candidate = (LOCAL_REGISTRY_PATH.parent / url).resolve()
        if rel_candidate.is_file():
            return rel_candidate, catalog_item

        cwd_candidate = Path(url).expanduser().resolve()
        if cwd_candidate.is_file():
            return cwd_candidate, catalog_item

        if url.startswith("http://") or url.startswith("https://"):
            download_target = temp_workspace / f"{catalog_item['id']}.magicext"
            print(f"-> Downloading '{catalog_item['name']}' from registry...")
            req = urllib.request.Request(
                url, headers={"User-Agent": "SafariMagicExtensionsManager/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
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
        manifest_file = extract_dir / "manifest.json"
        if manifest_file.exists() and effective_prompt:
            try:
                with open(manifest_file, "r", encoding="utf-8") as mf:
                    mdata = json.load(mf)
                if "browser_specific_settings" not in mdata:
                    mdata["browser_specific_settings"] = {}
                if "safari" not in mdata["browser_specific_settings"]:
                    mdata["browser_specific_settings"]["safari"] = {}
                mdata["browser_specific_settings"]["safari"]["prompt"] = effective_prompt
                if effective_name:
                    mdata["name"] = effective_name
                with open(manifest_file, "w", encoding="utf-8") as mf:
                    json.dump(mdata, mf, indent=2)
            except Exception as e:
                print(f"[Warning] Could not update extracted manifest prompt: {e}")

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
        extensions = get_installed_extensions(conn)
        matched = None
        for ext in extensions:
            if (
                target_identifier.lower() == ext["id"].lower()
                or target_identifier.lower() == ext["directory_name"].lower()
                or target_identifier.lower() in ext["name"].lower()
            ):
                matched = ext
                break

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
    print()


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
        print(f"      Install command: safari-magic-ext.py install {item.get('id')}\n")


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
    root.title("Safari Magic Extensions — Community Manager")
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

            query_params = urllib.parse.urlencode({
                "template": "extension_submission.yml",
                "title": f"[Extension Submission]: {name}",
                "extension_name": name,
                "author_handle": author,
                "ai_prompt": prompt,
                "description": desc,
                "selected_symbol": symbol,
                "symbol_color": color,
            })
            repo = os.getenv("SAFARI_MAGIC_HUB_REPO", "Vatsal057/safari-magic-extensions")
            issue_url = f"https://github.com/{repo}/issues/new?{query_params}"
            subprocess.run(["open", "-R", str(pkg_path)], check=False)
            subprocess.run(["open", issue_url], check=False)
            messagebox.showinfo(
                "Submission Prepared",
                f"1. Packaged: {pkg_path.name}\n2. Revealed in Finder.\n3. Opening GitHub submission form in your browser!\n\nJust drag the file into the issue and click Submit.",
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
        description="Share, package, install, and manage Safari Magic Extensions easily."
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
        type=str,
        help="Name, directory name, or ID of extension to pack",
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
        help="Creator name/handle to embed in package",
    )

    # Command: submit
    submit_parser = subparsers.add_parser(
        "submit", help="Package an extension and open GitHub submission form"
    )
    submit_parser.add_argument(
        "target",
        type=str,
        help="Name, directory name, or ID of extension to submit",
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
        help="Creator name/handle to embed in package",
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

    args = parser.parse_args()

    if args.command == "gui":
        launch_gui()
    elif args.command == "explore":
        explore_community(args.query)
    elif args.command == "pack":
        conn = get_db_connection(DB_PATH)
        try:
            pack_extension(
                target_identifier=args.target,
                output_dir=args.output_dir,
                author=args.author,
                conn=conn,
            )
        finally:
            conn.close()
    elif args.command == "submit":
        conn = get_db_connection(DB_PATH)
        try:
            pkg_path = pack_extension(
                target_identifier=args.target,
                author=args.author,
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

            query_params = urllib.parse.urlencode({
                "template": "extension_submission.yml",
                "title": f"[Extension Submission]: {name}",
                "extension_name": name,
                "author_handle": author,
                "ai_prompt": prompt,
                "description": desc,
                "selected_symbol": symbol,
                "symbol_color": color,
            })
            issue_url = f"https://github.com/{args.repo}/issues/new?{query_params}"

            print(f"\n==========================================")
            print(f"      Extension Submission Ready!         ")
            print(f"==========================================")
            print(f"Package: {pkg_path}")
            print(f"GitHub:  {issue_url}")
            print(f"\nNext steps:")
            print(f"1. The submission form is opening in your browser.")
            print(f"2. Drag and drop the revealed file into the issue form.")
            print(f"3. Click 'Submit new issue'!")

            subprocess.run(["open", "-R", str(pkg_path)], check=False)
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


if __name__ == "__main__":
    main()
