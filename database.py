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
        # 使用 expected_headers 可以避免 header 錯誤，但最好還是清理 Sheet
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"讀取交易紀錄失敗: {e}")
        # 回傳空 DataFrame 以避免程式崩潰
        return pd.DataFrame()

# --- [關鍵修改] 儲存交易 (移除多餘欄位) ---
def save_transaction(date_val, stock_id, stock_name, action, qty, price, account, notes, discount):
    ws = get_worksheet(SHEET_NAME)
    
    fees = logic.calculate_fees(qty, price, action, discount, stock_id)
    txn_id = logic.generate_txn_id()
    
    # 依照您最新的簡化欄位順序排列
    # 請確認 Google Sheet 的欄位順序與此一致
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
        notes                   # 備註 (建議保留)
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

# --- 寫入資產歷史紀錄 ---
def save_asset_history(date_str, total_assets, total_cash, total_stock):
    ws = get_worksheet(HISTORY_SHEET_NAME)
    
    # 寫入格式化後的字串
    row_data = [
        str(date_str),
        f"{total_assets:,}",
        f"{total_cash:,}",
        f"{total_stock:,}"
    ]
    
    try:
        # 檢查日期是否已存在，若存在則覆蓋
        col_dates = ws.col_values(1) # 取得第一欄的所有日期
        if str(date_str) in col_dates:
            # 找到列號 (gspread 是 1-based)
            row_idx = col_dates.index(str(date_str)) + 1
            cell_range = f"A{row_idx}:D{row_idx}"
            ws.update(range_name=cell_range, values=[row_data])
        else:
            ws.append_row(row_data)
            
    except Exception as e:
        print(f"Update history failed, fallback to append: {e}")
        ws.append_row(row_data)
