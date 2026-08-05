from copy import deepcopy
from unittest.mock import MagicMock

from state import reconcile_reverse_fills, update_T_from_history
from strategy import execute_reverse_mode


class _FakeQuotation:
    tradable = True


class _FakePrice:
    def __init__(self, last):
        self.open = last
        self.last = last


class _FakeBalance:
    def __init__(self, qty, avg):
        self.quantity = qty
        self.avg_price = avg


class _FakePurchaseAmount:
    def __init__(self, cash):
        self.orderable_cash = cash


def _make_broker_mock(last_price, position_qty, avg_price, orderable_cash):
    broker = MagicMock()
    broker.get_stock_quotation.return_value = _FakeQuotation()
    broker.get_stock_price.return_value = _FakePrice(last_price)
    broker.get_balance.return_value = _FakeBalance(position_qty, avg_price)
    broker.get_purchase_amount.return_value = _FakePurchaseAmount(orderable_cash)
    return broker


def test_reverse_entry_at_t_between_splits_minus_one_and_splits(monkeypatch):
    """T > 분할수-1 (20분할 T=19.5) → 리버스모드 진입, 1일차 MOC 매도."""
    monkeypatch.setattr("strategy.get_finnhub_ma5", lambda symbol: None)
    from strategy import 무한매수법_V4

    state = {"T": 19.5, "reverse_mode": {}, "close_prices": [50.0]}
    broker = _make_broker_mock(
        last_price=50.0, position_qty=100, avg_price=100.0, orderable_cash=1000.0
    )

    result = 무한매수법_V4(
        broker, symbol="SOXL", exchange_code="NYS", splits=20, symbol_type="SOXL",
        seed=0, T=19.5, state=state,
    )

    assert result["orders"], "리버스 진입 시 주문이 있어야 합니다"
    assert result["orders"][0]["order_type"] == "MOC"
    assert result["T"] == round(19.5 * 0.9, 4)


def test_no_reverse_entry_at_t_equal_to_splits_minus_one(monkeypatch):
    """T == 분할수-1 (20분할 T=19.0) → 일반모드 유지 (MOC 없음, T 유지)."""
    monkeypatch.setattr("strategy.get_finnhub_ma5", lambda symbol: None)
    from strategy import 무한매수법_V4

    state = {"T": 19.0, "reverse_mode": {}, "close_prices": [50.0]}
    broker = _make_broker_mock(
        last_price=50.0, position_qty=100, avg_price=100.0, orderable_cash=1000.0
    )

    result = 무한매수법_V4(
        broker, symbol="SOXL", exchange_code="NYS", splits=20, symbol_type="SOXL",
        seed=0, T=19.0, state=state,
    )

    assert result["T"] == 19.0
    assert result["orders"], "일반모드에서도 주문은 생성되어야 합니다"
    assert all(order["order_type"] != "MOC" for order in result["orders"])
    assert not any("리버스" in order.get("comment", "") for order in result["orders"])


def test_reverse_mode_advances_one_day_per_execution(monkeypatch):
    monkeypatch.setattr("strategy.get_finnhub_ma5", lambda symbol: None)
    state = {
        "T": 20.0,
        "reverse_mode": {},
        "close_prices": [100.0],
    }

    first = execute_reverse_mode(
        broker=None,
        symbol="SOXL",
        exchange_code="NYS",
        splits=20,
        symbol_type="SOXL",
        position_qty=325,
        avg_price=192.149,
        orderable_cash=0.0,
        last_price=118.0,
        state=state,
    )

    assert first["orders"][0]["order_type"] == "MOC"
    assert first["reverse_day"] == 1
    assert state["reverse_mode"] == {}

    second = execute_reverse_mode(
        broker=None,
        symbol="SOXL",
        exchange_code="NYS",
        splits=20,
        symbol_type="SOXL",
        position_qty=325,
        avg_price=192.149,
        orderable_cash=0.0,
        last_price=118.0,
        state=state,
    )

    assert second["orders"][0]["order_type"] == "MOC"
    assert second["reverse_day"] == 1
    assert state["reverse_mode"] == {}


