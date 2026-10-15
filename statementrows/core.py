"""Read transactions out of a bank or credit card statement PDF and check them
against the statement's own running balance and totals.

Nothing is written to disk here. The PDF is read from the path given and every
result lives in memory until the caller decides what to save.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

import pdfplumber

# ---------------------------------------------------------------- words we look for

MONTHS = {
    1: "jan janv janvier januari januar enero ene gen genn",
    2: "feb fev fevr févr fevrier février februari februar febrero",
    3: "mar mars maart marz märz marzo mrt mär",
    4: "apr avr avril april abril abr",
    5: "may mai mei mayo",
    6: "jun juin juni junio",
    7: "jul juil juillet juli julio",
    8: "aug aout août augustus agosto ago",
    9: "sep sept septembre september septiembre set",
    10: "oct octobre okt oktober octubre",
    11: "nov novembre november noviembre",
    12: "dec déc decembre décembre december dezember diciembre dic dez",
}
MONTH_OF = {w: m for m, words in MONTHS.items() for w in words.split()}
MONTH_RE = "|".join(sorted(MONTH_OF, key=len, reverse=True))

DATE_WORDS = ("date", "datum", "fecha", "data", "posted", "post", "trans", "day")
ROLE_WORDS = [  # checked in this order, first hit wins
    ("balance", ("balance", "solde", "saldo", "running")),
    ("debit", ("withdrawal", "withdrawals", "debit", "debits", "débit", "débits",
               "money out", "paid out", "payments out", "retrait", "retraits", "cargo",
               "cargos", "afschrijving", "chèques", "cheques", "out")),
    ("credit", ("deposit", "deposits", "credit", "credits", "crédit", "crédits",
                "money in", "paid in", "dépôt", "dépôts", "abono", "abonos",
                "bijschrijving", "in")),
    ("amount", ("amount", "montant", "importe", "bedrag", "betrag", "valor")),
    ("loan", ("disbursement", "disbursements", "principal", "payment", "payments", "interest")),
]
OPENING_WORDS = ("balance brought forward", "brought forward", "opening balance",
                 "previous balance", "beginning balance", "balance forward",
                 "starting balance", "solde d'ouverture", "solde précédent",
                 "solde d’ouverture", "saldo anterior", "saldo inicial",
                 "beginsaldo", "vorheriger saldo", "balance b/f", "b/f")
CLOSING_WORDS = ("new balance", "closing balance", "ending balance", "balance carried forward",
                 "solde de fermeture", "solde de clôture", "nouveau solde", "saldo final",
                 "eindsaldo", "neuer saldo", "balance c/f", "statement balance")
STOP_WORDS = ("total", "totals", "subtotal", "sub-total", "year-to-date", "interest charges",
              "fees charged", "summary", "page ", "continued", "carried forward",
              "frais sur compte")

CARD_HINTS = ("credit card", "minimum payment", "payment due", "credit limit",
              "credit line", "cardmember", "cardholder", "card services", "apr")


@dataclass
class Txn:
    date: date | None
    description: str
    amount: Decimal              # money in is positive, money out is negative
    balance: Decimal | None
    page: int
    raw_date: str = ""
    date_2: date | None = None
    account: str = ""
    note: str = ""
    ref: str = ""                # cheque number, branch code or reference printed in its own column
    parts: list = field(default_factory=list, repr=False)   # the description, one entry per printed line
    check: str = ""              # "ok", "break", or "" when there is nothing to check against

    @property
    def direction(self) -> str:
        return "credit" if self.amount > 0 else "debit"


@dataclass
class Result:
    path: str
    status: str = "ok"           # ok · unbalanced · unchecked · no_table · needs_ocr · encrypted · unreadable
    kind: str = "bank"           # bank or card
    txns: list[Txn] = field(default_factory=list)
    opening: Decimal | None = None
    closing: Decimal | None = None
    problems: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    pages: int = 0
    period: tuple | None = None


# ---------------------------------------------------------------- page → lines

@dataclass
class Line:
    text: str
    xs: list[tuple[float, float]]   # x0, x1 for every character of text
    top: float
    size: float
    page: int

    def span(self, a: int, b: int) -> tuple[float, float]:
        return self.xs[a][0], self.xs[b - 1][1]

    @property
    def x0(self) -> float:
        for ch, (a, _) in zip(self.text, self.xs):
            if not ch.isspace():
                return a
        return 0.0


def _upright(obj) -> bool:
    if obj.get("object_type") != "char":
        return True
    m = obj.get("matrix")
    return bool(obj.get("upright", True)) and (m is None or (abs(m[1]) < 1e-3 and abs(m[2]) < 1e-3))


def _build_line(chars, page_no) -> Line:
    chars = sorted(chars, key=lambda c: c["x0"])
    text: list[str] = []
    xs: list[tuple[float, float]] = []   # one entry per character of the final string
    prev = None
    for c in chars:
        if prev is not None:
            gap = c["x0"] - prev["x1"]
            size = prev.get("size", 8) or 8
            if gap > size * 1.6:          # a wide gap is a cell boundary
                text.append("  "); xs += [(prev["x1"], c["x0"])] * 2
            elif gap > size * 0.18:
                text.append(" "); xs.append((prev["x1"], c["x0"]))
        t = c["text"]                     # a ligature such as "fi" is one glyph and two letters
        w = (c["x1"] - c["x0"]) / max(1, len(t))
        text.append(t); xs += [(c["x0"] + k * w, c["x0"] + (k + 1) * w) for k in range(len(t))]
        prev = c
    s = "".join(text)
    assert len(s) == len(xs)
    size = max((c.get("size", 0) for c in chars), default=0)
    return Line(s, xs, min(c["top"] for c in chars), size, page_no)


def page_lines(page, page_no: int) -> list[Line]:
    chars = [c for c in page.chars if _upright(c) and c["text"].strip() != ""]
    chars.sort(key=lambda c: (round(c["top"]), c["x0"]))
    rows: list[list[dict]] = []
    for c in chars:
        mid = (c["top"] + c["bottom"]) / 2
        for row in rows[-4:]:
            r = row[0]
            if abs((r["top"] + r["bottom"]) / 2 - mid) < max(2.0, (r["bottom"] - r["top"]) * 0.45):
                row.append(c); break
        else:
            rows.append([c])
    lines = []
    for row in rows:
        # two different text runs printed over each other: split them by font
        row.sort(key=lambda c: c["x0"])
        overlap = any(b["x0"] < a["x1"] - 1.0 for a, b in zip(row, row[1:]))
        if overlap:
            groups: dict[tuple, list] = {}
            for c in row:
                groups.setdefault((c.get("fontname"), round(c.get("size", 0), 1)), []).append(c)
            for g in groups.values():
                lines.append(_build_line(g, page_no))
        else:
            lines.append(_build_line(row, page_no))
    lines.sort(key=lambda l: (l.top, l.x0))
    return lines


# ---------------------------------------------------------------- numbers

class Locale:
    def __init__(self, decimal: str):
        self.decimal = decimal
        th = r"[,'’]" if decimal == "." else r"[ .  '’]"
        d = re.escape(decimal)
        cur = r"(?:[$€£¥₹]|Rs\.?|[A-Z]{3}\s?(?=[\d\-−]))"
        self.money = re.compile(
            rf"(?<![\w.,/:])(?P<pre>[-+−]\s?)?(?P<c1>{cur}\s?)?(?P<pre2>[-+−])?"
            rf"(?P<num>\(?\d{{1,3}}(?:{th}\d{{3}})*{d}\d{{2}}\)?|\(?\d+{d}\d{{2}}\)?)"
            rf"(?P<c2>\s?[$€£])?(?P<post>\s?(?:CR|DR|Cr|Dr|-|\+|−))?(?![\w,.]?\d)(?![A-Za-z])"
        )
        self.th = th

    def value(self, m: re.Match) -> Decimal:
        num = m.group("num")
        neg = num.startswith("(") and num.endswith(")")
        num = num.strip("()")
        num = re.sub(self.th, "", num).replace(self.decimal, ".")
        v = Decimal(num)
        sign = (m.group("pre") or "") + (m.group("pre2") or "") + (m.group("post") or "")
        if neg or "-" in sign or "−" in sign or "DR" in sign.upper():
            v = -v
        return v


def guess_locale(text: str) -> Locale:
    dot = len(re.findall(r"\d[,]\d{3}\.\d{2}(?!\d)|(?<![\d,.])\d{1,3}\.\d{2}(?![\d,])", text))
    comma = len(re.findall(r"\d[.  ]\d{3},\d{2}(?!\d)|(?<![\d,.])\d{1,3},\d{2}(?![\d.])", text))
    return Locale("," if comma > dot else ".")


# ---------------------------------------------------------------- dates

DATE_PATTERNS = [
    ("ymd", re.compile(r"(?P<y>(?:19|20)\d{2})[-/.](?P<m>\d{1,2})[-/.](?P<d>\d{1,2})(?!\d)")),
    ("num3", re.compile(r"(?P<a>\d{1,2})[/.\-](?P<b>\d{1,2})[/.\-](?P<y>\d{4}|\d{2})(?!\d)")),
    ("dmon", re.compile(rf"(?P<d>\d{{1,2}})[ \-.]?(?P<mon>{MONTH_RE})\.?(?:[ \-,.]+(?P<y>(?:19|20)\d{{2}}|\d{{2}})(?![\d.,]))?(?![a-zà-ÿ])", re.I)),
    ("mond", re.compile(rf"(?P<mon>{MONTH_RE})\.?[ \-](?P<d>\d{{1,2}})(?!\d)(?!\.\d)(?:,?[ ](?P<y>(?:19|20)\d{{2}}))?", re.I)),
    ("num2", re.compile(r"(?P<a>\d{1,2})[/.\-](?P<b>\d{1,2})(?![\d/.\-]\d)(?![.,]\d)")),
]


@dataclass
class RawDate:
    kind: str
    parts: dict
    end: int
    text: str


def match_date_at(text: str, pos: int) -> RawDate | None:
    for kind, rx in DATE_PATTERNS:
        m = rx.match(text, pos)
        if m:
            gd = m.groupdict()
            if kind in ("dmon", "mond") and gd["mon"].lower() not in MONTH_OF:
                continue
            nxt = text[m.end(): m.end() + 1]
            if nxt and nxt.isalnum() and kind not in ("dmon", "mond"):
                continue
            if kind in ("num3", "num2"):
                x, y = int(gd["a"]), int(gd["b"])
                # 50.43 is an amount, not a date; and an amount with a trailing sign is never a date
                if not (1 <= x <= 31 and 1 <= y <= 31 and min(x, y) <= 12) or nxt in ("-", "+", "−"):
                    continue
            return RawDate(kind, gd, m.end(), m.group(0))
    return None


def leading_dates(text: str) -> tuple[list[RawDate], int]:
    """Dates at the start of a line, up to two (posting and transaction). A serial number and a
    transaction id may come first ('12  S8559  06/01/2024 ...'); they are skipped."""
    start = len(text) - len(text.lstrip())
    for skip in range(3):
        found, pos = _dates_from(text, start)
        if found:
            return found, pos
        m = re.match(r"[A-Za-z]{0,3}\d[\w\-/]{0,15}\s+", text[start:])
        if not m:
            break
        start += m.end()
    return [], len(text) - len(text.lstrip())


def _dates_from(text: str, pos: int) -> tuple[list[RawDate], int]:
    found = []
    for _ in range(2):
        rd = match_date_at(text, pos)
        if not rd:
            break
        found.append(rd)
        pos = rd.end
        # a time printed after a date belongs to it: 01/01/2024 12:12:52 PM
        t = re.match(r"\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AaPp][Mm])?", text[pos:])
        if t:
            pos += t.end()
        while pos < len(text) and text[pos] == " ":
            pos += 1
    return found, pos


def _year(y: str | None) -> int | None:
    if not y:
        return None
    y = int(y)
    return y + 2000 if y < 100 else y


def resolve(rd: RawDate, order: str, end: date | None) -> date | None:
    p = rd.parts
    try:
        if rd.kind == "ymd":
            return date(int(p["y"]), int(p["m"]), int(p["d"]))
        if rd.kind in ("num3", "num2"):
            a, b = int(p["a"]), int(p["b"])
            d, m = (a, b) if order == "dmy" else (b, a)
            y = _year(p.get("y"))
        else:
            d, m, y = int(p["d"]), MONTH_OF[p["mon"].lower()], _year(p.get("y"))
        if y is None:
            if end is None:
                return None
            y = end.year - 1 if (m, d) > (end.month, end.day) and m > end.month else end.year
        return date(y, m, d)
    except (ValueError, KeyError):
        return None


def pick_order(raws: list[RawDate], hint_us: bool) -> str:
    nums = [(int(r.parts["a"]), int(r.parts["b"])) for r in raws if r.kind in ("num3", "num2")]
    if any(a > 12 for a, _ in nums):
        return "dmy"
    if any(b > 12 for _, b in nums):
        return "mdy"
    if len(nums) >= 3:
        def drops(order):
            seq = [(b, a) if order == "dmy" else (a, b) for a, b in nums]
            return sum(1 for x, y in zip(seq, seq[1:]) if y < x)
        dd, md = drops("dmy"), drops("mdy")
        if dd != md:
            return "dmy" if dd < md else "mdy"
    return "mdy" if hint_us else "dmy"


def statement_end(lines: list[Line], order: str) -> date | None:
    """The statement date, used to give a year to dates that lack one: a full date repeated on
    most pages (the page header) if there is one, otherwise the latest full date printed."""
    best = None
    seen: dict[date, set[int]] = {}
    for l in lines:
        t = l.text
        for kind, rx in DATE_PATTERNS[:4]:
            for m in rx.finditer(t):
                rd = RawDate(kind, m.groupdict(), m.end(), m.group(0))
                if not rd.parts.get("y") or (kind in ("dmon", "mond") and len(rd.parts["y"]) == 2):
                    continue          # 'Dec 30 Dec 30' must not become 30 Dec 2030
                if kind in ("dmon", "mond") and rd.parts["mon"].lower() not in MONTH_OF:
                    continue
                d = resolve(rd, order, None)
                if d and 1990 < d.year < 2100:
                    seen.setdefault(d, set()).add(l.page)
                    if best is None or d > best:
                        best = d
    pages = max((l.page for l in lines), default=1)
    if pages >= 2:
        common = [d for d, ps in seen.items() if len(ps) >= max(2, pages / 2)]
        if common:
            return max(common)
    return best


# ---------------------------------------------------------------- the table header

@dataclass
class Col:
    role: str
    x0: float
    x1: float
    label: str


def _cells(line: Line) -> list[tuple[str, float, float]]:
    out = []
    for m in re.finditer(r"\S+(?: \S+)*", line.text):
        a, b = line.span(m.start(), m.end())
        out.append((m.group(0), a, b))
    return out


def _role(label: str) -> str | None:
    low = " " + re.sub(r"[()$€£+\-−:]", " ", label.lower()) + " "
    for role, words in ROLE_WORDS:
        for w in words:
            if f" {w} " in low or (len(w) > 4 and w in low):
                return role
    return None


def find_header(lines: list[Line], i: int) -> list[Col] | None:
    """A table header: a date word plus money words, or at least two money words one of them a balance.
    Read word by word, because headers are often printed with single spaces between columns."""
    line = lines[i]
    if re.search(r"\d[.,]\d{2}(?!\d)", line.text):
        return None                  # a line carrying money is a row or a summary, never a header
    size = line.size or 8
    groups: list[list] = []          # [role, x0, x1, label]
    has_date = False
    for m in re.finditer(r"\S+", line.text):
        word = m.group(0)
        a, b = line.span(m.start(), m.end())
        r = _role(word)
        if r is None and any(re.match(rf"{w}", word.lower()) for w in DATE_WORDS):
            r = "date"
        g = groups[-1] if groups else None
        if g and a - g[2] < size * 1.2 and (r is None or g[0] is None or r == g[0]):
            g[2], g[3] = b, g[3] + " " + word
            if g[0] is None and r:
                g[0], g[1] = r, a        # the column starts at the word that names it
        else:
            groups.append([r, a, b, word])
    cols = []
    for r, a, b, label in groups:
        if r == "date":
            has_date = True
        elif r:
            cols.append(Col(r, a, b, label))
    roles = {c.role for c in cols}
    if not cols or not (has_date or (len(roles) >= 2 and "balance" in roles)):
        return None
    # a header word that names a money column must sit well to the right of the line start
    if max(c.x1 for c in cols) < line.x0 + 150:
        return None
    return cols


DESC_WORDS = ("description", "descriptions", "details", "detail", "particulars", "narration", "narrative",
              "merchant", "transaction", "payee", "memo", "libellé", "libelle", "détails", "omschrijving",
              "descripción", "descripcion", "concepto", "beschreibung", "verwendungszweck", "remarks",
              "counterparty", "beneficiary", "tegenpartij", "naam")


def header_desc_span(line: Line) -> tuple[float, float] | None:
    """The description column, judged from the header: it starts where the header word before it
    ends (headers are often centred over a wide column) and stops halfway to the next header word."""
    words = [(m.group(0), *line.span(m.start(), m.end())) for m in re.finditer(r"\S+", line.text)]
    first = last = None
    for k, (w, a, b) in enumerate(words):
        lw = w.lower().strip("():.")
        if lw in DESC_WORDS or (first is not None and lw in ("name", "or", "of", "and", "/", "&")):
            first = k if first is None else first
            last = k
        elif first is not None:
            break
    if first is None:
        return None
    lo = words[first - 1][2] + 0.5 if first > 0 else -1e9
    hi = words[last + 1][1] - 3 if last + 1 < len(words) else 1e9
    return lo, hi


# ---------------------------------------------------------------- reading one statement

def _assign(cols: list[Col], x1: float) -> Col | None:
    best = min(cols, key=lambda c: abs(c.x1 - x1))
    # numbers sit right-aligned under their header, allow a column's width of slack
    width = max(40.0, best.x1 - best.x0)
    return best if abs(best.x1 - x1) <= width + 25 else None


def _amounts(line: Line, loc: Locale, start: int):
    for m in loc.money.finditer(line.text, start):
        a, b = line.span(m.start("num"), m.end())
        yield m, loc.value(m), a, b


def _has_words(line: Line, words) -> bool:
    low = line.text.lower()
    return any(w in low for w in words)


def _summary_amount(line: Line, loc: Locale) -> Decimal | None:
    vals = [v for _, v, _, _ in _amounts(line, loc, 0)]
    return vals[-1] if vals else None


def read_statement(path: str) -> Result:
    res = Result(path=str(path))
    try:
        pdf = pdfplumber.open(path)
    except Exception as e:  # noqa: BLE001
        chain, x = [], e
        while x is not None and len(chain) < 6:
            chain.append(type(x).__name__ + " " + repr(getattr(x, "args", "")))
            x = x.__cause__ or x.__context__
        why = " ".join(chain).lower()
        res.status = "encrypted" if ("password" in why or "encrypt" in why) else "unreadable"
        res.problems.append(f"could not open: {type(e).__name__}")
        return res
    with pdf:
        res.pages = len(pdf.pages)
        lines: list[Line] = []
        image_pages = 0
        for n, page in enumerate(pdf.pages, 1):
            lines += page_lines(page.filter(_upright), n)
            area = sum(abs((i["x1"] - i["x0"]) * (i["bottom"] - i["top"])) for i in page.images)
            if area > 0.3 * page.width * page.height:
                image_pages += 1
    if not lines:
        res.status = "needs_ocr"
        res.problems.append("no text layer, this is a scan")
        return res

    full = "\n".join(l.text for l in lines)
    low = full.lower()
    loc = guess_locale(full)
    res.kind = "card" if sum(1 for h in CARD_HINTS if re.search(rf"\b{h}\b", low)) >= 2 else "bank"
    hint_us = ("$" in full and loc.decimal == "." and "cad" not in low) or "usd" in low

    # first pass: where the table header is, and every leading date
    raws = []
    for l in lines:
        ds, pos = leading_dates(l.text)
        # only lines that look like transactions vote on day/month order, not calendars or footers
        if ds and any(True for _ in _amounts(l, loc, pos)):
            raws += ds
    order = pick_order(raws, hint_us)
    if not any(r.kind in ("num3", "num2") for r in raws):
        # the rows print month names; let any numeric date elsewhere settle day/month order
        every = [RawDate("num3", m.groupdict(), m.end(), m.group(0))
                 for l in lines for m in DATE_PATTERNS[1][1].finditer(l.text)]
        order = pick_order(every, hint_us)
    end = statement_end(lines, order)

    # summary figures, read from anywhere in the document
    dated_bal: list[tuple[date, Decimal]] = []
    doc_totals = []
    for j, l in enumerate(lines):
        if find_header([l], 0):
            continue
        for role, v, n in section_totals(l, loc):
            doc_totals.append((None, role, v, n))
        if (_has_words(l, OPENING_WORDS) or _has_words(l, CLOSING_WORDS)) and _summary_amount(l, loc) is None:
            for nxt in lines[j + 1: j + 4]:
                vals = list(_amounts(nxt, loc, 0))
                if nxt.page != l.page or not vals:
                    continue
                lt = l.text.lower()
                for words, attr in ((OPENING_WORDS, "opening"), (CLOSING_WORDS, "closing")):
                    hit = next((w for w in words if w in lt), None)
                    if hit and getattr(res, attr) is None:
                        kx = l.xs[lt.index(hit)][0]
                        setattr(res, attr, min(vals, key=lambda v: abs(v[2] - kx))[1])
                break
            continue
        if _has_words(l, OPENING_WORDS) and res.opening is None:
            res.opening = _summary_amount(l, loc)
        elif _has_words(l, CLOSING_WORDS) and res.closing is None:
            res.closing = _summary_amount(l, loc)
        elif re.search(r"\bbalance (as of|at|on)\b|\bsaldo (per|op)\b", l.text.lower()):
            v = _summary_amount(l, loc)
            m = re.search(r"(?:as of|at|on|per|op)\s+(.+?)[:\s]", l.text, re.I)
            d = None
            if m:
                rd = match_date_at(m.group(1), 0)
                d = resolve(rd, order, end) if rd else None
            if v is not None and d:
                dated_bal.append((d, v))
    if dated_bal and (res.opening is None or res.closing is None):
        dated_bal.sort()
        if res.opening is None:
            res.opening = dated_bal[0][1]
        if res.closing is None and len(dated_bal) > 1:
            res.closing = dated_bal[-1][1]

    # second pass: rows
    cols: list[Col] | None = None
    account = ""
    second_is_trans = False
    cur: Txn | None = None
    totals: list[tuple[str, str, Decimal, int | None]] = []
    buf: list[Line] = []             # undated text lines waiting to be given to a row
    pre_k: int | None = None         # how many description lines a row prints ABOVE its date line
    desc_x: float | None = None
    last_page = 0
    cur_top = 0.0
    hdr_desc: tuple[float, float] | None = None
    account_open: dict[str, Decimal] = {}
    account_close: dict[str, Decimal] = {}

    def bounds() -> tuple[float, float]:
        if desc_right():
            return hdr_desc[0], hdr_desc[1]
        hi = min(c.x0 for c in cols) - 2 if cols else 1e9
        if hdr_desc:
            return hdr_desc[0], min(hi, hdr_desc[1])
        return (desc_x - 3 if desc_x is not None else -1e9), hi

    def desc_right() -> bool:
        # some credit unions print the description after the balance column
        return bool(hdr_desc and cols and hdr_desc[0] > max(c.x0 for c in cols))

    def part(line: Line, start: int = 0, stop: int | None = None) -> str:
        # only the text inside the description column belongs to the description
        return part_x(line, start, stop)[0]

    def part_x(line: Line, start: int = 0, stop: int | None = None) -> tuple[str, float, float]:
        """The description text on a line, where it ends, and the width of one of its characters."""
        lo, hi = bounds()
        stop = len(line.text) if stop is None else stop
        kept = [(w, a, e) for w, a, e in _words(line, start, stop, ends=True) if lo <= a < hi]
        if not kept:
            return "", 0.0, 0.0
        text = " ".join(w for w, _, _ in kept)
        span = kept[-1][2] - kept[-1][1]
        return text, kept[-1][2], span / max(1, len(kept[-1][0]))

    def outside(line: Line, start: int, stop: int) -> str:
        # text in this row that sits in some other non-money column: cheque numbers, branch codes
        lo, hi = bounds()
        return " ".join(w for w, a in _words(line, start, stop) if not (lo <= a < hi))

    def flush(to: Txn | None, items: list[Line]):
        if to is None:
            return
        for b in items:
            p_ = part_x(b)
            if p_[0]:
                to.parts.append(p_)

    for i, l in enumerate(lines):
        if l.page != last_page:
            flush(cur, buf); buf = []; last_page = l.page
        h = find_header(lines, i)
        if h:
            flush(cur, buf); buf = []
            cols, cur = h, None
            hdr_desc = header_desc_span(l)
            for back in reversed(lines[max(0, i - 6): i]):
                if back.page == l.page and ACCOUNT_RE.search(back.text):
                    name = re.sub(r"\s*\((continued|suite|cont\.?)\)\s*$", "", back.text.strip(), flags=re.I)
                    account = re.sub(r"\s{2,}", " ", name)
                    break
            lt = l.text.lower()
            second_is_trans = "trans" in lt and lt.find("trans") > lt.find("date") >= 0
            continue
        if not cols:
            continue
        ds, pos = leading_dates(l.text)
        placed = []
        for m, v, a, b in _amounts(l, loc, pos if ds else 0):
            c = _assign(cols, b)
            if c:
                placed.append((c, v, l.span(m.start(), m.start() + 1)[0], m))
        if ds and placed and l.x0 < cols[0].x0:
            amt, bal = None, None
            loan = any(c.role == "loan" for c, *_ in placed) or (
                {c.role for c in cols} <= {"balance", "loan"} and len(cols) > 1)
            for c, v, a, m in placed:
                if c.role == "loan":
                    continue
                if c.role == "balance":
                    bal = v
                elif c.role == "debit":
                    amt = -abs(v) if amt is None else amt
                elif c.role == "credit":
                    amt = abs(v) if amt is None else amt
                else:
                    amt = v if amt is None else amt
            if amt is not None and all(c.role != "debit" and c.role != "credit" for c, *_ in placed):
                first_a = min(a for _, _, a, _ in placed)
                mark = re.findall(r"(?<![\w/])(CR|DR|Cr|Dr|C|D)(?![\w/])",
                                  " ".join(w for w, a in _words(l, pos, _char_at(l, first_a))))
                if mark:
                    amt = abs(amt) if mark[-1].upper().startswith("C") else -abs(amt)
            note = ""
            if loan and bal is not None and not _has_words(l, OPENING_WORDS + CLOSING_WORDS):
                # a loan section prints interest, payment and disbursement; what moves the balance is
                # the principal, so the amount is the change in what is owed, labelled as such
                before = next((t.balance for t in reversed(res.txns) if t.account == account
                               and t.balance is not None), account_open.get(account))
                if before is not None:
                    amt, note = bal - before, "loan: change in amount owed"
            if amt is None and bal is not None and not _has_words(l, OPENING_WORDS + CLOSING_WORDS) \
                    and re.search(r"[A-Za-z]{3}", l.text[pos:_char_at(l, min(a for _, _, a, _ in placed))]):
                # a described row with a balance and no amount: a failed or informational entry.
                # Kept as 0.00 so it is not silently lost.
                amt, note = Decimal(0), "no amount printed"
            if _has_words(l, CLOSING_WORDS):
                # an 'Ending Balance' row: its debit and credit figures are the account's totals
                for c, v, _, _ in placed:
                    if c.role in ("debit", "credit"):
                        totals.append((account, c.role, abs(v), None))
                if bal is not None:
                    account_close[account] = bal
                flush(cur, buf); buf = []; cur = None
                continue
            if amt is None or _has_words(l, OPENING_WORDS):
                # a dated line carrying only a balance is a balance row, not a transaction
                if bal is not None and _has_words(l, OPENING_WORDS):
                    account_open.setdefault(account, bal)
                    if res.opening is None:
                        res.opening = bal
                continue
            first_amt = min(a for _, _, a, _ in placed)
            cut = _char_at(l, first_amt)
            if desc_x is None:
                desc_x = l.xs[pos][0] if pos < len(l.xs) else l.x0
            if desc_right():
                after = max(m.end() for _, _, _, m in placed)
                desc_px = part_x(l, after, len(l.text))
            else:
                desc_px = part_x(l, pos, cut)
            desc = desc_px[0]
            ref = outside(l, pos, cut)
            ref = re.sub(r"(?<![\w/])(CR|DR|Cr|Dr)(?![\w/])", "", ref).strip()
            skipped = l.text[: len(l.text) - len(l.text.lstrip())]
            lead = l.text[len(skipped): l.text.find(ds[0].text, len(skipped))].strip() if ds else ""
            if lead:
                ref = (lead + " " + ref).strip()
            if not desc and re.search(r"[A-Za-z]{3}", ref):
                desc, ref = ref, ""          # the header was not where the text is; keep the text
                desc_px = (desc, 0.0, 0.0)
            cand = [b for b in buf if part(b)]
            if pre_k is None:
                pre_k = len(cand) if not res.txns else 0
            k = min(pre_k, len(cand))
            if cand and not pre_k and cur is not None and cur.page == l.page:
                # lines sitting closer to this row than to the one above belong to this row
                gap_above = l.top - cur_top
                near = sum(1 for b in cand if (l.top - b.top) < (b.top - cur_top) - 0.15 * gap_above)
                k = max(k, near)
            if not desc and cand:
                # nothing printed beside the date: the row's text sits just above it, so take the
                # lines that are closer to this date line than to the row above
                prev_top = cur_top if (cur is not None and cur.page == l.page) else -1e9
                k = max(k, sum(1 for b in cand if (l.top - b.top) < (b.top - prev_top)))
            if not desc and not k and not re.search(r"[A-Za-z]{3}", ref):
                # a date and money with no words at all is a summary line, not a transaction;
                # if it really was one, the running balance will break and say so
                continue
            flush(cur, cand[: len(cand) - k])
            above = [part_x(b) for b in cand[len(cand) - k:]]
            buf = []
            d1 = resolve(ds[0], order, end)
            d2 = resolve(ds[1], order, end) if len(ds) > 1 else None
            cur = Txn(d2 if (second_is_trans and d2) else d1, "", amt, bal, l.page,
                      raw_date=" ".join(r.text for r in ds), date_2=d1 if (second_is_trans and d2) else d2,
                      account=account)
            cur.note = note
            cur.ref = ref
            cur.parts = [x for x in above + [desc_px] if x[0]]
            res.txns.append(cur)
            cur_top = l.top
            continue
        # a line with no date
        if _has_words(l, OPENING_WORDS):
            bals = [v for c, v, _, _ in placed if c.role == "balance"] or [v for c, v, _, _ in placed]
            if bals and res.opening is None:
                res.opening = bals[-1]
            continue
        low_l = l.text.lower().strip()
        for role, v, n in section_totals(l, loc):
            if any(t.account == account and t.page == l.page for t in res.txns):
                totals.append((account, role, v, n))   # only beside the rows it totals
        if any(low_l.startswith(w) or f" {w}" in low_l for w in STOP_WORDS) or _has_words(l, CLOSING_WORDS):
            flush(cur, buf); buf = []; cur = None
            continue
        if placed:
            if all(v == 0 for _, v, _, _ in placed):
                continue                      # an informational zero line, not part of any row
            flush(cur, buf); buf = []; cur = None   # money on an undated line ends the row
            continue
        if l.size and i and not find_header(lines, i - 1) and abs(l.top - _prev_top(lines, i)) > 3.2 * l.size:
            flush(cur, buf); buf = []; cur = None   # too far below the line above to belong to it
            continue
        text = l.text.strip()
        if text and not re.fullmatch(r"[\d\s/.\-]+", text) and len(text) < 120:
            buf.append(l)
    flush(cur, buf)

    _join_descriptions(res.txns)
    if not res.txns:
        res.status = "no_table"
        if image_pages:
            res.status = "needs_ocr"
            res.problems.append(f"no transaction table in the text, and {image_pages} page(s) are mostly a picture;"
                                " the statement is probably an image")
        else:
            res.problems.append("no transaction table found")
        return res
    res.period = statement_period(lines, order, end)
    _check(res, totals + doc_totals, account_open, account_close)
    _check_dates(res)
    return res


PERIOD_RE = re.compile(r"(?P<a>\S+(?: \S+){0,2}?)\s*(?:-|–|—|to|au|al|bis|tot|through)\s*(?P<b>\S+(?: \S+){0,2})", re.I)


def statement_period(lines: list[Line], order: str, end: date | None) -> tuple[date, date] | None:
    """The first 'date - date' or 'date to date' pair printed in the document."""
    for l in lines:
        t = l.text
        for k in range(len(t)):
            if k and t[k - 1].isalnum():
                continue
            a = match_date_at(t, k)
            if not a or (not a.parts.get("y") and a.kind not in ("dmon", "mond")):
                continue
            rest = re.match(r"\s*(?:-|–|—|to|au|al|bis|tot|through|thru|until)\s*", t[a.end:], re.I)
            if not rest:
                continue
            b = match_date_at(t, a.end + rest.end())
            if not b:
                continue
            db = resolve(b, order, end)
            da = resolve(a, order, db or end)
            if da and db and da < db and (db - da).days <= 400 and \
                    (end is None or -7 <= (end - db).days <= 45):
                return da, db
    return None


def _check_dates(res: Result) -> None:
    missing = [k + 1 for k, t in enumerate(res.txns) if t.date is None]
    if missing:
        res.problems.append(f"dates: {len(missing)} row(s) have a date that could not be read (rows {missing[:8]})")
        res.status = "unbalanced" if res.status == "ok" else res.status
    if res.period:
        a, b = res.period
        out = [k + 1 for k, t in enumerate(res.txns)
               if t.date and not (a.toordinal() - 35 <= t.date.toordinal() <= b.toordinal() + 3)]
        if out:
            res.problems.append(f"dates: {len(out)} row(s) fall outside the statement period {a} to {b} (rows {out[:8]})")
            res.status = "unbalanced" if res.status == "ok" else res.status
        elif not missing:
            res.checks.append(f"dates: all {len(res.txns)} rows fall inside the statement period {a} to {b}")
    elif not missing:
        ds = [t.date for t in res.txns]
        back = sum(1 for x, y, t1, t2 in zip(ds, ds[1:], res.txns, res.txns[1:])
                   if y < x and t1.account == t2.account)
        span = (max(ds) - min(ds)).days
        if back or span > 62:
            res.problems.append(f"dates: no statement period printed, and the rows run from {min(ds)} to {max(ds)}"
                                f" with {back} step(s) backwards; check the day/month order")
            res.status = "unbalanced" if res.status == "ok" else res.status
        else:
            res.checks.append(f"dates: no statement period printed; rows run in order from {min(ds)} to {max(ds)}")


ACCOUNT_RE = re.compile(r"(account|compte|cuenta|rekening|konto)\b.*\d{3,}|^\s*\d{2,4}:\s+\S", re.I)
TOTAL_RE = re.compile(
    r"(?:\btotal\s+(?:no\.?\s+of\s+)?|^\s*(?P<n>\d{1,4})\s+)"
    r"(?:(?P<cr>deposits?(?:\s*/\s*credits?)?|credits?|crédits?|dépôts?(?: et crédits)?|money in|paid in|incoming|abonos?)"
    r"|(?P<dr>withdrawals?|checks?\s*/\s*debits?|cheques?\s*/\s*debits?|debits?|débits?|money out|paid out|outgoing|cargos?|retraits?))"
    r"(?:\s+amount)?(?:\s*\((?P<n2>\d{1,4})\))?", re.I)


def section_totals(line: Line, loc: Locale):
    """'Total deposits 533.79', '8 Deposits/Credits 3,782.09' or 'Total Débits (18) 6 886,21 $':
    each keyword paired with the first amount after it, and the row count when one is printed."""
    hits = list(TOTAL_RE.finditer(line.text))
    for k, m in enumerate(hits):
        stop = hits[k + 1].start() if k + 1 < len(hits) else len(line.text)
        n = m.group("n") or m.group("n2")
        for mm in loc.money.finditer(line.text[:stop], m.end()):
            yield ("credit" if m.group("cr") else "debit"), abs(loc.value(mm)), (int(n) if n else None)
            break


def _join_descriptions(txns: list[Txn]) -> None:
    """Join each row's description lines. Some statements break a long word across two lines;
    such a line runs to the very edge of the column, so a line ending within a character of the
    furthest edge seen is glued to the next without a space."""
    ends = [(e, w) for t in txns for _, e, w in t.parts[:-1] if e]
    edge = max(e for e, _ in ends) if len(ends) >= 5 else None
    if edge is not None and sum(1 for e, w in ends if e >= edge - 0.6 * (w or 5)) < 3:
        edge = None                   # one long line is not a column edge; several reaching it are
    for t in txns:
        out = ""
        for k, (p, _, _) in enumerate(t.parts):
            prev = t.parts[k - 1] if k else None
            if not out:
                out = p
            elif edge and prev[1] >= edge - 0.6 * (prev[2] or 5) and out[-1].isalnum() and p[0].isalnum():
                out += p
            else:
                out += " " + p
        t.description = re.sub(r"\s{2,}", " ", out).strip()


def _words(line: Line, start: int, stop: int, ends: bool = False):
    for m in re.finditer(r"\S+", line.text[start:stop]):
        a = line.xs[start + m.start()][0]
        yield (m.group(0), a, line.xs[start + m.end() - 1][1]) if ends else (m.group(0), a)


def _char_at(line: Line, x: float) -> int:
    for k, (a, _) in enumerate(line.xs):
        if a >= x - 0.01:
            return k
    return len(line.text)


def _prev_top(lines: list[Line], i: int) -> float:
    return lines[i - 1].top if i else lines[i].top


# ---------------------------------------------------------------- checking the numbers

CENT = Decimal("0.01")


def _check(res: Result, totals=(), account_open=None, account_close=None) -> None:
    account_open, account_close = account_open or {}, account_close or {}
    txns = res.txns
    accounts = list(dict.fromkeys(t.account for t in txns))
    has_bal = [t for t in txns if t.balance is not None]
    breaks = 0
    if has_bal:
        # card balances count money owed, so a purchase raises the balance
        sign = 1
        prev = res.opening
        votes = {1: 0, -1: 0}
        p = res.opening
        for t in txns:
            if t.balance is None:
                continue
            if p is not None:
                for s in (1, -1):
                    if abs(p + s * t.amount - t.balance) < CENT:
                        votes[s] += 1
            p = t.balance
        sign = 1 if votes[1] >= votes[-1] else -1
        acct = txns[0].account
        if acct in account_open:
            prev = account_open[acct]
        for k, t in enumerate(txns):
            if t.account != acct:
                acct, prev = t.account, account_open.get(t.account)
            if t.balance is None:
                continue
            if prev is None:
                t.check = ""
            elif abs(prev + sign * t.amount - t.balance) < CENT:
                t.check = "ok"
            else:
                # the column was misread but the balance moved by the same size: trust the balance
                delta = (t.balance - prev) * sign
                if abs(abs(delta) - abs(t.amount)) < CENT:
                    t.amount = delta
                    t.check = "ok (direction from balance)"
                else:
                    t.check = "break"
                    breaks += 1
                    res.problems.append(
                        f"row {k + 1} ({t.raw_date} {t.description[:40]}): balance {t.balance} "
                        f"does not follow from {prev} and {t.amount}")
            prev = t.balance
        okc = sum(1 for t in txns if t.check.startswith("ok"))
        unc = sum(1 for t in has_bal if not t.check)
        res.checks.append(f"running balance: {okc} of {len(has_bal)} rows follow from the row above"
                          + (f" ({unc} first row(s) of an account had nothing above to check against)" if unc else ""))
        if res.closing is None and len(accounts) == 1:
            res.closing = has_bal[-1].balance
    for acct, close in account_close.items():
        rows = [t for t in txns if t.account == acct and t.balance is not None]
        if rows and rows[-1].balance == close:
            res.checks.append(f"{acct or 'the statement'}: last row's balance equals the printed ending balance {close}")
        elif rows:
            res.problems.append(f"{acct or 'the statement'}: last row's balance {rows[-1].balance} is not the printed "
                                f"ending balance {close}")
            breaks += 1
    seen_tot = set()
    for acct, role, want, n in totals:
        if acct is None and len(accounts) > 1:
            continue                  # a document-wide total cannot be pinned to one of several accounts
        if (acct or "", role) in seen_tot:
            continue
        seen_tot.add((acct or "", role))
        rows = [t for t in txns if (acct is None or t.account == acct) and t.direction == role]
        got = sum((abs(t.amount) for t in rows), Decimal(0))
        name = acct or "the statement"
        counted = f" ({len(rows)} rows)" if n is None else f" ({len(rows)} rows, the statement says {n})"
        if abs(got - want) < CENT and (n is None or n == len(rows)):
            res.checks.append(f"{name}: {role}s add up to the printed total {want}{counted}")
        else:
            missing = f"; {n - len(rows)} {role} row(s) are missing, often a page left out of the PDF" \
                if n and n > len(rows) else ""
            res.problems.append(f"{name}: {role}s add up to {got}{counted}, the statement prints {want}{missing}")
            breaks += 1
    total = sum((t.amount for t in txns), Decimal(0))
    if res.opening is not None and res.closing is not None and len(accounts) == 1:
        ok_bank = abs(res.opening + total - res.closing) < CENT
        ok_card = abs(res.opening - total - res.closing) < CENT
        if ok_card and not ok_bank:
            res.kind = "card"
        if res.kind == "card" and ok_bank and not ok_card and not has_bal:
            # the card printed purchases as positive: turn them into money out
            for t in txns:
                t.amount = -t.amount
            total = -total
        if ok_bank or ok_card:
            res.checks.append(f"totals: opening {res.opening} and the {len(txns)} rows give closing {res.closing}")
        else:
            gap = (res.closing - res.opening - total) if res.kind == "bank" else (res.opening - total - res.closing)
            res.problems.append(f"totals: opening {res.opening} plus the rows does not reach closing {res.closing} (off by {gap})")
            breaks += 1
    if breaks:
        res.status = "unbalanced"
    elif not res.checks:
        res.status = "unchecked"
        res.problems.append("no balance or totals printed, nothing to check the rows against")
