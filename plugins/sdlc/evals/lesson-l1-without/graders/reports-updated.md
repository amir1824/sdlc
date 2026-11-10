---
type: regex
target:
  source: file
  path: shop/reports.py
pattern: 'PriceCalculator\(\s*[^,)]*\)'
match: not_contains
---
A call site in the source that the plan does not name; only the whole suite or a grep finds it. Passing: no call to PriceCalculator in it has fewer than two arguments.
