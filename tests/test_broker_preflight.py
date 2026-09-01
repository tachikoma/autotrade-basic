"""
브로커 preflight — 모의 전 API 사전 테스트 (read-only 전수 + 비시장성 주문·취소 1건)

용어: 인증 대신 preflight / 브로커 검증 / API 사전 테스트 사용.

실행:
  uv run python tests/test_broker_preflight.py --broker kis --symbol TQQQ
  uv run pytest tests/test_broker_preflight.py -v
  uv run pytest tests/test_broker_preflight.py -m preflight -v

전략이 실제 호출하는 API만 검증합니다:
  - get_daily_closes(5) → list[float]
  - get_balance / get_purchase_amount
  - get_order_history — 빈 이력과 체결 후 이력 표준 필드
  - get_stock_price / get_stock_quotation / is_trading_day
  - 주문 사전 테스트: BUY LIMIT 1주(현재가-5% 등) → 이력 매칭 → cancel → 0체결 재확인
    cancel 미구현 시 OrderNotAcceptedError 거부 확인으로 대체

단일 계좌·이력 최소화를 위해 비시장성 가격을 사용합니다. 취소 이력의 0체결은
state.py에서 ft_ccld_qty<=0 제외라 T/net_invested에 영향 없습니다.
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from broker.base import OrderNotAcceptedError, BrokerError

STANDARD_FIELDS = {
    "ord_dt", "ord_tmd", "ord_datetime_kst", "ord_datetime_utc",
    "prdt_name", "sll_buy_dvsn_cd_name", "ft_ord_qty", "ft_ccld_qty",
    "ft_ccld_unpr3", "ft_ccld_amt3", "nccs_qty", "prcs_stat_name",
    "tr_mket_name", "tr_crcy_cd", "odno", "ovrs_excg_cd",
}

# 브로커별 필수 자격증명 (tests/conftest.py와 동일 기준)
CREDENTIALS = {
    "kis": ["KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO"],
    "kiwoom": ["KIWOOM_APP_KEY", "KIWOOM_APP_SECRET"],
    "ls": ["LS_APP_KEY", "LS_APP_SECRET"],
    "toss": ["TOSS_APP_KEY", "TOSS_APP_SECRET"],
    "nhplug": ["NHPLUG_APP_KEY", "NHPLUG_APP_SECRET", "NHPLUG_ACCT_NO"],
}


def _has_credentials(broker: str) -> bool:
    keys = CREDENTIALS.get(broker, [])
    return all(os.getenv(k) for k in keys)


def _create_real_broker(broker: str):
    """TRADE_MODE와 무관하게 실제 브로커 인스턴스를 생성합니다 (DryBroker 우회)."""
    broker = broker.lower()
    if broker == "kis":
        from broker.kis.adapter import KISBroker
        return KISBroker()
    if broker == "kiwoom":
        from broker.kiwoom.adapter import KiwoomBroker
        return KiwoomBroker()
    if broker == "ls":
        from broker.ls.adapter import LSBroker
        return LSBroker()
    if broker == "toss":
        from broker.toss.adapter import TossBroker
        return TossBroker()
    if broker == "nhplug":
        from broker.nhplug.adapter import NHPlugBroker
        return NHPlugBroker()
    raise ValueError(f"알 수 없는 브로커: {broker}")


def _check_standard_fields(history):
    if not history:
        return
    for item in history:
        missing = STANDARD_FIELDS - set(item.keys())
        assert not missing, f"표준 필드 누락: {missing} / keys={sorted(item.keys())}"


def run_preflight(broker_name: str, symbol: str = "TQQQ", exchange: str = "NAS"):
    broker_name = broker_name.lower()
    symbol = symbol.upper()

    if not _has_credentials(broker_name):
        print(f"[preflight skip] {broker_name} 자격증명 없음 → skip")
        return "skip"

    broker = _create_real_broker(broker_name)
    print(f"[preflight] broker={broker_name} symbol={symbol} exchange={exchange}")

    # 1) read-only 전수
    print("[1/6] is_trading_day")
    trading_day = broker.is_trading_day()
    assert isinstance(trading_day, bool)
    print(f"  → {trading_day}")

    print("[2/6] get_stock_price / get_stock_quotation")
    price = broker.get_stock_price(symbol, exchange)
    print(f"  price open={price.open} last={price.last}")
    quotation = broker.get_stock_quotation(symbol, exchange)
    print(f"  quotation tradable={quotation.tradable} last={quotation.last}")
    assert quotation.last > 0

    print("[3/6] get_balance")
    balance = broker.get_balance(symbol, exchange)
    print(f"  balance={balance}")

    print("[4/6] get_purchase_amount (orderable_cash)")
    pa = broker.get_purchase_amount(symbol, exchange)
    print(f"  orderable_cash={pa.orderable_cash}")
    assert pa.orderable_cash >= 0

    print("[5/6] get_daily_closes(5)")
    closes = broker.get_daily_closes(symbol, exchange, days=5)
    print(f"  closes({len(closes)}): {closes}")
    assert isinstance(closes, list)

    print("[6/6] get_order_history — 빈 이력 파싱")
    history = broker.get_order_history(symbol, exchange, days=5)
    print(f"  history {len(history)}건")
    _check_standard_fields(history)
    # 체결 후 이력이 있으면 표준 필드 재검증 (없으면 빈 케이스만 통과)
    if history:
        print("  표준 필드 확인 완료")
    else:
        print("  이력 없음 — 빈 응답 처리 확인")

    # 7) 주문 사전 테스트 — 비시장성 LIMIT 1주
    # 전략 종목과 동일 계좌에서 이력을 남기므로, 비시장성 가격으로 0체결을 노립니다.
    has_cancel = hasattr(broker, "cancel_order")
    print(f"[7/7] 주문 사전 테스트 (cancel 구현={has_cancel})")

    # 현재가 기준 -5% 가격 (호가는 adapter가 normalize)
    non_market_price = round(quotation.last * 0.95, 2) if quotation.last else 10.0
    if non_market_price <= 0:
        non_market_price = 1.0
    print(f"  BUY LIMIT 1주 @ ${non_market_price} (현재가 ${quotation.last} 대비 -5%)")

    if has_cancel:
        # 성공 접수 → 이력 매칭 → 취소 → 재확인
        ex_code = broker.exchange_code(exchange)
        result = broker.place_order(symbol, ex_code, "BUY", 1, non_market_price, "LIMIT")
        assert result is not None and result.order_id, "주문 접수 실패 — OrderResult 없음"
        odno = str(result.order_id)
        print(f"  접수 odno={odno} time={result.order_time} reservation={result.is_reservation}")
        # 데모 LOC/MOC→LIMIT 변환 로그는 adapter가 출력
        time.sleep(1.0)
        history_after = broker.get_order_history(symbol, exchange, days=5)
        matched = [h for h in history_after if str(h.get("odno")) == odno or str(h.get("odno")).lstrip("0") == odno.lstrip("0")]
        assert matched, f"주문이력에서 odno={odno} 미발견 — ord_dt/odno 매핑 확인 필요"
        print(f"  이력 매칭 {len(matched)}건 odno={odno}")

        # 취소
        print(f"  cancel_order odno={odno}")
        # cancel_order 시그니처는 브로커별 상이할 수 있어 위치 인자 1개 우선 시도
        try:
            broker.cancel_order(odno)  # type: ignore
        except TypeError:
            broker.cancel_order(odno, symbol, exchange)  # type: ignore
        time.sleep(1.5)
        history_canceled = broker.get_order_history(symbol, exchange, days=5)
        canceled = [h for h in history_canceled if str(h.get("odno")) == odno or str(h.get("odno")).lstrip("0") == odno.lstrip("0")]
        assert canceled, f"취소 후 이력에서 odno={odno} 미발견"
        item = canceled[0]
        _check_standard_fields([item])
        ft_ccld = int(float(item.get("ft_ccld_qty", "0") or 0))
        nccs = int(float(item.get("nccs_qty", "0") or 0)) if item.get("nccs_qty") is not None else 0
        status = str(item.get("prcs_stat_name", ""))
        print(f"  취소 후 상태={status} ft_ccld_qty={ft_ccld} nccs_qty={nccs}")
        assert ft_ccld == 0, f"0체결 취소 기대였으나 ft_ccld_qty={ft_ccld} — 체결 발생 시 전량매도 복원 없이 모의 진입 금지"
        # remaining 0은 브로커별 nccs_qty 0 또는 prcs_stat_name 취소로 확인
        assert nccs == 0 or "취소" in status or "CANCEL" in status.upper(), f"취소 미완료: {item}"
        print("[preflight 통과] read-only 전수 + 주문·취소 1건 0체결 확인")
    else:
        print("  cancel 미구현 → OrderNotAcceptedError 거부 확인으로 대체")
        ex_code = broker.exchange_code(exchange)
        try:
            broker.place_order(symbol, ex_code, "BUY", 99999, 0.01, "LIMIT")
            raise AssertionError("OrderNotAcceptedError 기대였으나 주문이 접수됨")
        except OrderNotAcceptedError as e:
            print(f"  거부 확인: {e}")
            print("[preflight 통과] read-only 전수 + 거부 경로 확인 (성공 접수 경로는 모의 첫 주문으로 위임)")
        except BrokerError as e:
            # 일부 브로커는 BrokerError로 거부
            print(f"  거부(BrokerError) 확인: {e}")
            print("[preflight 통과] read-only 전수 + 거부 경로 확인")

    broker.close()
    return "pass"


# pytest 진입점 — 자격증명 없으면 skip, 있으면 실 API 호출
@pytest.mark.preflight
@pytest.mark.parametrize("broker_name", ["kis", "kiwoom", "ls", "toss", "nhplug"])
def test_preflight_all_brokers(broker_name):
    if not _has_credentials(broker_name):
        pytest.skip(f"{broker_name} 자격증명 없음")
    result = run_preflight(broker_name, symbol="TQQQ", exchange="NAS")
    assert result in ("pass", "skip")


def test_preflight_kis_tqqq():
    if not _has_credentials("kis"):
        pytest.skip("KIS 자격증명 없음")
    assert run_preflight("kis", "TQQQ", "NAS") in ("pass", "skip")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="브로커 preflight — 모의 전 API 사전 테스트")
    parser.add_argument("--broker", required=True, help="kis|kiwoom|ls|toss|nhplug")
    parser.add_argument("--symbol", default="TQQQ", help="예: TQQQ, SOXL")
    parser.add_argument("--exchange", default="NAS", help="예: NAS, AMS")
    args = parser.parse_args()
    sys.exit(0 if run_preflight(args.broker, args.symbol, args.exchange) in ("pass", "skip") else 1)
