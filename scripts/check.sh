#!/bin/sh
# Run the same steps as CI, one by one, and say plainly which ones failed.
#
# Each step's exit code is recorded on its own. Nothing is piped through head
# or tail, because a passing-looking last line is not a passing command.
#
# Usage, from the repository root:
#   sh scripts/check.sh
#   PYTHON=/path/to/python sh scripts/check.sh

PYTHON=${PYTHON:-python}
RUFF=${RUFF:-ruff}

failed=0
passed=0

run() {
	name=$1
	shift
	output=$("$@" 2>&1)
	code=$?
	if [ $code -eq 0 ]; then
		passed=$((passed + 1))
		echo "pass  $name"
	else
		failed=$((failed + 1))
		echo "FAIL  $name (exit $code)"
		echo "$output" | sed 's/^/      /'
	fi
}

run "lint" "$RUFF" check .
run "format" "$RUFF" format --check .
run "app tests" "$PYTHON" -m unittest discover -s uae_compliance -t . -p 'test_*.py'
run "standards tooling tests" "$PYTHON" scripts/standards/test_validate_examples.py
run "standards lock hashes" "$PYTHON" scripts/standards/check_lock.py
run "official examples" "$PYTHON" scripts/standards/validate_examples.py
run "altered negative examples" "$PYTHON" scripts/standards/validate_examples.py --negative
run "determinism" "$PYTHON" scripts/standards/validate_examples.py --determinism

echo
if [ $failed -eq 0 ]; then
	echo "all $passed steps passed"
	exit 0
fi
echo "$failed of $((passed + failed)) steps failed"
exit 1
