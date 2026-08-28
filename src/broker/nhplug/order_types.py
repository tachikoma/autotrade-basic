"""
NHPLUG 주문 유형 및 TR_ID 레지스트리 — 주문 유형 코드, TR_ID 매핑.

NH투자증권 나무 API의 ahi_nmn_pr_tp_cd 코드와 gbstock TR_ID를 정의합니다.
"""
from broker.base import OrderNotAcceptedError


# ── 주문 유형 코드 매핑 ──────────────────────────────────────────────
# NHPLUG API의 ahi_nmn_pr_tp_cd 코드 (openapi.json 정본 기준)
ORDER_TYPE_MAP = {
    "LIMIT":  "00",  # 지정가
    "MARKET": "03",  # 시장가
    "LOO":    "11",  # 장개시지정가
    "LOC":    "12",  # 장마감지정가
    "MOO":    "13",  # 장개시시장가
    "MOC":    "14",  # 장마감시장가
}

# 모의투자에서 지원하지 않는 주문 유형 — LIMIT으로 자동 변환
DEMO_UNSUPPORTED_ORDER_TYPES = {"LOC", "LOO", "MOO", "MOC"}


def get_ord_dvsn(order_type: str) -> str:
    """
    주문 유형명(LOC, LIMIT 등) → NHPLUG 주문 구분 코드(00, 06 등).

    Raises:
        OrderNotAcceptedError: 지원하지 않는 주문 유형인 경우
    """
    if order_type not in ORDER_TYPE_MAP:
        raise OrderNotAcceptedError(f"지원하지 않는 주문 유형입니다: {order_type}")
    return ORDER_TYPE_MAP[order_type]


# ── TR_ID 레지스트리 (gbstock) ───────────────────────────────────────
TR_ID_ACCTINFO = "N2ACCTINFO"               # 계좌번호 조회
TR_ID_PRICE = "GSS10030"                # 현재가
TR_ID_PERIOD = "GSC10060"               # 기간별시세 (일봉 종가)
TR_ID_BALANCE = "GSB10010"              # 잔고
TR_ID_BUYABLE_AMOUNT = "GSB10020"       # 매수가능금액
TR_ID_UNEXECUTED = "GSB10030"           # 체결내역/미체결
TR_ID_DAILY_TRANSACTION = "GSB10040"    # 일별거래내역
TR_ID_BUY_ORDER = "GSO10010"            # 매수 주문
TR_ID_SELL_ORDER = "GSO10020"           # 매도 주문
TR_ID_MODIFY_ORDER = "GSO10030"         # 정정
TR_ID_CANCEL_ORDER = "GSO10040"         # 취소