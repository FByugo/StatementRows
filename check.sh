#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/pip install -q -e ".[test]"; } || exit 2
.venv/bin/python -m pytest -q tests || exit 1
# the README states how many tests there are; a number typed from memory has been wrong three times
n=$(.venv/bin/python -m pytest -q --collect-only tests 2>/dev/null | grep -cE "::")
said=$(grep -oE "runs [0-9]+ tests" README.md | grep -oE "[0-9]+")
[ "$n" = "$said" ] || { echo "README says $said tests, there are $n"; exit 1; }
echo "check: all green ($n tests)"
