import pandas as pd
from collections import deque
import uuid

# --- 常數設定 ---
COMMISSION_RATE = 0.001425
MIN_FEE = 1
TAX_RATE = 0.003       # 一般股票交易稅
ETF_TAX_RATE = 0.001   # ETF 交易稅

def calculate_fees(qty, price, action, discount=1.0, stock_id=""):
    """計算單筆交易的費用與淨收付"""
    gross_amount = int(qty * price)
    
    commission = 0
    tax = 0
    
    if action in ['買進', '賣出']:
        raw_commission = int(gross_amount * COMMISSION_RATE * discount)
        commission = max(raw_commission, MIN_FEE) if gross_amount > 0 else 0

    if action == '賣出':
        clean_id = str(stock_id).strip()
        current_tax_rate = ETF_TAX_RATE if clean_id.startswith("00") else TAX_RATE
        tax = int(gross_amount * current_tax_rate)
    
    other_fees = 0
    total_fees = commission + tax + other_fees
    
    net_cash_flow = 0
    if action in ['買進', '現金增資']:
        net_cash_flow = -(gross_amount + total_fees)
    elif action == '賣出':
        net_cash_flow = gross_amount - total_fees
    elif action == '現金股利':
        net_cash_flow = gross_amount - total_fees
    elif action == '入金':
        net_cash_flow = gross_amount
    elif action == '出金':
        net_cash_flow = -gross_amount
        
    return {
        "gross_amount": gross_amount,
        "commission": commission,
        "tax": tax,
        "other_fees": other_fees,
        "total_fees": total_fees,
        "net_cash_flow": net_cash_flow
    }

def generate_txn_id():
    return f"TXN-{str(uuid.uuid4())[:8].upper()}"

def _safe_float(value):
    """輔助函式：安全轉換字串為浮點數 (處理逗號)"""
    try:
        if isinstance(value, (int, float)):
            return float(value)
        clean_val = str(value).replace(',', '').replace('$', '').strip()
        if not clean_val:
            return 0.0
        return float(clean_val)
    except:
        return 0.0

def calculate_fifo_report(df):
    """接收 DataFrame，回傳 FIFO 計算後的庫存 DataFrame"""
    # 先清除欄位名稱前後的空白，避免讀取錯誤
    df.columns = df.columns.str.strip()
    
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
        
        if action in ['入金', '出金']:
            continue

        if sid and stock_name:
            names_map[sid] = stock_name
        
        qty = _safe_float(row.get(col_qty))
        price = _safe_float(row.get(col_price))
        fee = _safe_float(row.get(col_fee))
        tax = _safe_float(row.get(col_tax))
        other = _safe_float(row.get(col_other))

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
    """計算未實現損益"""
    if df_fifo.empty:
        return df_fifo

    df_fifo['股票'] = df_fifo.apply(lambda row: f"{row['股票名稱']}({row['股票代號']})", axis=1)
    df_fifo['目前市價'] = df_fifo['股票代號'].map(current_price_map).fillna(0)
    df_fifo['股票市值'] = df_fifo.apply(lambda row: row['庫存股數'] * row['目前市價'], axis=1)
    
    total_market_value = df_fifo['股票市值'].sum()
    df_fifo['佔總資產比例 (%)'] = df_fifo.apply(
        lambda row: 0 if total_market_value == 0 else (row['股票市值'] / total_market_value) * 100,
        axis=1
    )
    
    def get_sell_costs(row):
        market_value = int(row['股票市值'])
        stock_id = str(row['股票代號']).strip()
        
        if market_value == 0: return 0, 0, 0 
        
        current_tax_rate = ETF_TAX_RATE if stock_id.startswith("00") else TAX_RATE
        tax = int(market_value * current_tax_rate)
        raw_comm = int(market_value * COMMISSION_RATE)
        comm = max(raw_comm, MIN_FEE)
        
        return tax + comm, comm, tax

    costs_df = df_fifo.apply(get_sell_costs, axis=1, result_type='expand')
    costs_df.columns = ['total_fee', 'comm', 'tax']
    
    df_fifo['未實現損益'] = df_fifo['股票市值'] - df_fifo['總持有成本 (FIFO)'] - costs_df['total_fee']

    df_fifo['報酬率 (%)'] = df_fifo.apply(
        lambda row: 0 if row['總持有成本 (FIFO)'] == 0 else (row['未實現損益'] / row['總持有成本 (FIFO)']) * 100,
        axis=1
    )
    
    df_fifo['賣出額外費用'] = costs_df.apply(
        lambda x: f"{int(x['total_fee'])} ({int(x['comm'])}+{int(x['tax'])})", axis=1
    )
    
    df_fifo['配息金額'] = 0

    df_fifo = df_fifo.sort_values(by='佔總資產比例 (%)', ascending=False).reset_index(drop=True)
    
    return df_fifo

