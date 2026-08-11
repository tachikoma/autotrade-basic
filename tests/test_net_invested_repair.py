"""
net_invested(순투입) 신뢰성 상태머신 + 일회성 복구 모드 테스트.

배경: SOXL net_invested=0.00 손상 사고 — 마이그레이션 백필 실패로 필드가 0으로 고정되고,
reconciliation(0에서 매도금 차감 → clamp 0)으로 왜곡되어 시드 캡이 풀려 리버스 BUY가 과매수됨.
방지책:
  - net_invested_status: "valid"(신뢰) | "unresolved"(신뢰 불가, 신규 전략 주문 보류)
  - STATE_REVERSE_AUDIT_ONLY (read-only 감사)
  - STATE_REVERSE_RECONCILE_ONLY (체결만 반영, 주문 없음)
  - STATE_NET_INVESTED_REPAIR_ONLY (명시 값 CAS 복구)
"""
import os
import sys
from unittest.mock import patch

import pytest

# repo 루트 + src 경로 추가
_repo_root = os.path.join(os.path.dirname(__file__), "..")
_src_path = os.path.join(_repo_root, "src")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from trading_bot import _net_invested_repair_only
from state import canonical_state_hash
import strategy
from broker.base import StockPrice, StockQuotation, Balance


def _make_state(**overrides):
    """reconcile 후 SOXL 상태를 재현합니다 (T=16.2, day_count=2, 진행 중인 리버스 cycle)."""
    state = {
        "T": 16.2,
        "last_updated": "2026-08-04T19:16:50+00:00",
        "cycle_start_date": "",
        "effective_seed": 0.0,
        "net_invested": 0.0,
        "net_invested_status": "unresolved",
        "last_processed_ordno": "000005315",
        "additional_loc_odno": [],
        "orders_meta": {
            "000004615": {
                "side": "SELL", "total_qty": 32, "t_target": 0.0, "is_additional": False,
                "processed_filled_qty": 32, "processed_filled_amount": 4376.64,
                "applied_fill_fraction": 1.0, "terminal": True,
                "reverse_action": "sell", "reverse_day": 1, "cycle_id": "C8",
                "submitted_at": "20260806041650", "submitted_session": "2026-08-05",
                "reverse_base_t": 20.0, "reverse_t_factor": 0.9,
            },
            "000005315": {
                "side": "SELL", "total_qty": 29, "t_target": 0.0, "is_additional": False,
                "processed_filled_qty": 29, "processed_filled_amount": 3910.05,
                "applied_fill_fraction": 1.0, "terminal": True,
                "reverse_action": "sell", "reverse_day": 2, "cycle_id": "C8",
                "submitted_at": "20260807033000", "submitted_session": "2026-08-06",
                "reverse_base_t": 18.0, "reverse_t_factor": 0.9,
            },
            "000005316": {
                "side": "BUY", "total_qty": 40, "t_target": 0.0, "is_additional": False,
                "processed_filled_qty": 0, "processed_filled_amount": 0.0,
                "applied_fill_fraction": 0.0, "terminal": True,
                "reverse_action": "buy", "reverse_day": 2, "cycle_id": "C8",
                "submitted_at": "20260807033000", "submitted_session": "2026-08-06",
            },
        },
        "balance_mismatch": {},
        "state_version": "v2",
        "close_prices": [],
        "reverse_mode": {
            "active": True, "cycle_id": "C8", "day_count": 2,
            "cumulative_sell_proceeds": 8286.69, "last_planned_session": "2026-08-06",
        },
        "pending_order_intent": None,
        "pending_order_batch": None,
    }
    state.update(overrides)
    return state


class _FakeBroker:
    """strategy gate 테스트용 최소 스텁."""

    def get_stock_quotation(self, symbol, exchange_code):
        return StockQuotation(tradable=True, last=10.0)

    def get_stock_price(self, symbol, exchange_code):
        return StockPrice(open=10.0, last=10.0)

    def get_balance(self, symbol, exchange_code):
        return Balance(quantity=293, avg_price=20.0)

    def get_purchase_amount(self, symbol, exchange_code):
        from broker.base import PurchaseAmount
        return PurchaseAmount(orderable_cash=1000.0)


class TestStrategyGate:
    def test_unresolved_차단(self):
        """unresolved 상태면 무한매수법_V4가 신규 전략 주문을 생성하지 않아야 합니다."""
        state = _make_state()
        state["net_invested_status"] = "unresolved"
        result = strategy.무한매수법_V4(
            _FakeBroker(), symbol="SOXL", exchange_code="AMS", splits=20,
            symbol_type="SOXL", seed=50000.0, T=16.2, state=state,
        )
        assert result["orders"] == []

    def test_valid_진행(self):
        """valid 상태면 게이트를 통과해 정상 전략 흐름으로 진행합니다."""
        state = _make_state()
        state["net_invested_status"] = "valid"
        result = strategy.무한매수법_V4(
            _FakeBroker(), symbol="SOXL", exchange_code="AMS", splits=20,
            symbol_type="SOXL", seed=50000.0, T=16.2, state=state,
        )
        assert "symbol" in result


