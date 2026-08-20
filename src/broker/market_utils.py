"""
시장/시간 공통 유틸리티 — 증권사 무관한 공통 함수들.

KIS, 키움, LS 등 모든 증권사가 공통으로 사용하는
시간 계산, 미국 장 영업일 확인 등의 유틸리티를 제공합니다.
"""
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import exchange_calendars as xcals


_XNYS_CALENDAR = None


def get_kst_now() -> datetime:
    """한국시간(KST) 현재 시각을 반환합니다."""
    return datetime.now(ZoneInfo("Asia/Seoul"))


def resolve_real_kst_from_ord(ord_dt: str, ord_tmd: str):
    """KIS 계열(주문일=미국 영업일, 주문시각=KST) 주문이력의 실제 한국 시각을 복원합니다.

    한국 증권사(KIS/LS/키움) 해외주식 주문이력 API는 ord_dt=미국(ET) 영업일,
    ord_tmd=KST 시각을 반환합니다. 봇이 장중(KST 자정 전후) 주문하므로 KST
    날짜는 ord_dt 또는 ord_dt+1입니다. 후보 KST 시각을 ET로 되돌렸을 때
    날짜가 ord_dt와 일치하는 후보를 선택합니다.

    실패 시 None을 반환합니다.
    """
    kst_tz = ZoneInfo("Asia/Seoul")
    et_tz = ZoneInfo("America/New_York")
    for offset_days in (0, 1):
        try:
            candidate = datetime.strptime(ord_dt + ord_tmd, "%Y%m%d%H%M%S")
            candidate = candidate.replace(tzinfo=kst_tz) + timedelta(days=offset_days)
            if candidate.astimezone(et_tz).strftime("%Y%m%d") == ord_dt:
                return candidate
        except Exception:
            continue
    try:
        return datetime.strptime(ord_dt + ord_tmd, "%Y%m%d%H%M%S").replace(tzinfo=kst_tz)
    except Exception:
        return None


def normalize_order_price(price) -> float:
    """
    미국 주식 호가 단위 규칙에 맞춰 주문가를 정규화합니다 (버림).

    규칙:
    - $1.00 미만: 소수점 4자리까지 ($0.0001 단위)
    - $1.00 이상: 소수점 2자리까지 ($0.01 단위)

    브로커가 거부하는 소수점 자릿수 초과 가격을 미리 차단합니다.

    IEEE 754 부동소수점 오차 방지를 위해 Decimal 연산을 사용합니다.
    예: math.floor(140.42 * 100) / 100 = 140.41 (버그) → 이 함수는 140.42 반환
    """
    from decimal import Decimal
    price = float(price)
    if price < 1.0:
        return float(int(Decimal(str(price)) * 10000) / 10000)
    return float(int(Decimal(str(price)) * 100) / 100)


def is_us_dst() -> bool:
    """현재 시각 기준으로 미국 동부시간(ET)의 서머타임 적용 여부를 반환합니다."""
    ny_now = datetime.now(ZoneInfo("America/New_York"))
    return bool(ny_now.dst() and ny_now.dst() != timedelta(0))


def is_us_trading_day() -> bool:
    """
    오늘이 미국 증시 영업일인지 확인합니다 (NYSE 기준).

    exchange_calendars 라이브러리의 XNYS(뉴욕증권거래소) 캘린더를 사용하여
    오늘 날짜가 정규 세션일인지 판단합니다.

    Returns:
        True: 오늘은 영업일 (정규장이 열리는 날)
        False: 오늘은 휴장일 (주말 또는 공휴일)
    """
    global _XNYS_CALENDAR
    if _XNYS_CALENDAR is None:
        _XNYS_CALENDAR = xcals.get_calendar("XNYS")
    now_et = datetime.now(ZoneInfo("America/New_York"))
    return _XNYS_CALENDAR.is_session(now_et.strftime("%Y-%m-%d"))
