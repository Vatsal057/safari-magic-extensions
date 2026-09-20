# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] - 2026-09-20

### Fixed

- **The CLI crashed on a stock Mac.** It used PEP 604 (`X | None`) annotations,
  which are evaluated at import time and need Python 3.10, but macOS ships 3.9.6
  as `/usr/bin/python3`. `safari-magic-ext install <id>` failed with
  `TypeError: unsupported operand type(s) for |` for anyone who had not separately
  installed a newer Python, while documentation stated macOS included a suitable
  version. The CLI and both maintainer scripts now run on 3.9.6.
- `install-cli.sh` executes the downloaded tool rather than only byte-compiling it.
  `py_compile` checks syntax only, which is why the above shipped unnoticed. If the
  interpreter is unsuitable, it reports the failure directly.
- `explore <id>` found nothing while `install <id>` worked, because the search did
  not cover the catalog `id`. Pasting an ID copied from the gallery now works.

### Added

- CI runs the Python suite on a 3.9 / 3.13 matrix so the stock-macOS interpreter
  cannot regress.

### Changed

- The website leads with the 1-line CLI installer and interactive web gallery.

## [1.1.0] - 2026-09-20

A repository-wide cleanup. The headline items are the catalog lookup fix (the installed
CLI previously could not reach the catalog at all) and hardened archive extraction.

### Fixed

- **The installed CLI could never load the community catalog.** The catalog path was
  resolved relative to the script file, but `install-cli.sh` copies the script to
  `~/.local/bin`, where no `web/` directory exists, and there was no default remote
  URL, only an undocumented `SAFARI_MAGIC_REGISTRY_URL` environment variable. As a
  result `explore` listed nothing and `install <id>` failed for every user who
  installed the tool as documented. The CLI now fetches the published catalog, falls
  back to a local checkout, then to a cache in `~/Library/Caches/safari-magic-ext`.
- **Catalog IDs are now readable slugs** (`night-meadow-new-tab`) instead of raw
  UUIDs, so the documented `install <id>` commands work. Lookups still accept a
  UUID, a name, or a slug.
- `pack` and `convert` now operate on a staged copy, preserving `manifest.json`
  inside your source directory.
- `convert` operates independently of Safari's database, functioning on any system.
- Ambiguous extension names (for example `night` matching three extensions) now
  report the candidates instead of silently picking the first match.
- The gallery's "nature" filter showed every extension, because the button emitted
  `data-filter="ambient"` while the script compared against `nature`.
- `install-cli.sh` now uses `curl --fail`; previously an HTTP error page could be
  written to disk and marked executable.
- The pull request template pointed at `packages/` rather than `web/packages/`, so
  submissions opened as PRs never triggered the verification workflow.
- Relative `download_url` values in the catalog are now resolved against the catalog's
  own base URL.

### Security

- Archive extraction rejects absolute paths, `..` traversal, and symlink members
  before extracting. The previous check used a string prefix comparison, which
  accepted a sibling path such as `/tmp/dest-evil` for destination `/tmp/dest`, and
  screened no symlinks.
- `scripts/verify_packages.py` runs these checks in CI for every submitted package and
  publishes the results to the workflow job summary.

### Added

- `Makefile` with `make test`, `registry`, `verify`, `serve`, and `lint`.
- `scripts/verify_packages.py`, replacing an inline heredoc in the workflow so package
  validation can be run locally.
- `web/registry_curation.json` as the input for gallery presentation data (tags,
  preview art, featured slot).
- CI workflow that byte-compiles the CLI, validates packages, checks the registry,
  and runs ShellCheck.
- `LICENSE` (MIT), `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, a bug report
  template, and this changelog.
- `safari-magic-ext --version`.
- `scripts/build_registry.py --check`, which verifies the committed catalog matches the
  packages on disk without writing.

### Changed

- Repository layout: the site moved to `web/` and maintainer tooling to `scripts/`.
  `safari-magic-ext.py` and `install-cli.sh` remain at the root because they are
  fetched by fixed URLs.
- Catalog presentation data is read from the registry instead of being re-derived in
  the browser from extension names.
- Registry generation is idempotent: `updated_at` only advances when the catalog
  content actually changes.

### Removed

- A stale 124-line duplicate of the catalog embedded in `web/app.js`, one entry of
  which pointed at the wrong package.
- Fabricated `likes` counts, which no interface displayed.

## [1.0.0] - 2026-09-19

Initial release: the `.magicext` package format, the CLI and tkinter GUI, the web
gallery, and the GitHub submission workflow.

[1.1.1]: https://github.com/Vatsal057/safari-magic-extensions/releases/tag/v1.1.1
[1.1.0]: https://github.com/Vatsal057/safari-magic-extensions/releases/tag/v1.1.0
[1.0.0]: https://github.com/Vatsal057/safari-magic-extensions/releases/tag/v1.0.0
