"""Windows entry point: drop statement PDFs, or a folder of them, onto the program.

The results go into a folder called 'excel' next to the first thing dropped. Started with nothing
dropped on it, it converts every PDF in the folder the program sits in."""
from __future__ import annotations

import sys
from pathlib import Path

from .core import read_statement
from .output import write_all


def collect(args: list[str]) -> list[Path]:
    files: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            files += sorted(x for x in p.iterdir() if x.suffix.lower() == ".pdf")
        elif p.suffix.lower() == ".pdf":
            files.append(p)
    return files


def main() -> int:
    args = sys.argv[1:]
    if not args:
        here = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
        args = [str(here)]
    files = collect(args)
    if not files:
        print("No PDF files found. Drop statement PDFs, or a folder of them, onto this program.")
        input("\nPress Enter to close.")
        return 2
    out = files[0].parent / "excel"
    good = 0
    for f in files:
        try:
            res = read_statement(str(f))
            write_all(res, out, f.stem)
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the rest
            print(f"!! {f.name}: could not be read ({type(e).__name__})")
            continue
        ok = res.status == "ok"
        good += ok
        print(f"{'ok' if ok else '!!'} {f.name}: {res.status}, {len(res.txns)} rows")
        for p in res.problems:
            print(f"     - {p}")
    print(f"\n{good} of {len(files)} statement(s) balanced. The Excel files are in:\n{out}")
    input("\nPress Enter to close.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
