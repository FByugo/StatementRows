"""Statements built here to imitate quirks seen in common US layouts. They are imitations from general
knowledge of those layouts, not copies of any bank's statement, so they test the reader's rules, not
any bank's real file."""
from datetime import date
from decimal import Decimal

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from statementrows.core import read_statement


def draw(path, lines):
    """lines: list of (y_step, [(x, text, align)]) with align 'l' or 'r'."""
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 8.5)
    y = 750
    for step, cells in lines:
        for x, text, align in cells:
            (c.drawString if align == "l" else c.drawRightString)(x, y, text)
        y -= step
    c.save()
    return path


def test_beginning_balance_row_without_a_date_and_plain_minus(tmp_path):
    rows = [(13, [(40, "CHECKING SUMMARY", "l")]),
            (13, [(40, "Beginning Balance", "l"), (300, "$1,250.00", "r")]),
            (13, [(40, "Ending Balance", "l"), (300, "$2,893.37", "r")]),
            (20, [(40, "Statement period: January 1, 2026 through January 31, 2026", "l")]),
            (13, [(40, "TRANSACTION DETAIL", "l")]),
            (13, [(40, "DATE", "l"), (90, "DESCRIPTION", "l"), (460, "AMOUNT", "r"), (550, "BALANCE", "r")]),
            (13, [(90, "Beginning Balance", "l"), (550, "$1,250.00", "r")]),
            (13, [(40, "01/02", "l"), (90, "Payroll Direct Dep Acme Co PPD ID: 9000111", "l"), (460, "2,250.00", "r"), (550, "3,500.00", "r")]),
            (13, [(40, "01/04", "l"), (90, "Card Purchase 01/03 Trader Joe's #552 Portland OR Card 4421", "l"), (460, "-61.18", "r"), (550, "3,438.82", "r")]),
            (13, [(40, "01/09", "l"), (90, "Zelle Payment To Sam 1928374", "l"), (460, "-45.00", "r"), (550, "3,393.82", "r")]),
            (13, [(40, "01/15", "l"), (90, "Online Transfer To Sav ...4410", "l"), (460, "-500.00", "r"), (550, "2,893.82", "r")]),
            (13, [(40, "01/31", "l"), (90, "Monthly Service Fee", "l"), (460, "-0.45", "r"), (550, "2,893.37", "r")]),
            (13, [(90, "Ending Balance", "l"), (550, "$2,893.37", "r")])]
    res = read_statement(str(draw(tmp_path / "a.pdf", rows)))
    assert res.status == "ok", res.problems
    assert len(res.txns) == 5
    assert res.txns[1].description.startswith("Card Purchase 01/03 Trader Joe's")
    assert res.txns[1].date == date(2026, 1, 4)          # the 01/03 inside the description is not the date
    assert res.opening == Decimal("1250.00") and res.closing == Decimal("2893.37")


def test_signs_written_apart_from_the_dollar_sign(tmp_path):
    rows = [(13, [(40, "Opening balance", "l"), (300, "$400.00", "r")]),
            (13, [(40, "Closing balance", "l"), (300, "$3,524.90", "r")]),
            (20, [(40, "Sep 1 - Sep 30, 2026", "l")]),
            (13, [(40, "Date", "l"), (100, "Description", "l"), (300, "Category", "l"), (460, "Amount", "r"), (550, "Balance", "r")]),
            (13, [(40, "Sep 2", "l"), (100, "Deposit from ACME PAYROLL", "l"), (300, "Credit", "l"), (460, "+ $3,250.00", "r"), (550, "$3,650.00", "r")]),
            (13, [(40, "Sep 5", "l"), (100, "Debit Card Purchase - KROGER", "l"), (300, "Debit", "l"), (460, "- $86.42", "r"), (550, "$3,563.58", "r")]),
            (13, [(40, "Sep 21", "l"), (100, "Debit Card Purchase - CITY TRANSIT", "l"), (300, "Debit", "l"), (460, "- $38.68", "r"), (550, "$3,524.90", "r")])]
    res = read_statement(str(draw(tmp_path / "b.pdf", rows)))
    assert res.status == "ok", res.problems
    assert [float(t.amount) for t in res.txns] == [3250.00, -86.42, -38.68]
    assert res.txns[0].date == date(2026, 9, 2)


def test_card_with_two_dates_and_credits_marked_minus_dollar(tmp_path):
    rows = [(13, [(40, "Previous Balance", "l"), (300, "$1,020.15", "r")]),
            (13, [(40, "New Balance", "l"), (300, "$648.90", "r")]),
            (13, [(40, "Minimum Payment Due", "l"), (300, "$35.00", "r")]),
            (13, [(40, "Payment Due Date", "l"), (300, "03/01/26", "r")]),
            (20, [(40, "Closing Date 02/03/26   Account Ending 1004", "l")]),
            (13, [(40, "Trans. date", "l"), (95, "Post date", "l"), (150, "Description", "l"), (500, "Amount", "r")]),
            (13, [(40, "Jan 05", "l"), (95, "Jan 06", "l"), (150, "SQ *BLUE BOTTLE COFFEE OAKLAND CA", "l"), (500, "$6.75", "r")]),
            (13, [(40, "Jan 14", "l"), (95, "Jan 14", "l"), (150, "INTERNET PAYMENT - THANK YOU", "l"), (500, "-$500.00", "r")]),
            (13, [(40, "Jan 22", "l"), (95, "Jan 23", "l"), (150, "AMAZON.COM*RT4 SEATTLE WA", "l"), (500, "$121.99", "r")]),
            (13, [(40, "Feb 01", "l"), (95, "Feb 02", "l"), (150, "SPOTIFY USA", "l"), (500, "$11.99", "r")]),
            (13, [(40, "Feb 02", "l"), (95, "Feb 03", "l"), (150, "RETURN AMAZON.COM*RT4", "l"), (500, "-$11.98", "r")])]
    res = read_statement(str(draw(tmp_path / "c.pdf", rows)))
    assert res.status == "ok", res.problems
    assert res.kind == "card"
    assert [float(t.amount) for t in res.txns] == [-6.75, 500.00, -121.99, -11.99, 11.98]
    assert res.txns[0].date == date(2026, 1, 5) and res.txns[0].date_2 == date(2026, 1, 6)


def test_unknown_opening_label_is_never_ok(tmp_path):
    # the first row could be missing and nothing would show it: say so instead of 'ok'
    rows = [(13, [(40, "Kontostand am Anfang des Zeitraums", "l"), (300, "1,000.00", "r")]),
            (20, [(40, "Statement period 01/01/2026 - 01/31/2026", "l")]),
            (13, [(40, "Date", "l"), (90, "Description", "l"), (460, "Amount", "r"), (550, "Balance", "r")]),
            (13, [(40, "01/03", "l"), (90, "RENT JANUARY", "l"), (460, "-1,200.00", "r"), (550, "2,300.00", "r")]),
            (13, [(40, "01/05", "l"), (90, "GROCERY STORE", "l"), (460, "-86.42", "r"), (550, "2,213.58", "r")])]
    res = read_statement(str(draw(tmp_path / "u.pdf", rows)))
    assert res.status == "partly_checked"
    assert any("opening balance not found" in p for p in res.problems)
