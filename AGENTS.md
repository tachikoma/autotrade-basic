# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-25
**Updated:** 2026-07-30
**Branch:** `develop`

## OVERVIEW
미국 주식 자동매매 봇 (Python). 4개 증권사(KIS, KIWOOM, LS, TOSS) API를 지원하며, 무한매수법 V4 전략을 실행. GitHub Actions에서 `repository_dispatch`로 트리거됨.

## STRUCTURE
```
autotrade-basic/
├── src/
│   ├── broker/          # 브로커별 API 구현체
│   │   ├── base.py      # 공통 에러/데이터 클래스
│   │   ├── kis/         # 한국투자증권
│   │   ├── kiwoom/      # 키움증권
│   │   ├── ls/          # LS증권
│   │   ├── toss/        # 토스증권
│   │   └── market_utils.py  # 시간/시장 유틸리티
│   ├── market_data.py   # 시세 데이터 (Finnhub 5일 MA)
│   ├── strategy.py      # 전략 로직 (+ 리버스모드)
│   ├── state.py         # 상태 관리 (+ reverse_mode/close_prices)
│   ├── config.py        # 환경변수 설정
│   ├── telegram.py      # 텔레그램 발송
│   └── notifier.py      # 알림 라우팅
├── tests/               # pytest 기반 테스트
├── .github/workflows/   # GitHub Actions
└── trading_bot.py       # 메인 파이프라인
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| 전략 로직 이해 | src/strategy.py | `무한매수법_V4()`, T값/별지점 계산, `execute_reverse_mode()` |
| 브로커 구현 | src/broker/{kis,kiwoom,ls,toss}/ | 각 브로커별 API 어댑터 |
| 공통 인터페이스 | src/broker/base.py | `Broker`, `OrderResult`, `BrokerError`, `get_daily_closes()` |
| 일봉 종가 조회 | src/broker/base.py `get_daily_closes()` | TR: KIS=HHDFS76240000, LS=g3204, KIWOOM=usa06012, TOSS=GET /api/v1/candles |
| 상태 파일 관리 | src/state.py | state.json 로드/저장, T 갱신, reverse_mode 상태 |
| 환경변수 설정 | src/config.py | 종목 설정, 모드, 수수료, T 보정 env var |
| 시세 데이터 | src/market_data.py | Finnhub 5일 이동평균 조회 |
| 파이프라인 흐름 | trading_bot.py | state→전략→주문→저장 전체 순서 |

## BROKER ERROR HANDLING
| 브로커 | 성공 코드 | 에러 코드 | 에러 메시지 | 검증 위치 |
|--------|----------|----------|------------|----------|
| KIS | `rt_cd == "0"` | `msg_cd` | `msg1` | 각 메서드 |
| KIWOOM | `return_code == 0` | `return_code` | `return_msg` | `_check_response()` |
| LS | `rsp_cd == "00000"` | `rsp_cd` | `rsp_msg` | 각 메서드 |
| TOSS | `error` 없음 | `error.code` | `error.message` | `_request_with_rate_retry()` |

**참고**: 주문 시각은 모든 브로커에서 `get_kst_now()` 로컬 시간 사용 (API 응답 시간 미사용)

## CONVENTIONS
- **패키지 의존성**: `requests`, `python-dotenv`, `exchange-calendars` (`uv` 관리)
- **실행**: `uv run python trading_bot.py` / `uv run python tests/test_dryrun.py`
- **환경변수**: `.env` 파일, 대문자 snake_case (예: `KIS_APP_KEY`, `TRADE_MODE`)
- **KoCra v4**: 변수/함수명은 영어, 주석/로그는 한국어
- **한 함수 한 역할**: 함수당 단일 책임 원칙
- **김작가님 규칙**: 초보자 가독성 우선, 과도한 추상화 금지
- **Finnhub API**: 리버스모드 5일 MA 별지점 계산용 (선택, 없으면 state close_prices fallback)

## ANTI-PATTERNS (THIS PROJECT)
- `__pycache__/` — 절대 커밋 금지 (`.gitignore`에 있음)
- `.state.json` — 커밋 금지 (GH Actions 캐시로만 관리)
- `KIS_ACCOUNT_NO` 없는 상태로 KIS API 호출 금지 (KIWOOM/LS/TOSS는 계좌번호 불필요)
- 모의투자 미지원 주문 유형(LOC/LOO/MOC/MOO) → 자동 LIMIT 변환 (broker별 adapter)
- `TRADE_MODE` 무단 LIVE 전환 금지 (DRY 먼저 확인)
- `.venv` 의존성 직접 수정 금지 — 항상 `uv` 사용
- `FINNHUB_API_KEY` 없어도 동작은 하나, 리버스모드 MA(5) 별지점 정확도를 위해 등록 권장

## UNIQUE STYLES
- 유니코드 함수명 `무한매수법_V4()` — 전략 함수만 한글명
- T값(float)이 누적 매수 횟수를 나타내는 독특한 상태 관리
- 모의/실전 TR_ID를 KIS_MODE에 따라 동적 전환
- DRY 모드에서는 주문 출력만 하고 실행하지 않음
- 리버스모드(`execute_reverse_mode()`): T≥분할수 시 발동, 5일 MA 별지점 기반 무한매도+쿼터매수
- T값 환경변수 보정: `FORCE_T_REINFERENCE`, `{SYMBOL}_FORCE_T`, `{SYMBOL}_MAX_T`

## COMMANDS
```bash
# 전략 what-if 검증 (API/상태 미접촉)
uv run python tests/test_dryrun.py

