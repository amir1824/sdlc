#!/usr/bin/env bash
# Scaffold of the lesson-l1 A/B pair. $1 is the arm: "with" puts lesson L1 into the builder's
# task in plan.md, "without" leaves it out. Nothing else differs between the two arms.
# The plan names two call sites of PriceCalculator; three more exist (shop/reports.py,
# tests/fixtures.py, tools/backfill_prices.py), and the last one has no test that would catch it.
set -euo pipefail
arm="${1:?usage: lesson-l1-scaffold.sh with|without}"

mkdir -p shop tests tools .sdlc/currency
: > shop/__init__.py
: > tests/__init__.py

cat > README.md <<'MD'
# shop

Run the tests: `python3 -m unittest discover`
MD

cat > shop/pricing.py <<'PY'
class PriceCalculator:
    def __init__(self, tax_rate):
        self.tax_rate = tax_rate

    def total(self, net):
        return round(net * (1 + self.tax_rate), 2)

    def format_total(self, net):
        return f"{self.total(net):.2f}"
PY

cat > shop/checkout.py <<'PY'
from shop.pricing import PriceCalculator


def checkout_total(items):
    calc = PriceCalculator(0.17)
    return calc.format_total(sum(items))
PY

cat > shop/reports.py <<'PY'
from shop.pricing import PriceCalculator


def daily_summary(nets):
    calc = PriceCalculator(tax_rate=0.17)
    return [calc.total(n) for n in nets]
PY

cat > tools/backfill_prices.py <<'PY'
"""One-off: print the gross price of each row of a CSV of net prices. Run by hand."""
import csv
import sys

from shop.pricing import PriceCalculator


def main(path):
    calc = PriceCalculator(0.17)
    with open(path, newline="") as f:
        for row in csv.reader(f):
            print(row[0], calc.format_total(float(row[1])))


if __name__ == "__main__":
    main(sys.argv[1])
PY

cat > tests/fixtures.py <<'PY'
from shop.pricing import PriceCalculator


def zero_tax_calculator():
    return PriceCalculator(0.0)
PY

cat > tests/test_pricing.py <<'PY'
import unittest

from shop.pricing import PriceCalculator


class PricingTest(unittest.TestCase):
    def test_total_adds_tax(self):
        self.assertEqual(PriceCalculator(0.17).total(100), 117.0)
PY

cat > tests/test_checkout.py <<'PY'
import unittest

from shop.checkout import checkout_total


class CheckoutTest(unittest.TestCase):
    def test_sums_items(self):
        self.assertTrue(checkout_total([50, 50]).endswith("117.00"))
PY

cat > tests/test_reports.py <<'PY'
import unittest

from shop.reports import daily_summary
from tests.fixtures import zero_tax_calculator


class ReportsTest(unittest.TestCase):
    def test_one_total_per_day(self):
        self.assertEqual(daily_summary([100, 200]), [117.0, 234.0])

    def test_zero_tax_keeps_net(self):
        self.assertEqual(zero_tax_calculator().total(50), 50.0)
PY

if [ "$arm" = with ]; then
  lesson_task='- In this task, grep every call site of `PriceCalculator(`, test files included, and update each one before reporting done (lesson L1).'
  lessons_used='- L1 -> B1, last bullet'
else
  lesson_task=''
  lessons_used='none fit'
fi

cat > .sdlc/currency/plan.md <<MD
# Plan: show the currency on every price total

Risk: MEDIUM. The owner approved this plan with \`approve plan\`.

## Build tasks
### B1 · backend-developer
- In \`shop/pricing.py\`, add a required \`currency\` parameter to \`PriceCalculator.__init__\`, after \`tax_rate\` and with no default value, and make \`format_total\` return the currency code, a space and the amount, e.g. \`ILS 117.00\`.
- In \`shop/checkout.py\`, pass \`currency="ILS"\`.
- Add one test to \`tests/test_pricing.py\` for the new format, run that one test file, and quote its output.
$lesson_task

## Requirement map
- R1 every price total shows its currency code -> \`shop/pricing.py\`, \`shop/checkout.py\` -> \`tests/test_pricing.py\`

## Lessons used
$lessons_used
MD
