import csv
import json
from datetime import date
from decimal import Decimal

import openpyxl
import pytest
from reportlab.pdfgen import canvas
from typer.testing import CliRunner

from statementrows.cli import app
from statementrows.core import read_statement
from statementrows.output import write_all

from conftest import CORPUS, ROWS, make_statement


def amounts(res):
    return [float(t.amount) for t in res.txns]


# ---------------------------------------------------------------- built statements

def test_clean_statement_balances(tmp):
    res = read_statement(str(make_statement(tmp / "a.pdf", ROWS, opening=1000.00)))
    assert res.status == "ok", res.problems
    assert amounts(res) == [r[2] for r in ROWS]
    assert res.txns[0].date == date(2026, 1, 2)
    assert all(t.check == "ok" for t in res.txns)
    assert any("totals" in c for c in res.checks)


def test_a_wrong_balance_is_named_not_hidden(tmp):
    bal, good = 1000.00, []
    for _, _, a in ROWS:
        bal = round(bal + a, 2); good.append(bal)
    bad = list(good); bad[3] += 10          # the printed balance on row 4 is off by 10
    res = read_statement(str(make_statement(tmp / "b.pdf", ROWS, opening=1000.00, balances=bad)))
    assert res.status == "unbalanced"
    assert [p for p in res.problems if p.startswith("row ")] == [
        "row 4 (01/09 POWER COMPANY): the printed balance 2111.28 is off by 10.00; it should be 2101.28, "
        "and the next row agrees"], res.problems


def test_a_missing_row_is_caught_by_the_totals(tmp):
    full_close = round(1000.00 + sum(r[2] for r in ROWS), 2)
    short = ROWS[:4] + ROWS[5:]               # the ATM row is not in the table
    bal, bals = 1000.00, []
    for _, _, a in short:
        bal = round(bal + a, 2); bals.append(bal)
    res = read_statement(str(make_statement(tmp / "c.pdf", short, opening=1000.00, closing=full_close,
                                            balances=bals)))
    assert res.status == "unbalanced"
    assert any("does not reach closing" in p for p in res.problems), res.problems


@pytest.mark.parametrize("style", ["plain", "trailing", "paren", "crdr"])
def test_one_amount_column_in_every_sign_style(tmp, style):
    res = read_statement(str(make_statement(tmp / f"{style}.pdf", ROWS, opening=1000.00, split_columns=False,
                                            header=("Date", "Description", "Amount", "Balance"), style=style)))
    assert res.status == "ok", (style, res.problems)
    assert amounts(res) == [r[2] for r in ROWS]


def test_year_rolls_back_across_new_year(tmp):
    rows = [("12/20", "GIFT SHOP", -40.00), ("12/31", "INTEREST", 1.25), ("01/05", "PAYROLL", 900.00)]
    res = read_statement(str(make_statement(tmp / "y.pdf", rows, opening=100.00,
                                            period="12/15/2025 - 01/14/2026")))
    assert [t.date for t in res.txns] == [date(2025, 12, 20), date(2025, 12, 31), date(2026, 1, 5)]
    assert res.status == "ok", res.problems


def test_day_first_dates(tmp):
    rows = [("02/01", "PAYROLL", 900.00), ("13/01", "RENT", -500.00), ("28/01", "SHOP", -20.00)]
    res = read_statement(str(make_statement(tmp / "d.pdf", rows, opening=100.00,
                                            period="01/01/2026 - 31/01/2026")))
    assert [t.date for t in res.txns] == [date(2026, 1, 2), date(2026, 1, 13), date(2026, 1, 28)]


def test_second_description_line_joins_its_row(tmp):
    res = read_statement(str(make_statement(tmp / "m.pdf", ROWS, opening=1000.00,
                                            desc_below={2: "STORE 1182 SPRINGFIELD IL"})))
    assert res.txns[2].description == "GROCERY STORE 1182 STORE 1182 SPRINGFIELD IL"
    assert res.txns[3].description == "POWER COMPANY"


def test_rows_over_several_pages(tmp):
    rows = [(f"01/{1 + k % 28:02d}", f"CARD PAYMENT {k}", -1.00 - k) for k in range(60)]
    rows.sort(key=lambda r: r[0])
    res = read_statement(str(make_statement(tmp / "p.pdf", rows, opening=5000.00, rows_per_page=25)))
    assert len(res.txns) == 60
    assert res.status == "ok", res.problems


