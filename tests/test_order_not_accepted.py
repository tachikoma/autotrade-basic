"""
주문 미접수 분류(OrderNotAcceptedError)와 가격 정규화 관련 테스트.

배경: 리버스모드 1일차 MOC 매도가 소수점 3자리 가격($116.756)으로 전달되어
키움 API가 ord_uv 형식 오류로 거부 → LIVE 배치가 전체 중단됐던 사례에서,
"확정적 미접수"만 fence를 해제하도록 타입 계약을 추가했습니다.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# src 디렉터리를 Python 경로에 추가
_src_path = str(Path(__file__).parent.parent / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from broker.base import (
    OrderError,
    OrderNotAcceptedError,
)
from broker.market_utils import normalize_order_price


def _make_response(json_data, status_code=200, headers=None):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.headers = headers or {"cont-yn": "N", "next-key": ""}
    if not resp.ok:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"HTTP {status_code}"
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


def test_order_not_accepted_is_order_error():
    """OrderNotAcceptedError는 OrderError의 하위 타입이어야 합니다 (호환성)."""
    assert issubclass(OrderNotAcceptedError, OrderError)


def test_normalize_order_price_rules():
    """가격 정규화: $1 이상은 소수점 2자리, $1 미만은 소수점 4자리 (버림)."""
    assert normalize_order_price(116.756) == 116.75
    assert normalize_order_price(69.189) == 69.18
    assert normalize_order_price(0.98769) == 0.9876
    assert normalize_order_price(50.0) == 50.0


class TestKiwoomOrderRejection:
    """키움 주문 거부/불확실 분류 테스트."""

    @pytest.fixture(autouse=True)
    def _patch_kiwoom(self, request):
        fixed_kst = datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        target = "broker.kiwoom.adapter"
        patches = [
            patch(f"{target}.KiwoomSession"),
            patch(f"{target}.get_access_token", return_value="mock_token"),
            patch(f"{target}.is_us_trading_day", return_value=True),
            patch(f"{target}.get_kst_now", return_value=fixed_kst),
            patch("config.BROKER_CONFIG", {
                "app_key": "test",
                "app_secret": "test",
                "account_no": "12345678",
                "domain": "https://mockapi.kiwoom.com",
                "acnt_prdt_cd": "",
            }),
            patch("config.BROKER_MODE", "real"),
            patch("config.HTTP_TIMEOUT", (10, 30)),
        ]
        for p in patches:
            p.start()
            request.addfinalizer(p.stop)

        session_cls = sys.modules[target].KiwoomSession
        session_instance = MagicMock()
        session_cls.return_value = session_instance
        self._mock_session = session_instance

    def _create_broker(self):
        from broker.kiwoom.adapter import KiwoomBroker
        return KiwoomBroker()

    def test_rejection_raises_order_not_accepted(self):
        """return_code != 0 (예: 가격 형식 오류) → OrderNotAcceptedError."""
        self._mock_session.request_with_tr.return_value = _make_response({
            "return_code": 2,
            "return_msg": "입력 값 오류입니다[1517:ord_uv 형식 오류]",
        })
        broker = self._create_broker()
        with pytest.raises(OrderNotAcceptedError, match="ord_uv"):
            broker.place_order("SOXL", "NY", "SELL", 32, 116.756, "MOC")

    def test_network_timeout_is_uncertain(self):
        """네트워크 타임아웃 → OrderError (미접수 확정 아님, fence 유지 대상)."""
        self._mock_session.request_with_tr.side_effect = requests.exceptions.ReadTimeout("timed out")
        broker = self._create_broker()
        with pytest.raises(OrderError) as excinfo:
            broker.place_order("SOXL", "NY", "SELL", 32, 116.756, "MOC")
        assert not isinstance(excinfo.value, OrderNotAcceptedError)

    def test_price_is_normalized_before_send(self):
        """$1 이상 가격은 소수점 2자리로 정규화되어 전달되어야 합니다."""
        captured = {}

        def _side_effect(tr_id, body, token, extra_headers=None):
            captured["body"] = dict(body)
            return _make_response({"return_code": 0, "ord_no": "12345"})

        self._mock_session.request_with_tr.side_effect = _side_effect
        broker = self._create_broker()
        broker.place_order("SOXL", "NY", "SELL", 32, 116.756, "MOC")

        assert captured["body"]["ord_uv"] == "116.75"


def test_reverse_day1_moc_price_is_tick_adjusted(monkeypatch):
    """리버스모드 1일차 MOC 매도 가격이 호가 단위로 보정되어야 합니다."""
    monkeypatch.setattr("strategy.get_finnhub_ma5", lambda symbol: None)
    from strategy import execute_reverse_mode

    state = {"T": 20.0, "reverse_mode": {}, "close_prices": [100.0]}
    result = execute_reverse_mode(
        broker=None,
        symbol="SOXL",
        exchange_code="NYS",
        splits=20,
        symbol_type="SOXL",
        position_qty=325,
        avg_price=192.149,
        orderable_cash=0.0,
        last_price=116.756,
        state=state,
    )

    assert result["orders"][0]["order_type"] == "MOC"
    assert result["orders"][0]["price"] == 116.75
