import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import logic  # 匯入邏輯層

# --- 常數設定 ---
SHEET_NAME = '交易紀錄'
INDEX_SHEET_NAME = 'INDEX' # 新增：股票代碼對照表

# --- 連線核心 ---
@st.cache_resource
def get_worksheet(sheet_name):
    """
    建立 Google Sheet 連線，並開啟指定的工作表 (Tab)
    """
    # 1. 檢查 Secrets 設定
    if "gcp_service_account" not in st.secrets:
        st.error("❌ 未設定 gcp_service_account 金鑰！")
        st.stop()
    if "spreadsheet_url" not in st.secrets:
        st.error("❌ 未設定 spreadsheet_url！")
        st.stop()

    # 2. 建立連線
    creds_dict = st.secrets["gcp_service_account"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # 3. 開啟試算表
    sheet_url = st.secrets["spreadsheet_url"]
    try:
        sheet = client.open_by_url(sheet_url)
        return sheet.worksheet(sheet_name)
    except Exception as e:
        st.error(f"❌ 無法開啟工作表 '{sheet_name}'，請確認名稱正確: {e}")
        st.stop()

# --- 新增：讀取股票代碼表 ---
@st.cache_data(ttl=3600) # 設定快取 1 小時
def get_stock_info_map():
    """
    讀取 INDEX 表，回傳字典格式：{ '2330': '台積電', '0050': '元大台灣50' }
    """
    try:
        ws = get_worksheet(INDEX_SHEET_NAME)
        data = ws.get_all_records()
        
        stock_map = {}
        for row in data:
            # 確保欄位名稱對應 (這裡假設 INDEX 表頭是 symbol 和 name)
            # 使用 .get() 避免欄位名稱大小寫不一致導致報錯
            # 強制轉字串並去空白
            symbol = str(row.get('symbol', row.get('Symbol', ''))).strip()
            name = str(row.get('name', row.get('Name', ''))).strip()
            
            if symbol and name:
                stock_map[symbol] = name
                
        return stock_map
    except Exception as e:
        # 若讀取失敗 (例如沒有 INDEX 表)，回傳空字典，不要讓程式崩潰
        print(f"Warning: 讀取 INDEX 表失敗: {e}")
        return {}

# --- 既有功能：讀取交易紀錄 ---
def load_data():
    """讀取所有交易紀錄"""
    ws = get_worksheet(SHEET_NAME)
    data = ws.get_all_records()
    return pd.DataFrame(data)

# --- 既有功能：儲存交易 ---
def save_transaction(date_val, stock_id, stock_name, action, qty, price, account, notes):
    """將交易寫入 Google Sheet"""
    ws = get_worksheet(SHEET_NAME)
    
    # 1. 呼叫 logic 計算費用
    fees = logic.calculate_fees(qty, price, action)
    
    # 2. 呼叫 logic 產生 ID
    txn_id = logic.generate_txn_id()
    
    # 3. 組合資料列 (必須對應 Sheet 欄位順序)
    row_data = [
        txn_id, 
        str(date_val), 
        str(stock_id), 
        stock_name, 
        action, 
        qty, 
        price,
        fees['commission'], 
        fees['tax'], 
        fees['other_fees'], 
        fees['gross_amount'], 
        fees['total_fees'], 
        fees['net_cash_flow'],
        False,  # Sync Status
        account, 
        notes
    ]
    
    # 4. 執行寫入
    ws.append_row(row_data)
    
    # 5. 清除快取 (強制下一次 load_data 抓到最新資料)
    st.cache_data.clear()