# DRY 모드 실행
TRADE_MODE=DRY uv run python trading_bot.py

# LIVE 모드 실행 (실제 주문)
TRADE_MODE=LIVE uv run python trading_bot.py

# T값 보정: 전체 이력 재추정 (DRY 자동 전환)
FORCE_T_REINFERENCE=true uv run python trading_bot.py

# T값 강제 설정 (1회성)
TQQQ_FORCE_T=29 SOXL_FORCE_T=19 TRADE_MODE=DRY uv run python trading_bot.py

# T값 상한 설정 (재추정 시 분할수 초과 방지)
SOXL_MAX_T=19 FORCE_T_REINFERENCE=true uv run python trading_bot.py

# 테스트 실행
uv run pytest tests/ -v
```

## COMMUNICATION RULES

- **질문과 수정 요청 구분**: 사용자가 물음표(?)로 끝내면 "질문"으로 간주한다.
  - 질문에는 **분석/답변만** 하고, 코드 수정을 하지 않는다.
  - 수정이 필요하면 사용자가 명시적으로 "수정해줘", "진행해줘", "적용해줘" 등으로 요청해야 한다.
  - 답변 중 수정이 필요하다고 판단되면 "수정할까요?"라고 먼저 물어본다.
- **검증 요청은 수정 아님**: "확인해줘", "맞는지 봐줘" 등은 검증만 수행하고 결과만 보고한다.

## NOTES
- GitHub Actions: `repository_dispatch`로만 트리거 (cron 없음)
- 기본 거래소: TQQQ(NAS), SOXL(AMS)
- KIS 모의투자는 초당 1회, 실전은 초당 20회 rate-limit
- LS 조회 TR(g3101 등)은 초당 1회, 주문 TR은 초당 10회 rate-limit (모의/실전 동일)
- 복리 재투자: `REINVEST` 기본 활성화 (해제 시 `false`)
- **시드 설정 필수**: 모든 종목에 `{SYMBOL}_SEED` 설정 필수 (달러 금액만 허용, FULL 미지원)
- **KIWOOM/LS/TOSS**: `BROKER_CONFIG`에 `account_no` 불필요 (AppKey/Secret만으로 API 호출 가능)
- **주문 시각**: 모든 브로커에서 `get_kst_now()` 사용 (API 응답 시간 미사용)
- **KIS ODNO 정규화**: 주문 접수 API는 leading zero 10자리(`0000052248`), 체결 조회는 trimmed(`52248`) 반환 → `kis/adapter.py`에서 `str(int(odno))`로 정규화 후 반환 (다른 브로커는 해당 없음)
- **KIWOOM 모의투자 주문이력(ust21150)**: 날짜별 개별 조회, 빈 결과/`501724` 에러 시 `[정보]` 로그 출력 (line 534-545)
- **ORDER_HISTORY_VERBOSE=true**: LIVE 모드에서도 `[주문이력 요약]` 상세 출력 (DRY는 항상 출력). KIS/KIWOOM/LS/TOSS 공통
- **T 보정 환경변수**:
  - `FORCE_T_REINFERENCE=true`: `last_updated` 초기화 → 전체 이력(90일)에서 T 재추정 (LIVE→DRY 자동 전환)
  - `{SYMBOL}_FORCE_T={value}`: state.json의 T를 강제 덮어쓰기 (orders_meta/balance_mismatch 초기화)
  - `{SYMBOL}_MAX_T={value}`: T 자동추정 결과의 상한선 (기본값: `{SYMBOL}_SPLITS - 1`, 분할수 초과 방지)
  - FORCE_T_REINFERENCE 실행 시 small_seed_days(소액 시드 오추정)가 감지되면 포지션 기반 T 추정값이 함께 출력되며, 해당 값을 `{SYMBOL}_FORCE_T`로 설정하여 직접 보정 가능
- **리버스모드** (`src/strategy.py execute_reverse_mode()`):
  - 발동: `T >= splits` + position > 0
  - 1일차: MOC 매도 (보유량 1/10(20분할) or 1/20(40분할)) → T × 0.9/0.95
  - 2일차+: LOC 매도 @5일MA + LOC 매수 (잔금/4) @별지점-0.01
  - T 갱신: 매도×0.9/0.95, 매수 후 T+(분할수-T)×0.25
  - 종료 조건: 종가 > 평단×(1-0.15)(TQQQ) or ×(1-0.20)(SOXL)
  - 별지점: Finnhub 5일 MA → close_prices(state) → last_price fallback
- **close_prices**: state.json에 최근 5거래일 종가 저장 (Finnhub fallback용)
- **`get_daily_closes()`** (`src/broker/base.py`):
  - Broker 추상 메서드: `(symbol, exchange, days=5) → list[float]` (오래된 종가순)
  - KIS: HHDFS76240000 → `GET /uapi/overseas-price/v1/quotations/dailyprice` (최신순 → 역순)
  - LS: g3204 → `POST /overseas-stock/market-data` (최신순 → 역순) + Finnhub candle fallback
  - KIWOOM: usa06012 → `POST /api/us/chart` (최신순 → 역순)
  - TOSS: `GET /api/v1/candles?interval=1d` (최신순 → `reversed()`)
  - 리버스모드 `_get_reverse_star_point()`에서 close_prices 보강용으로 사용 가능
