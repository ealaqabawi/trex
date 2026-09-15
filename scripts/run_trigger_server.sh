#!/bin/sh
# Launcher for the n8n trigger server.
#
# launchd cannot exec .venv/bin/python3 directly: that's a python.org
# framework stub that re-execs itself via Python.app, which launchd refuses
# with EX_CONFIG (78) and no stderr. Going through /bin/sh sidesteps that.

set -e
# Resolve the project root from this script's own location so the repo
# carries no machine-specific absolute path.
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_ROOT"
exec .venv/bin/python3 -u -m service.trigger_server
