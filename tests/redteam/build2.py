"""Variants used to attack the first-round findings (step 5 of the brief)."""
from build import draw, money, OUT, _plain_rows
from reportlab.lib.pagesizes import letter


def sectioned(name, dep, wd, opening, head_lines=(), foot_lines=(), period_line=None):
    d, w = sum(a for *_, a in dep), sum(a for *_, a in wd)
    closing = round(opening + d - w, 2)
    rows = [(13, [(40, t, "l")]) for t in head_lines]
    if period_line:
        rows.append((13, [(40, period_line, "l")]))
    rows += [(13, [(40, "Beginning balance on April 1, 2026", "l"), (400, f"${money(opening)}", "r")]),
             (13, [(40, "Deposits and other additions", "l"), (400, money(d), "r")]),
             (13, [(40, "Withdrawals and other subtractions", "l"), (400, f"-{money(w)}", "r")]),
             (13, [(40, "Ending balance on April 30, 2026", "l"), (400, f"${money(closing)}", "r")]),
             (24, []),
             (14, [(40, "Deposits and other additions", "l")]),
             (14, [(40, "Date", "l"), (110, "Description", "l"), (540, "Amount", "r")])]
    for dt, ds, a in dep:
        rows.append((13, [(40, dt, "l"), (110, ds, "l"), (540, money(a), "r")]))
    rows.append((22, [(40, "Total deposits and other additions", "l"), (540, f"${money(d)}", "r")]))
    rows.append((14, [(40, "Withdrawals and other subtractions", "l")]))
    rows.append((14, [(40, "Date", "l"), (110, "Description", "l"), (540, "Amount", "r")]))
    for dt, ds, a in wd:
        rows.append((13, [(40, dt, "l"), (110, ds, "l"), (540, f"-{money(a)}", "r")]))
    rows.append((22, [(40, "Total withdrawals and other subtractions", "l"), (540, f"-${money(w)}", "r")]))
    rows.append((30, []))
    for t in foot_lines:
        rows.append((11, [(40, t, "l")]))
    return draw(OUT / name, [rows])


DEP_N = [("04/02/26", "PAYROLL ACME CO DES:DIRECT DEP", 2500.00), ("04/16/26", "PAYROLL ACME CO DES:DIRECT DEP", 2500.00)]
WD_N = [("04/03/26", "RENT APRIL", 1200.00), ("04/05/26", "GROCERY STORE 1182", 86.42),
        ("04/12/26", "PAYMENT TO CHASE CREDIT CARD ONLINE", 300.00), ("04/21/26", "TRANSIT CARD", 45.00)]

# A3: numeric dates, 'credit card' once, nothing else. Expect: one hint only -> bank -> signs right.
sectioned("A3_numeric_dates_one_hint.pdf", DEP_N, WD_N, 1000.00)
# A4: numeric dates, no 'credit card', but a footer with 'cardholder' and 'credit limit' (overdraft line of credit ad).
WD_PLAIN = [(d, ds.replace("CHASE CREDIT CARD", "CHASE CARD"), a) for d, ds, a in WD_N]
sectioned("A4_footer_two_hints.pdf", DEP_N, WD_PLAIN, 1000.00,
          foot_lines=("Overdraft line of credit: your credit limit is shown on page 2. Cardholder agreement applies.",))

# P2: BofA style check list: Date, Check #, Bank reference, Amount, one per line.
def checks_bofa(name, chase=False):
    opening = 1000.00
    dep = [("01/02/26", "PAYROLL ACME CO", 2500.00)]
    chk = [("1001", "01/10/26", 100.00), ("1002", "01/20/26", 50.00), ("1004", "01/27/26", 25.50)]
    d, ck = sum(a for *_, a in dep), sum(a for *_, a in chk)
    closing = round(opening + d - ck, 2)
    rows = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
            (13, [(40, "Beginning balance", "l"), (400, f"${money(opening)}", "r")]),
            (13, [(40, "Ending balance", "l"), (400, f"${money(closing)}", "r")]),
            (24, []),
            (14, [(40, "Deposits and other additions", "l")]),
            (14, [(40, "Date", "l"), (110, "Description", "l"), (540, "Amount", "r")])]
    for dt, ds, a in dep:
        rows.append((13, [(40, dt, "l"), (110, ds, "l"), (540, money(a), "r")]))
    rows.append((22, [(40, "Total deposits and other additions", "l"), (540, f"${money(d)}", "r")]))
    if chase:
        rows.append((14, [(40, "CHECKS PAID", "l")]))
        rows.append((14, [(40, "CHECK NO.", "l"), (110, "DESCRIPTION", "l"), (330, "DATE PAID", "l"), (540, "AMOUNT", "r")]))
        for n, dt, a in chk:
            rows.append((13, [(40, n, "l"), (110, "^", "l"), (330, dt[:5], "l"), (540, f"${money(a)}", "r")]))
        rows.append((22, [(40, "Total Checks Paid", "l"), (540, f"${money(ck)}", "r")]))
    else:
        rows.append((14, [(40, "Checks", "l")]))
        rows.append((14, [(40, "Date", "l"), (110, "Check #", "l"), (200, "Bank reference", "l"), (540, "Amount", "r")]))
        for k, (n, dt, a) in enumerate(chk):
            rows.append((13, [(40, dt, "l"), (110, n, "l"), (200, f"90001{k}2200", "l"), (540, f"-{money(a)}", "r")]))
        rows.append((22, [(40, "Total checks", "l"), (540, f"-${money(ck)}", "r")]))
    return draw(OUT / name, [rows])