def calculate_account_balances(df):
    """
    統計各帳戶的現金餘額 (強化版)
    1. 自動清除欄位名稱空白
    2. 強制清除金額欄位中的 ',' 與 '$' 符號
    3. 排除沒有帳戶名稱的異常資料
    """
    if df.empty:
        return {}

    # 1. 清除欄位名稱前後空白 (避免 "交易帳戶 " 這種錯誤)
    df.columns = df.columns.str.strip()

    col_account = '交易帳戶'
    col_net_cash = '淨收付金額'

    if col_account not in df.columns or col_net_cash not in df.columns:
        # 若找不到欄位，回傳空字典，避免報錯
        print("警告：找不到 '交易帳戶' 或 '淨收付金額' 欄位")
        return {}

    # 建立副本以免影響原始資料
    df_calc = df.copy()

    # 2. 清洗數據：轉字串 -> 移除 $ 與 , -> 轉數字 (失敗變0)
    df_calc[col_net_cash] = df_calc[col_net_cash].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False)
    df_calc[col_net_cash] = pd.to_numeric(df_calc[col_net_cash], errors='coerce').fillna(0)
    
    # 3. 排除帳戶名稱為空的資料 (避免加總到幽靈帳戶)
    df_calc = df_calc[df_calc[col_account].astype(str).str.strip() != '']

    balances = df_calc.groupby(col_account)[col_net_cash].sum().to_dict()
    
    return balances

# --- 新增：計算已實現損益 (Realized P&L) ---
def calculate_realized_report(df):
    """
    計算已實現損益流水帳
    包含：賣出損益、現金股利
    """
    # 清理欄位
    df.columns = df.columns.str.strip()
    
    col_date = '交易日期'
    col_id = '股票代號'
    col_name = '股票名稱'
    col_action = '交易類別'
    col_qty = '股數'
    col_price = '單價'
    col_fee = '手續費'
    col_tax = '交易稅'
    col_other = '其他費用'

    # 確保日期格式
    df[col_date] = pd.to_datetime(df[col_date])
    df = df.sort_values(by=col_date).reset_index(drop=True)
    
    portfolio = {} 
    realized_records = [] # 儲存已實現損益的清單

    for _, row in df.iterrows():
        action = row.get(col_action, '')
        
        # 忽略非損益相關交易
        if action in ['入金', '出金']:
            continue

        sid = str(row.get(col_id, '')).strip()
        stock_name = str(row.get(col_name, '')).strip()
        txn_date = row[col_date]
        
        # 數值處理
        qty = _safe_float(row.get(col_qty))
        price = _safe_float(row.get(col_price))
        fee = _safe_float(row.get(col_fee))
        tax = _safe_float(row.get(col_tax))
        other = _safe_float(row.get(col_other))

        # 總買入成本 (含費)
        total_buy_cost_raw = (qty * price) + fee + other
        # 總賣出收入 (已扣費)
        net_sell_proceeds = (qty * price) - fee - tax - other
        
        if sid not in portfolio: portfolio[sid] = deque()

        # --- 買進 / 股票股利 (建立庫存) ---
        if action in ['買進', '現金增資']:
            # 計算單位成本 (含手續費)
            unit_cost = total_buy_cost_raw / qty if qty > 0 else 0
            portfolio[sid].append({'qty': qty, 'unit_cost': unit_cost})
            
        elif action == '股票股利':
            # 成本視為 0 (或僅含手續費)
            unit_cost = (fee + other) / qty if qty > 0 else 0
            portfolio[sid].append({'qty': qty, 'unit_cost': unit_cost})

        # --- 賣出 (實現損益 - FIFO) ---
        elif action == '賣出':
            sell_qty = qty
            cost_basis = 0 # 這一批賣出的總成本
            
            while sell_qty > 0 and portfolio[sid]:
                batch = portfolio[sid].popleft()
                
                if batch['qty'] > sell_qty:
                    # 庫存夠賣，扣除部分
                    cost_basis += sell_qty * batch['unit_cost']
                    batch['qty'] -= sell_qty
                    portfolio[sid].appendleft(batch) # 剩餘的塞回去
                    sell_qty = 0
                else:
                    # 庫存不夠或剛好，整批用掉
                    cost_basis += batch['qty'] * batch['unit_cost']
                    sell_qty -= batch['qty']
            
            # 計算損益
            realized_pnl = net_sell_proceeds - cost_basis
            ret_percent = (realized_pnl / cost_basis * 100) if cost_basis > 0 else 0
            
            realized_records.append({
                '交易日期': txn_date,
                '股票代號': sid,
                '股票名稱': stock_name,
                '交易類別': '賣出',
                '已實現損益': int(realized_pnl),
                '報酬率 (%)': ret_percent,
                '本金(成本)': int(cost_basis)
            })

        # --- 現金股利 (直接視為獲利) ---
        elif action == '現金股利':
            # 股利淨額即為獲利 (net_sell_proceeds 已經是 股利總額 - 匯費)
            realized_records.append({
                '交易日期': txn_date,
                '股票代號': sid,
                '股票名稱': stock_name,
                '交易類別': '股息',
                '已實現損益': int(net_sell_proceeds),
                '報酬率 (%)': 0, # 股利通常不算報酬率，或視為 100%? 這裡先放 0 避免干擾平均
                '本金(成本)': 0
            })

    # 轉為 DataFrame
    df_res = pd.DataFrame(realized_records)
    
    if not df_res.empty:
        # 增加 年、月 欄位方便繪圖
        df_res['年'] = df_res['交易日期'].dt.year
        df_res['月'] = df_res['交易日期'].dt.strftime('%Y-%m')
        # 顯示欄位優化
        df_res['股票'] = df_res.apply(lambda row: f"{row['股票名稱']}({row['股票代號']})", axis=1)

    return df_res
