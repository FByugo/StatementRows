"""45 statements built by an adversarial review on 2026-10-15 to break the reader. Each expectation is the
correct answer stated in that review (builders: tests/redteam/build.py, build2.py)."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from statementrows.core import read_statement

RT = Path(__file__).parent / "redteam"
D = Decimal


def r(name):
    return read_statement(str(RT / name))


def money(res):
    return (sum((t.amount for t in res.txns if t.amount > 0), D(0)), sum((t.amount for t in res.txns if t.amount < 0), D(0)))


def years(res):
    return {t.date.year for t in res.txns if t.date}


def desc(res, k):
    return res.txns[k].description


CASES = {
    # class 1: ok on wrong output
    "A2_bank_sections_april_only.pdf": lambda s: s.status == "ok" and s.kind == "bank" and money(s) == (D("5000.00"), D("-1631.42")),
    "A_bank_sections_mentions_card.pdf": lambda s: s.kind == "bank" and money(s)[0] == D("5000.00"),
    "A4_footer_two_hints.pdf": lambda s: s.kind == "bank" and money(s)[0] == D("5000.00"),
    "A3_numeric_dates_one_hint.pdf": lambda s: s.status == "ok" and money(s)[0] == D("5000.00"),
    "B_card_with_running_balance.pdf": lambda s: s.status == "ok" and s.kind == "card" and money(s) == (D("500.00"), D("-166.54")),
    "C2_bank_rewards_expiry.pdf": lambda s: years(s) == {2026} and s.period == (date(2026, 1, 1), date(2026, 1, 31)),
    "C_promo_date_in_future.pdf": lambda s: years(s) == {2026},
    "T_repeated_old_date.pdf": lambda s: years(s) == {2026},
    "T2_footer_revision_date.pdf": lambda s: years(s) == {2026},
    "D2_balance_last_statement_row_missing.pdf": lambda s: s.status != "ok",
    "D_balance_last_statement.pdf": lambda s: s.status == "ok" and s.opening == D("1000.00"),
    "D3_beginning_balance_row_missing.pdf": lambda s: s.status == "unbalanced",
    "Q_notice_line_in_table.pdf": lambda s: len(s.txns) == 5 and s.closing == D("1901.28") and s.status == "ok",
    "Q2_notice_line_with_closing.pdf": lambda s: len(s.txns) == 5 and s.status == "ok",
    "S_two_line_header.pdf": lambda s: s.status == "ok" and any(t.balance is not None for t in s.txns),
    "S2_two_line_header_wrong_daily_balance.pdf": lambda s: s.status == "unbalanced",
    "R_flipped_sign_balances.pdf": lambda s: s.status != "ok" and any("balance moved the other way" in p for p in s.problems),
    "E_page_break_inside_row.pdf": lambda s: desc(s, 2) == "GROCERY STORE 1182 STORE 1182 SPRINGFIELD IL",
    "E2_page_break_no_header_repeat.pdf": lambda s: desc(s, 2) == "GROCERY STORE 1182 STORE 1182 SPRINGFIELD IL",
    "F_long_description.pdf": lambda s: desc(s, 1).startswith("RENT JANUARY ONLINE TRANSFER"),
    "U_total_wine.pdf": lambda s: "TOTAL WINE" in desc(s, 1),
    # class 3: correct statement refused
    "G_many_debit_totals.pdf": lambda s: s.status == "ok",
    "H_date_range_in_description.pdf": lambda s: s.status == "ok",
    "I_card_summary_table.pdf": lambda s: s.status == "ok" and s.opening == D("812.40") and s.closing == D("478.94"),
    "J_payment_column.pdf": lambda s: s.status == "ok" and len(s.txns) == 6,
    "P_check_list_one_per_line.pdf": lambda s: s.status == "ok" and sorted(t.amount for t in s.txns if t.amount < 0) == [D("-100.00"), D("-50.00"), D("-25.50")],
    "P3_checks_chase_style.pdf": lambda s: s.status == "ok" and sorted(t.amount for t in s.txns if t.amount < 0) == [D("-100.00"), D("-50.00"), D("-25.50")],
    "P2_checks_bofa_style.pdf": lambda s: s.status == "ok",
    "K_landscape.pdf": lambda s: s.status == "ok",
    "K2_rotated.pdf": lambda s: s.status == "ok",
    "K3_text_rotated.pdf": lambda s: s.status == "ok",
    "L2_lakh_grouping.pdf": lambda s: len(s.txns) == 3 and s.closing != D("35000.00"),
    "L3_overdraft_OD.pdf": lambda s: s.status == "ok",
    "N_negative_in_credit_section.pdf": lambda s: s.status == "ok" and D("-25.00") in [t.amount for t in s.txns],
    "M_two_statements.pdf": lambda s: any("second statement" in p for p in s.problems),
    "W_zero_pages.pdf": lambda s: s.status == "unreadable",
    "X1_corrupt_page2.pdf": lambda s: "scan" not in " ".join(s.problems),
    # controls and crash attempts that already held
    "O_amount_in_description.pdf": lambda s: s.status == "ok",
    "V_draw_order.pdf": lambda s: s.status == "ok",
    "L4_foreign_currency_row.pdf": lambda s: D("-49.12") in [t.amount for t in s.txns],
    "X2_giant_line.pdf": lambda s: True,
    "X3_owner_pw.pdf": lambda s: s.status == "ok",
    "X4_dotted_I.pdf": lambda s: True,
    "X5_zero_page_size.pdf": lambda s: True,
}


@pytest.mark.parametrize("name", sorted(CASES), ids=lambda n: n[:-4])
def test_redteam(name):
    res = r(name)
    assert CASES[name](res), (res.status, res.kind, res.opening, res.closing, res.period, money(res),
                              [(str(t.date), str(t.amount), t.description[:40]) for t in res.txns][:8], res.problems[:4])
