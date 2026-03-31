# API 키, 환경변수 등 설정값을 관리하는 파일
import os
from dotenv import load_dotenv

# .env 파일에서 환경변수 읽기
load_dotenv()

# 한국투자증권 API 설정
KIS_APP_KEY = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
# 실계좌(기본) 계좌번호와 모의계좌(데모) 계좌번호를 분리해서 읽습니다.
# .env 예시: KIS_ACCOUNT_NO=12345678, KIS_ACCOUNT_NO_DEMO=87654321
KIS_ACCOUNT_NO_REAL = os.getenv("KIS_ACCOUNT_NO", "")
KIS_ACCOUNT_NO_DEMO = os.getenv("KIS_ACCOUNT_NO_DEMO", "")

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
	# 실전 모드 선택 시 실계좌를 사용합니다. 환경변수 미설정시 경고 출력
	KIS_ACCOUNT_NO = KIS_ACCOUNT_NO_REAL
	if not KIS_ACCOUNT_NO:
		print("경고: KIS_MODE=real 이지만 KIS_ACCOUNT_NO(실계좌)가 설정되어 있지 않습니다.")
else:
	KIS_DOMAIN = "https://openapivts.koreainvestment.com:29443"
	# 데모(모의) 모드에서는 데모 계좌를 사용합니다. 환경변수 미설정시 경고 출력
	KIS_ACCOUNT_NO = KIS_ACCOUNT_NO_DEMO
	if not KIS_ACCOUNT_NO:
		print("경고: KIS_MODE=demo 이지만 KIS_ACCOUNT_NO_DEMO(모의계좌)가 설정되어 있지 않습니다.")

# 종목 정보
# 여러 종목을 매매하려면 SYMBOLS 환경변수를 사용하세요.
# 사용법: SYMBOLS=TQQQ:NAS,SOXL:AMS
# 기존 단일 종목 방식도 계속 호환됩니다: SYMBOL=TQQQ EXCHANGE=NAS
#
# 종목별 세부 설정 (환경변수 이름 규칙: {종목코드}_{설정명})
# 예시:
#   TQQQ_SPLITS=40        → TQQQ 분할 수 (미설정 시 전역 SPLITS 사용)
#   TQQQ_TAKE_PROFIT=0.10 → TQQQ 익절률
#   TQQQ_BIG_BUY_RANGE=0.10 → TQQQ 큰수 상승률
#   TQQQ_SEED=10000       → TQQQ에 투입할 시드 (달러, 0이면 계좌 전체 사용)
#   SOXL_SPLITS=20
#   SOXL_SEED=5000
def _parse_symbols():
	"""
	환경변수에서 종목 목록을 읽어 종목별 설정 dict 리스트로 반환합니다.

	반환 형태:
	  [
	    {
	      "symbol": "TQQQ", "exchange": "NAS",
	      "splits": 40, "take_profit": 0.10, "big_buy_range": 0.10,
	      "seed": 10000  # 0이면 계좌 전체 사용
	    },
	    ...
	  ]

	설정 우선순위:
	  1. SYMBOLS=TQQQ:NAS,SOXL:AMS  (복수 종목)
	  2. SYMBOL=TQQQ  EXCHANGE=NAS  (기존 단일 종목 방식, 하위 호환)
	  3. 기본값: TQQQ(나스닥) + SOXL(아멕스)
	"""
	raw = os.getenv("SYMBOLS", "").strip()
	pairs = []
	if raw:
		for item in raw.split(","):
			item = item.strip()
			if ":" in item:
				sym, exch = item.split(":", 1)
				pairs.append((sym.strip().upper(), exch.strip().upper()))

	if not pairs:
		# 기존 단일 종목 방식 (하위 호환)
		single_symbol = os.getenv("SYMBOL", "").strip().upper()
		single_exchange = os.getenv("EXCHANGE", "").strip().upper()
		if single_symbol and single_exchange:
			pairs = [(single_symbol, single_exchange)]
		else:
			# 기본값: TQQQ(나스닥) + SOXL(아멕스)
			pairs = [("TQQQ", "NAS"), ("SOXL", "AMS")]

	result = []
	for sym, exch in pairs:
		result.append({
			"symbol": sym,
			"exchange": exch,
			# 종목별 설정이 없으면 전역 기본값을 사용합니다
			"splits": int(os.getenv(f"{sym}_SPLITS") or SPLITS),
			"take_profit": float(os.getenv(f"{sym}_TAKE_PROFIT") or TAKE_PROFIT),
			"big_buy_range": float(os.getenv(f"{sym}_BIG_BUY_RANGE") or BIG_BUY_RANGE),
			# 시드: 이 종목에 투입할 최대 금액 (달러). 0이면 계좌 전체 주문가능금액 사용
			"seed": float(os.getenv(f"{sym}_SEED") or "0"),
		})
	return result

SYMBOLS = _parse_symbols()

# 하위 호환성을 위해 첫 번째 종목을 SYMBOL/EXCHANGE로도 제공합니다
SYMBOL = SYMBOLS[0]["symbol"]
EXCHANGE = SYMBOLS[0]["exchange"]

# 계좌 정보
ACNT_PRDT_CD = "01"  # 계좌상품코드 (상품코드)

# 전략 파라미터
SPLITS = int(os.getenv("SPLITS") or "40")  # 분할 수
TAKE_PROFIT = float(os.getenv("TAKE_PROFIT") or "0.10")  # 익절률 (예: 0.10 = 10%)
BIG_BUY_RANGE = float(os.getenv("BIG_BUY_RANGE") or "0.10")  # 큰수 상승률 (예: 0.10 = 10%)

# 거래 모드
# 환경변수에서 값을 읽어 대문자로 정규화하고 유효성 검사 수행
_trade_mode_raw = os.getenv("TRADE_MODE") or ""
_trade_mode = _trade_mode_raw.strip().upper()
if _trade_mode not in ("DRY", "LIVE"):
	if _trade_mode_raw:
		print(f"경고: 잘못된 TRADE_MODE 값('{_trade_mode_raw}')이 감지되어 'DRY'로 설정합니다.")
	TRADE_MODE = "DRY"
else:
	TRADE_MODE = _trade_mode
