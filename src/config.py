# API 키, 환경변수 등 설정값을 관리하는 파일
import os
from dotenv import load_dotenv

# .env 파일에서 환경변수 읽기
load_dotenv()

# 한국투자증권 API 설정
KIS_APP_KEY = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
KIS_ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO", "")

# 한국투자증권 API 엔드포인트
# 환경변수 `KIS_MODE`로 demo(모의) 또는 real(실전) 환경을 선택합니다.
# 기본값은 demo(모의)입니다. .env 예: KIS_MODE=real
#
# KIS_MODE 값 매핑:
# - "real": https://openapi.koreainvestment.com:9443
# - 기타(기본): https://openapivts.koreainvestment.com:29443 (모의)
KIS_MODE = os.getenv("KIS_MODE", "demo").strip().lower()
if KIS_MODE == "real":
	KIS_DOMAIN = "https://openapi.koreainvestment.com:9443"
else:
	KIS_DOMAIN = "https://openapivts.koreainvestment.com:29443"

# 종목 정보
SYMBOL = os.getenv("SYMBOL") or "TQQQ"  # 종목 코드 (예: TQQQ, AAPL, TSLA)
EXCHANGE = os.getenv("EXCHANGE") or "NAS"  # 거래소 코드 (NAS: 나스닥, NYS: 뉴욕 등)

# 계좌 정보
ACNT_PRDT_CD = "01"  # 계좌상품코드 (상품코드)

# 전략 파라미터
SPLITS = int(os.getenv("SPLITS") or "40")  # 분할 수
TAKE_PROFIT = float(os.getenv("TAKE_PROFIT") or "0.10")  # 익절률 (예: 0.10 = 10%)
BIG_BUY_RANGE = float(os.getenv("BIG_BUY_RANGE") or "0.10")  # 큰수 상승률 (예: 0.10 = 10%)

# 거래 모드
TRADE_MODE = os.getenv("TRADE_MODE") or "DRY"  # 거래 모드 (DRY: 주문 정보만 출력, LIVE: 실제 주문)
