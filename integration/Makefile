# Shell settings
SHELL := /bin/bash

# Environment settings
ENV ?= dev

# Project settings
PROJECT_NAME := connect-extensions

# Python settings
PYTHON ?= $(shell command -v python || command -v python3)
UV ?= uv
# Read UV version from pyproject.toml with more portable command
UV_VERSION ?= $(shell grep 'required-version' pyproject.toml 2>/dev/null | sed -E 's/.*required-version = "([^"]+)".*/\1/' || echo "0.6.14")
# uv defaults virtual environment to `$VIRTUAL_ENV` if set; otherwise .venv
VIRTUAL_ENV ?= .venv
UV_LOCK := uv.lock

EXTENSION_NAME ?=
# pytest settings
PYTEST_ARGS ?= "-s"

define GET_PORT
$(UV) run -- python -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()'
endef

.DEFAULT_GOAL := latest


.PHONY: \
	$(CONNECT_VERSIONS) \
	all \
	clean \
	debug-env \
	dev \
	ensure-lockfile \
	ensure-uv \
	help \
	latest \
	package-extension \
	print-versions \
	test-%


# All versions starting with the first Connect version that fully supports extensions and version matching
CONNECT_VERSIONS := \
	release \
	2025.11.0 \
	2025.07.0 \
	2025.06.0 \
	2025.05.0 \
	2025.04.0


LATEST_VERSION := $(firstword $(filter-out release,$(CONNECT_VERSIONS)))


# Ensure uv.lock file exists and dev dependencies are installed, beware circular references since it calls `dev`
$(UV_LOCK): dev
	$(UV) lock


# Install dependencies for Connect integration tests
dev: ensure-uv
	$(UV) pip install --upgrade -e .


# Ensure uv.lock file exists
ensure-lockfile:
	@if [ ! -f "$(UV_LOCK)" ]; then \
		echo "Lock file not found, creating it..."; \
		$(UV) lock; \
	fi


# Create virtualenv for Connect integration tests
$(VIRTUAL_ENV):
	@echo "Creating virtualenv at $(VIRTUAL_ENV)"
	$(UV) venv $(VIRTUAL_ENV)


# Output environment debug information
debug-env:
	@echo "=== ENVIRONMENT DEBUG INFO ==="; \
	echo "Current directory: $$(pwd)"; \
	echo "Python executable: $$(which python)"; \
	echo "Python version: $$(python --version)"; \
	echo "UV executable: $$(which uv)"; \
	echo "UV version: $$(uv --version 2>&1)"; \
	echo "VIRTUAL_ENV: $(VIRTUAL_ENV)"; \
	echo "Does .venv exist? $$(test -d $(VIRTUAL_ENV) && echo 'YES' || echo 'NO')"; \
	echo "UV_LOCK: $(UV_LOCK)"; \
	echo "Does uv.lock exist? $$(test -f $(UV_LOCK) && echo 'YES' || echo 'NO')"; \
	echo "================================"


