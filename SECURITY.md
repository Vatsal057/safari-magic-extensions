# Security Policy

## Reporting a Vulnerability

Submit vulnerability reports through GitHub's private vulnerability reporting interface:

1. Open the repository's **Security** tab.
2. Select **Report a vulnerability**.
3. Include reproduction steps, environment details, and the potential security impact.

Do not report security vulnerabilities in public issues or discussions.

## Scope

The primary security boundaries include:

- **Package extraction:** `.magicext` files are treated as untrusted archives. Archive members with absolute paths, directory traversal sequences (`..`), or symbolic links are rejected prior to extraction in `safari-magic-ext.py` (`assert_archive_is_safe`). Any extraction bypass represents a vulnerability.
- **Safari container writes:** Installation extracts files into `~/Library/Containers/com.apple.Safari/Data/Library/Safari/MagicExtensions` and updates Safari's SQLite database. Any mechanism that writes outside this designated path constitutes a vulnerability.
- **Catalog updates:** `web/community_registry.json` is delivered over HTTPS. Any flaw allowing arbitrary remote command execution or unintended path resolution is considered in scope.
- **Bootstrap installer:** `install-cli.sh` downloads and verifies `safari-magic-ext.py`. Flaws allowing unverified script execution are in scope.

## Out of Scope

- Client-side behaviour of individual WebExtensions running within Safari's standard extension sandbox.
- System-level Full Disk Access prompt requirements enforced by macOS Transparency, Consent, and Control (TCC).

## Verified Packages

All community extensions in `web/packages/` undergo validation by `scripts/verify_packages.py` in CI. If you identify a package violating these policies, report it privately for removal.