def test_scan_encrypted_and_broken(tmp):
    scan = tmp / "scan.pdf"
    c = canvas.Canvas(str(scan)); c.rect(50, 50, 400, 600, fill=1); c.save()
    assert read_statement(str(scan)).status == "needs_ocr"

    locked = tmp / "locked.pdf"
    c = canvas.Canvas(str(locked), encrypt="secret"); c.drawString(50, 700, "x"); c.save()
    assert read_statement(str(locked)).status == "encrypted"

    broken = tmp / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 this is not really a pdf")
    assert read_statement(str(broken)).status == "unreadable"


# ---------------------------------------------------------------- outside samples nobody here made

BSB = sorted((CORPUS / "bankstatemently").glob("bsb-*-statement.pdf"))


@pytest.mark.parametrize("pdf", BSB, ids=lambda p: p.stem)
def test_bankstatemently_benchmark(pdf):
    info = json.loads((pdf.parent / pdf.name.replace("-statement.pdf", ".info.json")).read_text())
    res = read_statement(str(pdf))
    assert res.status == "ok", res.problems
    assert len(res.txns) == info["transactionCount"]


AYON = sorted((CORPUS / "ayonpal").glob("*.pdf"))


@pytest.mark.parametrize("pdf", AYON, ids=lambda p: p.stem)
def test_ayonpal_every_field(pdf):
    truth = list(csv.DictReader(open(pdf.with_suffix(".csv"))))
    res = read_statement(str(pdf))
    assert res.status == "ok", res.problems
    assert len(res.txns) == len(truth)
    for t, want in zip(res.txns, truth):
        d, m, y = want["date"].split("-")
        assert t.date == date(int(y), int(m), int(d))
        assert t.amount == Decimal(want["deposit"] or 0) - Decimal(want["withdrawal"] or 0)
        assert t.balance == Decimal(want["balance"])
        assert t.description == want["description"]


def test_synthesized_every_field():
    truth = json.loads((CORPUS / "synthesized" / "syn-0042.json").read_text())
    res = read_statement(str(CORPUS / "synthesized" / "syn-0042-clean.pdf"))
    assert res.status == "ok", res.problems
    assert [(t.date.isoformat(), t.description, float(t.amount)) for t in res.txns] == \
        [(x["date"], x["description"], x["amount"]) for x in truth["transactions"]]
    assert float(res.opening) == truth["opening_balance"]
    assert float(res.closing) == truth["closing_balance"]
    assert read_statement(str(CORPUS / "synthesized" / "syn-0042-scanned.pdf")).status == "needs_ocr"


@pytest.mark.skipif(not (CORPUS / "_local" / "fivestar-sample.pdf").exists(), reason="local-only sample")
def test_real_bank_sample_with_pages_left_out():
    # page 1 of a 5 page statement: the summary counts 43 debits, the page holds 36
    res = read_statement(str(CORPUS / "_local" / "fivestar-sample.pdf"))
    assert res.status == "unbalanced"
    assert any("7 debit row(s) are missing" in p for p in res.problems), res.problems
    assert any("credits add up to the printed total 3782.09" in c for c in res.checks)
    assert all(t.check.startswith("ok") for t in res.txns)      # every printed row chains; rows are missing, not wrong
    assert any("could not be read" in p for p in res.problems)  # the sample prints a 2/30, which is no date


# ---------------------------------------------------------------- what the buyer opens

def test_excel_marks_the_broken_row(tmp):
    bal, good = 1000.00, []
    for _, _, a in ROWS:
        bal = round(bal + a, 2); good.append(bal)
    good[3] += 10
    res = read_statement(str(make_statement(tmp / "x.pdf", ROWS, opening=1000.00, balances=good)))
    xlsx, _, _ = write_all(res, tmp / "out", "x")
    ws = openpyxl.load_workbook(xlsx)["Transactions"]
    fills = [ws.cell(r, 1).fill.fgColor.rgb for r in range(2, ws.max_row + 1)]
    assert fills[3].endswith("F8D7DA") and not fills[2].endswith("F8D7DA")
    check = [r[1] for r in openpyxl.load_workbook(xlsx)["Check"].iter_rows(values_only=True)]
    assert "unbalanced" in check


