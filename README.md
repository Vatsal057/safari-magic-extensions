# Safari Magic Extensions Community Hub 🪄

A community sharing and distribution platform for Apple Safari's AI-generated **Magic Extensions**.

Safari can generate an extension from a natural-language prompt. This project makes those
extensions shareable: it packages one into a single `.magicext` file (carrying the original
prompt as metadata), publishes it to a catalog, and installs it on someone else's Mac in one
command.

Three clients read the same catalog:

| Component | Path | What it is |
| --- | --- | --- |
| CLI + tkinter GUI | [`safari-magic-ext.py`](safari-magic-ext.py) | Single-file, stdlib-only manager |
| Native macOS app | [`app/`](app/) | SwiftUI app (`SafariMagicHub.app`) |
| Web gallery | [`web/`](web/) | Static GitHub Pages site |

> **Requirements:** macOS with Safari. The app needs nothing else installed. The CLI
> runs on the Python that ships with macOS (3.9.6+).
> Both the CLI and the app need **Full Disk Access** to read Safari's extension database
> (see [Troubleshooting](#7-troubleshooting)).


---

## Architecture Overview

```
[ Creator ]                        [ GitHub ]                          [ User ]

1. Generate in Safari       1. Issue form or PR                 1. Browse the web gallery
2. safari-magic-ext submit     (verified by Actions)                or: safari-magic-ext explore
                            2. Maintainer reviews & merges       2. One-click install:
                            3. Action rebuilds the registry         safari-magic-ext install <id>
                               and deploys to Pages
```

---

## 1. Install an extension

### Fastest — one paste into Terminal

```bash
# Install + run in a single line. Installs the CLI, then installs the extension.
curl -fsSL https://raw.githubusercontent.com/Vatsal057/safari-magic-extensions/main/install-cli.sh | bash -s -- install hacker-news-minimal
```

No setup required. Works on any Mac with Safari. Swap `hacker-news-minimal` for any
extension ID from `safari-magic-ext explore` or the [web gallery][gallery].

### Option A — the Mac app (no Terminal, nothing to install first)

1. Download the `.dmg` from the [latest release](https://github.com/Vatsal057/safari-magic-extensions/releases/latest).
2. Drag **SafariMagicHub** onto **Applications**.
3. Right-click the app and choose **Open**. This is only needed the first time; macOS
   warns because the app is not notarized (that requires a paid Apple Developer account).
4. Open the **Community Hub** tab and click Install.

The app also handles `.magicext` files, so once it is installed you can download a package
from the gallery and double-click it.

### Option B — install the CLI permanently

```bash
# Install the CLI once…
curl -fsSL https://raw.githubusercontent.com/Vatsal057/safari-magic-extensions/main/install-cli.sh | bash

# …then install anything by ID:
safari-magic-ext install hacker-news-minimal
```

Installs `safari-magic-ext` into `~/.local/bin` and adds it to your PATH automatically.
Runs on the Python that ships with macOS — nothing else needed. Pin a release with `REF=v1.1.1`.

> **One-time setup:** grant **Full Disk Access** to your terminal app in
> **System Settings → Privacy & Security → Full Disk Access**.
> macOS blocks any process that isn't the app itself from reading Safari's sandbox.

From a clone you can skip the installer entirely:

```bash
python3 safari-magic-ext.py --help
```

---

## 2. CLI Quick Reference

Extension IDs are readable slugs. Run `explore` to see the current ones.

```bash
# Browse the community catalog
safari-magic-ext explore
safari-magic-ext explore "pomodoro"

# Install from the community catalog
safari-magic-ext install night-meadow-new-tab

# Install from a local package, a folder, or a URL
safari-magic-ext install ~/Downloads/MyExtension.magicext
safari-magic-ext install ./my-extension-folder
safari-magic-ext install https://example.com/package.magicext

# List what you already have installed
safari-magic-ext list

# Package an installed extension for sharing
# (interactive picker if you omit the name)
safari-magic-ext pack
safari-magic-ext pack "Night Meadow New Tab" --author "vatsal"

# Turn any local web folder into a .magicext bundle (no Safari required)
safari-magic-ext convert ./my-extension-folder

# Submit to the GitHub catalog
# (interactive picker — no need to know the exact name)
safari-magic-ext submit
safari-magic-ext submit "Night Meadow New Tab"

# Export / back up to ~/Downloads
safari-magic-ext export all --zip

# Register extension folders Safari has on disk but not in its database
safari-magic-ext sync

# Open the tkinter GUI (also the default with no arguments)
safari-magic-ext gui
```

The catalog is fetched from GitHub Pages and cached in `~/Library/Caches/safari-magic-ext`,
so `explore` and `install` keep working offline. Point the CLI at your own fork with
`SAFARI_MAGIC_REGISTRY_URL`.

---

## 3. Building the Mac App Yourself

Most people should just download the release. To build from source:

```bash
./scripts/build_native_app.sh   # universal SafariMagicHub.app
open SafariMagicHub.app

./scripts/package_release.sh    # also produces dist/*.dmg, *.zip, SHA256SUMS.txt
```

The build compiles `app/Sources/*.swift` with `swiftc` (no Xcode project needed), merges the
`arm64` and `x86_64` slices with `lipo`, embeds the current catalog as an offline fallback, and
code-signs with your Apple Development identity if you have one (ad-hoc otherwise). Build a
single slice with `ARCHS="arm64" ./scripts/build_native_app.sh`.

The app is pure Swift and links only system frameworks, so **it needs no Python and no other
runtime** on the user's machine. It registers itself as the handler for `.magicext` files, so
double-clicking a package installs it.

### A note on notarization

Releases are code-signed but **not notarized**, because notarization requires a paid Apple
Developer account. That is why first launch needs right-click → Open. If you have a
Developer ID certificate installed, `build_native_app.sh` picks it up automatically; to remove
the warning for end users entirely you would additionally need to notarize and staple the app.

---

## 4. Web Gallery

**[Browse the gallery →](https://vatsal057.github.io/safari-magic-extensions/)**

The static gallery lives in [`web/`](web/). It has no build step and no dependencies:

- A **setup section** with both ways to get started — download the Mac app, or copy the
  one-line CLI installer. This is the prerequisite most people need first.
- **Search** across name, prompt, author, tag, and ID, plus the category ribbon. Every
  term in a multi-word query has to match.
- Each extension opens an **install panel** with the exact `install <id>` command, a
  direct package download, and the original prompt to copy and remix.
- **Shareable links**: `#ext=<id>` opens a specific extension, `#submit` opens the
  contribution instructions.

To view it locally:

```bash
make serve
# open http://localhost:8000
```

It must be served over HTTP. Opening `index.html` with `file://` blocks the `fetch` of the
catalog, and the page will say so rather than appearing empty.

To deploy: push to `main`, then set **Settings → Pages → Build and deployment → Source:
GitHub Actions**.

---

## 5. Submitting & Reviewing Extensions

### For creators

**If you have the CLI installed:**
```bash
# Interactive — picks from your installed extensions, no name needed.
safari-magic-ext submit

# Or name it explicitly:
safari-magic-ext submit "Nightlife in the Wild"
```

**No CLI yet? One paste does everything:**
```bash
curl -fsSL https://raw.githubusercontent.com/Vatsal057/safari-magic-extensions/main/install-cli.sh | bash -s -- submit
```
Installs the CLI, shows an interactive picker, packages the chosen extension, and opens the
submission form — all in one step.

In all cases the `.magicext` file is revealed in Finder and a pre-filled GitHub issue form
opens in your browser. Drag the file into the form and click Submit.

### For maintainers

1. Download the submitted `.magicext` and put it in `web/packages/`.
2. Optionally add presentation data (tags, preview image, featured slot) for its slug to
   [`web/registry_curation.json`](web/registry_curation.json).
3. Validate and regenerate:
   ```bash
   python3 scripts/verify_packages.py
   python3 scripts/build_registry.py
   ```
4. Commit both the package and the regenerated `web/community_registry.json`, then push to
   `main`. GitHub Actions re-verifies and deploys the gallery.

### How the registry is built

`web/community_registry.json` is **generated**. Never edit it by hand.

```
web/packages/*.magicext  ──┐
                           ├─→  scripts/build_registry.py  ─→  web/community_registry.json
web/registry_curation.json ┘
```

`scripts/build_registry.py` derives each `id` by slugifying the package name, validates every archive,
rejects duplicate IDs, and only changes `updated_at` when the content actually changes.
`python3 scripts/build_registry.py --check` verifies the committed file is current; CI runs it on
every pull request.

---

## 6. Packaging Standard (`.magicext`)

A `.magicext` file is a ZIP archive of a standard WebExtension plus a root-level `magic.json`:

```json
{
  "magic_format_version": 1,
  "id": "FBE0B00A-A8E0-4B92-B2A6-DAB05CBC8B58",
  "name": "Night Meadow New Tab",
  "author": "vatsal",
  "version": "1.0",
  "description": "A beautiful, premium 2D illustrated night ecosystem for your new tab page.",
  "prompt": "Build a beautiful, premium 2D illustrated night ecosystem that feels calm, natural, and alive on the new tab page.",
  "selected_symbol": "moon.stars.fill",
  "symbol_color_name": "blue",
  "packaged_at": "2026-09-20T12:00:00Z"
}
```

`id` here is the extension's Safari UUID. The catalog ID a user types is the slug derived from
`name`. `prompt` is the point of the format: it lets anyone remix the extension in Safari.

---

## 7. Troubleshooting

**"Extensions.db not found"** — Launch Safari at least once so it creates the database.

**"Cannot open Safari's extension database" / `OperationalError`** — macOS is blocking
access via TCC. Grant **Full Disk Access** to your terminal app:

**System Settings → Privacy & Security → Full Disk Access** → toggle ON your terminal
(Terminal.app, iTerm2, etc.), then close and reopen it.

**App shows an empty list** — same fix, but toggle ON `SafariMagicHub.app` instead.

**Safari restarts when I install something** — Safari only reloads its extension list at
launch, so installs relaunch it by default. Pass `--no-restart` to skip that.

---

## 8. Security

Packages are untrusted input, so extraction is guarded in every client:

- Archive members with absolute paths, `..` traversal, or symlinks are rejected before
  extraction (`assert_archive_is_safe` in the CLI, `validateArchiveEntries` in the app).
- Each resolved destination is re-checked against the extraction root, so a member cannot
  escape via a sibling-prefix path.
- `scripts/verify_packages.py` runs the same checks in CI on every submitted package and
  publishes the results to the job summary.

Found a security issue? Please open a private security advisory rather than a public issue.

---

## 9. Repository Layout

```
safari-magic-ext.py            The CLI + tkinter GUI (single file, stdlib only)
install-cli.sh                 Installs the CLI into ~/.local/bin
Launch Safari Magic Hub.command  Double-clickable launcher for the built app
Makefile                       Shortcuts for the commands below
app/                           SwiftUI sources + Info.plist
web/                           GitHub Pages gallery, packages, and the catalog
scripts/build_registry.py      Generates web/community_registry.json
scripts/verify_packages.py     Package validation (used locally and by CI)
scripts/generate_thumbnails.sh Renders real screenshots of each extension
scripts/build_native_app.sh    Builds the universal SafariMagicHub.app
.github/workflows/             CI, submission verification, Pages deploy
```

Maintainer tooling lives in `scripts/`. The two files at the root that look like
tooling stay there on purpose: `safari-magic-ext.py` and `install-cli.sh` are fetched
by fixed `raw.githubusercontent.com` URLs, so moving them would break the documented
install command for everyone who has already copied it.

### Common commands

```bash
make            # list available targets
make test       # everything CI runs: lint + verify + registry check
make registry   # regenerate the catalog
make app        # build SafariMagicHub.app
make serve      # preview the gallery at localhost:8000
```

Each target is a one-line wrapper, so you can always call the script directly instead.

## License

[MIT](LICENSE)

[gallery]: https://vatsal057.github.io/safari-magic-extensions/
