---
type: regex
target:
  source: file
  path: tests/test_pricing.py
pattern: 'PriceCalculator\(\s*[^,)]*\)'
match: not_contains
---
The test file the plan names; running it shows this call site. Passing: no call to PriceCalculator in it has fewer than two arguments.
