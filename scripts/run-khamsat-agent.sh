#!/usr/bin/env bash
set -euo pipefail

cd "$HOME/Projects/okal"
"$HOME/Projects/okal/.venv-okal-freelance/bin/python" scripts/khamsat-control.py --tick
