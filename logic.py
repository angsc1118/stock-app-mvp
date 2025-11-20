import pandas as pd
from collections import deque
import uuid

# --- 常數設定 ---
COMMISSION_RATE = 0.001425
# DISCOUNT = 0.6  <-- 移除這行，改由參數傳入
MIN_FEE = 1
TAX_RATE = 0.003

# 修改：新增 discount 參數
def calculate_fees(qty, price, action, discount=1.0):
    """
    計算單筆交易的費用與淨收付
    discount: 手續費折數 (ex: 0.6, 0.28, 0.168)
    """
    gross_amount = int(qty * price)
    
    # 手續費：使用傳入的 discount 計算
    raw_commission = int(gross_amount * COMMISSION_RATE * discount)
    
    # 最低手續費通常是 20 元 (不同券商不同，這裡維持您的設定 1 元或您可自行調整)
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
    """接收 DataFrame，回傳 FIFO 計算後的庫存 DataFrame (含股票名稱)"""
    # 欄位對應
    col_date = '交易日期'
    col_id = '股票代號'
    col_name = '股票名稱'
    col_action = '交易類別'
    col_qty = '股數'
    col_price = '單價'
    col_fee = '手續費'
    col_tax = '交易稅'
    col_other = '其他費用'

    df[col_date] = pd.to_datetime(df[col_date])
    df = df.sort_values(by=col_date).reset_index(drop=True)
    
    portfolio = {} 
    names_map = {}

    for _, row in df.iterrows():
        sid = str(row.get(col_id, '')).strip()
        action = row.get(col_action, '')
        stock_name = str(row.get(col_name, '')).strip()
        
        if sid and stock_name:
            names_map[sid] = stock_name
        
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
    
    report_data = []
    for sid, batches in portfolio.items():
        total_shares = sum(b['qty'] for b in batches)
        if total_shares > 0:
            total_cost = sum(b['qty'] * b['unit_cost'] for b in batches)
            report_data.append({
                '股票代號': sid,
                '股票名稱': names_map.get(sid, '未命名'),
                '庫存股數': int(total_shares),
                '總持有成本 (FIFO)': int(total_cost),
                '平均成本': round(total_cost / total_shares, 2)
            })
    
    return pd.DataFrame(report_data)

def calculate_unrealized_pnl(df_fifo, current_price_map):
    """
    接收 FIFO 庫存表與即時股價，計算未實現損益、總資產比例
    """
    if df_fifo.empty:
        return df_fifo

    # 1. 填入市價 (若無報價則補 0)
    df_fifo['目前市價'] = df_fifo['股票代號'].map(current_price_map).fillna(0)
    
    # 2. 計算市值
    df_fifo['股票市值'] = df_fifo.apply(lambda row: row['庫存股數'] * row['目前市價'], axis=1)
    
    # 3. 計算未實現損益
    df_fifo['未實現損益'] = df_fifo['股票市值'] - df_fifo['總持有成本 (FIFO)']
    
    # 4. 計算報酬率 (%)
    df_fifo['報酬率 (%)'] = df_fifo.apply(
        lambda row: 0 if row['總持有成本 (FIFO)'] == 0 else (row['未實現損益'] / row['總持有成本 (FIFO)']) * 100,
        axis=1
    )
    
    # 5. 新增：計算佔總資產比例 (%)
    total_market_value = df_fifo['股票市值'].sum()
    df_fifo['佔總資產比例 (%)'] = df_fifo.apply(
        lambda row: 0 if total_market_value == 0 else (row['股票市值'] / total_market_value) * 100,
        axis=1
    )
    
    # 6. 新增：配息金額 (保留欄位，預設為 0)
    df_fifo['配息金額'] = 0
    
    return df_fifo
