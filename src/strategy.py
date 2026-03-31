# 매수/매도 여부를 판단하는 전략 로직
import math
from collections import Counter
from trader import (
    get_overseas_stock_price,
    get_overseas_stock_quotation,
    get_overseas_balance,
    get_overseas_purchase_amount,
    get_overseas_order_history
)


def adjust_price_to_tick(price):
    """
    미국 주식 거래소의 호가 단위 규칙에 맞춰 가격을 조정합니다.
    
    호가 단위 규칙:
    - 가격이 $1.00 미만: 소수점 4자리까지 ($0.0001 단위)
    - 가격이 $1.00 이상: 소수점 2자리까지 ($0.01 단위)
    
    모든 가격은 버림(floor) 처리합니다.
    
    Parameters:
        price (float): 조정할 가격
    
    Returns:
        float: 호가 단위에 맞게 조정된 가격
    
    Examples:
        >>> adjust_price_to_tick(0.98769)
        0.9876
        >>> adjust_price_to_tick(56.375)
        56.37
        >>> adjust_price_to_tick(56.378)
        56.37
    """
    price = float(price)
    
    if price < 1.0:
        # $1.00 미만: 소수점 4자리까지
        return math.floor(price * 10000) / 10000
    else:
        # $1.00 이상: 소수점 2자리까지
        return math.floor(price * 100) / 100


