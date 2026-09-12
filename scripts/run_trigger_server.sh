#!/bin/sh
# Launcher for the n8n trigger server.
#
# launchd cannot exec .venv/bin/python3 directly: that's a python.org
# framework stub that re-execs itself via Python.app, which launchd refuses
# with EX_CONFIG (78) and no stderr. Going through /bin/sh sidesteps that.

set -e
cd /Users/emadalaqabawi/trex
exec .venv/bin/python3 -u -m service.trigger_server
