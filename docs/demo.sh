cd "$(dirname "$0")/.."; source docs/_say.sh; export PATH="$PWD/.venv/bin:$PATH"; clear
note "three sample statements, one with a balance someone edited"
run "ls examples/statements"
run "statementrows examples/statements --out /tmp/excel"
run "cut -d, -f1-3,5,6 /tmp/excel/riverbend-sep.csv | column -s, -t"
note "the edited row is named, nothing is quietly fixed"
