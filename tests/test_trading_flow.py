from fastapi.testclient import TestClient

from db.store import DataStore
from dashboard.backend.main import app
import core.state as state_module
import routers.trading as trading_module
import services.execution_service as execution_service
import services.risk_service as risk_service


class DummyProvider:
    def get_price(self, symbol: str):
        return {"symbol": symbol, "price": 100.0, "name": "Dummy", "currency": "USD", "change_pct": 0.0}



def _setup_temp_runtime(monkeypatch, tmp_path):
    db_file = tmp_path / "runtime_test.db"
    temp_store = DataStore(str(db_file))
    temp_store.init_db()
    demo_user = temp_store.get_or_create_user("demo", "demo")

    monkeypatch.setattr(state_module, "store", temp_store)
    monkeypatch.setattr(state_module, "demo_user", demo_user)

    monkeypatch.setattr(trading_module, "store", temp_store)
    monkeypatch.setattr(trading_module, "demo_user", demo_user)

    monkeypatch.setattr(execution_service, "store", temp_store)
    monkeypatch.setattr(risk_service, "store", temp_store)

    provider = DummyProvider()
    monkeypatch.setattr(state_module, "provider", provider)
    monkeypatch.setattr(risk_service, "provider", provider)

    return temp_store



def test_strategy_to_paper_fill_flow(monkeypatch, tmp_path):
    _setup_temp_runtime(monkeypatch, tmp_path)

    with TestClient(app) as client:
        # create strategy
        s = client.post(
            "/api/strategies",
            json={
                "name": "Test Strat",
                "market": "US",
                "symbol": "AAPL",
                "timeframe": "1d",
                "config": {"entry": "demo"},
            },
        )
        assert s.status_code == 200
        strategy_id = s.json()["strategy_id"]

        # place paper market order
        o = client.post(
            "/api/orders/paper",
            json={
                "symbol": "AAPL",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 2,
                "strategy_id": strategy_id,
                "price_hint": 100,
            },
        )
        assert o.status_code == 200
        assert o.json()["success"] is True
        assert o.json()["status"] == "FILLED"

        # position should be updated
        p = client.get("/api/positions")
        assert p.status_code == 200
        positions = p.json()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "AAPL"
        assert positions[0]["quantity"] == 2

        # order history and runs should be available
        orders = client.get("/api/orders")
        assert orders.status_code == 200
        assert len(orders.json()) >= 1

        runs = client.get("/api/agent-runs")
        assert runs.status_code == 200
        assert len(runs.json()) >= 1



def test_risk_rule_blocks_symbol(monkeypatch, tmp_path):
    _setup_temp_runtime(monkeypatch, tmp_path)

    with TestClient(app) as client:
        r = client.post(
            "/api/risk-rules",
            json={
                "name": "Allow only MSFT",
                "rule_type": "allowed_symbols",
                "value": {"symbols": ["MSFT"]},
                "enabled": True,
            },
        )
        assert r.status_code == 200

        o = client.post(
            "/api/orders/paper",
            json={
                "symbol": "AAPL",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 1,
                "price_hint": 100,
            },
        )
        assert o.status_code == 200
        assert o.json()["success"] is False
        assert o.json()["status"] == "REJECTED"


def test_execution_config_and_kill_switch(monkeypatch, tmp_path):
    _setup_temp_runtime(monkeypatch, tmp_path)

    with TestClient(app) as client:
        cfg = client.get("/api/execution/config")
        assert cfg.status_code == 200
        assert cfg.json()["mode"] in {"PAPER", "LIVE"}
        assert cfg.json()["kill_switch"] is False

        up = client.post("/api/execution/config", json={"kill_switch": True})
        assert up.status_code == 200
        assert up.json()["success"] is True
        assert up.json()["kill_switch"] is True

        blocked = client.post(
            "/api/orders/execute",
            json={
                "symbol": "AAPL",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 1,
                "price_hint": 100,
            },
        )
        assert blocked.status_code == 200
        assert blocked.json()["success"] is False
        assert blocked.json()["status"] == "BLOCKED"
        assert blocked.json()["reason_code"] == "KILL_SWITCH"

        reset = client.post("/api/execution/config", json={"kill_switch": False, "mode": "PAPER"})
        assert reset.status_code == 200
        assert reset.json()["kill_switch"] is False
        assert reset.json()["mode"] == "PAPER"
