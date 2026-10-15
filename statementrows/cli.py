"""statementrows: bank and card statement PDFs to Excel, checked against the statement's own balances."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import typer

from .core import read_statement
from .output import summary, write_all, write_combined

app = typer.Typer(add_completion=False, help=__doc__)


@app.command()
def main(
    src: Path = typer.Argument(..., help="a statement PDF, or a folder of them"),
    out: Path = typer.Option(Path("out"), "--out", "-o", help="folder for the results"),
    strict: bool = typer.Option(False, help="exit 1 unless every statement balanced"),
    ocr: bool = typer.Option(False, help="read scanned pages with OCR (experimental, slow; needs rapidocr-onnxruntime)"),
) -> None:
    files = sorted(p for p in src.iterdir() if p.suffix.lower() == ".pdf") if src.is_dir() else [src]
    if not files:
        typer.echo(f"no PDFs in {src}", err=True)
        raise typer.Exit(2)
    out.mkdir(parents=True, exist_ok=True)
    report, results = [], []
    for f in files:
        res = read_statement(str(f), use_ocr=ocr)
        results.append(res)
        write_all(res, out, f.stem)
        sm = summary(res)
        report.append(sm)
        mark = "ok " if res.status == "ok" else "!! "
        typer.echo(f"{mark}{f.name}: {res.status}, {len(res.txns)} rows")
        for c in res.checks:
            typer.echo(f"     + {c}")
        for p in res.problems:
            typer.echo(f"     - {p}")
    with open(out / "summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "status", "rows", "opening", "closing", "money_in", "money_out", "period", "problems"])
        for sm in report:
            w.writerow([sm["file"], sm["status"], sm["rows"], sm["opening"], sm["closing"],
                        sm["money_in"], sm["money_out"], sm["period"], " | ".join(sm["problems"])])
    if len(results) > 1:
        write_combined(results, out / "all statements.xlsx")
    good = sum(1 for sm in report if sm["status"] == "ok")
    typer.echo(f"\n{good} of {len(report)} statement(s) balanced. Results in {out}/")
    if strict and good != len(report):
        raise typer.Exit(1)


if __name__ == "__main__":
    sys.exit(app())