def 무상태_무한매수법(symbol, exchange_code, splits, take_profit_rate, big_buy_range):
    """
    무상태 무한매수법 전략을 실행합니다.
    
    이 전략은 주문을 실제로 실행하지 않고, DryRun 모드로 예상되는 주문 목록을 반환합니다.
    
    전략 규칙:
    1. 포지션이 없을 때: 초기 진입 (2 * unit_qty) @ 현재가 (LIMIT)
    2. 포지션이 있을 때:
       - 익절 주문: 전체 수량 매도 @ 익절가 (LIMIT)
       - 추가 매수 (분할 제한 확인 후):
         * 평단 매수: unit_qty @ 평단가 (LOC)
         * 큰수 매수: unit_qty @ 큰수기준가 (LOC)
    
    Parameters:
        symbol (str): 종목 코드 (예: "TQQQ")
        exchange_code (str): 거래소 코드 (예: "NAS")
        splits (int): 분할 수 (기본 40)
        take_profit_rate (float): 익절 상승률 (예: 0.10 = 10%)
        big_buy_range (float): 큰수 상승률 (예: 0.10 = 10%)
    
    Returns:
        dict: DryRun 결과
            - symbol: 종목 코드
            - exchange: 거래소
            - tradable: 거래 가능 여부
            - open_price: 시가
            - last_price: 현재가
            - position_qty: 보유 수량
            - avg_price: 평단가
            - orderable_cash: 주문 가능 금액
            - unit_qty: 단위 주문 수량
            - max_position: 최대 포지션
            - take_profit_price: 익절가
            - big_buy_price: 큰수 기준가
            - orders: 예상 주문 목록
                [{
                    "side": "BUY" or "SELL",
                    "quantity": 주문 수량,
                    "price": 주문 단가 (LIMIT/LOC인 경우),
                    "order_type": "LIMIT", "LOC",
                    "comment": 주문 설명
                }]
    
    Raises:
        Exception: 잔고 부족 또는 API 호출 실패 시
    """
    
    # ========================================
    # 1. 시장 정보 조회
    # ========================================
    
    # 거래 가능 여부 확인
    quotation = get_overseas_stock_quotation(symbol, exchange_code)
    tradable = quotation.get("ordy", "N") == "Y"
    
    # 시가 / 현재가 조회
    price_detail = get_overseas_stock_price(symbol, exchange_code)
    open_price = float(price_detail.get("open", "0"))
    last_price = float(price_detail.get("last", "0"))
    
    # ========================================
    # 2. 보유 정보 조회
    # ========================================
    
    balance = get_overseas_balance(symbol, exchange_code)
    
    if balance:
        position_qty = int(balance.get("quantity", "0"))
        avg_price = float(balance.get("avg_price", "0"))
    else:
        position_qty = 0
        avg_price = 0.0
    
    # ========================================
    # 3. 주문가능금액 조회
    # ========================================
    
    psamount = get_overseas_purchase_amount(symbol, exchange_code)
    orderable_cash = float(psamount.get("ord_psbl_frcr_amt", "0"))
    
    # ========================================
    # 4. unit_qty 결정
    # ========================================
    
    unit_qty = 0
    
    if position_qty > 0:
        # 최근 체결내역 조회
        order_history = get_overseas_order_history(symbol, exchange_code, days=30)
        
        # 매도 이후 매수 내역 중 최빈값 찾기
        sell_found = False
        buy_quantities = []
        
        for order in order_history:
            side = order.get("sll_buy_dvsn_cd_name", "")
            qty = int(order.get("ft_ccld_qty", "0"))
            
            if "매도" in side or "SELL" in side.upper():
                sell_found = True
            elif sell_found and ("매수" in side or "BUY" in side.upper()):
                buy_quantities.append(qty)
        
        if buy_quantities:
            # 최빈값을 unit_qty로 설정
            counter = Counter(buy_quantities)
            unit_qty = counter.most_common(1)[0][0]
        else:
            # 매도 이후 매수가 없다면, 기본 계산식 사용
            base_cash = orderable_cash / (splits * 2)
            unit_qty = math.floor(base_cash / last_price)
    else:
        # 포지션 없음: 기본 계산식 사용
        base_cash = orderable_cash / (splits * 2)
        unit_qty = math.floor(base_cash / last_price)
    
    # unit_qty가 0이면 잔고 부족 에러
    if unit_qty == 0:
        raise Exception(
            f"잔고 부족: 주문 가능 금액이 부족합니다. "
            f"현재 잔고: ${orderable_cash:.2f}"
        )
    
    # ========================================
    # 5. 공통 계산
    # ========================================
    
    max_position = unit_qty * splits
    big_buy_price = adjust_price_to_tick(open_price * (1 + big_buy_range))
    
    take_profit_price = None
    if avg_price > 0:
        take_profit_price = adjust_price_to_tick(avg_price * (1 + take_profit_rate))
    
    # ========================================
    # 6. 예상 주문 생성
    # ========================================
    
    orders = []
    
    if position_qty == 0:
        # 포지션 없음: 초기 진입 (현재가 LIMIT 주문)
        initial_qty = 2 * unit_qty
        initial_price = adjust_price_to_tick(last_price)
        
        orders.append({
            "side": "BUY",
            "quantity": initial_qty,
            "price": initial_price,  # 현재가로 LIMIT 주문
            "order_type": "LIMIT",
            "comment": "초기 진입"
        })
    else:
        # 포지션 있음: 익절 주문
        if take_profit_price:
            orders.append({
                "side": "SELL",
                "quantity": position_qty,
                "price": take_profit_price,
                "order_type": "LIMIT",
                "comment": "익절"
            })
        
        # 추가 매수 (분할 제한 체크)
        if position_qty < max_position:
            # 평단 매수
            avg_price_adjusted = adjust_price_to_tick(avg_price)
            orders.append({
                "side": "BUY",
                "quantity": unit_qty,
                "price": avg_price_adjusted,
                "order_type": "LOC",
                "comment": "평단 매수"
            })
            
            # 큰수 매수
            orders.append({
                "side": "BUY",
                "quantity": unit_qty,
                "price": big_buy_price,
                "order_type": "LOC",
                "comment": "큰수 매수"
            })
    
    # ========================================
    # 7. 결과 반환
    # ========================================
    
    return {
        "symbol": symbol,
        "exchange": exchange_code,
        "tradable": tradable,
        "open_price": open_price,
        "last_price": last_price,
        "position_qty": position_qty,
        "avg_price": avg_price,
        "orderable_cash": orderable_cash,
        "unit_qty": unit_qty,
        "max_position": max_position,
        "take_profit_price": take_profit_price,
        "big_buy_price": big_buy_price,
        "orders": orders
    }
