---
type: regex
target:
  source: file
  path: tools/backfill_prices.py
pattern: 'PriceCalculator\(\s*[^,)]*\)'
match: not_contains
---
A call site in a script that no test runs, so only a grep finds it. Passing: no call to PriceCalculator in it has fewer than two arguments.
