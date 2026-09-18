from money.importers.monzo import normalize_transaction as monzo_normalize


def test_monzo_normalize_transaction():
    raw = {
        "id": "tx_00009abcXYZ",
        "created": "2026-08-03T10:15:00.000Z",
        "amount": -450,  # pence, spend
        "description": "ACME COFFEE SHOP",
        "merchant": {"name": "Acme Coffee Shop"},
    }
    norm = monzo_normalize(raw)
    assert norm == {
        "date": "2026-08-03",
        "amount": -4.50,
        "description": "ACME COFFEE SHOP",
        "merchant": "Acme Coffee Shop",
        "external_id": "tx_00009abcXYZ",
    }


def test_monzo_normalize_transaction_no_merchant():
    raw = {
        "id": "tx_00009def",
        "created": "2026-08-04T09:00:00.000Z",
        "amount": 250000,
        "description": "SALARY ACME LTD",
        "merchant": None,
    }
    norm = monzo_normalize(raw)
    assert norm["merchant"] is None
    assert norm["amount"] == 2500.0
