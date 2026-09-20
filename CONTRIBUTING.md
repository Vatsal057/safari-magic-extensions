# Contributing

Thanks for helping build the Safari Magic Extensions Community Hub.

There are two kinds of contribution: **submitting an extension** and **changing the code**.

---

## Submitting an extension

The easiest path is the CLI, which packages the extension and opens a pre-filled issue form:

```bash
safari-magic-ext submit "My Extension Name"
```

Prefer a pull request? Then:

1. Package it: `safari-magic-ext pack "My Extension Name" --author "your-handle"`
2. Copy the `.magicext` file into `web/packages/`.
3. Validate it: `python3 scripts/verify_packages.py`
4. Regenerate the catalog: `python3 scripts/build_registry.py`
5. Commit the package **and** the updated `web/community_registry.json`.

Your extension's catalog ID is the slug of its name, which `scripts/build_registry.py` prints
(`Night Meadow New Tab` → `night-meadow-new-tab`). Users install it with that ID.

### Thumbnails

Thumbnails are **real screenshots** of the extension's new-tab page, not hand-picked art.
Generate them with:

```bash
make thumbnails      # renders each package headless into web/assets/thumbnails/<slug>.png
```

This needs a Chromium-based browser (Chrome, Edge, Brave, or Chromium). Each package is
self-contained HTML, so the screenshot shows what the extension actually looks like. Animated
pages are captured after a short settle time. Commit the generated PNG alongside your package.

### Gallery presentation (optional)

`web/registry_curation.json` controls tags and, if needed, an image override. Add an entry
keyed by your slug:

```json
"my-extension-name": {
  "tags": ["ambient", "newtab"]
}
```

- `tags` must come from `ambient`, `focus`, `newtab`, `tech` (these are the gallery filters).
- Image priority is: `art_image` override → generated screenshot → `assets/<slug>.{jpg,png,svg}`
  → a default. Only set `art_image` if the screenshot is a poor representation (for example a
  page that only looks right after interaction).
- Every extension appears equally in the gallery; there is no featured slot. Users order the
  list themselves with the sort control.

### Submission requirements

Your package must contain, at the archive root:

- `manifest.json` — a valid WebExtension manifest
- `magic.json` — with at least a non-empty `name` and `prompt`

It must not contain absolute paths, `..` traversal, or symlinks; CI rejects those. It must not
include obfuscated code, analytics, or external tracking.

---

## Changing the code

### Layout

| Path | What it is |
| --- | --- |
| `safari-magic-ext.py` | CLI + tkinter GUI. Single file, standard library only. |
| `install-cli.sh` | Bootstrap installer for the CLI. |
| `app/Sources/` | SwiftUI app sources. |
| `web/` | Static gallery. No build step, no dependencies. |
| `scripts/build_registry.py` | Generates `web/community_registry.json`. |
| `scripts/verify_packages.py` | Package validation, shared by contributors and CI. |
| `scripts/build_native_app.sh` | Builds the universal `SafariMagicHub.app`. |

Maintainer tooling belongs in `scripts/`. `safari-magic-ext.py` and `install-cli.sh` stay
at the repository root because they are fetched by fixed `raw.githubusercontent.com`
URLs — moving them breaks the published install command.

### Before you open a pull request

```bash
make test                        # lint + package validation + registry check
./scripts/build_native_app.sh    # only if you touched app/Sources
```

`make test` expands to exactly what CI runs:

```bash
python3 -m compileall -q safari-magic-ext.py scripts/
shellcheck --severity=warning scripts/build_native_app.sh install-cli.sh "Launch Safari Magic Hub.command"
python3 scripts/verify_packages.py
python3 scripts/build_registry.py --check
```

Run `make` with no arguments to see every target.

### Conventions worth knowing

- **`safari-magic-ext.py` must stay a single stdlib-only file.** `install-cli.sh` downloads
  just that file, so it cannot import anything from this repository, and it cannot take
  third-party dependencies. Some logic is therefore duplicated between it and
  `scripts/verify_packages.py` on purpose.
- **Never hand-edit `web/community_registry.json`.** It is generated. Edit the packages or
  `web/registry_curation.json` and re-run `scripts/build_registry.py`.
- **Don't hardcode machine-specific paths.** Resolve locations from the bundle, the working
  directory, or `Path.home()`.
- **Archive extraction is security-sensitive.** If you touch it, keep the traversal and
  symlink checks in both the Python and Swift paths.
- **Three clients share one catalog format.** A field added to the registry may need handling
  in `web/app.js`, `safari-magic-ext.py`, and `app/Sources/Models.swift`.

### Things that need root access to test

Installing an extension writes into Safari's sandboxed container and requires Full Disk
Access. Commands that don't need it: `pack`, `convert`, `explore`, and everything in
`scripts/build_registry.py` / `scripts/verify_packages.py`.

---

## Reporting bugs

Open an issue with your macOS version, Safari version, the exact command you ran, and the full
output. For anything security-related, please use a private security advisory instead.
