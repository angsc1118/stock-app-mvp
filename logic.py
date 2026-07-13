# ==============================================================================
# 檔案名稱: logic.py
# 
# 修改歷程:
# 2025-12-11 14:00:00: [Feat] 第四階段：目標進度增加時間維度運算 (Time Pacer)
# 2025-12-11 13:30:00: [Feat] 第三階段：支援「還款」邏輯 (視為負向現金流)
# ==============================================================================

import pandas as pd
from collections import deque
import uuid
from datetime import datetime
import math

# --- 常數設定 ---
COMMISSION_RATE = 0.001425
MIN_FEE = 1
TAX_RATE = 0.003       
ETF_TAX_RATE = 0.001   

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
    elif action in ['出金', '還款']:
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
    try:
        if isinstance(value, (int, float)):
            return float(value)
        clean_val = str(value).replace(',', '').replace('$', '').strip()
        if not clean_val:
            return 0.0
        return float(clean_val)
    except:
        return 0.0

def _get_action_sort_order(action):
    if action in ['買進', '現金增資', '股票股利']: return 1
    elif action == '賣出': return 2
    else: return 3

def calculate_fifo_report(df):
    if df.empty: return pd.DataFrame()
    df = df.copy()
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
    df['sort_order'] = df[col_action].apply(_get_action_sort_order)
    df = df.sort_values(by=[col_date, 'sort_order']).reset_index(drop=True)
    
    portfolio = {} 
    names_map = {}

    for _, row in df.iterrows():
        sid = str(row.get(col_id, '')).strip()
        action = row.get(col_action, '')
        stock_name = str(row.get(col_name, '')).strip()
        if action in ['入金', '出金', '還款']: continue 
        
        if sid and stock_name: names_map[sid] = stock_name
        
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
    EPSILON = 0.001
    for sid, batches in portfolio.items():
        total_shares = sum(b['qty'] for b in batches)
        if total_shares > EPSILON:
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
    if df_fifo.empty: return df_fifo
    df_fifo['股票'] = df_fifo.apply(lambda row: f"{row['股票名稱']}({row['股票代號']})", axis=1)
    df_fifo['目前市價'] = df_fifo['股票代號'].map(current_price_map).fillna(0)
    df_fifo['股票市值'] = df_fifo.apply(lambda row: row['庫存股數'] * row['目前市價'], axis=1)
    
    total_market_value = df_fifo['股票市值'].sum()
    df_fifo['佔總資產比例 (%)'] = df_fifo.apply(
        lambda row: 0 if total_market_value == 0 else (row['股票市值'] / total_market_value) * 100, axis=1
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
        lambda row: 0 if row['總持有成本 (FIFO)'] == 0 else (row['未實現損益'] / row['總持有成本 (FIFO)']) * 100, axis=1
    )
    df_fifo['賣出額外費用'] = costs_df.apply(lambda x: f"{int(x['total_fee'])} ({int(x['comm'])}+{int(x['tax'])})", axis=1)
    df_fifo['配息金額'] = 0
    df_fifo = df_fifo.sort_values(by='佔總資產比例 (%)', ascending=False).reset_index(drop=True)
    return df_fifo

