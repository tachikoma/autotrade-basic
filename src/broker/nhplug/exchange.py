"""
NHPLUG 거래소 코드 매핑 — 사용자 코드 ↔ 국가코드/통화코드.

NHPLUG는 미국 주식 모두 fc_sec_trd_nat_cd="200"을 사용합니다 (NAS/NYS/AMS 구분 없음).
"""
from broker.base import BrokerError


# 사용자 거래소 코드 → (외화증권거래국가코드, 통화코드)
_EXCHANGE_MAP = {
    "NAS": ("200", "USD"),      # 미국 나스닥
    "NYS": ("200", "USD"),      # 미국 뉴욕
    "AMS": ("200", "USD"),      # 미국 아멕스
    "JPN": ("070", "JPY"),      # 일본
    "HKG": ("120", "HKD"),      # 홍콩
    "SHH": ("160", "CNY"),      # 상해
    "SHZ": ("170", "CNY"),      # 심천
}


def convert_exchange_code(exchange_code: str) -> tuple[str, str]:
    """
    API 호출에 사용되는 국가코드와 통화코드로 변환합니다.

    Parameters:
        exchange_code (str): 사용자 입력 거래소 코드 (NAS, NYS, AMS 등)

    Returns:
        tuple: (외화증권거래국가코드, 통화코드)

    Raises:
        BrokerError: 지원하지 않는 거래소 코드인 경우
    """
    if exchange_code in _EXCHANGE_MAP:
        return _EXCHANGE_MAP[exchange_code]
    raise BrokerError(f"지원하지 않는 거래소 코드입니다: {exchange_code}")


def get_api_exchange_code(exchange_code: str) -> str:
    """사용자 거래소 코드 → 국가코드만 반환 (예: 'NAS' → '200')."""
    return convert_exchange_code(exchange_code)[0]