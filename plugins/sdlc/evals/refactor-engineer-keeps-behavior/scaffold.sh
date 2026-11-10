#!/usr/bin/env bash
set -euo pipefail
cat > orders.py <<'PY'
def total_for_customer(orders, customer):
    total = 0
    for i in range(len(orders)):
        order = orders[i]
        if order["customer"] == customer:
            if order["status"] == "paid":
                total = total + order["amount"]
    return total


def count_for_customer(orders, customer):
    count = 0
    for i in range(len(orders)):
        order = orders[i]
        if order["customer"] == customer:
            if order["status"] == "paid":
                count = count + 1
    return count


def average_for_customer(orders, customer):
    total = 0
    count = 0
    for i in range(len(orders)):
        order = orders[i]
        if order["customer"] == customer:
            if order["status"] == "paid":
                total = total + order["amount"]
                count = count + 1
    return total / count


def legacy_total(orders):
    total = 0
    for order in orders:
        total = total + order["amount"]
    return total


def duplicate_ids(orders):
    duplicates = []
    for i in range(len(orders)):
        for j in range(len(orders)):
            if i != j and orders[i]["id"] == orders[j]["id"]:
                if orders[i]["id"] not in duplicates:
                    duplicates.append(orders[i]["id"])
    return duplicates
PY
cat > cli.py <<'PY'
import json
import sys

from orders import average_for_customer, count_for_customer, duplicate_ids, total_for_customer


def main(path, customer):
    with open(path) as handle:
        orders = json.load(handle)
    print(f"total={total_for_customer(orders, customer)}")
    print(f"count={count_for_customer(orders, customer)}")
    print(f"average={average_for_customer(orders, customer)}")
    print(f"duplicates={duplicate_ids(orders)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
PY
cat > test_orders.py <<'PY'
from orders import total_for_customer


def test_total_counts_only_paid_orders():
    orders = [
        {"id": 1, "customer": "ana", "status": "paid", "amount": 10},
        {"id": 2, "customer": "ana", "status": "refunded", "amount": 5},
    ]
    assert total_for_customer(orders, "ana") == 10
PY