def calculate_realized_report(df):
    if df.empty: return pd.DataFrame()
    df = df.copy()
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
    df['sort_order'] = df[col_action].apply(_get_action_sort_order)
    df = df.sort_values(by=[col_date, 'sort_order']).reset_index(drop=True)
    
    portfolio = {} 
    realized_records = []

    for _, row in df.iterrows():
        action = row.get(col_action, '')
        if action in ['入金', '出金', '還款']: continue
        
        sid = str(row.get(col_id, '')).strip()
        stock_name = str(row.get(col_name, '')).strip()
        txn_date = row[col_date]
        qty = _safe_float(row.get(col_qty))
        price = _safe_float(row.get(col_price))
        fee = _safe_float(row.get(col_fee))
        tax = _safe_float(row.get(col_tax))
        other = _safe_float(row.get(col_other))
        
        total_buy_cost_raw = (qty * price) + fee + other
        net_sell_proceeds = (qty * price) - fee - tax - other
        
        if sid not in portfolio: portfolio[sid] = deque()
        
        if action in ['買進', '現金增資']:
            unit_cost = total_buy_cost_raw / qty if qty > 0 else 0
            portfolio[sid].append({'qty': qty, 'unit_cost': unit_cost})
        elif action == '股票股利':
            unit_cost = (fee + other) / qty if qty > 0 else 0
            portfolio[sid].append({'qty': qty, 'unit_cost': unit_cost})
        elif action == '賣出':
            sell_qty = qty
            cost_basis = 0
            while sell_qty > 0 and portfolio[sid]:
                batch = portfolio[sid].popleft()
                if batch['qty'] > sell_qty:
                    cost_basis += sell_qty * batch['unit_cost']
                    batch['qty'] -= sell_qty
                    portfolio[sid].appendleft(batch)
                    sell_qty = 0
                else:
                    cost_basis += batch['qty'] * batch['unit_cost']
                    sell_qty -= batch['qty']
            realized_pnl = net_sell_proceeds - cost_basis
            ret_percent = (realized_pnl / cost_basis * 100) if cost_basis > 0 else 0
            realized_records.append({
                '交易日期': txn_date, '股票代號': sid, '股票名稱': stock_name, '交易類別': '賣出',
                '已實現損益': int(realized_pnl), '報酬率 (%)': ret_percent, '本金(成本)': int(cost_basis)
            })
        elif action == '現金股利':
            realized_records.append({
                '交易日期': txn_date, '股票代號': sid, '股票名稱': stock_name, '交易類別': '股息',
                '已實現損益': int(net_sell_proceeds), '報酬率 (%)': 0, '本金(成本)': 0
            })
    df_res = pd.DataFrame(realized_records)
    if not df_res.empty:
        df_res['年'] = df_res['交易日期'].dt.year
        df_res['月'] = df_res['交易日期'].dt.strftime('%Y-%m')
        df_res['股票'] = df_res.apply(lambda row: f"{row['股票名稱']}({row['股票代號']})", axis=1)
    return df_res

def calculate_account_balances(df):
    if df.empty: return {}
    df.columns = df.columns.str.strip()
    col_account = '交易帳戶'
    col_net_cash = '淨收付金額'
    if col_account not in df.columns or col_net_cash not in df.columns: return {}

    df_calc = df.copy()
    df_calc[col_net_cash] = df_calc[col_net_cash].astype(str).str.replace(r'[$,]', '', regex=True)
    df_calc[col_net_cash] = pd.to_numeric(df_calc[col_net_cash], errors='coerce').fillna(0)
    
    df_calc = df_calc[df_calc[col_account].astype(str).str.strip() != '']
    balances = df_calc.groupby(col_account)[col_net_cash].sum().to_dict()
    return balances

def get_volume_multiplier(current_time_str, mp_df):
    if mp_df.empty: return 1.0
    mp_df.columns = mp_df.columns.str.strip()
    col_time = "時間點迄 (HH:MM)"
    col_mult = "量能倍數"
    if col_time not in mp_df.columns or col_mult not in mp_df.columns: return 1.0
    try:
        for index, row in mp_df.iterrows():
            limit_time = str(row[col_time]).strip()
            if ':' in limit_time:
                h, m = limit_time.split(':')
                limit_time = f"{int(h):02d}:{int(m):02d}"
            if current_time_str <= limit_time: return float(row[col_mult])
        return 1.0
    except: return 1.0

def calculate_volume_ratio(current_vol, vol_10ma, multiplier):
    if vol_10ma is None or vol_10ma == 0: return 0, 0
    est_vol = current_vol * multiplier
    vol_10ma_sheets = vol_10ma / 1000
    if vol_10ma_sheets == 0: return int(est_vol), 0
    ratio = est_vol / vol_10ma_sheets
    return int(est_vol), round(ratio, 2)

