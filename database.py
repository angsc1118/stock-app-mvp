# database.py
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import logic  # 匯入剛剛寫的 logic

SHEET_NAME = '交易紀錄'

@st.cache_resource
def get_worksheet():
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
        return sheet.worksheet(SHEET_NAME)
    except Exception as e:
        st.error(f"❌ 無法開啟試算表: {e}")
        st.stop()

def load_data():
    """讀取所有交易紀錄"""
    ws = get_worksheet()
    data = ws.get_all_records()
    return pd.DataFrame(data)

def save_transaction(date_val, stock_id, stock_name, action, qty, price, account, notes):
    """將交易寫入 Google Sheet"""
    ws = get_worksheet()
    
    # 1. 呼叫 logic 計算費用 (這裡不自己算，交給專業的 logic)
    fees = logic.calculate_fees(qty, price, action)
    
    # 2. 呼叫 logic 產生 ID
    txn_id = logic.generate_txn_id()
    
    # 3. 組合資料列
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
        False, 
        account, 
        notes
    ]
    
    # 4. 執行寫入
    ws.append_row(row_data)
    st.cache_data.clear() # 清除快取
