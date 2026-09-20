# Safari Magic Extensions Community Hub 🪄

A community sharing & distribution platform for Apple Safari's AI-generated **Magic Extensions**.

Includes:
- **CLI & Native Mac GUI**: Single-file `.magicext` packaging, sideloading, and 1-click installation.
- **Web Showcase**: High-aesthetic web gallery hosted directly on GitHub Pages (`docs/`).
- **GitHub Review System**: Submit extensions via GitHub Issue Forms or Pull Requests; approve and publish with 1 click.

---

## Architecture Overview

```
[ Developer / Creator ]                [ GitHub Platform ]                     [ User / Consumer ]
                               ┌────────────────────────────────┐
1. Generate in Safari          │ 1. GitHub Issue Form / PR      │      1. Browse Web Gallery (docs/)
2. Run:                        │    (auto-verified by Actions)  │         or run: safari-magic-ext explore
   safari-magic-ext submit     │ 2. Admin Reviews & Merges      │      2. 1-Click Install:
                               │ 3. Action rebuilds registry &  │         safari-magic-ext install <id>
                               │    deploys to GitHub Pages     │
                               └────────────────────────────────┘
```

---

## 1. Web Gallery (GitHub Pages)

The static web gallery lives in [docs/](docs/):
- **Live Search & Tags**: Filter by name, prompt keywords, creator, or category (`#newtab`, `#ambient`, `#productivity`).
- **Prompt Copy**: 1-click copy of the exact natural language AI prompt so users can remix it inside Safari.
- **Direct Package Download**: Instant download of `.magicext` bundles.
- **Terminal Syntax**: Quick-copy CLI commands (`safari-magic-ext install <id>`).

To view locally:
```bash
python3 -m http.server 8000 --directory docs
# Open http://localhost:8000
```

To deploy to GitHub:
1. Push this repository to GitHub.
2. In your repo settings: **Settings > Pages > Build and deployment > Source: GitHub Actions** (or Deploy from branch `/docs`).

---

## 2. Submitting & Handling Extensions

### For Creators: Submit in 1 Step
```bash
python3 safari-magic-ext.py submit "Nightlife in the Wild"
```
This command automatically:
1. Packages the extension into a `.magicext` bundle with AI prompt metadata.
2. Reveals the `.magicext` file in macOS Finder.
3. Opens the pre-filled GitHub Issue submission form in your browser.
4. Simply drag the revealed `.magicext` file into the form and click **Submit new issue**!

### For Maintainers: Review & Approval Workflow
When a community member submits an issue:
1. Download their attached `.magicext` file and place it in the `packages/` directory.
2. Run `python3 build_registry.py` (or let the GitHub Action do it automatically on PR merge).
3. Commit and push to `main`.
4. GitHub Actions verifies the archive security (preventing zip-slip attacks) and deploys the updated gallery to GitHub Pages instantly!

---

## 3. CLI Quick Reference

```bash
# Explore community extensions
python3 safari-magic-ext.py explore
python3 safari-magic-ext.py explore "pomodoro"

# Install from community ID
python3 safari-magic-ext.py install nightlife-wild

# Install from local package or direct URL
python3 safari-magic-ext.py install ~/Downloads/MyExtension.magicext
python3 safari-magic-ext.py install https://example.com/package.magicext

# Package an installed extension
python3 safari-magic-ext.py pack "Night Meadow New Tab" --author "vatsal"

# Submit directly to GitHub
python3 safari-magic-ext.py submit "Night Meadow New Tab"

# Open the Native Dual-Tab GUI
python3 safari-magic-ext.py
```

---

## 4. Packaging Standard (`.magicext`)

A `.magicext` file is a ZIP archive containing standard WebExtension assets plus `magic.json`:
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

---

## 5. Security Guardrails

All package extractions in `safari-magic-ext.py` and GitHub Actions enforce strict Zip-Slip path sanitization, preventing directory traversal or path breakout into the host filesystem.
