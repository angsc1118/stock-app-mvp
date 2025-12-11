# ==============================================================================
# 檔案名稱: database.py
# 
# 修改歷程:
# 2025-12-11 12:40:00: [Feat] 第一階段：新增 load_goals 函式，讀取「目標設定」工作表
# 2025-11-27 14:50:00: [Feat] 新增 save_watchlist 函式
# ==============================================================================

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import logic

# --- 常數設定 ---
SHEET_NAME = '交易紀錄'
INDEX_SHEET_NAME = 'INDEX'
ACCOUNT_SHEET_NAME = '交割帳戶設定'
HISTORY_SHEET_NAME = '資產歷史紀錄'
WATCHLIST_SHEET_NAME = '自選股清單'
MP_TABLE_SHEET_NAME = 'mp_table'
GOALS_SHEET_NAME = '目標設定' # [New] 新增目標設定表

# --- 連線核心 ---
@st.cache_resource
def get_worksheet(sheet_name):
    """建立 Google Sheet 連線"""
    if "gcp_service_account" not in st.secrets:
        st.error("❌ 未設定 gcp_service_account 金鑰！")
        st.stop()
    if "spreadsheet_url" not in st.secrets:
        st.error("❌ 未設定 spreadsheet_url！")
        st.stop()

    creds_dict = st.secrets["gcp_service_account"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    sheet_url = st.secrets["spreadsheet_url"]
    try:
        sheet = client.open_by_url(sheet_url)
        return sheet.worksheet(sheet_name)
    except Exception as e:
        print(f"無法開啟工作表 '{sheet_name}': {e}")
        return None

# --- 讀取股票代碼表 ---
@st.cache_data(ttl=3600)
def get_stock_info_map():
    ws = get_worksheet(INDEX_SHEET_NAME)
    if not ws: return {}
    try:
        data = ws.get_all_records()
        stock_map = {}
        for row in data:
            symbol = str(row.get('symbol', row.get('Symbol', ''))).strip()
            name = str(row.get('name', row.get('Name', ''))).strip()
            if symbol and name:
                stock_map[symbol] = name
        return stock_map
    except: return {}

# --- 讀取帳戶與折數 ---
@st.cache_data(ttl=3600)
def get_account_settings():
    ws = get_worksheet(ACCOUNT_SHEET_NAME)
    if not ws: return {"預設帳戶": 0.6}
    try:
        data = ws.get_all_records()
        account_map = {}
        for row in data:
            name = str(row.get('帳戶名稱', row.get('Account', ''))).strip()
            discount_val = row.get('手續費折數', row.get('Discount', 0.6))
            try: discount = float(discount_val)
            except: discount = 0.6 
            if name: account_map[name] = discount
        return account_map if account_map else {"預設帳戶": 0.6}
    except: return {"預設帳戶": 0.6}

# --- 讀取交易紀錄 ---
def load_data():
    ws = get_worksheet(SHEET_NAME)
    if not ws: return pd.DataFrame()
    try:
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"讀取交易紀錄失敗: {e}")
        return pd.DataFrame()

# --- 儲存交易 ---
def save_transaction(date_val, stock_id, stock_name, action, qty, price, account, notes, discount):
    ws = get_worksheet(SHEET_NAME)
    if not ws: raise Exception(f"找不到工作表: {SHEET_NAME}")
    
    fees = logic.calculate_fees(qty, price, action, discount, stock_id)
    txn_id = logic.generate_txn_id()
    
    row_data = [
        txn_id, str(date_val), str(stock_id), stock_name, action, qty, price,
        fees['commission'], fees['tax'], fees['other_fees'], fees['gross_amount'],
        fees['total_fees'], fees['net_cash_flow'], account, notes
    ]
    
    all_values = ws.get_all_values()
    next_row = len(all_values) + 1
    formatted_row = [str(item) if item is not None else "" for item in row_data]
    ws.update(range_name=f"A{next_row}", values=[formatted_row])
    st.cache_data.clear()

# --- 讀取資產歷史紀錄 ---
def load_asset_history():
    ws = get_worksheet(HISTORY_SHEET_NAME)
    if not ws: return pd.DataFrame()
    try:
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except: return pd.DataFrame()

# --- 寫入資產歷史紀錄 ---
def save_asset_history(date_str, total_assets, total_cash, total_stock):
    ws = get_worksheet(HISTORY_SHEET_NAME)
    if not ws: raise Exception(f"找不到工作表: {HISTORY_SHEET_NAME}")
    
    row_data = [str(date_str), f"{total_assets:,}", f"{total_cash:,}", f"{total_stock:,}"]
    try:
        col_dates = ws.col_values(1)
        if str(date_str) in col_dates:
            row_idx = col_dates.index(str(date_str)) + 1
            ws.update(range_name=f"A{row_idx}:D{row_idx}", values=[row_data])
        else:
            all_values = ws.get_all_values()
            next_row = len(all_values) + 1
            ws.update(range_name=f"A{next_row}", values=[row_data])
    except Exception as e:
        ws.append_row(row_data)

# --- 讀取自選股清單 ---
@st.cache_data(ttl=10) 
def load_watchlist():
    ws = get_worksheet(WATCHLIST_SHEET_NAME)
    if not ws: return pd.DataFrame()
    try:
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        required_cols = ['群組', '股票代號', '股票名稱', '警示價_高', '警示價_低', '備註']
        for col in required_cols:
            if col not in df.columns: df[col] = ""
        return df
    except Exception as e:
        print(f"Warning: 讀取自選股失敗: {e}")
        return pd.DataFrame()

# --- 儲存自選股清單 ---
def save_watchlist(df):
    ws = get_worksheet(WATCHLIST_SHEET_NAME)
    if not ws: raise Exception(f"找不到工作表: {WATCHLIST_SHEET_NAME}")
    try:
        ws.clear()
        df_to_save = df.astype(str)
        data_to_write = [df_to_save.columns.values.tolist()] + df_to_save.values.tolist()
        ws.update(values=data_to_write)
        load_watchlist.clear()
    except Exception as e:
        raise Exception(f"儲存自選股失敗: {e}")

# --- 讀取量能倍數表 ---
@st.cache_data(ttl=3600)
def load_mp_table():
    ws = get_worksheet(MP_TABLE_SHEET_NAME)
    if not ws: return pd.DataFrame()
    try:
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Warning: 讀取 mp_table 失敗: {e}")
        return pd.DataFrame()

# --- [New] 讀取目標設定 ---
# --- [Updated] 讀取目標設定 ---
@st.cache_data(ttl=60)
def load_goals():
    ws = get_worksheet(GOALS_SHEET_NAME)
    if not ws: return pd.DataFrame()
    try:
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # [Fix] 新增 '目標類型' 到必要欄位
        required_cols = ['目標名稱', '目標金額', '起始日期', '截止日期', '狀態', '目標類型']
        for col in required_cols:
            if col not in df.columns: df[col] = ""
            
        # 資料型態轉換
        if '目標金額' in df.columns:
            df['目標金額'] = df['目標金額'].astype(str).str.replace(',', '')
            df['目標金額'] = pd.to_numeric(df['目標金額'], errors='coerce').fillna(0)
            
        # 預設值處理：若目標類型為空，預設為 "還款" (相容舊資料)
        if '目標類型' in df.columns:
            df['目標類型'] = df['目標類型'].replace('', '還款')
            
        # 只回傳狀態為「進行中」的目標
        if '狀態' in df.columns:
            df = df[df['狀態'] == '進行中']
            
        return df
    except Exception as e:
        print(f"Warning: 讀取目標設定失敗: {e}")
        return pd.DataFrame()
