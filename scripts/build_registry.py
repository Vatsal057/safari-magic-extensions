#!/usr/bin/env python3
"""Build & sync the community registry for the Safari Magic Gallery.

Scans `web/packages/*.magicext`, validates each archive, merges maintainer
curation from `web/registry_curation.json`, and writes `web/community_registry.json`.

The generated registry is consumed by three clients, so its shape matters:
  * the web gallery              (web/app.js)
  * the Python CLI               (safari-magic-ext.py, `explore` / `install <id>`)
  * the native macOS app         (app/Sources/CommunityRegistry.swift)

Extension IDs are human-readable slugs derived from the package name, so that
`safari-magic-ext install night-meadow-new-tab` is memorable. Never hand-edit
the generated registry; edit the curation file or the packages instead.

Usage (from the repository root):
  python3 scripts/build_registry.py            # regenerate the registry
  python3 scripts/build_registry.py --check    # verify it is up to date, exit 1 if not

Runs on the Python that ships with macOS (3.9.6); the __future__ import keeps the
`X | None` annotations lazy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
import zipfile

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"
PACKAGES_DIR = WEB_DIR / "packages"
REGISTRY_FILE = WEB_DIR / "community_registry.json"
CURATION_FILE = WEB_DIR / "registry_curation.json"

REGISTRY_NAME = "Safari Magic Extensions Community Hub"
REGISTRY_VERSION = 1

# Must stay in sync with the ribbon buttons in web/index.html (data-filter).
VALID_TAGS = {"ambient", "focus", "newtab", "tech"}
DEFAULT_TAGS = ["newtab"]
DEFAULT_ART = "assets/hero_cyberpunk.jpg"
DEFAULT_SYMBOL = "puzzlepiece.extension"
DEFAULT_COLOR = "blue"


def slugify(value: str) -> str:
    """Convert a package name into a stable, lowercase, dash-separated ID.

    Mirrors `slugify` in safari-magic-ext.py so CLI lookups match registry IDs.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug or "extension"


