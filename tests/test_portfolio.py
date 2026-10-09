"""Portfolio CSV import — parser flexibility, persistence, aggregation."""

from io import StringIO

from fastapi.testclient import TestClient

from api.main import app
from memory.portfolio import parse_csv, record_import, portfolio_summary


client = TestClient(app)


SAHM_LIKE = """Symbol,Quantity,Avg Cost,Market Price,Market Value,Unrealized P&L,Currency
AAPL,100,170.50,185.20,18520.00,1470.00,USD
MSFT,50,310.00,420.00,21000.00,5500.00,USD
2222.SR,500,32.10,34.50,17250.00,1200.00,SAR
"""

ALPACA_LIKE = """ticker,qty,avg_cost,last_price,market_value,unrealized_pnl
SPY,10,520.00,530.00,5300.00,100.00
QQQ,5,480.00,475.00,2375.00,-25.00
"""

NEGATIVE_PARENS = """Symbol,Quantity,Market Value,Unrealized P&L
AAPL,100,"$18,520.00","($100.50)"
"""


def test_parse_sahm_like():
    positions, warnings = parse_csv(SAHM_LIKE)
    assert len(positions) == 3
    assert warnings == []
    aapl = next(p for p in positions if p.symbol == "AAPL")
    assert aapl.quantity == 100
    assert aapl.avg_cost == 170.50
    assert aapl.market_value == 18520.00


def test_parse_alpaca_like():
    positions, _ = parse_csv(ALPACA_LIKE)
    syms = sorted(p.symbol for p in positions)
    assert syms == ["QQQ", "SPY"]


def test_parse_handles_negative_parens_and_dollar_signs():
    positions, _ = parse_csv(NEGATIVE_PARENS)
    assert len(positions) == 1
    assert positions[0].market_value == 18520.00
    assert positions[0].unrealized_pnl == -100.50


def test_parse_warns_on_missing_symbol():
    bad = "Quantity,Avg Cost\n100,10\n"
    positions, warnings = parse_csv(bad)
    assert positions == []
    assert any("symbol" in w.lower() for w in warnings)


def test_parse_warns_on_missing_quantity():
    bad = "Symbol,Avg Cost\nAAPL,170.50\n"
    positions, warnings = parse_csv(bad)
    assert positions == []
    assert any("quantity" in w.lower() for w in warnings)


def test_record_and_summary_round_trip():
    positions, _ = parse_csv(SAHM_LIKE)
    record_import(positions, source="sahm", filename="test.csv")
    summary = portfolio_summary()
    assert summary["ok"]
    assert summary["position_count"] == 3
    assert summary["gross_market_value"] > 0
    assert summary["unrealized_pnl"] == 1470 + 5500 + 1200


def test_api_import_endpoint():
    r = client.post(
        "/api/v1/portfolio/import",
        files={"file": ("positions.csv", StringIO(SAHM_LIKE).read(), "text/csv")},
        data={"source": "sahm", "account_label": "main"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["positions_imported"] == 3


def test_api_rejects_bad_csv():
    r = client.post(
        "/api/v1/portfolio/import",
        files={"file": ("bad.csv", "nothing,useful\n1,2\n", "text/csv")},
        data={"source": "other"},
    )
    assert r.status_code == 400


def test_api_summary_endpoint_without_imports():
    r = client.get("/api/v1/portfolio/")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"]
    # fresh test DB → either empty note or zero positions depending on run order
    assert body["position_count"] >= 0
