import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import logic  # 匯入邏輯層

# --- 常數設定 ---
SHEET_NAME = '交易紀錄'
INDEX_SHEET_NAME = 'INDEX'
ACCOUNT_SHEET_NAME = '交割帳戶設定'

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

# --- 修改：讀取帳戶與折數 ---
@st.cache_data(ttl=3600)
def get_account_settings():
    """
    讀取 '交割帳戶設定' 表，回傳 { '帳戶名稱': 折數 } 的字典
    例如: { '元大-敦化': 0.6, '富邦': 0.168 }
    """
    try:
        ws = get_worksheet(ACCOUNT_SHEET_NAME)
        # 使用 get_all_records 讀取，自動將第一列作為 Key
        data = ws.get_all_records()
        
        account_map = {}
        for row in data:
            # 嘗試讀取欄位，相容不同的命名習慣
            name = str(row.get('帳戶名稱', row.get('Account', ''))).strip()
            
            # 讀取折數，若無則預設為 0.6 (或 1.0，視您需求)
            discount_val = row.get('手續費折數', row.get('Discount', 0.6))
            
            # 確保折數是數字
            try:
                discount = float(discount_val)
            except:
                discount = 0.6 # 轉換失敗的預設值

            if name:
                account_map[name] = discount
                
        if not account_map:
            return {"預設帳戶": 0.6}
            
        return account_map
    except Exception as e:
        print(f"Warning: 讀取帳戶表失敗: {e}")
        return {"無法讀取帳戶": 1.0}

# --- 既有功能：讀取交易紀錄 ---
def load_data():
    ws = get_worksheet(SHEET_NAME)
    data = ws.get_all_records()
    return pd.DataFrame(data)

# --- 修改：儲存交易 (增加 discount 參數) ---
def save_transaction(date_val, stock_id, stock_name, action, qty, price, account, notes, discount):
    ws = get_worksheet(SHEET_NAME)
    
    # 1. 將折數傳給邏輯層計算
    fees = logic.calculate_fees(qty, price, action, discount)
    
    txn_id = logic.generate_txn_id()
    
    row_data = [
        txn_id, str(date_val), str(stock_id), stock_name, action, qty, price,
        fees['commission'], fees['tax'], fees['other_fees'], 
        fees['gross_amount'], fees['total_fees'], fees['net_cash_flow'],
        False, account, notes
    ]
    
    ws.append_row(row_data)
    st.cache_data.clear()
