# StatementRows accuracy record (2026-10-15)

Written on claude-opus-5-5, not Fable 5. Every number here came from a command run in this session, but the conclusions need a re-check on Fable 5.

## What "right" means here

A statement counts as right when all three of these hold:

1. Every row's printed balance follows from the row above it, plus or minus that row's amount, to the cent.
2. The opening balance plus all the rows equals the printed closing balance. Printed totals (for example "8 Deposits/Credits 3,782.09") must also match the rows, both the amount and the count.
3. Every date falls inside the printed statement period. If no period is printed, the dates must run in order and span no more than 62 days.

If any of these fails, the file's status is `unbalanced` and the failing row is named. Nothing is guessed. A scan comes back `needs_ocr`, a locked file `encrypted`, and a broken file `unreadable`.

Mutation proof:
- Loosening the balance tolerance to 1,000,000 fails 3 tests.
- Switching off the date check fails 1 test, even without the local-only samples.
- Ignoring the section heading's sign fails 1 test.
- Dropping the once-a-day balance handling fails 1 test.
- `check.sh` exits 1 in every case (measured directly, not through a pipe).

## First contact: each sample's result before any fix aimed at it

| sample | where from | first contact | now |
|---|---|---|---|
| bsb-001..005 | Bankstatemently open benchmark, MIT (development set) | 3 ok, 1 break (two accounts), 1 no table (French header) | 5/5 ok, row counts equal the benchmark's |
| astra, meridian, northstar | AyonPal parser repo, MIT (held out at first) | numbers 10/10 and 20/20; northstar 8 of 24 rows | 54/54 rows, every field equal to the answer files |
| syn-0042 | Synthesized, CC BY 4.0 | numbers 8/8 and balanced, dates 0/8 (flagged, not guessed) | every field equal to the answer file |
| Five Star Bank sample | five-starbank.com, real bank, local only | 37 rows, 7 lost (an amount read as a date) | 44/44 chain; correctly reports 7 debit rows missing (page 1 of 5) and one printed date "2/30" |
| Builder's Bank sample | docs.landing.ai, local only | 30/30 chain, totals ok | same; correctly reports the printed totals leave out 303.28 of rows |
| CU Answers sample (7 accounts) | credit union software vendor sample, local only | 35/44 chain, accounts mixed | 45/45 chain, all 7 ending balances and totals match; flags 4 out-of-period dates printed in the sample itself |
| AgamiAI Type 1, 4 files | Apache-2.0, answer files | numbers 634/637, descriptions 0 | numbers 637/637, descriptions 601/637 |
| AgamiAI Type 2, 4 files | Apache-2.0, answer files | no table found (serial and id before the date) | numbers 647/647, descriptions 614/647 |
| CFPB handout, OppU card sample | public card examples | no table | no table, which is correct: one is a summary only, the other a template full of $XXX.XX |
| Carson Bank sample | carsonbank.com, real bank, local only | 29 of 47 dates unreadable: one amount in a loan table ("26.08") was read as 26 August and flipped the whole file to day first | dates right; the 8 checks in its check list read; correctly `unbalanced`, because its summary counts 10 deposits and 54 debits against 34 and 21 rows |
| SD Mines admissions sample | university page | no table | not looked at further |
| Niagara Univ. examples, CU Answers style guide | university page, vendor guide | needs_ocr (pictures) | correct |

## The clean holdout: run once, nothing changed afterwards

20 AgamiAI statements (numbers 50 to 59 of both digital layouts), downloaded after the code was frozen:

- 3,251 of 3,251 rows have the exact date, amount and balance from the answer files.
- 3,072 of 3,251 descriptions are exact (94.5%). Most misses are names the PDF breaks across two lines in the middle of a word.
- All 20 come back `unbalanced`, and in every one the rows named are exactly the rows where the dataset's own printed balances fail to add up. The generator plants these inconsistencies; the tool finds all of them and invents none.

## What this does NOT show yet

- **Two real banks' own samples** (Five Star, Carson) and one real credit union layout (CU Answers). Everything else is synthetic. Real Chase, Bank of America or Wells Fargo statements have not been seen. The section layout and the once-a-day balance are tested only on statements built here to imitate them.
- **The holdout tests two layouts the code was tuned on.** It shows consistency within a layout, not coverage of new banks.
- **Scanned statements are refused.** There is no OCR on this machine.
- **Credit card sections inside a combined statement** (the CU sample's page 7) are read, but nothing checks the sign of their amounts.
- **Description accuracy depends on the layout**: about 94% on the two AgamiAI layouts, and 100% on the four other samples that ship answer files (AyonPal x3, Synthesized).
