# ==============================================================================
# 檔案名稱: database.py
# 
# 修改歷程:
# 2025-11-24 11:10:00: [Fix] 修正 save_transaction 寫入位置錯誤 (改用指定列號寫入，避免 append_row 誤判)
# 2025-11-23: [Update] 新增 load_mp_table 函式，讀取盤中量能倍數表
# ==============================================================================

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
WATCHLIST_SHEET_NAME = '自選股清單'
MP_TABLE_SHEET_NAME = 'mp_table'

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

# --- [關鍵修正] 儲存交易 (指定位置寫入) ---
def save_transaction(date_val, stock_id, stock_name, action, qty, price, account, notes, discount):
    ws = get_worksheet(SHEET_NAME)
    if not ws: raise Exception(f"找不到工作表: {SHEET_NAME}")
    
    fees = logic.calculate_fees(qty, price, action, discount, stock_id)
    txn_id = logic.generate_txn_id()
    
    # 確保每個元素都轉為字串或數值，避免 gspread 寫入錯誤
    row_data = [
        txn_id,                 # 交易ID
        str(date_val),          # 交易日期
        str(stock_id),          # 股票代號
        stock_name,             # 股票名稱
        action,                 # 交易類別
        qty,                    # 股數
        price,                  # 單價
        fees['commission'],     # 手續費
        fees['tax'],            # 交易稅
        fees['other_fees'],     # 其他費用
        fees['gross_amount'],   # 成交總金額
        fees['total_fees'],     # 總費用
        fees['net_cash_flow'],  # 淨收付金額
        account,                # 交易帳戶
        notes                   # 備註
    ]
    
    # 1. 取得目前已有資料的最後一列 (使用 len(get_all_values) 最準確)
    # 雖然耗效能一點，但能保證不會覆蓋
    all_values = ws.get_all_values()
    next_row = len(all_values) + 1
    
    # 2. 指定範圍寫入 (例如 A501:O501)
    # row_data 的長度為 15，對應 A 到 O 欄
    col_count = len(row_data)
    # 將欄位數轉為字母 (例如 15 -> O)，這裡簡化直接計算範圍
    # gspread update 支援直接給 row index 和 col index
    
    # 使用 update_cells 或 update (range)
    # 這裡使用 range 寫法： f"A{next_row}"
    # 注意：如果 row_data 有空值，update 可能會報錯，需確保 list 完整
    
    # 簡單暴力的解法：先用 append_row，但強制指定 table_range 參數 (gspread 新版功能)
    # 或者回歸最原始且穩定的方法：update
    
    # 轉換 row_data 為字串陣列，避免 JSON 序列化問題
    formatted_row = [str(item) if item is not None else "" for item in row_data]
    
    # 指定從第一欄開始寫入
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
            # 對於歷史紀錄，append_row 通常比較安全，因為它是單純的 log
            # 但為了保險，我們也可以用同樣的邏輯
            all_values = ws.get_all_values()
            next_row = len(all_values) + 1
            ws.update(range_name=f"A{next_row}", values=[row_data])
            
    except Exception as e:
        # 如果讀取失敗，退回 append_row
        ws.append_row(row_data)

# --- 讀取自選股清單 ---
@st.cache_data(ttl=600) 
def load_watchlist():
    ws = get_worksheet(WATCHLIST_SHEET_NAME)
    if not ws: return pd.DataFrame()
    try:
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Warning: 讀取自選股失敗: {e}")
        return pd.DataFrame()

# --- 讀取量能倍數表 (mp_table) ---
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