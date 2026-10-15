#!/usr/bin/env bash
# Builds dist/StatementRows.exe with the Windows Python on this machine (run from WSL).
# The build happens in C:\Temp\sr_build so the vault does not fill with build files.
set -u
B=/mnt/c/Temp/sr_build
mkdir -p "$B"
[ -x "$B/venv/Scripts/python.exe" ] || cmd.exe /c "py -3.12 -m venv C:\Temp\sr_build\venv && C:\Temp\sr_build\venv\Scripts\python -m pip install -q pdfplumber openpyxl typer pyinstaller" || exit 2
rm -rf "$B/src" && mkdir -p "$B/src" && cp -r "$(dirname "$0")/statementrows" "$B/src/" && rm -rf "$B/src/statementrows/__pycache__"
printf 'import sys\nfrom statementrows.dragdrop import main\nsys.exit(main())\n' > "$B/src/entry.py"
(cd "$B" && cmd.exe /c "cd /d C:\Temp\sr_build && venv\Scripts\pyinstaller --onefile --console --name StatementRows --paths src --distpath dist --workpath work --specpath work src\entry.py --noconfirm --log-level WARN") || exit 1
mkdir -p "$(dirname "$0")/dist" && cp "$B/dist/StatementRows.exe" "$(dirname "$0")/dist/"
ls -la "$(dirname "$0")/dist/StatementRows.exe"
