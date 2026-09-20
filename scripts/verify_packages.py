#!/usr/bin/env python3
"""Validate .magicext submission packages.

Checks every package (or just the ones named on the command line) for:
  * archive safety  - no absolute paths, no `..` traversal, no symlinks
  * required files  - magic.json and manifest.json at the archive root
  * required fields - a non-empty name and prompt in magic.json
  * ID uniqueness   - no two packages resolving to the same registry slug

Run locally before opening a pull request:
    python3 scripts/verify_packages.py

In GitHub Actions the results are also written to the job summary.

Note: safari-magic-ext.py deliberately carries its own copy of the archive
safety check. It ships as a single standalone file (install-cli.sh downloads
only that file), so it cannot import from this repository.
"""

import json
import os
from pathlib import Path
import stat
import sys
import zipfile


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGES_DIR = REPO_ROOT / "web" / "packages"

# build_registry.py sits alongside this file, so a plain import works.
from build_registry import read_package_metadata, slugify


def scan_archive_safety(pkg: Path) -> list[str]:
    """Return a list of safety problems found in the archive."""
    problems: list[str] = []
    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            for member in zf.infolist():
                name = member.filename
                normalized = name.replace("\\", "/")

                if normalized.startswith("/"):
                    problems.append(f"absolute path in member '{name}'")
                elif len(normalized) > 1 and normalized[1] == ":":
                    problems.append(f"absolute Windows path in member '{name}'")

                if ".." in normalized.split("/"):
                    problems.append(f"path traversal in member '{name}'")

                mode = member.external_attr >> 16
                if mode and stat.S_ISLNK(mode):
                    problems.append(f"symbolic link in member '{name}'")
    except (zipfile.BadZipFile, OSError) as err:
        problems.append(f"could not read archive: {err}")

    return problems


def verify(packages: list[Path]) -> tuple[list[str], list[dict]]:
    """Verify packages. Returns (errors, summary rows)."""
    errors: list[str] = []
    rows: list[dict] = []
    seen: dict[str, str] = {}

    for pkg in packages:
        print(f"\nChecking {pkg.name}")

        safety_problems = scan_archive_safety(pkg)
        for problem in safety_problems:
            errors.append(f"{pkg.name}: {problem}")
            print(f"  ✗ {problem}")

        if safety_problems:
            # An unreadable or unsafe archive cannot be inspected further.
            continue

        try:
            meta = read_package_metadata(pkg)
        except (ValueError, zipfile.BadZipFile, OSError) as err:
            errors.append(f"{pkg.name}: {err}")
            print(f"  ✗ {err}")
            continue

        name = str(meta["name"]).strip()
        slug = slugify(name)

        if slug in seen:
            errors.append(
                f"{pkg.name}: registry ID '{slug}' collides with {seen[slug]}"
            )
            print(f"  ✗ duplicate registry ID '{slug}' (also from {seen[slug]})")
            continue
        seen[slug] = pkg.name

        rows.append(
            {
                "package": pkg.name,
                "id": slug,
                "name": name,
                "author": str(meta.get("author") or "unknown"),
                "symbol": str(meta.get("selected_symbol") or "puzzlepiece.extension"),
                "color": str(meta.get("symbol_color_name") or "blue"),
            }
        )
        print(f"  ✓ {name}  (id: {slug})")

    return errors, rows


def write_job_summary(rows: list[dict], errors: list[str]) -> None:
    """Publish a markdown table to the GitHub Actions job summary, if running in CI."""
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    lines = ["## 🪄 Extension package verification", ""]

    if rows:
        lines += [
            "| Package | Registry ID | Name | Author | Symbol |",
            "| --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| `{r['package']}` | `{r['id']}` | {r['name']} | @{r['author']} "
            f"| {r['symbol']} ({r['color']}) |"
            for r in rows
        ]
        lines.append("")

    if errors:
        lines += ["### ❌ Problems found", ""]
        lines += [f"- {err}" for err in errors]
    else:
        lines.append("### ✓ All packages passed validation")

    try:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as err:
        print(f"[Warning] Could not write job summary: {err}")


def main() -> int:
    args = sys.argv[1:]
    if args:
        packages = [Path(a) for a in args]
        missing = [p for p in packages if not p.is_file()]
        if missing:
            for p in missing:
                print(f"Error: no such package: {p}", file=sys.stderr)
            return 1
    else:
        if not PACKAGES_DIR.is_dir():
            print(f"Error: missing packages directory {PACKAGES_DIR}", file=sys.stderr)
            return 1
        packages = sorted(PACKAGES_DIR.glob("*.magicext"), key=lambda p: p.name)

    if not packages:
        print(f"No .magicext packages found in {PACKAGES_DIR}. Nothing to verify.")
        return 0

    print(f"Inspecting {len(packages)} package(s)...")
    errors, rows = verify(packages)
    write_job_summary(rows, errors)

    if errors:
        print(f"\n❌ {len(errors)} problem(s) found:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"\n✓ All {len(rows)} package(s) passed security and metadata validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
