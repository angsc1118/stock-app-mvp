# logic.py
import pandas as pd
from collections import deque
import uuid

# --- 常數設定 ---
COMMISSION_RATE = 0.001425
DISCOUNT = 0.6
MIN_FEE = 1
TAX_RATE = 0.003

def calculate_fees(qty, price, action):
    """計算單筆交易的費用與淨收付"""
    gross_amount = int(qty * price)
    
    # 手續費
    raw_commission = int(gross_amount * COMMISSION_RATE * DISCOUNT)
    commission = max(raw_commission, MIN_FEE) if gross_amount > 0 else 0
    
    # 交易稅
    tax = int(gross_amount * TAX_RATE) if action == '賣出' else 0
    
    other_fees = 0
    total_fees = commission + tax + other_fees
    
    # 淨收付
    net_cash_flow = 0
    if action in ['買進', '現金增資']:
        net_cash_flow = -(gross_amount + total_fees)
    elif action == '賣出':
        net_cash_flow = gross_amount - total_fees
    elif action == '現金股利':
        net_cash_flow = gross_amount - total_fees
        
    return {
        "gross_amount": gross_amount,
        "commission": commission,
        "tax": tax,
        "other_fees": other_fees,
        "total_fees": total_fees,
        "net_cash_flow": net_cash_flow
    }

def generate_txn_id():
    """產生唯一交易 ID"""
    return f"TXN-{str(uuid.uuid4())[:8].upper()}"

def calculate_fifo_report(df):
    """接收 DataFrame，回傳 FIFO 計算後的庫存 DataFrame"""
    # 欄位對應 (須與 Google Sheet 表頭一致)
    col_date = '交易日期'
    col_id = '股票代號'
    col_action = '交易類別'
    col_qty = '股數'
    col_price = '單價'
    col_fee = '手續費'
    col_tax = '交易稅'
    col_other = '其他費用'

    # 確保資料格式正確
    df[col_date] = pd.to_datetime(df[col_date])
    df = df.sort_values(by=col_date).reset_index(drop=True)
    
    portfolio = {} 

    for _, row in df.iterrows():
        sid = str(row[col_id])
        action = row[col_action]
        
        try:
            qty = float(row[col_qty]) if row[col_qty] != '' else 0
            price = float(row[col_price]) if row[col_price] != '' else 0
            fee = float(row[col_fee]) if row[col_fee] != '' else 0
            tax = float(row[col_tax]) if row[col_tax] != '' else 0
            other = float(row[col_other]) if row[col_other] != '' else 0
        except:
            continue

        total_buy_cost = (qty * price) + fee + other
        
        if sid not in portfolio: portfolio[sid] = deque()

        if action in ['買進', '現金增資']:
            unit_cost = total_buy_cost / qty if qty > 0 else 0
            portfolio[sid].append({'qty': qty, 'unit_cost': unit_cost})
            
        elif action == '股票股利':
            portfolio[sid].append({'qty': qty, 'unit_cost': (fee+other)/qty if qty>0 else 0})

        elif action == '賣出':
            sell_qty = qty
            while sell_qty > 0 and portfolio[sid]:
                batch = portfolio[sid].popleft()
                if batch['qty'] > sell_qty:
                    batch['qty'] -= sell_qty
                    portfolio[sid].appendleft(batch)
                    sell_qty = 0
                else:
                    sell_qty -= batch['qty']
    
    # 整理報表
    report_data = []
    for sid, batches in portfolio.items():
        total_shares = sum(b['qty'] for b in batches)
        if total_shares > 0:
            total_cost = sum(b['qty'] * b['unit_cost'] for b in batches)
            report_data.append({
                '股票代號': sid,
                '庫存股數': int(total_shares),
                '總持有成本 (FIFO)': int(total_cost),
                '平均成本': round(total_cost / total_shares, 2)
            })
    
    return pd.DataFrame(report_data)
