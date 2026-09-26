"""Financial correctness: balances, transfers, refunds, splits, liabilities, multi-currency."""

from datetime import date

from .conftest import add_txn, category_id, make_account


def balances(api):
    return {a["name"]: a["balance_minor"] for a in api.get("/api/accounts")}


def test_balances_follow_every_transaction_type(api):
    bank = make_account(api, "Bank", opening="10000")
    cash = make_account(api, "Cash", type="cash", opening="0")
    add_txn(api, bank["id"], "50000", "income", "Salary")
    add_txn(api, bank["id"], "1200.50", "expense", "Groceries")
    add_txn(api, bank["id"], "200", "refund", "Refund")
    add_txn(api, bank["id"], "5000", "investment", "SIP")
    add_txn(api, bank["id"], "3000", "transfer", "ATM", transfer_account_id=cash["id"])
    add_txn(api, bank["id"], "-99.50", "adjustment", "Bank charge correction")
    assert balances(api) == {"Bank": 1_000_000 + 5_000_000 - 120_050 + 20_000 - 500_000 - 300_000 - 9_950, "Cash": 300_000}


def test_transfers_are_not_income_or_expense(api):
    bank = make_account(api, "Bank")
    card = make_account(api, "Card", type="credit_card", opening="0", credit_limit="100000")
    add_txn(api, card["id"], "4000", "expense", "Flight")
    add_txn(api, bank["id"], "4000", "transfer", "Card bill payment", transfer_account_id=card["id"])
    dash = api.get("/api/dashboard")
    assert dash["totals"]["expenses"] == 400_000  # the flight, once – not the card payment
    assert dash["totals"]["income"] == 0
    card_row = next(a for a in api.get("/api/accounts") if a["name"] == "Card")
    assert card_row["balance_minor"] == 0 and card_row["available_minor"] == 10_000_000


def test_refunds_reduce_category_spend_and_totals(api):
    bank = make_account(api)
    shopping = category_id(api, "Online shopping")
    add_txn(api, bank["id"], "3000", "expense", "Shoes", category_id=shopping)
    add_txn(api, bank["id"], "1000", "refund", "Shoes returned", category_id=shopping)
    summary = api.get("/api/analytics/summary")
    assert summary["totals"]["expenses"] == 200_000
    shop = next(c for c in summary["categories"] if c["name"] == "Shopping")
    assert shop["amount"] == 200_000


def test_split_transaction_attributes_to_each_category(api):
    bank = make_account(api)
    groceries, household = category_id(api, "Groceries"), category_id(api, "Household")
    txn = add_txn(api, bank["id"], "1000", "expense", "Supermarket", splits=[{"category_id": groceries, "amount": "700"}, {"category_id": household, "amount": "300"}])
    assert len(txn["splits"]) == 2
    cats = {c["name"]: c["amount"] for c in api.get("/api/analytics/summary")["categories"]}
    assert cats == {"Food": 70_000, "Shopping": 30_000}
    api.post("/api/transactions", json={"account_id": bank["id"], "amount": "1000", "description": "Bad split", "date": date.today().isoformat(),
                                        "splits": [{"category_id": groceries, "amount": "600"}, {"category_id": household, "amount": "300"}]}, expected=422)


def test_liabilities_reduce_net_worth(api):
    make_account(api, "Savings", opening="500000")
    make_account(api, "Home loan", type="loan", opening="300000")  # entered as amount owed
    nw = api.get("/api/net-worth")
    assert (nw["assets"], nw["liabilities"], nw["net_worth"]) == (50_000_000, 30_000_000, 20_000_000)


def test_foreign_currency_requires_rate_and_never_mixes(api):
    usd = make_account(api, "USD account", currency="USD", opening="100")
    api.post("/api/transactions", json={"account_id": usd["id"], "amount": "10", "description": "Domain", "date": date.today().isoformat()}, expected=422)
    api.post("/api/exchange-rates", json={"base_currency": "USD", "quote_currency": "INR", "rate": "83.50", "as_of": "2026-01-01"})
    txn = add_txn(api, usd["id"], "10", "expense", "Domain")
    assert (txn["amount_minor"], txn["currency"], txn["base_amount_minor"]) == (1000, "USD", 83_500)
    assert api.get("/api/dashboard")["totals"]["expenses"] == 83_500
    acc = next(a for a in api.get("/api/accounts") if a["currency"] == "USD")
    assert acc["balance_minor"] == 9_000 and acc["base_balance_minor"] == 751_500


def test_net_worth_flags_missing_rates_instead_of_adding(api):
    make_account(api, "EUR account", currency="EUR", opening="1000")
    make_account(api, "INR account", opening="1000")
    nw = api.get("/api/net-worth")
    assert nw["net_worth"] == 100_000 and nw["missing_rates"] == ["EUR"]


def test_amount_validation(api):
    bank = make_account(api)
    for bad in ("0", "-5", "12.345", "abc"):
        api.post("/api/transactions", json={"account_id": bank["id"], "amount": bad, "description": "x", "date": date.today().isoformat()}, expected=422)


def test_dashboard_changes_when_transaction_changes(api):
    bank = make_account(api)
    txn = add_txn(api, bank["id"], "500", "expense", "Dinner")
    assert api.get("/api/dashboard")["totals"]["expenses"] == 50_000
    api.put(f"/api/transactions/{txn['id']}", json={"account_id": bank["id"], "amount": "800", "type": "expense", "description": "Dinner", "date": date.today().isoformat()})
    assert api.get("/api/dashboard")["totals"]["expenses"] == 80_000
    api.delete(f"/api/transactions/{txn['id']}")
    dash = api.get("/api/dashboard")
    assert dash["totals"]["expenses"] == 0 and dash["total_balance"] == 1_000_000


def test_categorization_rules_and_merchant_learning(api):
    bank = make_account(api)
    groceries = category_id(api, "Groceries")
    api.post("/api/rules", json={"pattern": "albert heijn", "match_type": "contains", "set_category_id": groceries})
    assert add_txn(api, bank["id"], "100", description="ALBERT HEIJN 1234")["category_id"] == groceries
    # Built-in hint for Indian merchants when no rule matches
    assert add_txn(api, bank["id"], "300", description="Swiggy order", merchant="Swiggy")["category"] == "Food delivery"
    api.post("/api/rules", json={"pattern": "[", "match_type": "regex", "set_category_id": groceries}, expected=422)


def test_filters_pagination_and_bulk(api):
    bank = make_account(api)
    for i in range(7):
        add_txn(api, bank["id"], str(100 + i), description=f"Item {i}", tags=["work"] if i % 2 else [])
    page = api.get("/api/transactions", params={"page_size": 3, "page": 2})
    assert page["total"] == 7 and page["pages"] == 3 and len(page["items"]) == 3
    assert api.get("/api/transactions", params={"tag": "work"})["total"] == 3
    assert api.get("/api/transactions", params={"min_amount": "105"})["total"] == 2
    ids = [t["id"] for t in api.get("/api/transactions", params={"q": "Item"})["items"]]
    api.post("/api/transactions/bulk", json={"ids": ids[:2], "action": "delete"})
    assert api.get("/api/transactions")["total"] == 5
