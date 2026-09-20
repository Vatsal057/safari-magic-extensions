# Contributing

Contributions to the Safari Magic Extensions Community Hub are welcome. You can contribute by submitting an extension or by improving the codebase.

---

## Submitting an Extension

The recommended path is the CLI submit command:

```bash
safari-magic-ext submit "My Extension Name"
```

The CLI packages the selected extension and opens a pre-filled submission issue with the archive payload.

### Submitting via Pull Request

If you prefer submitting through a Git pull request:

1. Package the extension:
   ```bash
   safari-magic-ext pack "My Extension Name" --author "your-handle"
   ```
2. Copy the `.magicext` file into `web/packages/`.
3. Validate package integrity:
   ```bash
   python3 scripts/verify_packages.py
   ```
4. Regenerate the catalog:
   ```bash
   python3 scripts/build_registry.py
   ```
5. Commit both the package file and the updated `web/community_registry.json`.

The catalog identifier is the slug printed by `scripts/build_registry.py` (for example, `night-meadow-new-tab`). Users install the extension using this slug.

### Generating Thumbnails

Thumbnails are real browser screenshots of the extension's new-tab page. Generate them with:

```bash
make thumbnails
```

This renders each package using a local Chromium-compatible browser into `web/assets/thumbnails/<slug>.png`. Commit the generated PNG with your package.

### Gallery Metadata (Optional)

`web/registry_curation.json` specifies category tags and optional image overrides. Add an entry matching your extension's slug:

```json
"my-extension-name": {
  "tags": ["ambient", "newtab"]
}
```

Allowed tags: `ambient`, `focus`, `newtab`, `tech`.

### Package Requirements

The archive root must contain:

- `manifest.json`: Valid WebExtension manifest format.
- `magic.json`: Metadata with non-empty `name` and `prompt` strings.

Archives containing absolute paths, directory traversal sequences (`..`), or symbolic links fail verification. Packages must be free of obfuscated scripts and external tracking endpoints.

---

## Modifying Code

### Repository Structure

| Path | Description |
| --- | --- |
| `safari-magic-ext.py` | CLI and GUI application. Single file using Python standard library. |
| `install-cli.sh` | Shell installer for the CLI binary. |
| `web/` | Static gallery frontend (HTML, CSS, vanilla JavaScript). |
| `scripts/build_registry.py` | Compiles `web/community_registry.json`. |
| `scripts/verify_packages.py` | Package validator run locally and in CI. |

`safari-magic-ext.py` and `install-cli.sh` remain at the root because external installation commands fetch them from fixed URLs.

### Pre-Commit Validation

Before opening a pull request, run:

```bash
make test
```

This runs the automated checks:

```bash
python3 -m compileall -q safari-magic-ext.py scripts/
shellcheck --severity=warning install-cli.sh scripts/generate_thumbnails.sh
python3 scripts/verify_packages.py
python3 scripts/build_registry.py --check
```

Run `make` to list all targets.

### Implementation Guidelines

- **Keep `safari-magic-ext.py` self-contained:** It must depend only on Python's standard library. Do not introduce imports from external packages.
- **Do not edit `web/community_registry.json` directly:** Update the package or `web/registry_curation.json`, then execute `scripts/build_registry.py`.
- **Use dynamic paths:** Derive paths using `pathlib.Path.home()` or the current working directory rather than hardcoded machine paths.
- **Security checks:** Keep path traversal and symlink guards active during archive extraction.
- **Shared schema:** Field updates in the registry require matching updates in `web/app.js` and `safari-magic-ext.py`.

### Permissions

Writing to Safari's extension database requires Full Disk Access. Testing `pack`, `convert`, `explore`, and the verification scripts runs with standard user permissions.

---

## Reporting Bugs

Open a GitHub issue with your macOS version, Safari version, command executed, and console output. For security vulnerabilities, open a private security advisory instead.
