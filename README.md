# Safari Magic Extensions Community Hub

Share and discover AI-generated Magic Extensions for Apple Safari.

Safari can generate extensions from natural language prompts. This hub packages those extensions into standalone `.magicext` bundles with prompt metadata, publishes them to a catalog, and provides single-command installation on macOS.

| Component | Path | Description |
| --- | --- | --- |
| CLI and GUI Manager | [`safari-magic-ext.py`](safari-magic-ext.py) | Python standard library manager (terminal and tkinter GUI) |
| Web Gallery | [`web/`](web/) | Interactive gallery with search, prompts, and direct install commands |

> **Requirements:** macOS with Safari. The CLI runs on system Python 3.9.6 or later. Reading Safari's extension database requires granting Full Disk Access to your terminal app (see [Troubleshooting](#6-troubleshooting)).

---

## Architecture

```
[ Creator ]                          [ GitHub Actions ]                  [ User ]

1. Generate in Safari         1. Issue submission with payload    1. Browse web gallery
2. safari-magic-ext submit       (Base64 package data)               or: safari-magic-ext explore
                              2. Verification and screenshot run  2. Install command:
                              3. Published to community gallery      safari-magic-ext install <id>
```

---

## 1. Installation

### Quick install

Run this command in Terminal to install the CLI and an extension together:

```bash
curl -fsSL https://raw.githubusercontent.com/Vatsal057/safari-magic-extensions/main/install-cli.sh | bash -s -- install hacker-news-minimal
```

Replace `hacker-news-minimal` with any slug from `safari-magic-ext explore` or the [web gallery][gallery].

### Install the CLI

Install the tool to `~/.local/bin`:

```bash
curl -fsSL https://raw.githubusercontent.com/Vatsal057/safari-magic-extensions/main/install-cli.sh | bash
```

The installer adds `~/.local/bin` to your `PATH` in `~/.zshrc`. It uses the Python 3 interpreter bundled with macOS. To pin a specific release version, set `REF=v1.1.1`.

> **Setup step:** Grant **Full Disk Access** to your terminal application in:
> **System Settings → Privacy & Security → Full Disk Access**.
> macOS protects Safari's container from third-party read access by default.

When working inside a repository checkout, invoke the script directly:

```bash
python3 safari-magic-ext.py --help
```

---

## 2. CLI Reference

Extension identifiers are human-readable slugs. Use `explore` to list available items.

```bash
# Browse community extensions
safari-magic-ext explore
safari-magic-ext explore "pomodoro"

# Install from the catalog
safari-magic-ext install night-meadow-new-tab

# Install from a local package, folder, or remote URL
safari-magic-ext install ~/Downloads/MyExtension.magicext
safari-magic-ext install ./my-extension-folder
safari-magic-ext install https://example.com/package.magicext

# List installed extensions
safari-magic-ext list

# Package an installed extension (prompts for selection if name is omitted)
safari-magic-ext pack
safari-magic-ext pack "Night Meadow New Tab" --author "vatsal"

# Convert a local web folder to a .magicext bundle independently of Safari
safari-magic-ext convert ./my-extension-folder

# Submit an extension to the community catalog
safari-magic-ext submit
safari-magic-ext submit "Night Meadow New Tab"

# Export packages as zip archives to ~/Downloads
safari-magic-ext export all --zip

# Sync on-disk extension folders into Safari's database
safari-magic-ext sync

# Launch the visual interface
safari-magic-ext gui
```

The CLI caches catalog data at `~/Library/Caches/safari-magic-ext` so `explore` and `install` remain usable offline. To target a custom catalog URL, set `SAFARI_MAGIC_REGISTRY_URL`.

---

## 3. Web Gallery

**[Open the Community Gallery](https://vatsal057.github.io/safari-magic-extensions/)**

The gallery lives in [`web/`](web/) as static HTML, CSS, and vanilla JavaScript:

- **Live search:** Filters across extension names, prompts, authors, tags, and IDs.
- **Category filters:** Narrow results by `ambient`, `focus`, `newtab`, or `tech`.
- **Automated previews:** Headless browser screenshots of each extension's actual new-tab page.
- **Install modal:** Displays copyable CLI commands, direct package downloads, and original prompts.
- **Deep links:** Anchor links `#ext=<id>` open a specific modal; `#submit` jumps to submission instructions.

To run the gallery locally:

```bash
make serve
# Open http://localhost:8000
```

The gallery must be served via HTTP because browser security policies block catalog `fetch` requests when opened through `file://`.

---

## 4. Submitting Extensions

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

### Automated Ingestion Pipeline

When an issue is opened with the `extension-submission` label:

1. **Extraction:** GitHub Actions extracts the package data.
2. **Security validation:** `scripts/verify_packages.py` checks file paths, permissions, and metadata.
3. **Screenshot capture:** Headless Chromium renders a 1280x800 preview of the extension.
4. **Catalog update:** `scripts/build_registry.py` compiles `web/community_registry.json`.
5. **Publishing:** The workflow commits the changes to `main`, closes the issue, and deploys to GitHub Pages.

---

## 5. Packaging Standard (`.magicext`)

A `.magicext` package is a zip archive containing a standard WebExtension structure and a root `magic.json`:

```json
{
  "magic_format_version": 1,
  "id": "FBE0B00A-A8E0-4B92-B2A6-DAB05CBC8B58",
  "name": "Night Meadow New Tab",
  "author": "vatsal",
  "version": "1.0",
  "description": "2D illustrated night ecosystem for your new tab page.",
  "prompt": "Build a 2D illustrated night ecosystem that feels calm and natural on the new tab page.",
  "selected_symbol": "moon.stars.fill",
  "symbol_color_name": "blue",
  "packaged_at": "2026-09-20T12:00:00Z"
}
```

The `id` field stores Safari's internal UUID. The command-line slug derives from `name`. The `prompt` string preserves the AI instruction used to generate the extension.

---

## 6. Troubleshooting

**Extensions.db not found:**
Launch Safari at least once so the browser initializes its database.

**Cannot open Safari's extension database / OperationalError:**
macOS blocked access via TCC. Open **System Settings → Privacy & Security → Full Disk Access** and enable your terminal app (Terminal, iTerm2, Ghostty). Restart the terminal application afterward.

**Safari restarts during installation:**
Safari loads extensions during launch. Installs restart the browser by default. To skip restarting Safari, pass `--no-restart`.

---

## 7. Security

Packages are treated as untrusted input. Extraction incorporates these protections:

- Rejection of archive members with absolute paths, directory traversal (`..`), or symbolic links.
- Post-resolution path checks ensuring all extracted files reside inside the target directory.
- Continuous validation in CI via `scripts/verify_packages.py` on all catalog entries.

To report a vulnerability, open a private security advisory on GitHub instead of a public issue.

---

## 8. Repository Layout

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

[gallery]: https://vatsal057.github.io/safari-magic-extensions/
