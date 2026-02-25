from db.store import DataStore


def test_phase2_domain_tables_and_crud(tmp_path):
    db_file = tmp_path / "trading_os_test.db"
    store = DataStore(str(db_file))
    store.init_db()

    user = store.get_or_create_user("u-1", "tester")

    strategy_id = store.create_strategy(
        user_id=user.id,
        name="Mean Reversion",
        market="US",
        symbol="AAPL",
        config_json='{"entry":"rsi<30"}',
    )
    strategies = store.list_strategies(user.id)
    assert any(s.id == strategy_id for s in strategies)

    order_id = store.create_order(
        user_id=user.id,
        strategy_id=strategy_id,
        symbol="AAPL",
        side="BUY",
        order_type="LIMIT",
        quantity=10,
        limit_price=100.0,
    )
    store.update_order_status(order_id, "SUBMITTED", broker_order_id="brk-1")
    orders = store.list_orders(user.id)
    assert orders[0].status == "SUBMITTED"

    store.upsert_position(user.id, "AAPL", quantity=10, avg_cost=100.0, last_price=110.0)
    positions = store.get_open_positions(user.id)
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"

    rule_id = store.create_risk_rule(
        user_id=user.id,
        name="Daily Loss Guard",
        rule_type="max_daily_loss",
        value_json='{"usd":500}',
    )
    rules = store.list_risk_rules(user.id)
    assert any(r.id == rule_id for r in rules)

    run_id = store.record_agent_run(
        user_id=user.id,
        strategy_id=strategy_id,
        run_type="execute",
        input_json='{"symbol":"AAPL"}',
    )
    store.update_agent_run(run_id, "SUCCESS", output_json='{"order_id":1}')
    runs = store.list_recent_agent_runs(user.id)
    assert runs[0].status == "SUCCESS"

    # execution config flags
    assert store.get_execution_mode() == "PAPER"
    assert store.is_kill_switch_on() is False
    store.set_execution_mode("LIVE")
    store.set_kill_switch(True)
    assert store.get_execution_mode() == "LIVE"
    assert store.is_kill_switch_on() is True
