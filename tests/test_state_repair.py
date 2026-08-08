"""
일회성 상태 복구(STATE_REPAIR_ONLY) 테스트 — 특히 STATE_REPAIR_TARGET_T(T만 보정) 모드.

배경: ord_dt(미국영업일) vs submitted_at(KST) 날짜 컨벤션 버그로 리버스 매도가
일반 쿼터매도로 오분류되어 T=20 → 15로 오반영된 상태를, T만 20으로 되돌리면
다음 RUN의 reconcile_reverse_fills가 체결 기반으로 T=18/day_count=1을 재계산합니다.
"""
import os
import sys
from unittest.mock import patch

import pytest

# repo 루트 + src 경로 추가 (trading_bot import용)
_repo_root = os.path.join(os.path.dirname(__file__), "..")
_src_path = os.path.join(_repo_root, "src")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from trading_bot import _repair_state_only


def _make_corrupted_state(**overrides):
    """8/8 실행 후 오염된 SOXL 상태를 재현합니다 (T=15, reconciliation 차단, MOC 체결 미반영)."""
    state = {
        "T": 15.0,
        "last_updated": "2026-08-04T19:16:50+00:00",
        "cycle_start_date": "",
        "effective_seed": 0.0,
        "last_processed_ordno": "000004615",
        "additional_loc_odno": [],
        "orders_meta": {
            "000004615": {
                "side": "SELL",
                "total_qty": 32,
                "t_target": 0.0,
                "is_additional": False,
                "processed_filled_qty": 0,
                "applied_fill_fraction": 0.0,
                "reverse_action": "sell",
                "reverse_day": 1,
                "cycle_id": "C8",
                "submitted_at": "20260806041650",
                "submitted_session": "2026-08-05",
                "reverse_base_t": 20.0,
                "reverse_t_factor": 0.9,
                "reverse_t_target": 0.0,
            }
        },
        "balance_mismatch": {},
        "state_version": "v2",
        "close_prices": [],
        "reverse_mode": {
            "active": True,
            "cycle_id": "C8",
            "day_count": 0,
            "cumulative_sell_proceeds": 0.0,
            "last_planned_session": "2026-08-05",
            "reconciliation_error": "reverse_order_history_missing",
            "reconciliation_only": True,
        },
        "pending_order_intent": None,
        "pending_order_batch": None,
    }
    state.update(overrides)
    return state


class TestRepairStateOnly:
    def _set_fingerprint(self, monkeypatch, target_t="", t="15.0"):
        monkeypatch.setenv("STATE_REPAIR_SYMBOL", "SOXL")
        monkeypatch.setenv("STATE_REPAIR_EXPECT_T", t)
        monkeypatch.setenv("STATE_REPAIR_EXPECT_DAY_COUNT", "0")
        monkeypatch.setenv("STATE_REPAIR_EXPECT_PROCEEDS", "0")
        monkeypatch.setenv("STATE_REPAIR_EXPECT_LAST_UPDATED", "2026-08-04T19:16:50+00:00")
        monkeypatch.setenv("STATE_REPAIR_EXPECT_LAST_ORDNO", "000004615")
        monkeypatch.setenv("STATE_REPAIR_EXPECT_REVERSE_IDS", "000004615")
        monkeypatch.setenv("STATE_REPAIR_EXPECT_REVERSE_SUBMITTED_AT", "20260806041650")
        if target_t:
            monkeypatch.setenv("STATE_REPAIR_TARGET_T", target_t)
        else:
            monkeypatch.delenv("STATE_REPAIR_TARGET_T", raising=False)

    def test_fingerprint_env_누락_시_중단(self, monkeypatch):
        monkeypatch.delenv("STATE_REPAIR_SYMBOL", raising=False)
        with pytest.raises(RuntimeError, match="fingerprint 환경변수가 없습니다"):
            _repair_state_only()

    def test_fingerprint_불일치_시_중단(self, monkeypatch):
        state = _make_corrupted_state()
        # 기대 T를 상태와 다르게 설정 → 불일치
        self._set_fingerprint(monkeypatch, target_t="20", t="99.0")
        with patch("trading_bot.load_state", return_value=state), \
             patch("trading_bot.save_state") as mock_save:
            with pytest.raises(RuntimeError, match="fingerprint 불일치"):
                _repair_state_only()
        mock_save.assert_not_called()

    def test_target_t_보정시_리버스_cycle_유지(self, monkeypatch):
        """T=15 → 20 보정, reverse_mode/orders_meta는 보존 → 다음 RUN에서 reconciliation이 재계산."""
        state = _make_corrupted_state()
        self._set_fingerprint(monkeypatch, target_t="20")
        with patch("trading_bot.load_state", return_value=state), \
             patch("trading_bot.save_state") as mock_save:
            _repair_state_only()
        assert state["T"] == 20.0
        # 리버스 cycle/orders_meta 보존
        assert state["reverse_mode"]["active"] is True
        assert state["reverse_mode"]["cycle_id"] == "C8"
        assert "000004615" in state["orders_meta"]
        assert state["orders_meta"]["000004615"]["processed_filled_qty"] == 0
        mock_save.assert_called_once()

    def test_target_t_없으면_기존_reverse_mode_초기화(self, monkeypatch):
        state = _make_corrupted_state()
        self._set_fingerprint(monkeypatch)
        with patch("trading_bot.load_state", return_value=state), \
             patch("trading_bot.save_state") as mock_save:
            _repair_state_only()
        assert state["reverse_mode"] == {}
        assert state["T"] == 15.0
        mock_save.assert_called_once()
