"""
키움증권 해외주식 주문체결내역 조회 테스트 (특정 종목)

이 테스트는 키움증권 모의투자 API(mockapi.kiwoom.com)를 호출하여
특정 종목의 최근 30일 체결내역을 조회합니다.

실행:
  BROKER=kiwoom BROKER_MODE=demo KIWOOM_APP_KEY=... KIWOOM_APP_SECRET=... \\
    uv run pytest tests/test_kiwoom_order_history.py -v -s

참고:
  - 모의투자(ust21150): 일별 조회, 각 날짜별로 API 호출
  - 실전(ust21100): 기간 조회, 단일 API 호출
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_src_path = str(Path(__file__).resolve().parent.parent / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

import pytest
from config import SYMBOLS


@pytest.mark.skipif(
    os.environ.get("BROKER") != "kiwoom",
    reason="BROKER=kiwoom 환경변수가 필요합니다",
)
class TestKiwoomSymbolOrderHistory:
    """
    키움증권 해외주식 주문체결내역 조회 테스트.
    BROKER=kiwoom 환경변수 필수.
    """

    TEST_SYMBOL = SYMBOLS[0]["symbol"]
    TEST_EXCHANGE = SYMBOLS[0]["exchange"]

    def test_overseas_symbol_order_history(self):
        from broker.kiwoom.adapter import KiwoomBroker

        symbol = self.TEST_SYMBOL
        exchange = self.TEST_EXCHANGE

        print("=" * 120)
        print(f"키움증권 해외주식 주문체결내역 조회 테스트")
        print(f"종목: {symbol} | 거래소: {exchange} | 조회 기간: 최근 30일")
        print("=" * 120)

        try:
            broker = KiwoomBroker()
            history = broker.get_order_history(symbol, exchange, days=30)

            if not history:
                print("\n⚠️ 해당 기간에 체결내역이 없습니다.")
                return

            print(f"\n✅ 조회 성공! (총 {len(history)}건)\n")

            # 테이블 헤더
            header = (
                f"{'#':<4} {'일자':<10} {'시간':<8} {'종목명':<30} "
                f"{'매도/매수':<12} {'주문수':<8} {'체결수':<8} "
                f"{'체결가':<12} {'체결금액':<14} {'상태':<10}"
            )
            print(header)
            print("-" * len(header))

            for idx, order in enumerate(history, 1):
                dt = order.get("ord_dt", "")
                tmd = (order.get("ord_tmd") or "").zfill(6)
                tmd_fmt = f"{tmd[:2]}:{tmd[2:4]}:{tmd[4:6]}" if len(tmd) == 6 else tmd
                name = (order.get("prdt_name") or "")[:28]
                side = order.get("sll_buy_dvsn_cd_name", "")
                ord_qty = order.get("ft_ord_qty", "0")
                ccld_qty = order.get("ft_ccld_qty", "0")
                price = order.get("ft_ccld_unpr3", "0")
                amt = order.get("ft_ccld_amt3", "0")
                status = order.get("prcs_stat_name", "")

                print(
                    f"{idx:<4} {dt:<10} {tmd_fmt:<8} {name:<30} "
                    f"{side:<12} {ord_qty:<8} {ccld_qty:<8} "
                    f"{price:<12} {amt:<14} {status:<10}"
                )

            # 통계
            print("\n" + "=" * 120)
            print("📊 통계 정보:")
            print("=" * 120)

            total_buy = sum(
                int(o.get("ft_ccld_qty", "0"))
                for o in history
                if "매수" in o.get("sll_buy_dvsn_cd_name", "")
            )
            total_sell = sum(
                int(o.get("ft_ccld_qty", "0"))
                for o in history
                if "매도" in o.get("sll_buy_dvsn_cd_name", "")
            )

            print(f"  종목: {symbol}")
            print(f"  총 매수: {total_buy}주")
            print(f"  총 매도: {total_sell}주")
            print(f"  총 체결: {len(history)}건")

            # 최신 거래
            latest = history[0]
            lt_dt = latest.get("ord_dt", "")
            lt_tmd = (latest.get("ord_tmd") or "").zfill(6)
            lt_side = latest.get("sll_buy_dvsn_cd_name", "")
            lt_qty = latest.get("ft_ccld_qty", "0")
            lt_price = latest.get("ft_ccld_unpr3", "0")
            print(f"  최신 거래: {lt_dt} {lt_tmd} - {lt_side} {lt_qty}주 @ {lt_price}")

            print("\n✅ 테스트 완료")

        except Exception as e:
            print(f"❌ 테스트 실패: {e}")
            import traceback
            traceback.print_exc()
            raise
