from fastapi.testclient import TestClient

from dashboard.backend.main import app
from routers import market as market_router_module


def test_health_endpoint():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_root_page():
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_search_endpoint():
    client = TestClient(app)
    resp = client.get("/api/search", params={"q": "AAPL"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(item["symbol"] == "AAPL" for item in data)


def test_agent_config_endpoint():
    client = TestClient(app)
    g = client.get("/api/agent/config")
    assert g.status_code == 200
    cfg = g.json()
    assert "agent_name" in cfg
    assert "capabilities" in cfg

    p = client.post(
        "/api/agent/config",
        json={"mode": "semi_auto", "agent_name": "Test Agent"},
    )
    assert p.status_code == 200
    assert p.json().get("success") is True


def test_price_and_chart_with_stubbed_provider(monkeypatch):
    def fake_price(symbol, timeout=8.0):
        return {
            "symbol": symbol,
            "name": "Test",
            "currency": "USD",
            "price": 123.45,
            "change_pct": 1.23,
        }

    def fake_chart(symbol, period):
        return {
            "symbol": symbol,
            "period": period,
            "data": [{"date": "2026-01-01", "open": 1, "high": 2, "low": 1, "close": 2}],
        }

    monkeypatch.setattr(market_router_module.provider, "get_price", fake_price)
    monkeypatch.setattr(market_router_module.provider, "get_chart_data", fake_chart)

    client = TestClient(app)

    p = client.get("/api/price/AAPL")
    assert p.status_code == 200
    assert p.json()["symbol"] == "AAPL"

    c = client.get("/api/chart/AAPL", params={"period": "1d"})
    assert c.status_code == 200
    assert c.json()["symbol"] == "AAPL"
    assert len(c.json()["data"]) == 1
