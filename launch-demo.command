#!/bin/zsh
set -eu
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print 'Create a Python 3.10+ environment first; see docs/demo.md.'
  exit 1
fi
exec .venv/bin/python scripts/run_demo.py
