# Safari Magic Extensions Community Hub

Share and discover AI-generated Magic Extensions for Apple Safari.

Safari can generate extensions from natural language prompts. This hub packages those extensions into standalone `.magicext` bundles with prompt metadata, publishes them to a catalog, and provides single-command installation on macOS.

> **[Visit the Live Web Gallery](https://vatsal057.github.io/safari-magic-extensions/)**
> Browse extensions, view real screenshots, copy AI prompts, inspect download counts, and 1-click install.

| Component | Path | Description |
| --- | --- | --- |
| Web Gallery | [`web/`](web/) | Interactive gallery with search, prompts, and direct install commands |
| CLI and GUI Manager | [`safari-magic-ext.py`](safari-magic-ext.py) | Python standard library manager (terminal and tkinter GUI) |

> **Requirements:** macOS with Safari. The CLI runs on system Python 3.9.6 or later. Reading Safari's extension database requires granting Full Disk Access to your terminal app (see [Troubleshooting](#7-troubleshooting)).

---

## 1. Explore via the Web Gallery

The easiest way to discover extensions is directly in your browser:

**[Open the Community Gallery](https://vatsal057.github.io/safari-magic-extensions/)**

- **Browse & Search:** Filter across extension names, prompts, authors, and category tags (`ambient`, `focus`, `newtab`, `tech`).
- **Live Download Counts:** See popular extensions with real-time download tracking.
- **Sort Options:** Order by Most Downloaded, Newest first, Oldest first, or Alphabetical.
- **Inspect Prompts:** Read and copy the exact natural-language prompts used to generate each extension in Safari.
- **1-Click Install Commands:** Copy terminal commands (Homebrew or 1-step curl) or download the `.magicext` package directly.
- **Deep Links:** Share specific extensions using `#ext=<id>` (for example, `#ext=nightlife-in-the-wild`) or jump to `#submit`.

To preview the gallery locally:

```bash
make serve
# Open http://localhost:8000
```

---

## 2. Installation & Quick Setup

### Option A: Homebrew (Recommended)

```bash
brew install Vatsal057/tap/safari-magic-ext
safari-magic-ext install nightlife-in-the-wild
```

### Option B: Single command (No Homebrew required)

Install the CLI tool and an extension together in one step:

```bash
curl -fsSL https://raw.githubusercontent.com/Vatsal057/safari-magic-extensions/main/install-cli.sh | bash -s -- install nightlife-in-the-wild
```

To install just the standalone CLI:

```bash
curl -fsSL https://raw.githubusercontent.com/Vatsal057/safari-magic-extensions/main/install-cli.sh | bash
```

The installer adds `~/.local/bin` to your `PATH` in `~/.zshrc`. It uses the Python 3 interpreter bundled with macOS.

> **Setup step:** Grant **Full Disk Access** to your terminal application in:
> **System Settings -> Privacy & Security -> Full Disk Access**.
> macOS protects Safari's container from third-party read access by default.

When working inside a repository checkout, invoke the script directly:

```bash
python3 safari-magic-ext.py --help
```

---

## 3. CLI Reference

Extension identifiers are human-readable slugs. Use `explore` to list available items.

```bash
# Browse community extensions with download stats
safari-magic-ext explore
safari-magic-ext explore "zen"

# Install from the catalog
safari-magic-ext install nightlife-in-the-wild

# Install from a local package, folder, or remote URL
safari-magic-ext install ~/Downloads/MyExtension.magicext
safari-magic-ext install ./my-extension-folder
safari-magic-ext install https://example.com/package.magicext

# List installed extensions
safari-magic-ext list

# Package an installed extension (prompts for selection if name is omitted)
safari-magic-ext pack
safari-magic-ext pack "Nightlife in the Wild" --author "vatsal"

# Convert a local web folder to a .magicext bundle independently of Safari
safari-magic-ext convert ./my-extension-folder

# Submit an extension to the community catalog
safari-magic-ext submit
safari-magic-ext submit "Nightlife in the Wild"

# Export packages as zip archives to ~/Downloads
safari-magic-ext export all --zip

# Sync on-disk extension folders into Safari's database
safari-magic-ext sync

# Launch the visual interface
safari-magic-ext gui
```

The CLI caches catalog data at `~/Library/Caches/safari-magic-ext` so `explore` and `install` remain usable offline. To target a custom catalog URL, set `SAFARI_MAGIC_REGISTRY_URL`.

---

## 4. Architecture

```
[ Creator ]                          [ GitHub Actions ]                  [ User ]

1. Generate in Safari         1. Issue submission with payload    1. Browse web gallery
2. safari-magic-ext submit       (Base64 package data)               or: safari-magic-ext explore
                              2. Verification and screenshot run  2. Install command:
                              3. Published to community gallery      safari-magic-ext install <id>
```

---

## 5. Submitting Extensions

### For Creators

Submit extensions with the CLI:

```bash
safari-magic-ext submit
```

The command prompts you to select an installed extension, packages it, and opens the GitHub submission form with the extension payload embedded in the body.

If the CLI is not yet installed:

```bash
curl -fsSL https://raw.githubusercontent.com/Vatsal057/safari-magic-extensions/main/install-cli.sh | bash -s -- submit
```

You can also submit directly from the web gallery by dragging your extension folder into the **Share yours** dropzone.

### Automated Ingestion Pipeline

When an issue is opened with the `extension-submission` label:

1. **Extraction:** GitHub Actions extracts the package data.
2. **Security validation:** `scripts/verify_packages.py` checks file paths, permissions, and metadata.
3. **Screenshot capture:** Headless Chromium renders a 1280x800 preview of the extension.
4. **Catalog update:** `scripts/build_registry.py` compiles `web/community_registry.json`.
5. **Publishing:** The workflow commits the changes to `main`, closes the issue, and deploys to GitHub Pages.

---

## 6. Packaging Standard (`.magicext`)

A `.magicext` package is a zip archive containing a standard WebExtension structure and a root `magic.json`:

```json
{
  "magic_format_version": 1,
  "id": "FBE0B00A-A8E0-4B92-B2A6-DAB05CBC8B58",
  "name": "Nightlife in the Wild",
  "author": "vatsal",
  "version": "1.0",
  "description": "Nightlife 24B7 Safari Extension",
  "prompt": "Create Nightlife 24B7; make it day time; revert",
  "selected_symbol": "moon.stars.fill",
  "symbol_color_name": "purple",
  "packaged_at": "2026-09-20T06:22:18Z"
}
```

The `id` field stores Safari's internal UUID. The command-line slug derives from `name`. The `prompt` string preserves the AI instruction used to generate the extension.

---

## 7. Troubleshooting

**Extensions.db not found:**
Launch Safari at least once so the browser initializes its database.

**Cannot open Safari's extension database / OperationalError:**
macOS blocked access via TCC. Open **System Settings -> Privacy & Security -> Full Disk Access** and enable your terminal app (Terminal, iTerm2, Ghostty). Restart the terminal application afterward.

**Safari restarts during installation:**
Safari loads extensions during launch. Installs restart the browser by default. To skip restarting Safari, pass `--no-restart`.

**Note on Native Application Deprecation:**
Earlier experimental releases included a native `SafariMagicHub.app` bundle. The hub has transitioned completely to the zero-dependency CLI (`safari-magic-ext`) and static Web Gallery, removing macOS sandbox restrictions and avoiding unsigned binary warnings.

---

## 8. Security

Packages are treated as untrusted input. Extraction incorporates these protections:

- Rejection of archive members with absolute paths, directory traversal (`..`), or symbolic links.
- Post-resolution path checks ensuring all extracted files reside inside the target directory.
- Continuous validation in CI via `scripts/verify_packages.py` on all catalog entries.

To report a vulnerability, open a private security advisory on GitHub instead of a public issue.

---

## 9. Repository Layout

```
safari-magic-ext.py            CLI and tkinter GUI (single file, standard library only)
install-cli.sh                 Installer script for ~/.local/bin
Makefile                       Task shortcuts
web/                           Gallery interface, extension packages, and catalog
scripts/build_registry.py      Compiles web/community_registry.json
scripts/verify_packages.py     Package validation script for local and CI use
scripts/generate_thumbnails.sh Renders screenshots of extensions
.github/workflows/             CI, submission ingestion, and Pages deployment
```

### Common Commands

```bash
make            # List available targets
make test       # Run CI validation suite: compile check, package tests, registry check
make registry   # Recompile community catalog
make serve      # Preview gallery at http://localhost:8000
```

## License

[MIT](LICENSE)
