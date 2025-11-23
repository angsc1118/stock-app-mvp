import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import logic  # 匯入邏輯層

# --- 常數設定 ---
SHEET_NAME = '交易紀錄'
INDEX_SHEET_NAME = 'INDEX'
ACCOUNT_SHEET_NAME = '交割帳戶設定'
HISTORY_SHEET_NAME = '資產歷史紀錄'
WATCHLIST_SHEET_NAME = '自選股清單' # 新增

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
        # 改為 print 警告，避免因為找不到某個新 sheet 就讓整個 app 當掉
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
        fees['commission'], fees['tax'], fees['other_fees'], 
        fees['gross_amount'], fees['total_fees'], fees['net_cash_flow'],
        False, account, notes
    ]
    ws.append_row(row_data)
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
            ws.append_row(row_data)
    except Exception as e:
        ws.append_row(row_data)

# --- [新增] 讀取自選股清單 ---
@st.cache_data(ttl=600) # 快取 10 分鐘，避免頻繁讀取 Sheet
def load_watchlist():
    """讀取自選股設定"""
    ws = get_worksheet(WATCHLIST_SHEET_NAME)
    if not ws: return pd.DataFrame()
    try:
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Warning: 讀取自選股失敗: {e}")
        return pd.DataFrame()
