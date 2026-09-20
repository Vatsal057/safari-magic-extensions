# Safari Magic Extensions Community Hub
#
# Convenience entry points. Every target is just a thin wrapper around a script,
# so you can always run the underlying command directly instead.

.DEFAULT_GOAL := help
.PHONY: help registry check verify thumbnails serve lint test clean

PYTHON ?= python3

help: ## Show this help
	@echo "Safari Magic Extensions Community Hub"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-10s\033[0m %s\n", $$1, $$2}'
	@echo ""

registry: ## Regenerate web/community_registry.json from web/packages/
	$(PYTHON) scripts/build_registry.py

check: ## Verify the committed registry matches the packages (no writes)
	$(PYTHON) scripts/build_registry.py --check

verify: ## Validate every .magicext package (security + metadata)
	$(PYTHON) scripts/verify_packages.py

thumbnails: ## Render real screenshots of each extension into web/assets/thumbnails/
	./scripts/generate_thumbnails.sh
	$(PYTHON) scripts/build_registry.py

serve: ## Serve the web gallery at http://localhost:8000
	$(PYTHON) -m http.server 8000 --directory web

lint: ## Byte-compile Python and shellcheck the shell scripts
	$(PYTHON) -m compileall -q safari-magic-ext.py scripts/
	@command -v shellcheck >/dev/null 2>&1 \
		&& shellcheck --severity=warning \
			install-cli.sh \
			scripts/generate_thumbnails.sh \
		|| echo "shellcheck not installed; skipping (brew install shellcheck)"

# What CI runs. Run this before opening a pull request.
test: lint verify check ## Run all checks (lint + verify + registry check)
	$(PYTHON) safari-magic-ext.py --version
	@echo ""
	@echo "✓ All checks passed"

clean: ## Remove build output and caches
	rm -rf build dist
	find . -name '__pycache__' -type d -not -path './.git/*' -prune -exec rm -rf {} +
	find . -name '.DS_Store' -not -path './.git/*' -delete
