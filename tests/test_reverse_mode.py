from copy import deepcopy
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

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


def test_reconcile_matches_moc_fill_with_off_by_one_ord_dt():
    """MOC/LOC 주문은 제출 KST일 vs 이력 ord_dt(ET 영업일)이 하루 어긋나도 누락 오판 없이 반영돼야 합니다.

    봇은 KST 04:xx(=전일 ET 15:xx)에 주문하므로 이력 ord_dt는 제출일의 전일입니다.
    이전 버그: _order_for_meta가 ord_dt == submitted_at[:8]로 비교해 미스매치 →
    '리버스 주문 이력 누락' 오판으로 신규 주문을 영구 차단했습니다.
    """
    state = {
        "T": 20.0,
        "reverse_mode": {"active": True, "cycle_id": "C6", "day_count": 0},
        "orders_meta": {
            "000004615": {
                "side": "SELL",
                "total_qty": 32,
                "processed_filled_qty": 0,
                "reverse_action": "sell",
                "reverse_day": 1,
                "reverse_base_t": 20.0,
                "reverse_t_factor": 0.9,
                "cycle_id": "C6",
                "submitted_at": "20260806041650",
                "submitted_session": "2026-08-05",
            }
        },
    }
    history = [{
        "odno": "000004615",
        "ord_dt": "20260805",           # 미국(ET) 영업일 — submitted_at(08-06)과 하루 차이
        "ord_tmd": "041650",            # KST 시각
        "ord_datetime_utc": "2026-08-04T19:16:50+00:00",
        "sll_buy_dvsn_cd_name": "매도",
        "ft_ccld_qty": "32",
        "ft_ccld_unpr3": "136.77",
        "ft_ccld_amt3": "4376.64",
        "nccs_qty": "0",
        "prcs_stat_name": "체결",
    }]

    reconcile_reverse_fills(state, history)

    assert state["reverse_mode"].get("reconciliation_error") is None
    assert state["reverse_mode"].get("reconciliation_only") is None
    assert state["T"] == 18.0
    assert state["reverse_mode"]["day_count"] == 1
    assert state["reverse_mode"]["cumulative_sell_proceeds"] == 4376.64


def test_generic_path_skips_reverse_moc_fill_with_off_by_one_ord_dt():
    """제출일과 이력 ord_dt가 하루 어긋난 리버스 매도가 일반 쿼터매도로 오분류되지 않아야 합니다.

    이전 버그: _is_reverse_order의 날짜 가드가 미스매치로 False 반환 → 리버스 매도가
    일반 쿼터매도(×0.75)로 처리되어 T=15로 오반영됐습니다. 수정 후에는 리버스 경로(×0.9)로
    T=18이 되어야 합니다.
    """
    state = {
        "T": 20.0,
        "last_updated": "2026-07-29T19:16:45+00:00",
        "last_processed_ordno": "000004932",
        "reverse_mode": {"active": True, "cycle_id": "C7", "day_count": 0},
        "orders_meta": {
            "000004615": {
                "side": "SELL",
                "total_qty": 32,
                "processed_filled_qty": 0,
                "reverse_action": "sell",
                "reverse_day": 1,
                "reverse_base_t": 20.0,
                "reverse_t_factor": 0.9,
                "cycle_id": "C7",
                "submitted_at": "20260806041650",
                "submitted_session": "2026-08-05",
            }
        },
    }
    history = [{
        "odno": "000004615",
        "ord_dt": "20260805",
        "ord_tmd": "041650",
        "ord_datetime_utc": "2026-08-04T19:16:50+00:00",
        "sll_buy_dvsn_cd_name": "매도",
        "ft_ccld_qty": "32",
        "ft_ccld_unpr3": "136.77",
        "ft_ccld_amt3": "4376.64",
        "nccs_qty": "0",
        "prcs_stat_name": "체결",
    }]

    update_T_from_history("SOXL", state, history, balance_qty=293)

    assert state["T"] == 18.0
    assert state["reverse_mode"]["day_count"] == 1
    assert state["reverse_mode"].get("reconciliation_error") is None
    assert state["reverse_mode"].get("reconciliation_only") is None


# --- 이전 세션 zero-fill 리버스 주문 자동 만료 가정 (데모 전용) ---


