"""Builds the attack PDFs. Each function states exactly what is on the page and what the right answer is."""
from pathlib import Path
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "pdfs"
OUT.mkdir(exist_ok=True)


def draw(path, pages, pagesize=letter, font=("Helvetica", 8.5), rotate=0):
    """pages: list of pages; a page is a list of (y_step, [(x, text, 'l'|'r')])."""
    c = canvas.Canvas(str(path), pagesize=pagesize)
    for page in pages:
        c.setFont(*font)
        if rotate:
            c.setPageRotation(rotate)
        y = pagesize[1] - 60
        for step, cells in page:
            for x, text, align in cells:
                (c.drawString if align == "l" else c.drawRightString)(x, y, text)
            y -= step
        c.showPage()
    c.save()
    return path


def money(v):
    return f"{abs(v):,.2f}"


# ---------------------------------------------------------------- A: a bank statement that mentions a credit card
def case_A_bank_sections_mentions_card():
    """BofA-style sectioned checking statement (no running balance). One description says 'credit card'
    and the footer says 'APR' once (marketing), as real statements do. Every amount is correct per section.
    Right answer: deposits +, withdrawals -, status ok."""
    dep = [("04/02/26", "PAYROLL ACME CO DES:DIRECT DEP", 2500.00), ("04/16/26", "PAYROLL ACME CO DES:DIRECT DEP", 2500.00)]
    wd = [("04/03/26", "RENT APRIL", 1200.00), ("04/05/26", "GROCERY STORE 1182", 86.42),
          ("04/12/26", "PAYMENT TO CHASE CREDIT CARD ONLINE", 300.00), ("04/21/26", "TRANSIT CARD", 45.00)]
    opening = 1000.00
    d, w = sum(a for *_, a in dep), sum(a for *_, a in wd)
    closing = round(opening + d - w, 2)
    rows = [(13, [(40, "Beginning balance on April 1, 2026", "l"), (400, f"${money(opening)}", "r")]),
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
    rows.append((11, [(40, "Looking for a new credit card? Ask about our Travel Rewards card with a 0% intro APR for 15 months.", "l")]))
    return draw(OUT / "A_bank_sections_mentions_card.pdf", [rows]), dict(dep=dep, wd=wd, opening=opening, closing=closing)


def case_A2_bank_sections_april_only():
    """Same statement, but the only card hint is the month abbreviation 'Apr' in the dates plus one
    'credit card' in a description. No marketing footer."""
    dep = [("Apr 02", "PAYROLL ACME CO DES:DIRECT DEP", 2500.00), ("Apr 16", "PAYROLL ACME CO DES:DIRECT DEP", 2500.00)]
    wd = [("Apr 03", "RENT APRIL", 1200.00), ("Apr 05", "GROCERY STORE 1182", 86.42),
          ("Apr 12", "PAYMENT TO CHASE CREDIT CARD ONLINE", 300.00), ("Apr 21", "TRANSIT CARD", 45.00)]
    opening = 1000.00
    d, w = sum(a for *_, a in dep), sum(a for *_, a in wd)
    closing = round(opening + d - w, 2)
    rows = [(13, [(40, "Statement period 04/01/2026 - 04/30/2026", "l")]),
            (13, [(40, "Beginning balance on April 1, 2026", "l"), (400, f"${money(opening)}", "r")]),
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
    return draw(OUT / "A2_bank_sections_april_only.pdf", [rows]), dict(opening=opening, closing=closing)


# ---------------------------------------------------------------- B: a card statement WITH a running balance
def case_B_card_with_running_balance():
    """A store/credit-union Visa statement that prints a running balance (amount owed). Purchases are
    printed as positive figures and raise the balance; the payment is printed negative and lowers it.
    Right answer: purchases are money out (negative), the payment is money in (positive)."""
    prev = 812.40
    txns = [("01/05", "STARBUCKS STORE 1182", 6.45), ("01/09", "AMAZON MKTPL*2X41", 89.99),
            ("01/12", "PAYMENT - THANK YOU", -500.00), ("01/20", "SHELL OIL 57444", 41.10),
            ("02/03", "LATE FEE", 29.00)]
    bal, bals = prev, []
    for *_, a in txns:
        bal = round(bal + a, 2); bals.append(bal)
    rows = [(13, [(40, "VISA PLATINUM  Account ending 4410", "l")]),
            (13, [(40, "Statement Closing Date 02/03/2026   Payment Due Date 02/28/2026", "l")]),
            (13, [(40, "Previous Balance", "l"), (300, f"${money(prev)}", "r")]),
            (13, [(40, "New Balance", "l"), (300, f"${money(bals[-1])}", "r")]),
            (13, [(40, "Minimum Payment Due", "l"), (300, "$35.00", "r")]),
            (13, [(40, "Credit Limit", "l"), (300, "$5,000.00", "r")]),
            (20, [(40, "TRANSACTIONS", "l")]),
            (13, [(40, "Date", "l"), (100, "Description", "l"), (460, "Amount", "r"), (550, "Balance", "r")])]
    for (dt, ds, a), b in zip(txns, bals):
        rows.append((13, [(40, dt, "l"), (100, ds, "l"), (460, ("-" if a < 0 else "") + money(a), "r"), (550, money(b), "r")]))
    return draw(OUT / "B_card_with_running_balance.pdf", [rows]), dict(txns=txns, prev=prev, new=bals[-1])


# ---------------------------------------------------------------- C: a far-future full date on the page
def case_C_promo_date_in_future():
    """A card statement whose rows carry no year and whose page also prints a promotional date two
    years out ('balance transfer offer ... until 06/30/2028'). Statement period is Jan 4 - Feb 3, 2026.
    Right answer: every row dated 2026 (Jan 5 .. Feb 2)."""
    rows = [(13, [(40, "Previous Balance", "l"), (300, "$1,020.15", "r")]),
            (13, [(40, "New Balance", "l"), (300, "$648.90", "r")]),
            (13, [(40, "Minimum Payment Due", "l"), (300, "$35.00", "r")]),
            (13, [(40, "Payment Due Date", "l"), (300, "03/01/26", "r")]),
            (20, [(40, "Opening/Closing Date 01/04/26 - 02/03/26   Account Ending 1004", "l")]),
            (13, [(40, "Trans. date", "l"), (95, "Post date", "l"), (150, "Description", "l"), (500, "Amount", "r")]),
            (13, [(40, "Jan 05", "l"), (95, "Jan 06", "l"), (150, "SQ *BLUE BOTTLE COFFEE OAKLAND CA", "l"), (500, "$6.75", "r")]),
            (13, [(40, "Jan 14", "l"), (95, "Jan 14", "l"), (150, "INTERNET PAYMENT - THANK YOU", "l"), (500, "-$500.00", "r")]),
            (13, [(40, "Jan 22", "l"), (95, "Jan 23", "l"), (150, "AMAZON.COM*RT4 SEATTLE WA", "l"), (500, "$121.99", "r")]),
            (13, [(40, "Feb 01", "l"), (95, "Feb 02", "l"), (150, "SPOTIFY USA", "l"), (500, "$11.99", "r")]),
            (13, [(40, "Feb 02", "l"), (95, "Feb 03", "l"), (150, "RETURN AMAZON.COM*RT4", "l"), (500, "-$11.98", "r")]),
            (30, []),
            (11, [(40, "Special offer: transfer a balance by 03/31/2026 and pay 0% APR on it until 06/30/2028.", "l")])]
    return draw(OUT / "C_promo_date_in_future.pdf", [rows]), {}


# ---------------------------------------------------------------- D: opening balance under a name the reader does not know
def case_D_balance_last_statement(drop_first=False):
    """Credit-union wording: 'Balance Last Statement' / 'Balance This Statement'. Rows carry a running
    balance. In the second file the first row of the table is missing (as if page 1 ended early),
    so the chain starts late. Right answer for the second file: not ok, a row is missing."""
    opening = 1000.00
    rows_src = [("01/02", "PAYROLL ACME CO", 2500.00), ("01/03", "RENT JANUARY", -1200.00),
                ("01/05", "GROCERY STORE 1182", -86.42), ("01/09", "POWER COMPANY", -112.30),
                ("01/14", "ATM WITHDRAWAL", -200.00), ("01/16", "PAYROLL ACME CO", 2500.00)]
    bal, bals = opening, []
    for *_, a in rows_src:
        bal = round(bal + a, 2); bals.append(bal)
    closing = bals[-1]
    table = list(zip(rows_src, bals))
    if drop_first:
        table = table[1:]
    rows = [(13, [(40, "Statement period 01/01/2026 through 01/31/2026", "l")]),
            (13, [(40, "Balance Last Statement", "l"), (300, money(opening), "r")]),
            (13, [(40, "Balance This Statement", "l"), (300, money(closing), "r")]),
            (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Withdrawals", "r"), (450, "Deposits", "r"), (550, "Balance", "r")])]
    for (dt, ds, a), b in table:
        rows.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
    name = "D2_balance_last_statement_row_missing.pdf" if drop_first else "D_balance_last_statement.pdf"
    return draw(OUT / name, [rows]), dict(opening=opening, closing=closing)


# ---------------------------------------------------------------- E: a row broken across a page
def case_E_page_break_inside_row():
    """The last row on page 1 has a second description line that lands at the top of page 2, after
    the repeated page header. Right answer: row 3's description is 'GROCERY STORE 1182 STORE 1182 SPRINGFIELD IL'."""
    opening = 1000.00
    src = [("01/02", "PAYROLL ACME CO", 2500.00), ("01/03", "RENT JANUARY", -1200.00),
           ("01/05", "GROCERY STORE 1182", -86.42), ("01/09", "POWER COMPANY", -112.30),
           ("01/14", "ATM WITHDRAWAL", -200.00)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    hdr = (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Withdrawals", "r"), (450, "Deposits", "r"), (550, "Balance", "r")])
    p1 = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
          (13, [(40, "Opening balance", "l"), (300, money(opening), "r")]),
          (13, [(40, "Closing balance", "l"), (300, money(bals[-1]), "r")]), hdr]
    for (dt, ds, a), b in list(zip(src, bals))[:3]:
        p1.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
    p2 = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026   Page 2 of 2", "l")]), hdr,
          (13, [(100, "STORE 1182 SPRINGFIELD IL", "l")])]
    for (dt, ds, a), b in list(zip(src, bals))[3:]:
        p2.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
    return draw(OUT / "E_page_break_inside_row.pdf", [p1, p2]), {}


# ---------------------------------------------------------------- F: a very long description line
def case_F_long_description():
    """Row 2's description continues on a second line that is 130 characters long (a landscape page,
    so it fits). Right answer: the continuation is part of row 2's description."""
    opening = 1000.00
    cont = "ONLINE TRANSFER REF 9988776655 TO JOHN SMITH MEMO RENT FOR JANUARY 2026 INCLUDING UTILITIES AND PARKING SPACE NUMBER 14 THANK YOU"
    assert len(cont) >= 120, len(cont)
    src = [("01/02", "PAYROLL ACME CO", 2500.00), ("01/03", "RENT JANUARY", -1200.00), ("01/05", "GROCERY STORE 1182", -86.42)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    rows = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
            (13, [(40, "Opening balance", "l"), (300, money(opening), "r")]),
            (13, [(40, "Closing balance", "l"), (300, money(bals[-1]), "r")]),
            (20, [(40, "Date", "l"), (100, "Description", "l"), (640, "Withdrawals", "r"), (700, "Deposits", "r"), (760, "Balance", "r")])]
    for k, ((dt, ds, a), b) in enumerate(zip(src, bals)):
        rows.append((13, [(40, dt, "l"), (100, ds, "l"), (700 if a > 0 else 640, money(a), "r"), (760, money(b), "r")]))
        if k == 1:
            rows.append((13, [(100, cont, "l")]))
    return draw(OUT / "F_long_description.pdf", [rows], pagesize=landscape(letter), font=("Helvetica", 7)), dict(cont=cont)


# ---------------------------------------------------------------- G: Chase-style several debit sections each with a total
def case_G_many_debit_totals():
    """Chase checking layout: no running balance; DEPOSITS AND ADDITIONS, ATM & DEBIT CARD WITHDRAWALS,
    ELECTRONIC WITHDRAWALS, FEES, each section with its own total line. Every number is consistent.
    Right answer: status ok."""
    opening = 1000.00
    dep = [("01/02", "Remote Online Deposit 1", 2500.00), ("01/16", "Remote Online Deposit 1", 2500.00)]
    atm = [("01/05", "Card Purchase 01/04 Trader Joe's #552 Card 4421", 61.18), ("01/14", "ATM Withdrawal 01/14 123 Main St Card 4421", 200.00)]
    ele = [("01/03", "Zelle Payment To Landlord 1928374", 1200.00), ("01/09", "Power Co Bill Pmt PPD ID: 9000111", 112.30)]
    fee = [("01/31", "Monthly Service Fee", 12.00)]
    tot_w = sum(a for *_, a in atm + ele + fee)
    closing = round(opening + sum(a for *_, a in dep) - tot_w, 2)
    rows = [(13, [(40, "CHECKING SUMMARY", "l")]),
            (13, [(40, "Beginning Balance", "l"), (300, f"${money(opening)}", "r")]),
            (13, [(40, "Deposits and Additions", "l"), (300, money(sum(a for *_, a in dep)), "r")]),
            (13, [(40, "ATM & Debit Card Withdrawals", "l"), (300, f"-{money(sum(a for *_, a in atm))}", "r")]),
            (13, [(40, "Electronic Withdrawals", "l"), (300, f"-{money(sum(a for *_, a in ele))}", "r")]),
            (13, [(40, "Fees", "l"), (300, f"-{money(sum(a for *_, a in fee))}", "r")]),
            (13, [(40, "Ending Balance", "l"), (300, f"${money(closing)}", "r")]),
            (20, [(40, "January 01, 2026 through January 31, 2026", "l")])]

    def section(title, items, total_label, neg):
        rows.append((14, [(40, title, "l")]))
        rows.append((14, [(40, "DATE", "l"), (90, "DESCRIPTION", "l"), (550, "AMOUNT", "r")]))
        for dt, ds, a in items:
            rows.append((13, [(40, dt, "l"), (90, ds, "l"), (550, ("-" if neg else "") + f"${money(a)}", "r")]))
        rows.append((20, [(40, total_label, "l"), (550, ("-" if neg else "") + f"${money(sum(a for *_, a in items))}", "r")]))

    section("DEPOSITS AND ADDITIONS", dep, "Total Deposits and Additions", False)
    section("ATM & DEBIT CARD WITHDRAWALS", atm, "Total ATM & Debit Card Withdrawals", True)
    section("ELECTRONIC WITHDRAWALS", ele, "Total Electronic Withdrawals", True)
    section("FEES", fee, "Total Fees", True)
    return draw(OUT / "G_many_debit_totals.pdf", [rows]), dict(opening=opening, closing=closing)


# ---------------------------------------------------------------- H: a date range inside a description
def case_H_date_range_in_description():
    """No 'period' line; the statement prints only 'Statement Date 01/31/2026'. One description is a hotel
    stay: 'MARRIOTT 01/10/26 - 01/13/26'. Every balance chains. Right answer: status ok."""
    opening = 1000.00
    src = [("01/02", "PAYROLL ACME CO", 2500.00), ("01/13", "MARRIOTT 01/10/26 - 01/13/26 DENVER CO", -412.80),
           ("01/20", "GROCERY STORE 1182", -86.42), ("01/28", "TRANSFER TO SAVINGS", -500.00)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    rows = [(13, [(40, "Statement Date 01/31/2026", "l")]),
            (13, [(40, "Opening balance", "l"), (300, money(opening), "r")]),
            (13, [(40, "Closing balance", "l"), (300, money(bals[-1]), "r")]),
            (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Withdrawals", "r"), (450, "Deposits", "r"), (550, "Balance", "r")])]
    for (dt, ds, a), b in zip(src, bals):
        rows.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
    return draw(OUT / "H_date_range_in_description.pdf", [rows]), {}


# ---------------------------------------------------------------- I: horizontal card summary table
def case_I_card_summary_table():
    """Capital One / Discover style: the account summary is a table with the labels on one line and the
    figures on the next. Sections below as before. Right answer: opening 812.40, closing 478.94, ok."""
    prev = 812.40
    credits = [("01/12", "PAYMENT THANK YOU-MOBILE", 500.00)]
    purchases = [("01/05", "STARBUCKS STORE 1182", 6.45), ("01/09", "AMAZON MKTPL*2X41", 89.99), ("01/20", "SHELL OIL 57444", 41.10)]
    fees = [("02/03", "LATE FEE", 29.00)]
    cr, pu, fe = sum(a for *_, a in credits), sum(a for *_, a in purchases), sum(a for *_, a in fees)
    new = round(prev - cr + pu + fe, 2)
    rows = [(13, [(40, "Opening/Closing Date 01/04/26 - 02/03/26", "l"), (540, "Payment Due Date 02/28/26", "r")]),
            (13, [(40, "Minimum Payment Due $40.00   Credit Limit $5,000.00", "l")]),
            (18, [(40, "Account Summary", "l")]),
            (13, [(40, "Previous Balance", "l"), (170, "Payments", "l"), (250, "Other Credits", "l"), (340, "Transactions", "l"), (430, "Fees", "l"), (500, "New Balance", "l")]),
            (13, [(40, f"${money(prev)}", "l"), (170, f"-${money(cr)}", "l"), (250, "$0.00", "l"), (340, f"${money(pu)}", "l"), (430, f"${money(fe)}", "l"), (500, f"${money(new)}", "l")]),
            (20, [(40, "ACCOUNT ACTIVITY", "l")]),
            (14, [(40, "Date", "l"), (150, "Description", "l"), (540, "Amount", "r")])]
    for title, items, neg in (("PAYMENTS AND OTHER CREDITS", credits, True), ("PURCHASE", purchases, False), ("FEES CHARGED", fees, False)):
        rows.append((14, [(40, title, "l")]))
        for dt, ds, a in items:
            rows.append((13, [(40, dt, "l"), (150, ds, "l"), (540, ("-" if neg else "") + money(a), "r")]))
        rows.append((8, []))
    return draw(OUT / "I_card_summary_table.pdf", [rows]), dict(prev=prev, new=new)


# ---------------------------------------------------------------- J: 'Payment' as the debit column's name
def case_J_payment_column():
    """A community-bank layout whose money-out column is headed 'Payment' and money-in 'Deposit'.
    Right answer: 6 rows, signs by column, ok."""
    opening = 1000.00
    src = [("01/02", "PAYROLL ACME CO", 2500.00), ("01/03", "RENT JANUARY", -1200.00),
           ("01/05", "GROCERY STORE 1182", -86.42), ("01/09", "POWER COMPANY", -112.30),
           ("01/14", "ATM WITHDRAWAL", -200.00), ("01/16", "PAYROLL ACME CO", 2500.00)]
    src2 = [src[1]] + [src[0]] + src[2:]      # the first row is a payment
    src2 = [("01/02", "RENT JANUARY", -1200.00), ("01/03", "PAYROLL ACME CO", 2500.00)] + src[2:]
    bal, bals = opening, []
    for *_, a in src2:
        bal = round(bal + a, 2); bals.append(bal)
    rows = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
            (13, [(40, "Beginning balance", "l"), (300, money(opening), "r")]),
            (13, [(40, "Ending balance", "l"), (300, money(bals[-1]), "r")]),
            (20, [(40, "Date", "l"), (100, "Payee", "l"), (360, "Payment", "r"), (450, "Deposit", "r"), (550, "Balance", "r")])]
    for (dt, ds, a), b in zip(src2, bals):
        rows.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
    return draw(OUT / "J_payment_column.pdf", [rows]), dict(src=src2)


# ---------------------------------------------------------------- K: landscape and rotated pages
def _plain_rows():
    opening = 1000.00
    src = [("01/02", "PAYROLL ACME CO", 2500.00), ("01/03", "RENT JANUARY", -1200.00), ("01/05", "GROCERY STORE 1182", -86.42)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    rows = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
            (13, [(40, "Opening balance", "l"), (300, money(opening), "r")]),
            (13, [(40, "Closing balance", "l"), (300, money(bals[-1]), "r")]),
            (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Withdrawals", "r"), (450, "Deposits", "r"), (550, "Balance", "r")])]
    for (dt, ds, a), b in zip(src, bals):
        rows.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
    return rows


def case_K_landscape():
    return draw(OUT / "K_landscape.pdf", [_plain_rows()], pagesize=landscape(letter)), {}


def case_K2_rotated():
    """Portrait content drawn on a page with /Rotate 90, the way some print-to-PDF drivers do it.
    The text layer is intact. Right answer: same as K."""
    return draw(OUT / "K2_rotated.pdf", [_plain_rows()], rotate=90), {}


def case_K3_text_rotated_in_page():
    """Text drawn with a 90 degree text matrix on a landscape page (a true sideways page)."""
    path = OUT / "K3_text_rotated.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 8.5)
    c.translate(letter[0], 0)
    c.rotate(90)
    y = letter[0] - 60
    for step, cells in _plain_rows():
        for x, text, align in cells:
            (c.drawString if align == "l" else c.drawRightString)(x, y, text)
        y -= step
    c.showPage(); c.save()
    return path, {}


# ---------------------------------------------------------------- L: amounts with no cents, lakh grouping, OD suffix
def case_L_no_cents():
    opening = 1000
    src = [("01/02", "PAYROLL ACME CO", 2500), ("01/03", "RENT JANUARY", -1200), ("01/05", "ATM", -200)]
    bal, bals = opening, []
    for *_, a in src:
        bal += a; bals.append(bal)
    rows = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
            (13, [(40, "Opening balance", "l"), (300, f"${opening:,}", "r")]),
            (13, [(40, "Closing balance", "l"), (300, f"${bals[-1]:,}", "r")]),
            (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Withdrawals", "r"), (450, "Deposits", "r"), (550, "Balance", "r")])]
    for (dt, ds, a), b in zip(src, bals):
        rows.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, f"${abs(a):,}", "r"), (550, f"${b:,}", "r")]))
    return draw(OUT / "L_no_cents.pdf", [rows]), {}


def case_L2_lakh_grouping():
    """Indian grouping: 1,23,456.78."""
    def lakh(v):
        s = f"{abs(v):.2f}"; ip, fp = s.split(".")
        if len(ip) <= 3:
            return f"{ip}.{fp}"
        head, last3 = ip[:-3], ip[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        return ",".join(parts + [last3]) + "." + fp
    opening = 250000.00
    src = [("02/01/2026", "SALARY CREDIT", 125000.00), ("05/01/2026", "RENT", -35000.00), ("09/01/2026", "UPI GROCERY", -1234.56)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    rows = [(13, [(40, "Statement period 01/01/2026 to 31/01/2026", "l")]),
            (13, [(40, "Opening balance", "l"), (300, lakh(opening), "r")]),
            (13, [(40, "Closing balance", "l"), (300, lakh(bals[-1]), "r")]),
            (20, [(40, "Date", "l"), (120, "Narration", "l"), (360, "Withdrawal", "r"), (450, "Deposit", "r"), (550, "Balance", "r")])]
    for (dt, ds, a), b in zip(src, bals):
        rows.append((13, [(40, dt, "l"), (120, ds, "l"), (450 if a > 0 else 360, lakh(a), "r"), (550, lakh(b), "r")]))
    return draw(OUT / "L2_lakh_grouping.pdf", [rows]), dict(lakh=lakh(bals[-1]))


def case_L3_overdraft_OD_suffix():
    """UK style: a negative balance printed as '150.00 OD'; period 01/01/2026 - 31/01/2026 day first."""
    opening = 100.00
    src = [("02/01", "RENT", -250.00), ("15/01", "SALARY", 1000.00)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    def fb(v):
        return f"{abs(v):,.2f} OD" if v < 0 else f"{v:,.2f}"
    rows = [(13, [(40, "Statement period 01/01/2026 - 31/01/2026", "l")]),
            (13, [(40, "Opening balance", "l"), (300, fb(opening), "r")]),
            (13, [(40, "Closing balance", "l"), (300, fb(bals[-1]), "r")]),
            (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Paid out", "r"), (450, "Paid in", "r"), (550, "Balance", "r")])]
    for (dt, ds, a), b in zip(src, bals):
        rows.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, fb(b), "r")]))
    return draw(OUT / "L3_overdraft_OD.pdf", [rows]), {}


def case_L4_foreign_currency_row():
    """A card row with the original currency printed beside the description: 'EUR 45.00' then the
    billed amount. One Amount column. Right answer: amount -49.12 and the EUR figure in the description."""
    rows = [(13, [(40, "Previous Balance", "l"), (300, "$100.00", "r")]),
            (13, [(40, "New Balance", "l"), (300, "$155.87", "r")]),
            (13, [(40, "Minimum Payment Due", "l"), (300, "$25.00", "r")]),
            (20, [(40, "Opening/Closing Date 01/04/26 - 02/03/26", "l")]),
            (13, [(40, "Date", "l"), (100, "Description", "l"), (540, "Amount", "r")]),
            (13, [(40, "PURCHASE", "l")]),
            (13, [(40, "01/10", "l"), (100, "AIRBNB PARIS FR", "l"), (420, "EUR 45.00", "r"), (540, "49.12", "r")]),
            (13, [(100, "45.00 EUR X 1.091555 (EXCHG RATE)", "l")]),
            (13, [(40, "01/20", "l"), (100, "SHELL OIL 57444", "l"), (540, "6.75", "r")])]
    return draw(OUT / "L4_foreign_currency_row.pdf", [rows]), {}


# ---------------------------------------------------------------- M: two statements in one PDF
def case_M_two_statements_one_pdf():
    """January and February statements of the same account, concatenated. Right answer: either two
    results, or a clear message that there are two statements; never a single verdict."""
    opening = 1000.00
    jan = [("01/02", "PAYROLL ACME CO", 2500.00), ("01/03", "RENT JANUARY", -1200.00), ("01/05", "GROCERY STORE 1182", -86.42)]
    feb = [("02/02", "PAYROLL ACME CO", 2500.00), ("02/03", "RENT FEBRUARY", -1200.00)]
    def page(period, op, src):
        bal, bals = op, []
        for *_, a in src:
            bal = round(bal + a, 2); bals.append(bal)
        rows = [(13, [(40, f"Statement period {period}", "l")]),
                (13, [(40, "Opening balance", "l"), (300, money(op), "r")]),
                (13, [(40, "Closing balance", "l"), (300, money(bals[-1]), "r")]),
                (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Withdrawals", "r"), (450, "Deposits", "r"), (550, "Balance", "r")])]
        for (dt, ds, a), b in zip(src, bals):
            rows.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
        return rows, bals[-1]
    p1, c1 = page("01/01/2026 - 01/31/2026", opening, jan)
    p2, c2 = page("02/01/2026 - 02/28/2026", c1, feb)
    return draw(OUT / "M_two_statements.pdf", [p1, p2]), dict(jan_close=c1, feb_close=c2)


# ---------------------------------------------------------------- N: a reversal printed negative inside the deposits section
def case_N_negative_in_credit_section():
    """Sectioned statement; the Deposits section contains a returned deposit printed as -25.00 and the
    section total is the net. Right answer: that row is -25.00, status ok."""
    opening = 1000.00
    dep = [("01/02", "PAYROLL ACME CO", 2500.00), ("01/06", "RETURNED DEPOSIT ITEM", -25.00), ("01/16", "PAYROLL ACME CO", 2500.00)]
    wd = [("01/03", "RENT JANUARY", 1200.00), ("01/05", "GROCERY STORE 1182", 86.42)]
    d, w = sum(a for *_, a in dep), sum(a for *_, a in wd)
    closing = round(opening + d - w, 2)
    rows = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
            (13, [(40, "Beginning balance", "l"), (400, f"${money(opening)}", "r")]),
            (13, [(40, "Ending balance", "l"), (400, f"${money(closing)}", "r")]),
            (24, []),
            (14, [(40, "Deposits and other additions", "l")]),
            (14, [(40, "Date", "l"), (110, "Description", "l"), (540, "Amount", "r")])]
    for dt, ds, a in dep:
        rows.append((13, [(40, dt, "l"), (110, ds, "l"), (540, ("-" if a < 0 else "") + money(a), "r")]))
    rows.append((22, [(40, "Total deposits and other additions", "l"), (540, f"${money(d)}", "r")]))
    rows.append((14, [(40, "Withdrawals and other subtractions", "l")]))
    rows.append((14, [(40, "Date", "l"), (110, "Description", "l"), (540, "Amount", "r")]))
    for dt, ds, a in wd:
        rows.append((13, [(40, dt, "l"), (110, ds, "l"), (540, f"-{money(a)}", "r")]))
    rows.append((22, [(40, "Total withdrawals and other subtractions", "l"), (540, f"-${money(w)}", "r")]))
    return draw(OUT / "N_negative_in_credit_section.pdf", [rows]), dict(closing=closing)


# ---------------------------------------------------------------- O: an amount inside a long description
def case_O_amount_in_description():
    """A Zelle memo carries a figure: 'ZELLE TO JOHN SMITH MEMO 150.00 FOR RENT SHARE'. The real
    withdrawal is 86.42. Description is wide and ends near the Withdrawals column."""
    opening = 1000.00
    src = [("01/02", "PAYROLL ACME CO", 2500.00),
           ("01/05", "ZELLE TO JOHN SMITH MEMO 150.00 FOR RENT SHARE JAN", -86.42),
           ("01/09", "POWER COMPANY", -112.30)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    rows = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
            (13, [(40, "Opening balance", "l"), (300, money(opening), "r")]),
            (13, [(40, "Closing balance", "l"), (300, money(bals[-1]), "r")]),
            (20, [(40, "Date", "l"), (90, "Description", "l"), (400, "Withdrawals", "r"), (470, "Deposits", "r"), (550, "Balance", "r")])]
    for (dt, ds, a), b in zip(src, bals):
        rows.append((13, [(40, dt, "l"), (90, ds, "l"), (470 if a > 0 else 400, money(a), "r"), (550, money(b), "r")]))
    return draw(OUT / "O_amount_in_description.pdf", [rows]), {}


# ---------------------------------------------------------------- P: a check list one per line with no description column
def case_P_check_list_one_per_line():
    """Sectioned statement whose CHECKS section lists 'Check No.  Date  Amount', one check per line.
    Right answer: 3 check rows of -100, -50, -25.50; status ok."""
    opening = 1000.00
    dep = [("01/02", "PAYROLL ACME CO", 2500.00)]
    chk = [("1001", "01/10", 100.00), ("1002", "01/20", 50.00), ("1004", "01/27", 25.50)]
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
    rows.append((14, [(40, "Checks", "l")]))
    rows.append((14, [(40, "Check No.", "l"), (120, "Date", "l"), (540, "Amount", "r")]))
    for n, dt, a in chk:
        rows.append((13, [(40, n, "l"), (120, dt, "l"), (540, money(a), "r")]))
    rows.append((22, [(40, "Total checks", "l"), (540, f"-${money(ck)}", "r")]))
    return draw(OUT / "P_check_list_one_per_line.pdf", [rows]), dict(closing=closing)


# ---------------------------------------------------------------- Q: a sentence inside the table that reads like a header
def case_Q_notice_line_in_table():
    """A notice printed between rows: 'Overdraft protection: transfers from your savings deposit account
    cover payments when your balance is low.' No closing balance line is printed (the last row carries it).
    Right answer: 5 rows, ok."""
    opening = 1000.00
    src = [("01/02", "PAYROLL ACME CO", 2500.00), ("01/03", "RENT JANUARY", -1200.00),
           ("01/05", "GROCERY STORE 1182", -86.42), ("01/09", "POWER COMPANY", -112.30), ("01/14", "ATM WITHDRAWAL", -200.00)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    rows = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
            (13, [(40, "Opening balance", "l"), (300, money(opening), "r")]),
            (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Withdrawals", "r"), (450, "Deposits", "r"), (550, "Balance", "r")])]
    for k, ((dt, ds, a), b) in enumerate(zip(src, bals)):
        rows.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
        if k == 2:
            rows.append((13, [(40, "Overdraft protection: transfers from your savings deposit account cover payments when your balance is low.", "l")]))
    return draw(OUT / "Q_notice_line_in_table.pdf", [rows]), dict(closing=bals[-1])


def case_Q2_notice_line_with_closing():
    """Same as Q but a 'Closing balance' line is printed in the summary."""
    opening = 1000.00
    src = [("01/02", "PAYROLL ACME CO", 2500.00), ("01/03", "RENT JANUARY", -1200.00),
           ("01/05", "GROCERY STORE 1182", -86.42), ("01/09", "POWER COMPANY", -112.30), ("01/14", "ATM WITHDRAWAL", -200.00)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    rows = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
            (13, [(40, "Opening balance", "l"), (300, money(opening), "r")]),
            (13, [(40, "Closing balance", "l"), (300, money(bals[-1]), "r")]),
            (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Withdrawals", "r"), (450, "Deposits", "r"), (550, "Balance", "r")])]
    for k, ((dt, ds, a), b) in enumerate(zip(src, bals)):
        rows.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
        if k == 2:
            rows.append((13, [(40, "Overdraft protection: transfers from your savings deposit account cover payments when your balance is low.", "l")]))
    return draw(OUT / "Q2_notice_line_with_closing.pdf", [rows]), dict(closing=bals[-1])


# ---------------------------------------------------------------- R: a deposit-column figure whose balance goes down
def case_R_balances_only_with_flipped_sign():
    """Row 3 is printed in the Deposits column (86.42) but the running balance DROPS by 86.42, and the
    closing balance agrees with the drop. The statement is internally inconsistent: the column says in,
    the balance says out. Right answer: not 'ok' without a visible flag in status/problems."""
    opening = 1000.00
    src = [("01/02", "PAYROLL ACME CO", 2500.00), ("01/03", "RENT JANUARY", -1200.00),
           ("01/05", "GROCERY STORE 1182", -86.42), ("01/09", "POWER COMPANY", -112.30)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    rows = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
            (13, [(40, "Opening balance", "l"), (300, money(opening), "r")]),
            (13, [(40, "Closing balance", "l"), (300, money(bals[-1]), "r")]),
            (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Withdrawals", "r"), (450, "Deposits", "r"), (550, "Balance", "r")])]
    for k, ((dt, ds, a), b) in enumerate(zip(src, bals)):
        col = 450 if a > 0 else 360
        if k == 2:
            col = 450          # printed in the Deposits column
        rows.append((13, [(40, dt, "l"), (100, ds, "l"), (col, money(a), "r"), (550, money(b), "r")]))
    return draw(OUT / "R_flipped_sign_balances.pdf", [rows]), {}


# ---------------------------------------------------------------- S: two-line Wells Fargo header
def case_S_two_line_header():
    """Wells Fargo prints its column names on two lines: 'Deposits/ Withdrawals/ Ending daily' over
    'Additions Subtractions balance'. Balances once per day. Right answer: ok with the chain checked."""
    opening = 1000.00
    src = [("1/2", "PAYROLL ACME CO", 2500.00), ("1/2", "COFFEE SHOP", -4.50), ("1/5", "RENT JANUARY", -1200.00),
           ("1/7", "GAS STATION", -38.10), ("1/7", "PHARMACY", -12.99)]
    bal, daily = opening, []
    for k, (d, _, a) in enumerate(src):
        bal = round(bal + a, 2)
        last = k + 1 == len(src) or src[k + 1][0] != d
        daily.append(bal if last else None)
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
    return draw(OUT / "S_two_line_header.pdf", [rows]), dict(closing=bal)


# ---------------------------------------------------------------- T: a page-header date repeated on every page that is not the statement date
def case_T_repeated_old_date():
    """A three-page statement whose page header repeats 'Account opened 05/12/2019' on every page. The
    statement period (01/01/2026 - 01/31/2026) is printed once on page 1. Rows have no year.
    Right answer: every row dated 2026."""
    opening = 1000.00
    src = [(f"01/{2 + k:02d}", f"CARD PAYMENT {k}", -(1.00 + k)) for k in range(24)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    hdr = (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Withdrawals", "r"), (450, "Deposits", "r"), (550, "Balance", "r")])
    pages = []
    for p in range(3):
        rows = [(13, [(40, "Test Savings Bank   Account opened 05/12/2019   Member number 44120", "l")])]
        if p == 0:
            rows += [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
                     (13, [(40, "Opening balance", "l"), (300, money(opening), "r")]),
                     (13, [(40, "Closing balance", "l"), (300, money(bals[-1]), "r")])]
        rows.append(hdr)
        for (dt, ds, a), b in list(zip(src, bals))[p * 8:(p + 1) * 8]:
            rows.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
        pages.append(rows)
    return draw(OUT / "T_repeated_old_date.pdf", pages), {}


# ---------------------------------------------------------------- U: a continuation line starting with a STOP word
def case_U_total_wine():
    """Row 2's second description line is 'TOTAL WINE & MORE SPRINGFIELD IL'. Right answer: it belongs to row 2."""
    opening = 1000.00
    src = [("01/02", "PAYROLL ACME CO", 2500.00), ("01/03", "DEBIT CARD PURCHASE 1182", -86.42), ("01/09", "POWER COMPANY", -112.30)]
    bal, bals = opening, []
    for *_, a in src:
        bal = round(bal + a, 2); bals.append(bal)
    rows = [(13, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
            (13, [(40, "Opening balance", "l"), (300, money(opening), "r")]),
            (13, [(40, "Closing balance", "l"), (300, money(bals[-1]), "r")]),
            (20, [(40, "Date", "l"), (100, "Description", "l"), (360, "Withdrawals", "r"), (450, "Deposits", "r"), (550, "Balance", "r")])]
    for k, ((dt, ds, a), b) in enumerate(zip(src, bals)):
        rows.append((13, [(40, dt, "l"), (100, ds, "l"), (450 if a > 0 else 360, money(a), "r"), (550, money(b), "r")]))
        if k == 1:
            rows.append((13, [(100, "TOTAL WINE & MORE SPRINGFIELD IL", "l")]))
    return draw(OUT / "U_total_wine.pdf", [rows]), {}


# ---------------------------------------------------------------- V: unusual drawing order (right-to-left, bottom-up)
def case_V_draw_order():
    """Same content as K, but every line is drawn bottom-up and each line's cells right-to-left, each
    cell as a separate text object. Right answer: identical to K."""
    path = OUT / "V_draw_order.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 8.5)
    y = letter[1] - 60
    placed = []
    for step, cells in _plain_rows():
        for x, text, align in cells:
            placed.append((y, x, text, align))
        y -= step
    for y, x, text, align in sorted(placed, key=lambda t: (t[0], -t[1])):
        (c.drawString if align == "l" else c.drawRightString)(x, y, text)
    c.showPage(); c.save()
    return path, {}


# ---------------------------------------------------------------- W: zero-page and empty PDFs
def case_W_zero_pages():
    path = OUT / "W_zero_pages.pdf"
    path.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\nxref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \ntrailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n110\n%%EOF\n")
    return path, {}


ALL = [v for k, v in sorted(globals().items()) if k.startswith("case_")]

if __name__ == "__main__":
    for fn in ALL:
        if fn is case_D_balance_last_statement:
            print(fn(False)[0]); print(fn(True)[0]); continue
        print(fn()[0])
