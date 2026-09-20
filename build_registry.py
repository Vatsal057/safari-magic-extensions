#!/usr/bin/env python3
"""Build & Sync Community Registry for GitHub Pages.

Scans packages/*.magicext, extracts magic.json metadata, validates archives,
and updates community_registry.json and docs/community_registry.json.
"""

import json
from pathlib import Path
import shutil
import sys
import time
import zipfile

ROOT_DIR = Path(__file__).resolve().parent
PACKAGES_DIR = ROOT_DIR / "packages"
DOCS_DIR = ROOT_DIR / "docs"
DOCS_PACKAGES_DIR = DOCS_DIR / "packages"
ROOT_REGISTRY = ROOT_DIR / "community_registry.json"
DOCS_REGISTRY = DOCS_DIR / "community_registry.json"


def build():
    print("🪄 Building Safari Magic Extensions Community Registry...")

    if not PACKAGES_DIR.exists():
        PACKAGES_DIR.mkdir(parents=True, exist_ok=True)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_PACKAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing registry as base for custom tags/overrides if present
    existing_meta = {}
    if ROOT_REGISTRY.exists():
        try:
            with open(ROOT_REGISTRY, "r", encoding="utf-8") as f:
                old_data = json.load(f)
                for ext in old_data.get("extensions", []):
                    existing_meta[ext["id"]] = ext
        except Exception:
            pass

    packages = list(PACKAGES_DIR.glob("*.magicext"))
    print(f"Found {len(packages)} package(s) in {PACKAGES_DIR}")

    built_extensions = []

    for pkg in sorted(packages, key=lambda p: p.name):
        try:
            with zipfile.ZipFile(pkg, "r") as zf:
                names = zf.namelist()
                if "magic.json" not in names:
                    print(f"  [Skip] {pkg.name}: Missing magic.json")
                    continue

                meta = json.loads(zf.read("magic.json").decode("utf-8"))
                ext_id = meta.get("id") or pkg.stem.lower().replace("_", "-")

                # Check if we have manual tags in existing registry
                tags = existing_meta.get(ext_id, {}).get("tags") or ["ambient", "newtab"]

                item = {
                    "id": ext_id,
                    "name": meta.get("name", pkg.stem),
                    "author": meta.get("author", "community"),
                    "version": meta.get("version", "1.0"),
                    "description": meta.get("description") or f"{meta.get('name')} Safari Extension",
                    "prompt": meta.get("prompt", ""),
                    "selected_symbol": meta.get("selected_symbol", "puzzlepiece.extension"),
                    "symbol_color_name": meta.get("symbol_color_name", "blue"),
                    "tags": tags,
                    "download_url": f"packages/{pkg.name}",
                }
                built_extensions.append(item)
                print(f"  ✓ Processed: {item['name']} ({pkg.name})")

                # Copy into docs/packages for static GitHub Pages download
                shutil.copy2(pkg, DOCS_PACKAGES_DIR / pkg.name)
        except Exception as err:
            print(f"  [Error] Failed to process {pkg.name}: {err}")

    # If registry has remote items not in local packages folder (e.g. external links), preserve them
    for ext_id, ext in existing_meta.items():
        if ext.get("download_url", "").startswith("http") and not any(b["id"] == ext_id for b in built_extensions):
            built_extensions.append(ext)

    registry_payload = {
        "version": 1,
        "registry_name": "Safari Magic Extensions Community Hub",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "extensions": built_extensions,
    }

    # Write root registry
    with open(ROOT_REGISTRY, "w", encoding="utf-8") as f:
        json.dump(registry_payload, f, indent=2)

    # Write docs registry for GitHub Pages
    with open(DOCS_REGISTRY, "w", encoding="utf-8") as f:
        json.dump(registry_payload, f, indent=2)

    print(f"\n✓ Successfully updated registries with {len(built_extensions)} extensions:")
    print(f"  - {ROOT_REGISTRY}")
    print(f"  - {DOCS_REGISTRY}")
    print(f"  - Synced packages to {DOCS_PACKAGES_DIR}")


if __name__ == "__main__":
    build()