class TestCanonicalStateHash:
    def test_해시_안정성(self):
        state = _make_state()
        assert canonical_state_hash(state) == canonical_state_hash(state)

    def test_필드_변경_시_해시_변경(self):
        state = _make_state()
        h1 = canonical_state_hash(state)
        state["net_invested"] = 54161.72
        assert h1 != canonical_state_hash(state)

    def test_사전_순서_영향_없음(self):
        state = _make_state()
        h1 = canonical_state_hash(state)
        state["orders_meta"]["000005316"]["cycle_id"] = state["orders_meta"]["000005316"].pop("cycle_id")
        assert h1 == canonical_state_hash(state)


class TestNetInvestedRepairOnly:
    def _set_fingerprint(self, monkeypatch, state):
        monkeypatch.setenv("STATE_NET_INVESTED_REPAIR_SYMBOL", "SOXL")
        monkeypatch.setenv("STATE_NET_INVESTED_REPAIR_TARGET", "54161.72")
        monkeypatch.setenv("STATE_NET_INVESTED_REPAIR_EXPECT_HASH", canonical_state_hash(state))
        monkeypatch.setenv("STATE_NET_INVESTED_REPAIR_EXPECT_NET_INVESTED", "0.0")
        monkeypatch.setenv("STATE_NET_INVESTED_REPAIR_EXPECT_STATUS", "unresolved")

    def test_env_누락_시_중단(self, monkeypatch):
        monkeypatch.delenv("STATE_NET_INVESTED_REPAIR_SYMBOL", raising=False)
        with pytest.raises(RuntimeError, match="fingerprint 환경변수가 없습니다"):
            _net_invested_repair_only()

    def test_hash_불일치_시_중단(self, monkeypatch):
        state = _make_state()
        self._set_fingerprint(monkeypatch, state)
        monkeypatch.setenv("STATE_NET_INVESTED_REPAIR_EXPECT_HASH", "deadbeef")
        with patch("trading_bot.load_state", return_value=state), \
             patch("trading_bot.save_state") as mock_save:
            with pytest.raises(RuntimeError, match="hash 불일치"):
                _net_invested_repair_only()
        mock_save.assert_not_called()

    def test_net_invested_불일치_시_중단(self, monkeypatch):
        state = _make_state()
        self._set_fingerprint(monkeypatch, state)
        monkeypatch.setenv("STATE_NET_INVESTED_REPAIR_EXPECT_NET_INVESTED", "99.0")
        with patch("trading_bot.load_state", return_value=state), \
             patch("trading_bot.save_state") as mock_save:
            with pytest.raises(RuntimeError, match="필드 불일치"):
                _net_invested_repair_only()
        mock_save.assert_not_called()

    def test_status_불일치_시_중단(self, monkeypatch):
        state = _make_state()
        self._set_fingerprint(monkeypatch, state)
        monkeypatch.setenv("STATE_NET_INVESTED_REPAIR_EXPECT_STATUS", "valid")
        with patch("trading_bot.load_state", return_value=state), \
             patch("trading_bot.save_state") as mock_save:
            with pytest.raises(RuntimeError, match="status 불일치"):
                _net_invested_repair_only()
        mock_save.assert_not_called()

    def test_미종결_리버스_주문_시_거부(self, monkeypatch):
        state = _make_state()
        state["orders_meta"]["000005316"]["terminal"] = False
        self._set_fingerprint(monkeypatch, state)
        with patch("trading_bot.load_state", return_value=state), \
             patch("trading_bot.save_state") as mock_save:
            with pytest.raises(RuntimeError, match="미종결 리버스 주문"):
                _net_invested_repair_only()
        mock_save.assert_not_called()

    def test_pending_fence_시_거부(self, monkeypatch):
        state = _make_state()
        state["pending_order_intent"] = {"side": "SELL", "submitted_session": "2026-08-05"}
        self._set_fingerprint(monkeypatch, state)
        with patch("trading_bot.load_state", return_value=state), \
             patch("trading_bot.save_state") as mock_save:
            with pytest.raises(RuntimeError, match="fence"):
                _net_invested_repair_only()
        mock_save.assert_not_called()

    def test_정상_복구_성공(self, monkeypatch):
        state = _make_state()
        self._set_fingerprint(monkeypatch, state)
        with patch("trading_bot.load_state", return_value=state), \
             patch("trading_bot.save_state") as mock_save:
            _net_invested_repair_only()
        assert state["net_invested"] == 54161.72
        assert state["net_invested_status"] == "valid"
        # T / reverse_mode / orders_meta 등 다른 필드는 보존
        assert state["T"] == 16.2
        assert state["reverse_mode"]["day_count"] == 2
        assert state["orders_meta"]["000005315"]["processed_filled_amount"] == 3910.05
        mock_save.assert_called_once()
