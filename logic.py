import pandas as pd
from collections import deque
import uuid

# --- 常數設定 ---
COMMISSION_RATE = 0.001425
MIN_FEE = 1
TAX_RATE = 0.003       # 一般股票交易稅
ETF_TAX_RATE = 0.001   # ETF 交易稅 (0.1%)

def calculate_fees(qty, price, action, discount=1.0, stock_id=""):
    """
    計算單筆交易的費用與淨收付
    """
    gross_amount = int(qty * price)
    
    # 手續費
    raw_commission = int(gross_amount * COMMISSION_RATE * discount)
    commission = max(raw_commission, MIN_FEE) if gross_amount > 0 else 0
    
    # 交易稅 (賣出才收)
    tax = 0
    if action == '賣出':
        # 判斷是否為 ETF (代號以 00 開頭)
        clean_id = str(stock_id).strip()
        current_tax_rate = ETF_TAX_RATE if clean_id.startswith("00") else TAX_RATE
        tax = int(gross_amount * current_tax_rate)
    
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
    接收 FIFO 庫存表與即時股價，計算未實現損益
    1. 計算賣出費用 (稅+手續費)
    2. 損益 = 市值 - 成本 - 賣出費用
    3. 依資產比例排序
    """
    if df_fifo.empty:
        return df_fifo

    # 1. 合併股票名稱與代號
    df_fifo['股票'] = df_fifo.apply(lambda row: f"{row['股票名稱']}({row['股票代號']})", axis=1)

    # 2. 填入市價
    df_fifo['目前市價'] = df_fifo['股票代號'].map(current_price_map).fillna(0)
    
    # 3. 計算市值
    df_fifo['股票市值'] = df_fifo.apply(lambda row: row['庫存股數'] * row['目前市價'], axis=1)
    
    # 4. 計算佔總資產比例 (%)
    total_market_value = df_fifo['股票市值'].sum()
    df_fifo['佔總資產比例 (%)'] = df_fifo.apply(
        lambda row: 0 if total_market_value == 0 else (row['股票市值'] / total_market_value) * 100,
        axis=1
    )
    
    # 5. 計算預估賣出費用 (內部函式：回傳數值以便計算)
    def get_sell_costs(row):
        market_value = int(row['股票市值'])
        stock_id = str(row['股票代號']).strip()
        
        if market_value == 0:
            return 0, 0, 0 # total, comm, tax
        
        # 判斷 ETF 稅率 (00開頭 0.1%, 其他 0.3%)
        current_tax_rate = ETF_TAX_RATE if stock_id.startswith("00") else TAX_RATE
        tax = int(market_value * current_tax_rate)
        
        # 手續費 (不打折)
        raw_comm = int(market_value * COMMISSION_RATE)
        comm = max(raw_comm, MIN_FEE)
        
        total = tax + comm
        return total, comm, tax

    # 計算每一行的賣出成本
    # 使用 apply expand=True 一次取得三個值
    costs_df = df_fifo.apply(get_sell_costs, axis=1, result_type='expand')
    costs_df.columns = ['total_fee', 'comm', 'tax']
    
    # 6. 計算未實現損益 (修正公式：市值 - 成本 - 賣出費用)
    df_fifo['未實現損益'] = df_fifo['股票市值'] - df_fifo['總持有成本 (FIFO)'] - costs_df['total_fee']

    # 7. 計算報酬率 (%)
    df_fifo['報酬率 (%)'] = df_fifo.apply(
        lambda row: 0 if row['總持有成本 (FIFO)'] == 0 else (row['未實現損益'] / row['總持有成本 (FIFO)']) * 100,
        axis=1
    )
    
    # 8. 產生顯示用的「賣出額外費用」字串
    df_fifo['賣出額外費用'] = costs_df.apply(
        lambda x: f"{int(x['total_fee'])} ({int(x['comm'])}+{int(x['tax'])})", 
        axis=1
    )
    
    # 9. 配息金額 (保留欄位)
    df_fifo['配息金額'] = 0

    # 10. 排序：依照「佔總資產比例 (%)」降冪排序 (大 -> 小)
    df_fifo = df_fifo.sort_values(by='佔總資產比例 (%)', ascending=False).reset_index(drop=True)
    
    return df_fifo
