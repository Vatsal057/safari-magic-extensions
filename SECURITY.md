# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Use GitHub's private reporting instead: go to the repository's **Security** tab →
**Report a vulnerability**. Include what you found, how to reproduce it, and what an attacker
could achieve.

## Scope

This project installs third-party code into Safari, so the areas below matter most:

- **Package extraction.** `.magicext` files are untrusted ZIP archives. Members with absolute
  paths, `..` traversal, or symlinks are rejected before extraction, in both
  `safari-magic-ext.py` (`assert_archive_is_safe`) and the native app
  (`PackageManager.validateArchiveEntries`). A bypass of either is a vulnerability.
- **Writes into Safari's container.** Installation copies files into
  `~/Library/Containers/com.apple.Safari/...` and writes to Safari's SQLite database. Any way
  to write outside the intended extension directory is a vulnerability.
- **The catalog.** `community_registry.json` is fetched over HTTPS. Report anything that lets a
  registry entry cause a download or write to an unintended location.
- **`install-cli.sh`.** It downloads and installs an executable. Report anything that lets
  unverified content be installed.

## Out of scope

- The behaviour of a submitted extension's own page content once installed. Extensions are
  reviewed on submission, but they are third-party code and run with normal WebExtension
  privileges.
- The need for Full Disk Access. That is a macOS TCC requirement for reading Safari's
  container, not a flaw in this project.

## Submitted packages

Every package added to `web/packages/` is checked in CI by `scripts/verify_packages.py`. If you
find a package in the catalog that contains malicious or obfuscated code, report it privately
and it will be removed.
