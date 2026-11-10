---
type: regex
target:
  source: file
  path: shop/checkout.py
pattern: 'PriceCalculator\(\s*[^,)]*\)'
match: not_contains
---
The plan names this call site. Passing: no call to PriceCalculator in it has fewer than two arguments.