# --- [Updated] 目標進度運算 (含時間維度) ---
# --- [Updated] 目標進度運算 (含時間維度 + 獲利目標自動追蹤) ---
def calculate_goal_progress(df_goals, df_txn):
    if df_goals.empty: return []

    # 1. 預先計算資料：還款累計
    current_repay_map = {}
    if not df_txn.empty:
        df_repay = df_txn[df_txn['交易類別'] == '還款'].copy()
        if not df_repay.empty:
            df_repay['淨收付金額'] = pd.to_numeric(df_repay['淨收付金額'].astype(str).str.replace(',', ''), errors='coerce').abs()
            current_repay_map = df_repay.groupby('股票名稱')['淨收付金額'].sum().to_dict()

    # 2. 預先計算資料：已實現損益 (供獲利目標使用)
    df_realized = calculate_realized_report(df_txn)
    if not df_realized.empty:
        # 確保日期格式為 datetime 以便比較
        df_realized['交易日期'] = pd.to_datetime(df_realized['交易日期'])

    goals_data = []
    today = datetime.now()

    for _, row in df_goals.iterrows():
        name = str(row.get('目標名稱', '')).strip()
        target = float(row.get('目標金額', 0))
        goal_type = str(row.get('目標類型', '還款')).strip() # 讀取類型
        
        if target <= 0: continue
        
        current = 0.0
        start_date_str = str(row.get('起始日期', ''))
        end_date_str = str(row.get('截止日期', ''))
        
        # --- 分流邏輯 ---
        if goal_type == '獲利':
            # 獲利型：計算區間內的已實現損益
            if not df_realized.empty:
                try:
                    s_dt = pd.to_datetime(start_date_str)
                    e_dt = pd.to_datetime(end_date_str)
                    # 篩選日期區間
                    mask = (df_realized['交易日期'] >= s_dt) & (df_realized['交易日期'] <= e_dt)
                    profit_sum = df_realized.loc[mask, '已實現損益'].sum()
                    # 若虧損 (負值)，顯示 0 (依需求不顯示負進度)
                    current = max(0, profit_sum)
                except:
                    current = 0
        else:
            # 還款型 (預設)：讀取還款累計 Map
            current = current_repay_map.get(name, 0.0)
        
        # --- 通用進度計算 ---
        pct = (current / target) * 100
        if pct > 100: pct = 100
        
        # 時間維度計算
        time_info = {
            'has_date': False,
            'time_pct': 0,
            'remaining_months': 0,
            'monthly_needed': 0,
            'status': 'normal'
        }
        
        try:
            start_dt = pd.to_datetime(start_date_str)
            end_dt = pd.to_datetime(end_date_str)
            
            if pd.notna(start_dt) and pd.notna(end_dt) and end_dt > start_dt:
                time_info['has_date'] = True
                total_days = (end_dt - start_dt).days
                elapsed_days = (today - start_dt).days
                
                if elapsed_days < 0: t_pct = 0
                elif elapsed_days > total_days: t_pct = 100
                else: t_pct = (elapsed_days / total_days) * 100
                
                time_info['time_pct'] = t_pct
                
                # 落後判斷 (寬容 5%)
                if pct < (t_pct - 5): time_info['status'] = 'behind'
                elif pct > (t_pct + 5): time_info['status'] = 'ahead'
                
                # 剩餘所需計算
                if current < target and end_dt > today:
                    remaining_days = (end_dt - today).days
                    remaining_months = max(remaining_days / 30, 1)
                    monthly_needed = (target - current) / remaining_months
                    time_info['remaining_months'] = remaining_months
                    time_info['monthly_needed'] = monthly_needed
        except:
            pass

        goals_data.append({
            'name': name,
            'target': target,
            'current': current,
            'percent': pct,
            'time_info': time_info
        })
        
    return goals_data
