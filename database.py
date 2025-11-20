import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import logic  # 匯入邏輯層

# --- 常數設定 ---
SHEET_NAME = '交易紀錄'
INDEX_SHEET_NAME = 'INDEX'
ACCOUNT_SHEET_NAME = '交割帳戶設定' # 新增：帳戶設定頁籤

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
        st.error(f"❌ 無法開啟工作表 '{sheet_name}'，請確認名稱正確: {e}")
        st.stop()

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

# --- 新增：讀取帳戶選單 ---
@st.cache_data(ttl=3600)
def get_account_options():
    """
    讀取 '交割帳戶設定' 的 A 欄 (帳戶名稱)，回傳列表
    """
    try:
        ws = get_worksheet(ACCOUNT_SHEET_NAME)
        # 讀取第一欄 (col_values(1))
        # 假設 A1 是標題 '帳戶名稱'，從 A2 開始是資料
        col_values = ws.col_values(1)
        
        # 移除標題 (如果第一行是標題)
        if col_values and (col_values[0] == '帳戶名稱' or col_values[0] == 'Account'):
            accounts = col_values[1:]
        else:
            accounts = col_values
            
        # 過濾空值並去空白
        valid_accounts = [acc.strip() for acc in accounts if acc.strip()]
        
        if not valid_accounts:
            return ["預設帳戶"] # 避免空清單導致錯誤
            
        return valid_accounts
    except Exception as e:
        print(f"Warning: 讀取帳戶表失敗: {e}")
        return ["無法讀取帳戶"]

# --- 既有功能：讀取交易紀錄 ---
def load_data():
    ws = get_worksheet(SHEET_NAME)
    data = ws.get_all_records()
    return pd.DataFrame(data)

# --- 既有功能：儲存交易 ---
def save_transaction(date_val, stock_id, stock_name, action, qty, price, account, notes):
    ws = get_worksheet(SHEET_NAME)
    fees = logic.calculate_fees(qty, price, action)
    txn_id = logic.generate_txn_id()
    
    row_data = [
        txn_id, str(date_val), str(stock_id), stock_name, action, qty, price,
        fees['commission'], fees['tax'], fees['other_fees'], 
        fees['gross_amount'], fees['total_fees'], fees['net_cash_flow'],
        False, account, notes
    ]
    
    ws.append_row(row_data)
    st.cache_data.clear()
