"""
NHPLUG 시장 시간 유틸 — KIS 모의투자 장 시간 로직을 공유합니다.

NHPLUG는 현재 예약주문을 사용하지 않지만, 향후 모의투자 장 시간 제약이
필요할 경우를 대비해 KIS의 market_hours 유틸을 재사용합니다.
"""
from broker.kis.market_hours import (
    is_kst_regular_market,
    is_kst_reserve_window,
    mask_account_no,
)

__all__ = ["is_kst_regular_market", "is_kst_reserve_window", "mask_account_no"]