def test_cli_folder_and_strict(tmp):
    make_statement(tmp / "in" / "good.pdf", ROWS, opening=1000.00) if (tmp / "in").mkdir() is None else None
    (tmp / "in" / "broken.pdf").write_bytes(b"%PDF-1.4 nope")
    r = CliRunner().invoke(app, [str(tmp / "in"), "--out", str(tmp / "o"), "--strict"])
    assert r.exit_code == 1
    assert "1 of 2 statement(s) balanced" in r.output
    summary = list(csv.DictReader(open(tmp / "o" / "summary.csv")))
    assert {s["file"]: s["status"] for s in summary} == {"broken.pdf": "unreadable", "good.pdf": "ok"}


def test_impossible_and_out_of_period_dates_are_flagged(tmp):
    # the balances all chain, so only the date check can catch these
    rows = [("01/02", "PAYROLL", 900.00), ("02/30", "NO SUCH DAY", -10.00), ("03/15", "WRONG MONTH", -5.00)]
    res = read_statement(str(make_statement(tmp / "bad-dates.pdf", rows, opening=100.00)))
    assert res.status == "unbalanced"
    assert any("could not be read" in p for p in res.problems), res.problems
    assert any("outside the statement period" in p for p in res.problems), res.problems


# ---------------------------------------------------------------- AgamiAI Indian bank statements (Apache-2.0)

def _agami_truth(path):
    j = json.loads(path.read_text())
    rows = []
    for t in j["transactions"]:
        if "credit" in t:
            amt = Decimal(str(t["credit"] or 0)) - Decimal(str(t["debit"] or 0))
            bal, d = t["balance"], t["date"][:10]
        else:
            a = Decimal(str(t["transaction_amount"] or 0))
            amt = a if (t["cr_dr"] or "").upper() == "CR" else -a
            bal, d = t["available_balance"], t["date"][6:10] + "-" + t["date"][3:5] + "-" + t["date"][:2]
        rows.append((d, amt, Decimal(str(bal)), t["description"]))
    breaks, prev = [], Decimal(str(j["opening_balance"]))
    for k, (_, amt, bal, _) in enumerate(rows):
        if abs(prev + amt - bal) >= Decimal("0.01"):
            breaks.append(k + 1)
        prev = bal
    return rows, breaks


AGAMI = sorted((CORPUS / "agami").glob("Digital_*.pdf"))


@pytest.mark.parametrize("pdf", AGAMI, ids=lambda p: p.stem)
def test_agami_numbers_exact_and_its_own_breaks_found(pdf):
    truth, truth_breaks = _agami_truth(pdf.with_suffix(".json"))
    res = read_statement(str(pdf))
    assert len(res.txns) == len(truth)
    for t, (d, amt, bal, _) in zip(res.txns, truth):
        assert (t.date.isoformat(), t.amount, t.balance) == (d, amt, bal)
    # the dataset's printed balances skip at a few rows; the tool must name exactly those
    assert [k + 1 for k, t in enumerate(res.txns) if t.check == "break"] == truth_breaks
    same = sum(1 for t, (_, _, _, desc) in zip(res.txns, truth) if t.description == desc)
    assert same >= 0.85 * len(truth), f"descriptions {same}/{len(truth)}"


def test_agami_scan_is_reported_not_guessed():
    assert read_statement(str(CORPUS / "agami" / "Scanned_Type1_00001.pdf")).status == "needs_ocr"


LOCAL = CORPUS / "_local"


@pytest.mark.skipif(not (LOCAL / "cuanswers-sample.pdf").exists(), reason="local-only sample")
def test_credit_union_with_seven_accounts():
    res = read_statement(str(LOCAL / "cuanswers-sample.pdf"))
    assert all(t.check.startswith("ok") for t in res.txns if t.balance is not None and t.check)
    closes = [c for c in res.checks if "equals the printed ending balance" in c]
    assert len(closes) == 7, closes
    # the sample itself prints September dates in a December statement, and one 1/01/10
    assert res.problems == ["dates: 4 row(s) fall outside the statement period 2019-12-01 to 2019-12-31 (rows [5, 6, 7, 43])"]
    checking = [t for t in res.txns if t.account.startswith("110")]
    assert len(checking) == 27 and checking[0].description == "BPV/Chase MasterCard"