def test_reverse_mode_does_not_use_unfilled_sell_proceeds_for_buy(monkeypatch):
    monkeypatch.setattr("strategy.get_finnhub_ma5", lambda symbol: None)
    state = {
        "T": 20.0,
        "reverse_mode": {
            "day_count": 1,
            "cumulative_sell_proceeds": 10000.0,
        },
        "close_prices": [100.0],
    }

    result = execute_reverse_mode(
        broker=None,
        symbol="SOXL",
        exchange_code="NYS",
        splits=20,
        symbol_type="SOXL",
        position_qty=325,
        avg_price=192.149,
        orderable_cash=0.0,
        last_price=118.0,
        state=state,
    )

    assert len(result["orders"]) == 1
    assert result["orders"][0]["side"] == "SELL"
    assert state["reverse_mode"]["cumulative_sell_proceeds"] == 10000.0


def test_dry_strategy_state_isolated_from_persisted_state(monkeypatch):
    monkeypatch.setattr("strategy.get_finnhub_ma5", lambda symbol: None)
    state = {
        "T": 20.0,
        "reverse_mode": {},
        "close_prices": [100.0],
    }
    strategy_state = deepcopy(state)

    execute_reverse_mode(
        broker=None,
        symbol="SOXL",
        exchange_code="NYS",
        splits=20,
        symbol_type="SOXL",
        position_qty=325,
        avg_price=192.149,
        orderable_cash=0.0,
        last_price=118.0,
        state=strategy_state,
    )

    assert state["reverse_mode"] == {}


def test_reverse_sell_fill_updates_t_and_day_once():
    state = {
        "T": 20.0,
        "reverse_mode": {"active": True, "day_count": 0, "cycle_id": "C1"},
        "orders_meta": {
            "RSELL": {
                "side": "SELL",
                "total_qty": 32,
                "processed_filled_qty": 0,
                "reverse_action": "sell",
                "reverse_day": 1,
                "reverse_base_t": 20.0,
                "reverse_t_factor": 0.9,
                "cycle_id": "C1",
            }
        },
    }
    history = [{
        "odno": "RSELL",
        "ord_datetime_utc": "2026-08-01T20:00:00+00:00",
        "ft_ccld_qty": "32",
        "ft_ccld_unpr3": "124.00",
        "ft_ccld_amt3": "3968.00",
        "nccs_qty": "0",
    }]

    reconcile_reverse_fills(state, history)
    reconcile_reverse_fills(state, history)

    assert state["T"] == 18.0
    assert state["reverse_mode"]["day_count"] == 1
    assert state["reverse_mode"]["cumulative_sell_proceeds"] == 3968.0
    assert state["orders_meta"]["RSELL"]["processed_filled_qty"] == 32


def test_reverse_buy_fill_updates_t_without_advancing_day():
    state = {
        "T": 20.0,
        "reverse_mode": {"active": True, "day_count": 1, "cycle_id": "C2"},
        "orders_meta": {
            "RSELL2": {
                "side": "SELL",
                "total_qty": 32,
                "processed_filled_qty": 0,
                "reverse_action": "sell",
                "reverse_day": 2,
                "reverse_base_t": 20.0,
                "reverse_t_factor": 0.9,
                "cycle_id": "C2",
            },
            "RBUY": {
                "side": "BUY",
                "total_qty": 32,
                "processed_filled_qty": 0,
                "reverse_action": "buy",
                "reverse_day": 2,
                "reverse_base_t": 18.0,
                "reverse_t_target": 0.5,
                "cycle_id": "C2",
            }
        },
    }
    history = [{
        "odno": "RSELL2",
        "ord_datetime_utc": "2026-08-02T20:00:00+00:00",
        "ft_ccld_qty": "32",
        "ft_ccld_unpr3": "124.00",
        "ft_ccld_amt3": "3968.00",
        "nccs_qty": "0",
    }, {
        "odno": "RBUY",
        "ord_datetime_utc": "2026-08-02T20:00:01+00:00",
        "ft_ccld_qty": "16",
        "ft_ccld_unpr3": "123.00",
        "ft_ccld_amt3": "1968.00",
        "nccs_qty": "16",
    }]

    reconcile_reverse_fills(state, history)

    assert state["T"] == 18.25
    assert state["reverse_mode"]["day_count"] == 2


