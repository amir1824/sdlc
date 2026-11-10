---
type: regex
target:
  source: file
  path: tests/fixtures.py
pattern: 'PriceCalculator\(\s*[^,)]*\)'
match: not_contains
---
A call site in a test helper that the plan does not name; only the whole suite or a grep finds it. Passing: no call to PriceCalculator in it has fewer than two arguments.