def test_auto_expire_prev_session_zero_fill_buy_demo(monkeypatch):
    """데모: 이전 세션 zero-fill 리버스 매수 → 자동 만료 가정, 차단 없음."""
    monkeypatch.setattr("config.BROKER_MODE", "demo")
    state = {
        "T": 12.0,
        "reverse_mode": {"active": True, "cycle_id": "C8", "day_count": 5},
        "orders_meta": {
            "RBUY1": {
                "side": "BUY",
                "total_qty": 40,
                "processed_filled_qty": 0,
                "reverse_action": "buy",
                "reverse_day": 2,
                "reverse_t_target": 0.5,
                "cycle_id": "C8",
                "submitted_at": "20260810041612",
                "submitted_session": "2026-08-10",
            }
        },
    }
    history = [{
        "odno": "RBUY1",
        "ord_dt": "20260810",
        "ord_datetime_utc": "2026-08-09T19:16:12+00:00",
        "sll_buy_dvsn_cd_name": "매수",
        "ft_ccld_qty": "0",
        "ft_ccld_amt3": "0",
        "nccs_qty": "40",
        "prcs_stat_name": "미체결",
    }]

    reconcile_reverse_fills(state, history)

    meta = state["orders_meta"]["RBUY1"]
    assert meta["terminal"] is True
    assert meta["terminal_assumed"] is True
    assert meta["terminal_assumption_reason"] == "auto_expired_demo_day_order_after_session"
    assert state["reverse_mode"].get("reconciliation_error") is None
    assert state["reverse_mode"].get("reconciliation_only") is None
    assert state["T"] == 12.0


def test_auto_expire_prev_session_zero_fill_sell_demo(monkeypatch):
    """데모: 이전 세션 zero-fill 리버스 매도 → 자동 만료 가정, 차단 없음."""
    monkeypatch.setattr("config.BROKER_MODE", "demo")
    state = {
        "T": 12.0,
        "reverse_mode": {"active": True, "cycle_id": "C9", "day_count": 1},
        "orders_meta": {
            "RSELL1": {
                "side": "SELL",
                "total_qty": 32,
                "processed_filled_qty": 0,
                "reverse_action": "sell",
                "reverse_day": 1,
                "reverse_base_t": 12.0,
                "reverse_t_factor": 0.9,
                "cycle_id": "C9",
                "submitted_at": "20260810041612",
                "submitted_session": "2026-08-10",
            }
        },
    }
    history = [{
        "odno": "RSELL1",
        "ord_dt": "20260810",
        "ord_datetime_utc": "2026-08-09T19:16:12+00:00",
        "sll_buy_dvsn_cd_name": "매도",
        "ft_ccld_qty": "0",
        "ft_ccld_amt3": "0",
        "nccs_qty": "32",
        "prcs_stat_name": "미체결",
    }]

    reconcile_reverse_fills(state, history)

    meta = state["orders_meta"]["RSELL1"]
    assert meta["terminal"] is True
    assert meta["terminal_assumed"] is True
    assert state["reverse_mode"].get("reconciliation_error") is None
    assert state["reverse_mode"].get("reconciliation_only") is None
    assert state["T"] == 12.0


def test_auto_expire_not_in_real_mode(monkeypatch):
    """실전: 같은 zero-fill 주문이라도 자동 만료하지 않고 차단 유지."""
    monkeypatch.setattr("config.BROKER_MODE", "real")
    state = {
        "T": 12.0,
        "reverse_mode": {"active": True, "cycle_id": "C10", "day_count": 5},
        "orders_meta": {
            "RBUY1": {
                "side": "BUY",
                "total_qty": 40,
                "processed_filled_qty": 0,
                "reverse_action": "buy",
                "reverse_day": 2,
                "reverse_t_target": 0.5,
                "cycle_id": "C10",
                "submitted_at": "20260810041612",
                "submitted_session": "2026-08-10",
            }
        },
    }
    history = [{
        "odno": "RBUY1",
        "ord_dt": "20260810",
        "ord_datetime_utc": "2026-08-09T19:16:12+00:00",
        "sll_buy_dvsn_cd_name": "매수",
        "ft_ccld_qty": "0",
        "ft_ccld_amt3": "0",
        "nccs_qty": "40",
        "prcs_stat_name": "미체결",
    }]

    reconcile_reverse_fills(state, history)

    meta = state["orders_meta"]["RBUY1"]
    assert meta.get("terminal") is not True
    assert state["reverse_mode"]["reconciliation_error"] == "reverse_order_not_terminal"
    assert state["reverse_mode"]["reconciliation_only"] is True


