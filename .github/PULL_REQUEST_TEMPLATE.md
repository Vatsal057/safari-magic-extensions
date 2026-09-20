## 🪄 Extension Submission Pull Request

Thank you for contributing to the Safari Magic Extensions Community Hub!

### Extension Details

- **Extension Name:**
- **Author:**
- **SF Symbol & Tint:**
- **Package added to `web/packages/`:** `web/packages/<Name>.magicext`
- **Registry ID** (the slug `scripts/build_registry.py` prints, e.g. `night-meadow-new-tab`):

### Original AI Prompt
```text
<Paste the exact prompt used to generate this extension in Safari>
```

### Description
<1-2 sentence description>

### Submission Checklist
- [ ] Added the `.magicext` package to the `web/packages/` directory.
- [ ] Ran `python3 scripts/verify_packages.py` and it passed.
- [ ] Ran `python3 scripts/build_registry.py` and committed the updated `web/community_registry.json`.
- [ ] Tested installation with `python3 safari-magic-ext.py install web/packages/<Name>.magicext`.
- [ ] Verified `manifest.json` and `magic.json` are present and valid.
- [ ] Verified no malicious scripts or external tracking dependencies are present.

<!--
Optional: to control how the extension appears in the gallery (tags, preview
image, featured slot), add an entry for your registry ID to
web/registry_curation.json and re-run scripts/build_registry.py.
-->