def test_recent_history_does_not_apply_reverse_sell_as_generic_quarter_sell():
    state = {
        "T": 20.0,
        "last_updated": "2026-07-31T19:00:00+00:00",
        "last_processed_ordno": "OLD",
        "reverse_mode": {"active": True, "day_count": 0, "cycle_id": "C1"},
        "orders_meta": {
            "RSELL": {
                "side": "SELL",
                "total_qty": 32,
                "processed_filled_qty": 0,
                "reverse_action": "sell",
                "reverse_day": 1,
                "reverse_base_t": 20.0,
                "reverse_t_factor": 0.9,
                "cycle_id": "C1",
            }
        },
    }
    history = [{
        "odno": "RSELL",
        "ord_dt": "20260801",
        "ord_datetime_utc": "2026-08-01T20:00:00+00:00",
        "sll_buy_dvsn_cd_name": "매도",
        "ft_ccld_qty": "32",
        "ft_ccld_unpr3": "124.00",
        "ft_ccld_amt3": "3968.00",
        "nccs_qty": "0",
    }]

    update_T_from_history("SOXL", state, history, balance_qty=293)

    assert state["T"] == 18.0
    assert state["reverse_mode"]["day_count"] == 1


def test_reverse_partial_sell_progress_is_monotonic_and_additive():
    state = {
        "T": 20.0,
        "reverse_mode": {"active": True, "cycle_id": "C3", "day_count": 0},
        "orders_meta": {
            "RSELL3": {
                "side": "SELL",
                "total_qty": 40,
                "processed_filled_qty": 0,
                "reverse_action": "sell",
                "reverse_day": 1,
                "reverse_base_t": 20.0,
                "reverse_t_factor": 0.9,
                "cycle_id": "C3",
            }
        },
    }

    def history(qty, amount, remaining):
        return [{
            "odno": "RSELL3",
            "ord_dt": "20260803",
            "ord_datetime_utc": "2026-08-03T20:00:00+00:00",
            "ft_ccld_qty": str(qty),
            "ft_ccld_unpr3": "124.00",
            "ft_ccld_amt3": str(amount),
            "nccs_qty": str(remaining),
        }]

    reconcile_reverse_fills(state, history(10, 1240, 30))
    assert state["T"] == 19.5
    reconcile_reverse_fills(state, history(20, 2480, 20))
    assert state["T"] == 19.0
    reconcile_reverse_fills(state, history(40, 4960, 0))
    assert state["T"] == 18.0
    assert state["reverse_mode"]["day_count"] == 1


def test_missing_previous_reverse_history_blocks_new_plans():
    state = {
        "T": 18.0,
        "reverse_mode": {
            "active": True,
            "cycle_id": "C4",
            "day_count": 1,
        },
        "orders_meta": {
            "RSELL4": {
                "side": "SELL",
                "total_qty": 32,
                "processed_filled_qty": 0,
                "reverse_action": "sell",
                "reverse_day": 2,
                "cycle_id": "C4",
                "submitted_at": "20260731191649",
            }
        },
    }

    reconcile_reverse_fills(state, [])

    assert state["reverse_mode"]["reconciliation_only"] is True
    assert state["reverse_mode"]["reconciliation_error"] == "reverse_order_history_missing"


def test_canceled_partial_sell_is_terminal_and_advances_day():
    state = {
        "T": 20.0,
        "reverse_mode": {"active": True, "cycle_id": "C5", "day_count": 0},
        "orders_meta": {
            "RSELL5": {
                "side": "SELL",
                "total_qty": 32,
                "processed_filled_qty": 0,
                "reverse_action": "sell",
                "reverse_day": 1,
                "reverse_base_t": 20.0,
                "reverse_t_factor": 0.9,
                "cycle_id": "C5",
            }
        },
    }
    history = [{
        "odno": "RSELL5",
        "ord_dt": "20260804",
        "ord_datetime_utc": "2026-08-04T20:00:00+00:00",
        "ft_ccld_qty": "16",
        "ft_ccld_unpr3": "124.00",
        "ft_ccld_amt3": "1984.00",
        "nccs_qty": "16",
        "cncl_qty": "16",
        "prcs_stat_name": "취소",
    }]

    reconcile_reverse_fills(state, history)

    assert state["T"] == 19.0
    assert state["reverse_mode"]["day_count"] == 1
