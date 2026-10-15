"""Builds small statement PDFs for the tests, so each case states exactly what is on the page."""
from __future__ import annotations

from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
CORPUS = HERE.parent / "corpus"


def fmt(v: float, style: str = "plain") -> str:
    s = f"{abs(v):,.2f}"
    if style == "trailing":
        return s + ("-" if v < 0 else "")
    if style == "paren":
        return f"({s})" if v < 0 else s
    if style == "crdr":
        return s + (" DR" if v < 0 else " CR")
    return ("-" if v < 0 else "") + s


def make_statement(path: Path, rows, *, opening: float, closing: float | None = None,
                   header=("Date", "Description", "Withdrawals", "Deposits", "Balance"),
                   period="01/01/2026 - 01/31/2026", split_columns=True, style="plain",
                   balances: list[float] | None = None, extra_lines=(), rows_per_page=40,
                   desc_below: dict[int, str] | None = None) -> Path:
    """rows: (date text, description, signed amount). Balances run from opening unless given."""
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 9)
    bal = opening
    computed = []
    for _, _, amt in rows:
        bal = round(bal + amt, 2)
        computed.append(bal)
    balances = balances or computed
    closing = computed[-1] if closing is None else closing

    def page_top(first: bool):
        y = 740
        if first:
            c.drawString(50, y, "Test Savings Bank"); y -= 14
            c.drawString(50, y, f"Statement period {period}"); y -= 14
            c.drawString(50, y, f"Opening balance {fmt(opening)}"); y -= 14
            c.drawString(50, y, f"Closing balance {fmt(closing)}"); y -= 14
            for line in extra_lines:
                c.drawString(50, y, line); y -= 14
            y -= 10
        xs = (50, 110, 330, 420, 510) if split_columns else (50, 110, 420, 510)
        for x, h in zip(xs, header):
            (c.drawString if x < 300 else c.drawRightString)(x if x < 300 else x + 40, y, h)
        return y - 16

    y = page_top(True)
    for k, ((d, desc, amt), b) in enumerate(zip(rows, balances)):
        if k and k % rows_per_page == 0:
            c.showPage(); c.setFont("Helvetica", 9); y = page_top(False)
        c.drawString(50, y, d)
        c.drawString(110, y, desc)
        if split_columns:
            x = 370 if amt < 0 else 460
            c.drawRightString(x, y, fmt(abs(amt), style) if style == "plain" else fmt(abs(amt)))
        else:
            c.drawRightString(460, y, fmt(amt, style))
        c.drawRightString(550, y, fmt(b))
        y -= 13
        if desc_below and k in desc_below:
            c.drawString(110, y, desc_below[k]); y -= 13
    c.save()
    return path


ROWS = [
    ("01/02", "PAYROLL ACME CO", 2500.00),
    ("01/03", "RENT JANUARY", -1200.00),
    ("01/05", "GROCERY STORE 1182", -86.42),
    ("01/09", "POWER COMPANY", -112.30),
    ("01/14", "ATM WITHDRAWAL", -200.00),
    ("01/16", "PAYROLL ACME CO", 2500.00),
    ("01/21", "TRANSIT CARD", -45.00),
    ("01/28", "TRANSFER TO SAVINGS", -500.00),
]


@pytest.fixture
def tmp(tmp_path):
    return tmp_path
