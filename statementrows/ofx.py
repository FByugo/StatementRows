"""Write a read statement as OFX (for Xero, Quicken, most accounting software) or as a QuickBooks
Web Connect .qbo file. Both are the same OFX 1.02 text; a .qbo adds the INTU.BID line QuickBooks
looks for. QuickBooks only accepts a bank id it knows, so the caller passes the id of the bank the
statement came from; nothing here picks one for them."""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from .core import Result

HEADER = """OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

"""


def _clean(text: str, n: int) -> str:
    # OFX 1.02 is SGML: no markup characters inside values, plain ASCII
    t = text.encode("ascii", "replace").decode().replace("?", " ")
    t = re.sub(r"[<>&]", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:n] or "TRANSACTION"


def _d(x: date) -> str:
    return x.strftime("%Y%m%d")


def build(res: Result, bank_id: str | None = None, acct_id: str = "0000", currency: str = "USD") -> str:
    """The OFX text. Rows without a date are left out and counted in a comment, never invented."""
    rows = [t for t in res.txns if t.date is not None]
    skipped = len(res.txns) - len(rows)
    dates = [t.date for t in rows] or [date.today()]
    start, end = (res.period if res.period else (min(dates), max(dates)))
    card = res.kind == "card"
    out = [HEADER, "<OFX>", "<SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO</STATUS>",
           f"<DTSERVER>{_d(end)}120000<LANGUAGE>ENG"]
    if bank_id:
        out.append(f"<INTU.BID>{_clean(bank_id, 10)}")
    out.append("</SONRS></SIGNONMSGSRSV1>")
    if card:
        out += ["<CREDITCARDMSGSRSV1><CCSTMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>",
                f"<CCSTMTRS><CURDEF>{currency}<CCACCTFROM><ACCTID>{_clean(acct_id, 22)}</CCACCTFROM>"]
    else:
        out += ["<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>",
                f"<STMTRS><CURDEF>{currency}<BANKACCTFROM><BANKID>{_clean(bank_id or '000000000', 9)}"
                f"<ACCTID>{_clean(acct_id, 22)}<ACCTTYPE>CHECKING</BANKACCTFROM>"]
    out.append(f"<BANKTRANLIST><DTSTART>{_d(start)}<DTEND>{_d(end)}")
    seen: dict[str, int] = {}
    for t in rows:
        key = f"{t.date}|{t.amount}|{t.description}"
        seen[key] = seen.get(key, 0) + 1
        # the same row read twice must get the same id, so a re-import does not double it
        fitid = hashlib.sha1(f"{key}|{seen[key]}".encode()).hexdigest()[:20]
        kind = "CREDIT" if t.amount > 0 else "DEBIT"
        if t.note == "check" or t.description.upper().startswith("CHECK "):
            kind = "CHECK"
        out.append(f"<STMTTRN><TRNTYPE>{kind}<DTPOSTED>{_d(t.date)}<TRNAMT>{t.amount:.2f}"
                   f"<FITID>{fitid}<NAME>{_clean(t.description, 32)}<MEMO>{_clean(t.description, 255)}</STMTTRN>")
    out.append("</BANKTRANLIST>")
    if res.closing is not None:
        bal = -res.closing if card else res.closing      # a card's balance is money owed
        out.append(f"<LEDGERBAL><BALAMT>{bal:.2f}<DTASOF>{_d(end)}</LEDGERBAL>")
    out.append("</CCSTMTRS></CCSTMTTRNRS></CREDITCARDMSGSRSV1>" if card else "</STMTRS></STMTTRNRS></BANKMSGSRSV1>")
    out.append("</OFX>")
    if skipped:
        out.append(f"<!-- {skipped} row(s) had no readable date and are not in this file -->")
    return "\n".join(out) + "\n"


def write(res: Result, path: Path, bank_id: str | None = None, acct_id: str = "0000") -> list[Path]:
    """One file per account: accounting software imports a file into one account, so a credit union
    statement with savings, checking and a loan becomes three files, each named after its account."""
    accounts = list(dict.fromkeys(t.account for t in res.txns))
    if len(accounts) <= 1:
        path.write_text(build(res, bank_id, acct_id), encoding="ascii", errors="replace")
        return [path]
    out = []
    for acct in accounts:
        part = copy.copy(res)
        part.txns = [t for t in res.txns if t.account == acct]
        bals = [t.balance for t in part.txns if t.balance is not None]
        part.closing = bals[-1] if bals else None
        digits = re.findall(r"\d{3,}", acct)
        slug = re.sub(r"[^A-Za-z0-9]+", "-", acct).strip("-")[:40] or "account"
        p = path.with_name(f"{path.stem}-{slug}{path.suffix}")
        p.write_text(build(part, bank_id, digits[-1] if digits else acct_id), encoding="ascii", errors="replace")
        out.append(p)
    return out


def amounts_in(text: str) -> list[Decimal]:
    """Read the amounts back out of an OFX file (used by the tests)."""
    return [Decimal(x) for x in re.findall(r"<TRNAMT>(-?\d+\.\d{2})", text)]
