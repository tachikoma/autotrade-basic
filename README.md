자동매매 봇(autotrade-basic)
===========================

이 문서는 저장소의 워크플로우 사용법과 `.env` / GitHub `Secrets` 및 `Repository variables` 설정 가이드를 제공합니다.

**요약**
- 실전용 워크플로우: `.github/workflows/trade_real.yml` (기본 `TRADE_MODE=LIVE`)
- 데모용 워크플로우: `.github/workflows/trade_demo.yml` (기본 `TRADE_MODE=DRY`)
- 공통 실행: `.github/workflows/trade_base.yml` (재사용 가능한 베이스)

1. 실행 모드 정리
-----------------
- `KIS_MODE` (broker mode): `real` 또는 `demo` — 어떤 계좌(실/모)를 쓸지 결정합니다.
- `TRADE_MODE` (execution mode): `LIVE` 또는 `DRY` — 실제 주문 실행 여부를 결정합니다.

2. 환경변수(.env) / 로컬 실행
------------------------------
프로젝트는 `.env`를 사용해 로컬 환경에서 설정을 읽습니다. 예시:

KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_ACCOUNT_NO=12345678           # 실계좌
KIS_ACCOUNT_NO_DEMO=87654321      # 모의계좌
KIS_MODE=demo                     # demo 또는 real
TRADE_MODE=DRY                    # DRY 또는 LIVE
SYMBOL=TQQQ
EXCHANGE=NAS
SPLITS=40
TAKE_PROFIT=0.10
BIG_BUY_RANGE=0.10

로컬 실행:
```
uv run python trading_bot.py
```

3. GitHub Actions 설정 (Secrets / Repository Variables)
------------------------------------------------------
- 민감값(인증키, 계좌번호 등)은 `Settings > Secrets`에 저장하세요.
	- 반드시 설정할 Secrets:
		- `KIS_APP_KEY`
		- `KIS_APP_SECRET`
		- `KIS_ACCOUNT_NO` (실전 계좌)
		- `KIS_ACCOUNT_NO_DEMO` (데모 계좌)
		- `TELEGRAM_BOT_TOKEN` (선택)
		- `TELEGRAM_CHAT_ID` (선택)

- 공통 기본값(민감하지 않은)은 `Settings > Variables`에 넣어 관리할 수 있습니다.
	- 예시 변수: `SYMBOL`, `EXCHANGE`, `SPLITS`, `TAKE_PROFIT`, `BIG_BUY_RANGE`

4. 워크플로우 사용법
--------------------
- 실전 자동 실행: `.github/workflows/trade_real.yml`이 ET(미국 동부시간) 프리마켓 진입 시 자동 실행되도록 스케줄링 되어 있습니다.
- 데모 자동 실행: `.github/workflows/trade_demo.yml`이 데모/예약검증용 스케줄로 설정되어 있습니다.
- 수동 실행: 각 워크플로우는 `workflow_dispatch` 입력을 지원합니다. 수동 실행 시 `trade_mode` 선택 가능(DRY/LIVE).

5. 안전 권장
------------
- 실전 실행 전 `ALLOW_LIVE` 같은 안전 토글(Secret)을 추가해 실수로 `LIVE` 실행되는 것을 방지하는 것을 권장합니다.
- 실전/데모 계좌가 혼재되지 않도록 `KIS_MODE`와 `KIS_ACCOUNT_NO[_DEMO]` 값을 확인하세요.

6. 운영 예시
-------------
- 데모(자동): `trade_demo.yml`는 repo `Variables`의 `SYMBOL` 등을 호출자 `with`로 넘기도록 설정되어 있어, 데모 환경에서 별도 관리를 쉽게 합니다.
- 실전(자동): `trade_real.yml`는 기본적으로 `TRADE_MODE=LIVE`로 동작하므로, 실제 배포 전 `Secrets`와 `ALLOW_LIVE`를 반드시 확인하세요.

7. 변경 이력(간단)
------------------
- 워크플로우를 reusable 패턴(`trade_base.yml`)으로 분리하였고, 실전/데모 호출자는 호출자(`trade_real.yml`, `trade_demo.yml`)로 분리하여 스케줄·시크릿을 분리했습니다.

문제가 있거나 추가 문서가 필요하면 알려주세요.

