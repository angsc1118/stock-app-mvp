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

# --- 連線核心 ---
@st.cache_resource
def get_worksheet(sheet_name):
    """
    建立 Google Sheet 連線，並開啟指定的工作表 (Tab)
    """
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
        raise Exception(f"無法開啟工作表 '{sheet_name}'，請確認已建立該分頁。錯誤: {e}")

# --- 讀取股票代碼表 ---
@st.cache_data(ttl=3600)
def get_stock_info_map():
    try:
        ws = get_worksheet(INDEX_SHEET_NAME)
        data = ws.get_all_records()
        
        stock_map = {}
        for row in data:
            symbol = str(row.get('symbol', row.get('Symbol', ''))).strip()
            name = str(row.get('name', row.get('Name', ''))).strip()
            if symbol and name:
                stock_map[symbol] = name
        return stock_map
    except Exception as e:
        print(f"Warning: 讀取 INDEX 表失敗: {e}")
        return {}

# --- 讀取帳戶與折數 ---
@st.cache_data(ttl=3600)
def get_account_settings():
    try:
        ws = get_worksheet(ACCOUNT_SHEET_NAME)
        data = ws.get_all_records()
        
        account_map = {}
        for row in data:
            name = str(row.get('帳戶名稱', row.get('Account', ''))).strip()
            discount_val = row.get('手續費折數', row.get('Discount', 0.6))
            try:
                discount = float(discount_val)
            except:
                discount = 0.6 
            if name:
                account_map[name] = discount
        if not account_map:
            return {"預設帳戶": 0.6}
        return account_map
    except Exception as e:
        print(f"Warning: 讀取帳戶表失敗: {e}")
        return {"無法讀取帳戶": 1.0}

# --- 讀取交易紀錄 ---
def load_data():
    try:
        ws = get_worksheet(SHEET_NAME)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"讀取交易紀錄失敗: {e}")
        return pd.DataFrame()

# --- 儲存交易 ---
def save_transaction(date_val, stock_id, stock_name, action, qty, price, account, notes, discount):
    ws = get_worksheet(SHEET_NAME)
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
    try:
        ws = get_worksheet(HISTORY_SHEET_NAME)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        return pd.DataFrame()

# --- [修改] 寫入資產歷史紀錄 (含覆蓋邏輯與格式化) ---
def save_asset_history(date_str, total_assets, total_cash, total_stock):
    """
    寫入一筆資產紀錄
    如果當天已存在紀錄，則更新該行；否則新增。
    數值會格式化為 "1,234,567" 字串。
    """
    ws = get_worksheet(HISTORY_SHEET_NAME)
    
    # 1. 準備寫入資料 (加上逗號格式)
    # 注意：這裡將數字轉為字串儲存，但 load_asset_history 讀取後
    # 因為 logic.py 的 helper 函式會處理逗號，所以不會有問題
    row_data = [
        str(date_str),
        f"{total_assets:,}",
        f"{total_cash:,}",
        f"{total_stock:,}"
    ]
    
    try:
        # 2. 檢查日期是否已存在 (讀取第一欄：日期)
        # col_values(1) 會回傳整欄資料列表，例如 ['日期', '2025-11-20', '2025-11-21']
        dates = ws.col_values(1)
        
        if str(date_str) in dates:
            # 3. 若存在 -> 找到列號並更新 (dates 列表是 0-based，且包含標題，所以要小心計算)
            # gspread 的行號是 1-based
            row_idx = dates.index(str(date_str)) + 1
            
            # 更新該列 (A{row}:D{row})
            # 這裡使用 range 寫法確保覆蓋整列
            cell_range = f"A{row_idx}:D{row_idx}"
            ws.update(range_name=cell_range, values=[row_data])
            
        else:
            # 4. 若不存在 -> 新增
            ws.append_row(row_data)
            
    except Exception as e:
        # 若讀取日期失敗或其他錯誤，退回到直接新增 (保險起見)
        print(f"Update history failed, fallback to append: {e}")
        ws.append_row(row_data)