checks_bofa("P2_checks_bofa_style.pdf")
checks_bofa("P3_checks_chase_style.pdf", chase=True)

# S2: Wells Fargo two-line header, one daily balance printed WRONG by 5.00. Expect: unbalanced if the balance column is read.
def wf(name, wrong=0.0):
    opening = 1000.00
    src = [("1/2", "PAYROLL ACME CO", 2500.00), ("1/2", "COFFEE SHOP", -4.50), ("1/5", "RENT JANUARY", -1200.00),
           ("1/7", "GAS STATION", -38.10), ("1/7", "PHARMACY", -12.99)]
    bal, daily = opening, []
    for k, (d, _, a) in enumerate(src):
        bal = round(bal + a, 2)
        last = k + 1 == len(src) or src[k + 1][0] != d
        daily.append(bal if last else None)
    daily[2] = round(daily[2] + wrong, 2)
    rows = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
            (13, [(40, "Beginning balance on 1/1", "l"), (300, f"${money(opening)}", "r")]),
            (13, [(40, "Ending balance on 1/31", "l"), (300, f"${money(bal)}", "r")]),
            (20, [(40, "Transaction history", "l")]),
            (11, [(40, "Date", "l"), (100, "Description", "l"), (380, "Deposits/", "r"), (470, "Withdrawals/", "r"), (550, "Ending daily", "r")]),
            (14, [(380, "Additions", "r"), (470, "Subtractions", "r"), (550, "balance", "r")])]
    for (dt, ds, a), b in zip(src, daily):
        cells = [(40, dt, "l"), (100, ds, "l"), (380 if a > 0 else 470, money(a), "r")]
        if b is not None:
            cells.append((550, money(b), "r"))
        rows.append((13, cells))
    return draw(OUT / name, [rows])

wf("S2_two_line_header_wrong_daily_balance.pdf", wrong=5.00)

# D3: the same missing-first-row file but with the recognised phrase 'Beginning balance'. Expect: unbalanced.
def d3():
    opening = 1000.00
    src = [("01/02", "PAYROLL ACME CO", 2500.00), ("01/03", "RENT JANUARY", -1200.00),
           ("01/05", "GROCERY STORE 1182", -86.42), ("01/09", "POWER COMPANY", -112.30),
           ("01/14", "ATM WITHDRAWAL", -200.00), ("01/16", "PAYROLL ACME CO", 2500.00)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    rows = [(13, [(40, "Statement period 01/01/2026 through 01/31/2026", "l")]),
            (13, [(40, "Beginning balance", "l"), (300, money(opening), "r")]),
            (13, [(40, "Ending balance", "l"), (300, money(bals[-1]), "r")]),
            (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Withdrawals", "r"), (450, "Deposits", "r"), (550, "Balance", "r")])]
    for (dt, ds, a), b in list(zip(src, bals))[1:]:
        rows.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
    return draw(OUT / "D3_beginning_balance_row_missing.pdf", [rows])

d3()

# E2: page break inside a row, but page 2 does NOT repeat the table header.
def e2():
    opening = 1000.00
    src = [("01/02", "PAYROLL ACME CO", 2500.00), ("01/03", "RENT JANUARY", -1200.00),
           ("01/05", "GROCERY STORE 1182", -86.42), ("01/09", "POWER COMPANY", -112.30), ("01/14", "ATM WITHDRAWAL", -200.00)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    hdr = (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Withdrawals", "r"), (450, "Deposits", "r"), (550, "Balance", "r")])
    p1 = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
          (13, [(40, "Opening balance", "l"), (300, money(opening), "r")]),
          (13, [(40, "Closing balance", "l"), (300, money(bals[-1]), "r")]), hdr]
    for (dt, ds, a), b in list(zip(src, bals))[:3]:
        p1.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
    p2 = [(13, [(100, "STORE 1182 SPRINGFIELD IL", "l")])]
    for (dt, ds, a), b in list(zip(src, bals))[3:]:
        p2.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
    return draw(OUT / "E2_page_break_no_header_repeat.pdf", [p1, p2])

e2()

# C2: the future date is a plain 'Rewards expire 12/31/2027' line and the period is a 'Statement period' line.
def c2():
    rows = _plain_rows()
    rows.append((30, []))
    rows.append((11, [(40, "Your bonus rewards points expire on 12/31/2027.", "l")]))
    return draw(OUT / "C2_bank_rewards_expiry.pdf", [rows])

c2()

# T2: the repeated date is a form revision in the page footer: 'Form CK-100 Rev. 06/01/2023'.
def t2():
    opening = 1000.00
    src = [(f"01/{2 + k:02d}", f"CARD PAYMENT {k}", -(1.00 + k)) for k in range(24)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    hdr = (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Withdrawals", "r"), (450, "Deposits", "r"), (550, "Balance", "r")])
    pages = []
    for p in range(3):
        rows = [(13, [(40, "Test Savings Bank", "l")])]
        if p == 0:
            rows += [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
                     (13, [(40, "Opening balance", "l"), (300, money(opening), "r")]),
                     (13, [(40, "Closing balance", "l"), (300, money(bals[-1]), "r")])]
        rows.append(hdr)
        for (dt, ds, a), b in list(zip(src, bals))[p * 8:(p + 1) * 8]:
            rows.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
        rows.append((400, []))
        rows.append((11, [(40, f"Form CK-100 Rev. 06/01/2023   Page {p + 1} of 3", "l")]))
        pages.append(rows)
    return draw(OUT / "T2_footer_revision_date.pdf", pages)

t2()
print("built")
