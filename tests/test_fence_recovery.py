"""
주문 fence 복구 로직 테스트.

배경: 불확실 주문(네트워크 오류 등)으로 남은 pending_order_intent/pending_order_batch가
모든 종목의 LIVE 실행을 시작 전에 막아 TQQQ까지 멈추는 사례에서,
이전 세션의 fence는 이력이 정착된 다음 RUN에서 자동 해제하도록 개선했습니다.
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

import pytest

# repo 루트 + src 경로 추가 (trading_bot import용)
_repo_root = os.path.join(os.path.dirname(__file__), "..")
_src_path = os.path.join(_repo_root, "src")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

import trading_bot
from trading_bot import _fence_session, _recover_order_fence, _clear_fence_only


def _make_state(**overrides):
    state = {
        "T": 20.0,
        "last_updated": "2026-07-29T19:16:45+00:00",
        "cycle_start_date": "",
        "effective_seed": 50000.0,
        "last_processed_ordno": "",
        "additional_loc_odno": [],
        "orders_meta": {},
        "balance_mismatch": {},
        "state_version": "v2",
        "close_prices": [],
        "reverse_mode": {},
        "pending_order_intent": None,
        "pending_order_batch": None,
    }
    state.update(overrides)
    return state


def _prior_session():
    """오늘보다 확실히 과거인 미국 세션 (YYYY-MM-DD)."""
    return "2020-01-01"


def _intent(session=None):
    return {
        "symbol": "SOXL",
        "side": "SELL",
        "quantity": 50,
        "price": 116.75,
        "order_type": "MOC",
        "comment": "[리버스] 1일차 MOC 매도",
        "submitted_session": session or _prior_session(),
    }


def _batch(session=None):
    return {
        "session": session or _prior_session(),
        "orders": [
            {"side": "SELL", "quantity": 50, "price": 116.75,
             "order_type": "MOC", "comment": "[리버스] 1일차 MOC 매도"},
        ],
    }


# ─────────────────────────────────────────────────────────
# _fence_session
# ─────────────────────────────────────────────────────────

class TestFenceSession:
    def test_intent_세션_반환(self):
        state = _make_state(pending_order_intent=_intent("2026-07-30"))
        assert _fence_session(state) == "2026-07-30"

    def test_batch_세션_반환(self):
        state = _make_state(pending_order_batch=_batch("2026-07-30"))
        assert _fence_session(state) == "2026-07-30"

    def test_intent_우선(self):
        state = _make_state(
            pending_order_intent=_intent("2026-07-30"),
            pending_order_batch=_batch("2026-07-29"),
        )
        assert _fence_session(state) == "2026-07-30"

    def test_fence_없으면_빈문자열(self):
        assert _fence_session(_make_state()) == ""

    def test_세션정보_없으면_빈문자열(self):
        intent = _intent()
        intent.pop("submitted_session", None)
        assert _fence_session(_make_state(pending_order_intent=intent)) == ""


# ─────────────────────────────────────────────────────────
# _recover_order_fence
# ─────────────────────────────────────────────────────────

class TestRecoverOrderFence:
    def test_fence_없으면_False(self):
        with patch("trading_bot.save_state") as mock_save, \
             patch("trading_bot.notify") as mock_notify:
            result = _recover_order_fence(_make_state(), "SOXL", live_qty=100)
        assert result is False
        mock_save.assert_not_called()
        mock_notify.assert_not_called()

    def test_이전_세션_intent_해제(self):
        state = _make_state(pending_order_intent=_intent())
        with patch("trading_bot.save_state") as mock_save, \
             patch("trading_bot.notify") as mock_notify:
            result = _recover_order_fence(state, "SOXL", live_qty=100)
        assert result is True
        assert state["pending_order_intent"] is None
        assert state["pending_order_batch"] is None
        mock_save.assert_called_once()
        mock_notify.assert_called_once()

    def test_이전_세션_batch_해제(self):
        state = _make_state(pending_order_batch=_batch())
        with patch("trading_bot.save_state") as mock_save, \
             patch("trading_bot.notify") as mock_notify:
            result = _recover_order_fence(state, "SOXL", live_qty=100)
        assert result is True
        assert state["pending_order_batch"] is None
        mock_save.assert_called_once()

    def test_잔고_확인_불가_시_fence_유지(self):
        state = _make_state(pending_order_intent=_intent())
        with patch("trading_bot.save_state") as mock_save:
            with pytest.raises(RuntimeError, match="잔고를 확인할 수 없어"):
                _recover_order_fence(state, "SOXL", live_qty=None)
        # fence는 그대로 유지 (저장되지 않음)
        assert state["pending_order_intent"] is not None
        mock_save.assert_not_called()

    def test_같은_세션_fence_유지(self):
        today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        state = _make_state(pending_order_intent=_intent(session=today))
        with patch("trading_bot.save_state") as mock_save:
            with pytest.raises(RuntimeError, match="fence가 남아 있어"):
                _recover_order_fence(state, "SOXL", live_qty=100)
        assert state["pending_order_intent"] is not None
        mock_save.assert_not_called()

    def test_세션정보_없으면_fence_유지(self):
        intent = _intent()
        intent.pop("submitted_session", None)
        state = _make_state(pending_order_intent=intent)
        with patch("trading_bot.save_state") as mock_save:
            with pytest.raises(RuntimeError, match="fence가 남아 있어"):
                _recover_order_fence(state, "SOXL", live_qty=100)
        assert state["pending_order_intent"] is not None
        mock_save.assert_not_called()


# ─────────────────────────────────────────────────────────
# _clear_fence_only (일회성 수동 복구)
# ─────────────────────────────────────────────────────────

def _intent_json(session=None):
    import json
    return json.dumps(_intent(session), ensure_ascii=False, sort_keys=True)


def _batch_json(session=None):
    import json
    return json.dumps(_batch(session), ensure_ascii=False, sort_keys=True)


class TestClearFenceOnly:
    def _set_env(self, monkeypatch, symbol="SOXL", t="20.0",
                 updated="2026-07-29T19:16:45+00:00", intent="", batch=""):
        monkeypatch.setenv("STATE_CLEAR_FENCE_SYMBOL", symbol)
        monkeypatch.setenv("STATE_CLEAR_FENCE_EXPECT_T", t)
        monkeypatch.setenv("STATE_CLEAR_FENCE_EXPECT_LAST_UPDATED", updated)
        monkeypatch.setenv("STATE_CLEAR_FENCE_EXPECT_INTENT", intent)
        monkeypatch.setenv("STATE_CLEAR_FENCE_EXPECT_BATCH", batch)

    def test_fingerprint_env_누락_시_중단(self, monkeypatch):
        monkeypatch.delenv("STATE_CLEAR_FENCE_SYMBOL", raising=False)
        monkeypatch.setenv("STATE_CLEAR_FENCE_ONLY", "true")
        with pytest.raises(RuntimeError, match="fingerprint 환경변수가 없습니다"):
            _clear_fence_only()

    def test_fingerprint_불일치_시_중단(self, monkeypatch):
        state = _make_state(
            pending_order_intent=_intent(),
            pending_order_batch=_batch(),
        )
        # 기대 fingerprint를 상태와 다르게 설정 (세션 다름) → 불일치
        self._set_env(
            monkeypatch,
            intent=_intent_json(session="2020-01-02"),
            batch=_batch_json(session="2020-01-02"),
        )
        with patch("trading_bot.load_state", return_value=state) as mock_load, \
             patch("trading_bot.save_state") as mock_save:
            with pytest.raises(RuntimeError, match="fingerprint 불일치"):
                _clear_fence_only()
        mock_save.assert_not_called()

    def test_fingerprint_일치_시_fence_해제(self, monkeypatch):
        state = _make_state(
            pending_order_intent=_intent(),
            pending_order_batch=_batch(),
        )
        self._set_env(monkeypatch, intent=_intent_json(), batch=_batch_json())
        with patch("trading_bot.load_state", return_value=state), \
             patch("trading_bot.save_state") as mock_save:
            _clear_fence_only()
        assert state["pending_order_intent"] is None
        assert state["pending_order_batch"] is None
        mock_save.assert_called_once()

    def test_fence_이미_없으면_무처리(self, monkeypatch, capsys):
        state = _make_state()
        self._set_env(monkeypatch, intent="", batch="")
        with patch("trading_bot.load_state", return_value=state), \
             patch("trading_bot.save_state") as mock_save:
            _clear_fence_only()
        out = capsys.readouterr().out
        assert "남아 있는 fence가 없습니다" in out
        mock_save.assert_not_called()