def test_auto_expire_not_for_today_session(monkeypatch):
    """데모: 오늘 세션의 미체결 주문은 만료 가정하지 않음 (다음 RUN에서 판정)."""
    monkeypatch.setattr("config.BROKER_MODE", "demo")
    today_session = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    today_compact = today_session.replace("-", "")
    state = {
        "T": 12.0,
        "reverse_mode": {"active": True, "cycle_id": "C11", "day_count": 5},
        "orders_meta": {
            "RBUY2": {
                "side": "BUY",
                "total_qty": 40,
                "processed_filled_qty": 0,
                "reverse_action": "buy",
                "reverse_day": 2,
                "reverse_t_target": 0.5,
                "cycle_id": "C11",
                "submitted_at": today_compact + "041612",
                "submitted_session": today_session,
            }
        },
    }
    history = [{
        "odno": "RBUY2",
        "ord_dt": today_compact,
        "ord_datetime_utc": today_compact + "T19:16:12+00:00",
        "sll_buy_dvsn_cd_name": "매수",
        "ft_ccld_qty": "0",
        "ft_ccld_amt3": "0",
        "nccs_qty": "40",
        "prcs_stat_name": "미체결",
    }]

    reconcile_reverse_fills(state, history)

    meta = state["orders_meta"]["RBUY2"]
    assert meta.get("terminal") is not True
    assert state["reverse_mode"].get("reconciliation_error") is None
    assert state["reverse_mode"].get("reconciliation_only") is None
    assert state["T"] == 12.0


def test_auto_expire_not_for_partial_fill(monkeypatch):
    """데모: 부분체결된 주문은 만료 가정하지 않고 차단 유지 + 체결분은 반영."""
    monkeypatch.setattr("config.BROKER_MODE", "demo")
    state = {
        "T": 12.0,
        "reverse_mode": {"active": True, "cycle_id": "C12", "day_count": 5},
        "orders_meta": {
            "RBUY3": {
                "side": "BUY",
                "total_qty": 40,
                "processed_filled_qty": 0,
                "reverse_action": "buy",
                "reverse_day": 2,
                "reverse_t_target": 0.5,
                "cycle_id": "C12",
                "submitted_at": "20260810041612",
                "submitted_session": "2026-08-10",
            }
        },
    }
    history = [{
        "odno": "RBUY3",
        "ord_dt": "20260810",
        "ord_datetime_utc": "2026-08-09T19:16:12+00:00",
        "sll_buy_dvsn_cd_name": "매수",
        "ft_ccld_qty": "16",
        "ft_ccld_amt3": "792.00",
        "nccs_qty": "24",
        "prcs_stat_name": "부분체결",
    }]

    reconcile_reverse_fills(state, history)

    meta = state["orders_meta"]["RBUY3"]
    assert meta.get("terminal") is not True
    assert state["reverse_mode"]["reconciliation_error"] == "reverse_order_not_terminal"
    assert state["reverse_mode"]["reconciliation_only"] is True
    assert state["T"] == 12.2


def test_auto_expire_late_fill_still_reflected(monkeypatch):
    """자동 만료 가정 후 늦은 체결이 들어오면 다음 RUN에 델타 그대로 반영."""
    monkeypatch.setattr("config.BROKER_MODE", "demo")
    state = {
        "T": 12.0,
        "reverse_mode": {"active": True, "cycle_id": "C13", "day_count": 5},
        "orders_meta": {
            "RBUY4": {
                "side": "BUY",
                "total_qty": 40,
                "processed_filled_qty": 0,
                "reverse_action": "buy",
                "reverse_day": 2,
                "reverse_t_target": 0.5,
                "cycle_id": "C13",
                "submitted_at": "20260810041612",
                "submitted_session": "2026-08-10",
            }
        },
    }
    zero_history = [{
        "odno": "RBUY4",
        "ord_dt": "20260810",
        "ord_datetime_utc": "2026-08-09T19:16:12+00:00",
        "sll_buy_dvsn_cd_name": "매수",
        "ft_ccld_qty": "0",
        "ft_ccld_amt3": "0",
        "nccs_qty": "40",
        "prcs_stat_name": "미체결",
    }]

    reconcile_reverse_fills(state, zero_history)

    meta = state["orders_meta"]["RBUY4"]
    assert meta["terminal"] is True
    assert meta["terminal_assumed"] is True

    late_history = [{
        "odno": "RBUY4",
        "ord_dt": "20260810",
        "ord_datetime_utc": "2026-08-09T19:16:12+00:00",
        "sll_buy_dvsn_cd_name": "매수",
        "ft_ccld_qty": "16",
        "ft_ccld_amt3": "792.00",
        "nccs_qty": "24",
        "prcs_stat_name": "부분체결",
    }]

    reconcile_reverse_fills(state, late_history)

    assert state["T"] == 12.2
    assert meta["processed_filled_qty"] == 16
    assert meta["terminal"] is True