# Ensure UV and virtualenv are available for Connect integration tests
ensure-uv:
	@if ! command -v $(UV) >/dev/null; then \
		$(PYTHON) -m ensurepip && $(PYTHON) -m pip install "uv == $(UV_VERSION)"; \
	fi
		
	@echo "Creating virtual environment without redirection..."
	@$(MAKE) $(VIRTUAL_ENV)
	
	@echo "=== Checking venv Python interpreter ==="
	@if [ -f "$(VIRTUAL_ENV)/bin/python3" ]; then \
		echo "Python3 interpreter exists at $(VIRTUAL_ENV)/bin/python3"; \
		ls -la $(VIRTUAL_ENV)/bin/python3; \
	else \
		echo "ERROR: Python3 interpreter NOT found at $(VIRTUAL_ENV)/bin/python3"; \
		echo "Creating it manually"; \
		mkdir -p $(VIRTUAL_ENV)/bin; \
		ln -sf $$(which python) $(VIRTUAL_ENV)/bin/python3; \
		chmod +x $(VIRTUAL_ENV)/bin/*; \
		ls -la $(VIRTUAL_ENV)/bin/python3; \
	fi
		
	echo "Installing UV in virtualenv"; \
	$(UV) pip install "uv == $(UV_VERSION)" --quiet; \


clean:
	rm -rf logs reports
	find . -type d -empty -delete


# Run test suite for a specific Connect version.
$(CONNECT_VERSIONS): %:
	@if [ -z "$(EXTENSION_NAME)" ]; then \
			echo "Error: EXTENSION_NAME is required. Usage: make <version> EXTENSION_NAME=<name>"; \
			exit 1; \
	fi
	PORT=$$($(GET_PORT)); \
	$(UV) run --with https://github.com/posit-dev/with-connect.git \
			with-connect --version $* --port $$PORT \
			-- $(MAKE) test-$* EXTENSION_NAME=$(EXTENSION_NAME)


# Run test suite against all Connect versions.
all:
	@if [ -z "$(EXTENSION_NAME)" ]; then \
			echo "Error: EXTENSION_NAME is required."; \
			echo "Usage: make all EXTENSION_NAME=<name>"; \
			exit 1; \
	fi
	@$(MAKE) $(CONNECT_VERSIONS) EXTENSION_NAME=$(EXTENSION_NAME)


# Run test suite against latest official Connect release version.
latest:
	@if [ -z "$(EXTENSION_NAME)" ]; then \
		echo "Error: EXTENSION_NAME is required."; \
		echo "Usage: make latest EXTENSION_NAME=<name>"; \
		exit 1; \
	fi
	@echo "Running tests with latest version: $(LATEST_VERSION)"
	$(MAKE) $(LATEST_VERSION) EXTENSION_NAME=$(EXTENSION_NAME)


# Show available versions
print-versions:
	@printf "%s\n" $(strip $(CONNECT_VERSIONS))


# Package an extension into a tar.gz file and save it to the integrations bundles folder. This only works for simple extensions.
# Usage: make package-extension EXTENSION_NAME=<extension-name>
package-extension:
	@if [ -z "$(EXTENSION_NAME)" ]; then \
			echo "Error: EXTENSION_NAME is required."; \
			echo "Usage: make package-extension EXTENSION_NAME=<extension-name>"; \
			exit 1; \
	fi
	@if [ ! -d "../extensions/$(EXTENSION_NAME)" ]; then \
			echo "Error: Extension directory 'extensions/$(EXTENSION_NAME)' does not exist."; \
			echo "Available extensions:"; \
			ls -1 ../extensions/; \
			exit 1; \
	fi
	@mkdir -p ./bundles
	@echo "Packaging extension: $(EXTENSION_NAME)"
	@# Change directory to the parent and create tarball with relative paths
	@pushd .. > /dev/null && tar -czf ./integration/bundles/$(EXTENSION_NAME).tar.gz -C ./extensions $(EXTENSION_NAME) && popd > /dev/null
	@echo "✅ Package created: ./bundles/$(EXTENSION_NAME).tar.gz"

# Show help message.
help:
	@echo "Makefile Targets:"
	@echo "  all              Run test suite for all Connect versions (requires EXTENSION_NAME)."
	@echo "  latest           Run test suite for latest Connect version (requires EXTENSION_NAME)."
	@echo "  <version>        Run test suite for specific Connect version (requires EXTENSION_NAME)."
	@echo "  clean            Clean up the project directory."
	@echo "  print-versions   Show the available Connect versions."
	@echo "  package-extension Package an extension into a tar.gz file."
	@echo "  dev              Install dependencies for development"
	@echo "  debug-env        Output environment debug information"
	@echo "  help             Show this help message."
	@echo
	@echo "Required Parameters:"
	@echo "  EXTENSION_NAME   Name of the extension directory (e.g., publisher-command-center)"
	@echo
	@echo "Common Usage:"
	@echo "  make <target> EXTENSION_NAME=<name>"
	@echo
	@echo "Examples:"
	@echo "  # Run tests for specific version:"
	@echo "  make -C ./integration 2025.03.0 \\"
	@echo "    EXTENSION_NAME=champion-dashboard"
	@echo
	@echo "  # Run tests for latest version:"
	@echo "  make -C ./integration latest \\"
	@echo "    EXTENSION_NAME=champion-dashboard
	@echo
	@echo "  # Start only Connect service in detached mode:"
	@echo "  make -C ./integration up-connect-only CONNECT_VERSION=2025.04.0"
	@echo
	@echo "  EXTENSION_NAME           Name of the extension to test. Required."
	@echo "  PYTEST_ARGS              Arguments to pass to pytest. Default: \"-s\""


# Run test suite for a specific version (called by with-connect)
test-%:
	@mkdir -p logs reports
	@echo "Testing against Connect version: $*"
	$(UV) run pytest tests/ $(PYTEST_ARGS) \
			--junit-xml=./reports/$*.xml | tee ./logs/$*.log