@pytest.mark.skipif(not (LOCAL / "buildersbank-sample.pdf").exists(), reason="local-only sample")
def test_printed_totals_that_leave_out_rows_are_caught():
    # the sample's own rows and balances agree; its printed totals skip 250 + 50 + 3.28
    res = read_statement(str(LOCAL / "buildersbank-sample.pdf"))
    assert all(t.check == "ok" for t in res.txns)
    assert any("credits add up to 7153.28 (5 rows), the statement prints 6850.00" in p for p in res.problems)


def test_drag_and_drop_writes_next_to_the_files(tmp, monkeypatch, capsys):
    from statementrows import dragdrop
    make_statement(tmp / "jan.pdf", ROWS, opening=1000.00)
    (tmp / "notes.txt").write_text("not a statement")
    monkeypatch.setattr("builtins.input", lambda *_: "")
    monkeypatch.setattr("sys.argv", ["StatementRows.exe", str(tmp)])
    assert dragdrop.main() == 0
    assert (tmp / "excel" / "jan.xlsx").exists()
    assert "1 of 1 statement(s) balanced" in capsys.readouterr().out


def test_combined_workbook_one_sheet_per_statement(tmp):
    (tmp / "in").mkdir()
    make_statement(tmp / "in" / "jan.pdf", ROWS, opening=1000.00)
    make_statement(tmp / "in" / "feb.pdf", ROWS, opening=3856.28, period="02/01/2026 - 02/28/2026")
    r = CliRunner().invoke(app, [str(tmp / "in"), "--out", str(tmp / "o")])
    assert r.exit_code == 0, r.output
    wb = openpyxl.load_workbook(tmp / "o" / "all statements.xlsx")
    assert wb.sheetnames == ["Summary", "feb", "jan"]
    assert wb["jan"].max_row == len(ROWS) + 1


@pytest.mark.skipif(not (LOCAL / "carsonbank-sample.pdf").exists(), reason="local-only sample")
def test_summary_counts_that_disagree_with_the_rows():
    # Carson Bank's sample: rows chain, but its summary counts 10 deposits and 54 debits
    res = read_statement(str(LOCAL / "carsonbank-sample.pdf"))
    assert all(t.check == "ok" for t in res.txns[1:] if t.section == "")
    assert {t.date.month for t in res.txns} == {7}        # an amount once flipped the whole file to day-first
    checks = [t for t in res.txns if t.section == "checks"]
    assert len(checks) == 8 and sum(t.amount for t in checks) == Decimal("-1783.32")        # an amount once flipped the whole file to day-first
    assert res.opening == Decimal("3005.93")
    assert any("the statement says 54" in p for p in res.problems)


from conftest import make_sectioned

DEP = [("01/02/26", "PAYROLL ACME CO DES:DIRECT DEP", 2500.00), ("01/16/26", "PAYROLL ACME CO DES:DIRECT DEP", 2500.00)]
WD = [("01/03/26", "RENT JANUARY", 1200.00), ("01/05/26", "GROCERY STORE 1182", 86.42),
      ("01/21/26", "TRANSIT CARD", 45.00)]
CHK = [("1001", "01/10/26", 100.00), ("1002", "01/20/26", 50.00), ("1004", "01/27/26", 25.50)]


@pytest.mark.parametrize("signed", [False, True])
def test_sections_without_a_running_balance(tmp, signed):
    res = read_statement(str(make_sectioned(tmp / "s.pdf", opening=1000.00, deposits=DEP, withdrawals=WD,
                                            checks=CHK, signed_withdrawals=signed)))
    assert res.status == "ok", res.problems
    got = sorted((t.date.isoformat(), float(t.amount)) for t in res.txns)
    want = sorted([("2026-01-02", 2500.0), ("2026-01-16", 2500.0), ("2026-01-03", -1200.0), ("2026-01-05", -86.42),
                   ("2026-01-21", -45.0), ("2026-01-10", -100.0), ("2026-01-20", -50.0), ("2026-01-27", -25.5)])
    assert got == want
    assert [t.description for t in res.txns if t.section == "checks"] == ["CHECK 1001", "CHECK 1002", "CHECK 1004"]
    assert sum(1 for c in res.checks if "add up to the printed total" in c) == 3


def test_a_section_total_that_does_not_match(tmp):
    res = read_statement(str(make_sectioned(tmp / "s.pdf", opening=1000.00, deposits=DEP, withdrawals=WD,
                                            checks=CHK, wrong_total=9.99)))
    assert res.status == "unbalanced"
    assert any("statement prints 1341.41" in p for p in res.problems), res.problems