def load_curation() -> dict:
    """Load maintainer curation, tolerating a missing file."""
    if not CURATION_FILE.exists():
        return {}
    try:
        with open(CURATION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as err:
        print(f"[Warning] Could not read {CURATION_FILE.name}: {err}")
        return {}
    return data.get("extensions", {}) or {}


def read_package_metadata(pkg: Path) -> dict:
    """Read and validate magic.json from a .magicext archive.

    Raises ValueError with a reviewer-friendly message on any problem so the
    submission workflow can report exactly what a contributor must fix.
    """
    with zipfile.ZipFile(pkg, "r") as zf:
        names = zf.namelist()

        if "magic.json" not in names:
            raise ValueError("missing magic.json at the archive root")
        if "manifest.json" not in names:
            raise ValueError("missing manifest.json at the archive root")

        try:
            meta = json.loads(zf.read("magic.json").decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise ValueError(f"magic.json is not valid JSON ({err})") from err

    if not isinstance(meta, dict):
        raise ValueError("magic.json must contain a JSON object")
    if not str(meta.get("name", "")).strip():
        raise ValueError("magic.json is missing a non-empty 'name'")
    if not str(meta.get("prompt", "")).strip():
        raise ValueError("magic.json is missing a non-empty 'prompt'")

    return meta


def resolve_art_image(slug: str, curated: dict) -> str:
    """Pick a preview image: curated override, then a slug-named asset, then default."""
    override = curated.get("art_image")
    if override:
        if not (WEB_DIR / override).exists():
            print(f"  [Warning] {slug}: curated art_image '{override}' not found on disk")
        return override

    for suffix in (".jpg", ".jpeg", ".png", ".svg"):
        candidate = Path("assets") / f"{slug}{suffix}"
        if (WEB_DIR / candidate).exists():
            return candidate.as_posix()

    return DEFAULT_ART


def normalize_tags(slug: str, curated: dict) -> list[str]:
    """Validate curated tags, warning about values the gallery cannot filter on."""
    tags = curated.get("tags") or DEFAULT_TAGS
    if not isinstance(tags, list):
        print(f"  [Warning] {slug}: 'tags' must be a list; using defaults")
        return list(DEFAULT_TAGS)

    clean = []
    for tag in tags:
        tag = str(tag).strip().lower()
        if not tag:
            continue
        if tag not in VALID_TAGS:
            print(
                f"  [Warning] {slug}: tag '{tag}' is not a gallery filter "
                f"({', '.join(sorted(VALID_TAGS))})"
            )
        if tag not in clean:
            clean.append(tag)

    return clean or list(DEFAULT_TAGS)


def build_extensions() -> tuple[list[dict], list[str]]:
    """Turn every package on disk into a registry entry. Returns (entries, errors)."""
    curation = load_curation()
    packages = sorted(PACKAGES_DIR.glob("*.magicext"), key=lambda p: p.name)
    print(f"Found {len(packages)} package(s) in {PACKAGES_DIR.relative_to(ROOT_DIR)}")

    entries: list[dict] = []
    errors: list[str] = []
    seen_slugs: dict[str, str] = {}
    featured_slugs: list[str] = []

    for pkg in packages:
        try:
            meta = read_package_metadata(pkg)
        except (ValueError, zipfile.BadZipFile, OSError) as err:
            errors.append(f"{pkg.name}: {err}")
            print(f"  ✗ {pkg.name}: {err}")
            continue

        name = str(meta["name"]).strip()
        slug = slugify(name)

        if slug in seen_slugs:
            errors.append(
                f"{pkg.name}: ID '{slug}' already used by {seen_slugs[slug]}. "
                "Rename one of the extensions so their IDs differ."
            )
            print(f"  ✗ {pkg.name}: duplicate ID '{slug}'")
            continue
        seen_slugs[slug] = pkg.name

        curated = curation.get(slug, {}) or {}
        tags = normalize_tags(slug, curated)
        if curated.get("featured"):
            featured_slugs.append(slug)

        entries.append(
            {
                "id": slug,
                "name": name,
                "author": str(meta.get("author") or "community"),
                "version": str(meta.get("version") or "1.0"),
                "description": str(
                    meta.get("description") or f"{name} Safari Extension"
                ).strip(),
                "prompt": str(meta["prompt"]).strip(),
                "selected_symbol": str(meta.get("selected_symbol") or DEFAULT_SYMBOL),
                "symbol_color_name": str(
                    meta.get("symbol_color_name") or DEFAULT_COLOR
                ),
                "tags": tags,
                "category": str(curated.get("category") or tags[0]),
                "art_image": resolve_art_image(slug, curated),
                "featured": bool(curated.get("featured", False)),
                "download_url": f"packages/{pkg.name}",
            }
        )
        print(f"  ✓ {name}  →  id: {slug}")

    if len(featured_slugs) > 1:
        errors.append(
            "More than one extension is marked 'featured' in "
            f"{CURATION_FILE.name}: {', '.join(featured_slugs)}"
        )
    elif entries and not featured_slugs:
        # Not fatal: the gallery falls back to the first entry.
        print(f"  [Notice] No extension marked 'featured' in {CURATION_FILE.name}")

    # Flag curation entries that no longer match a package, so the file
    # does not silently accumulate stale slugs.
    for slug in curation:
        if slug not in seen_slugs:
            print(f"  [Notice] {CURATION_FILE.name}: '{slug}' matches no package")

    return entries, errors


def load_existing_registry() -> dict | None:
    if not REGISTRY_FILE.exists():
        return None
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def render(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def build(check_only: bool = False) -> int:
    """Regenerate the registry. Returns a process exit code."""
    mode = "Checking" if check_only else "Building"
    print(f"🪄 {mode} Safari Magic Extensions community registry...")

    if not PACKAGES_DIR.exists():
        if check_only:
            print(f"\n✗ Missing packages directory: {PACKAGES_DIR}")
            return 1
        PACKAGES_DIR.mkdir(parents=True, exist_ok=True)

    entries, errors = build_extensions()

    if errors:
        print("\n✗ Registry build failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    existing = load_existing_registry()
    payload = {
        "version": REGISTRY_VERSION,
        "registry_name": REGISTRY_NAME,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "extensions": entries,
    }

    # Keep the build idempotent: only move `updated_at` when the catalog
    # content actually changed, so reruns produce no spurious diffs.
    def content_of(data: dict | None) -> object:
        if not data:
            return None
        return {k: v for k, v in data.items() if k != "updated_at"}

    unchanged = content_of(existing) == content_of(payload)
    if unchanged and existing:
        payload["updated_at"] = existing.get("updated_at", payload["updated_at"])

    if check_only:
        if unchanged and render(existing or {}) == render(payload):
            print(f"\n✓ {REGISTRY_FILE.name} is up to date ({len(entries)} extensions).")
            return 0
        print(
            f"\n✗ {REGISTRY_FILE.name} is out of date.\n"
            "  Run `python3 scripts/build_registry.py` and commit the result."
        )
        return 1

    REGISTRY_FILE.write_text(render(payload), encoding="utf-8")

    print(f"\n✓ Wrote {len(entries)} extension(s) to {REGISTRY_FILE.relative_to(ROOT_DIR)}")
    if unchanged:
        print("  (content unchanged)")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the committed registry matches the packages, without writing.",
    )
    args = parser.parse_args()
    sys.exit(build(check_only=args.check))


if __name__ == "__main__":
    main()
