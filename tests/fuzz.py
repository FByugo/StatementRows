"""Random statements: column layout, date style, sign style, currency sign, font size and page size
vary; the amounts and balances are known. python tests/fuzz.py SEED N [OUTDIR]"""
import random, sys, datetime as dt
from decimal import Decimal
from pathlib import Path
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from statementrows.core import read_statement

WORDS = "PAYROLL RENT GROCERY STORE COFFEE SHOP ONLINE TRANSFER ATM WITHDRAWAL PHARMACY GAS STATION UTILITY BILL INSURANCE PREMIUM REFUND AMAZON MARKETPLACE TAXI RIDE GYM MEMBERSHIP".split()
MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def fmt_amt(v, style, cur):
    s = f"{abs(v):,.2f}"
    s = (cur + s) if cur else s
    if v >= 0: return s
    return {"minus": "-" + s, "trail": s + "-", "paren": f"({s})"}[style]

def fmt_date(d, style, year_in_rows):
    if style == "mdy": return d.strftime("%m/%d") + (d.strftime("/%Y") if year_in_rows else "")
    if style == "dmy": return d.strftime("%d/%m") + (d.strftime("/%Y") if year_in_rows else "")
    if style == "iso": return d.isoformat()
    return f"{MON[d.month-1]} {d.day:02d}" + (f", {d.year}" if year_in_rows else "")

def build(path, rng):
    year = rng.choice([2024, 2025, 2026]); month = rng.randint(1, 12)
    start = dt.date(year, month, 1); end = (start + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
    n = rng.randint(3, 60)
    days = sorted(rng.randint(0, (end - start).days) for _ in range(n))
    opening = round(rng.uniform(100, 20000), 2)
    rows, bal = [], opening
    for d in days:
        v = round(rng.choice([1, -1, -1, -1]) * rng.uniform(0.5, 4000) * rng.choice([1, 1, 0.01, 10]), 2)
        if v == 0: v = -1.23
        bal = round(bal + v, 2)
        desc = " ".join(rng.choice(WORDS) for _ in range(rng.randint(1, 4)))
        rows.append((start + dt.timedelta(days=d), desc, v, bal))
    dstyle = rng.choice(["mdy", "dmy", "iso", "mon"])
    year_in_rows = rng.random() < 0.5
    split = rng.random() < 0.5
    sstyle = rng.choice(["minus", "trail", "paren"])
    cur = rng.choice(["", "", "$"])
    size = rng.choice([letter, A4])
    font = rng.choice([7, 8, 9, 10])
    c = canvas.Canvas(str(path), pagesize=size); c.setFont("Helvetica", font)
    W = size[0]
    def per(d): return fmt_date(d, "mdy" if dstyle == "mon" else dstyle, True) if dstyle != "mon" else f"{MON[d.month-1]} {d.day}, {d.year}"
    y = size[1] - 60
    c.drawString(40, y, f"Statement period {per(start)} - {per(end)}"); y -= 14
    c.drawString(40, y, "Opening balance"); c.drawRightString(300, y, fmt_amt(opening, "minus", cur)); y -= 14
    c.drawString(40, y, "Closing balance"); c.drawRightString(300, y, fmt_amt(bal, "minus", cur)); y -= 24
    xs = {"date": 40, "desc": 110}
    if split:
        cols = [("Withdrawals", W - 230), ("Deposits", W - 140), ("Balance", W - 45)]
    else:
        cols = [("Amount", W - 140), ("Balance", W - 45)]
    def header():
        nonlocal y
        c.drawString(xs["date"], y, "Date"); c.drawString(xs["desc"], y, "Description")
        for name, x in cols: c.drawRightString(x, y, name)
        y -= font + 6
    header()
    for d, desc, v, b in rows:
        if y < 60:
            c.showPage(); c.setFont("Helvetica", font); y = size[1] - 60; header()
        c.drawString(xs["date"], y, fmt_date(d, "mdy" if dstyle == "mon" else dstyle, year_in_rows) if dstyle != "mon" else fmt_date(d, "mon", year_in_rows))
        c.drawString(xs["desc"], y, desc)
        if split:
            c.drawRightString(cols[0][1] if v < 0 else cols[1][1], y, fmt_amt(abs(v), sstyle, cur))
        else:
            c.drawRightString(cols[0][1], y, fmt_amt(v, sstyle, cur))
        c.drawRightString(cols[-1][1], y, fmt_amt(b, "minus", cur))
        y -= font + 5
    c.save()
    return rows, dict(dstyle=dstyle, year_in_rows=year_in_rows, split=split, sstyle=sstyle, cur=cur, font=font, n=n)

if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("fuzz-out")
    out.mkdir(exist_ok=True)
    fails = 0
    for i in range(N):
        rng = random.Random(seed * 100000 + i)
        p = out / f"f{seed}_{i}.pdf"
        rows, cfg = build(p, rng)
        try:
            r = read_statement(str(p))
        except Exception as e:
            fails += 1; print("CRASH", i, cfg, type(e).__name__, e); continue
        got = [(t.date, t.amount) for t in r.txns]
        want = [(d, Decimal(f"{v:.2f}")) for d, _, v, _ in rows]
        if r.status != "ok" or got != want:
            fails += 1
            bad = next((k for k, (g, w) in enumerate(zip(got, want)) if g != w), None)
            print("FAIL", i, cfg, r.status, len(got), len(want), "first diff", bad, got[bad] if bad is not None and bad < len(got) else None, want[bad] if bad is not None else None, r.problems[:2])
        else:
            p.unlink()
    print(f"seed {seed}: {N - fails}/{N} exact")
