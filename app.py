import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import date
import uuid

# --- 設定與常數 (對應您的 GAS 設定) ---
SHEET_NAME = '交易紀錄'  # [cite: 1]
COMMISSION_RATE = 0.001425 # [cite: 3]
DISCOUNT = 0.6  # [cite: 2]
MIN_FEE = 1     # [cite: 3]
TAX_RATE = 0.003 # [cite: 3]

st.set_page_config(page_title="股票資產管理", layout="wide")
st.title('📊 股票資產管理系統 (Streamlit Cloud)')

# --- 1. 連線設定 ---
@st.cache_resource
def get_worksheet():
    # 從 Streamlit Secrets 讀取金鑰
    creds_dict = st.secrets["gcp_service_account"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # 請確認這裡的 URL 是正確的
    sheet_url = "https://docs.google.com/spreadsheets/d/您的試算表ID/edit" 
    sheet = client.open_by_url(sheet_url)
    return sheet.worksheet(SHEET_NAME)

# --- 2. 讀取資料 ---
def load_data():
    ws = get_worksheet()
    data = ws.get_all_records()
    return pd.DataFrame(data)

# --- 3. 寫入資料函式 ---
def add_transaction(date_val, stock_id, stock_name, action, qty, price, account, notes):
    ws = get_worksheet()
    
    # --- Python 端的計算邏輯 (重現 GAS 邏輯) ---
    # 1. 總成交金額 [cite: 87]
    gross_amount = int(qty * price)
    
    # 2. 手續費計算 (無條件捨去) [cite: 88, 89]
    raw_commission = int(gross_amount * COMMISSION_RATE * DISCOUNT)
    commission = max(raw_commission, MIN_FEE) if gross_amount > 0 else 0
    
    # 3. 交易稅計算 (僅賣出有) [cite: 92]
    tax = int(gross_amount * TAX_RATE) if action == '賣出' else 0
    
    # 4. 總費用 [cite: 96]
    other_fees = 0 # 暫時設為 0
    total_fees = commission + tax + other_fees
    
    # 5. 淨收付金額 [cite: 97-100]
    net_cash_flow = 0
    if action in ['買進', '現金增資']:
        net_cash_flow = -(gross_amount + total_fees)
    elif action == '賣出':
        net_cash_flow = gross_amount - total_fees
    elif action == '現金股利':
        net_cash_flow = gross_amount - total_fees # 假設 gross_amount 是股利總額
    
    # 產生唯一 ID (模擬 GAS 的 TXN-UUID) [cite: 57]
    txn_id = f"TXN-{str(uuid.uuid4())[:8].upper()}"
    
    # 準備寫入的一列資料 (順序必須對應 Google Sheet 欄位) [cite: 4]
    # ID, DATE, STOCK_ID, STOCK_NAME, ACTION, QTY, PRICE, COMMISSION, TAX, OTHER, GROSS, TOTAL_FEES, NET, SYNC, ACCOUNT, NOTES
    row_data = [
        txn_id,
        str(date_val),
        str(stock_id),
        stock_name,
        action,
        qty,
        price,
        commission,
        tax,
        other_fees,
        gross_amount,
        total_fees,
        net_cash_flow,
        False,  # Sync Status (設為 False 讓 GAS 有機會去處理它，如果需要的話)
        account,
        notes
    ]
    
    # 寫入 Google Sheet
    ws.append_row(row_data)
    st.cache_data.clear() # 清除快取，確保下次讀取是新的

# --- 4. 側邊欄：新增交易表單 ---
with st.sidebar:
    st.header("📝 新增交易")
    with st.form("add_txn_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        input_date = col1.date_input("交易日期", date.today())
        input_account = col2.text_input("交易帳戶", "帳戶A") # 暫時用手填，未來可讀取選單
        
        input_stock_id = col1.text_input("股票代號", "2330")
        input_stock_name = col2.text_input("股票名稱", "台積電") # 未來可做自動查詢
        
        input_action = st.selectbox("交易類別", ['買進', '賣出', '現金股利', '股票股利'])
        
        col3, col4 = st.columns(2)
        input_qty = col3.number_input("股數", min_value=1, value=1000, step=1000)
        input_price = col4.number_input("單價", min_value=0.0, value=500.0, step=0.5, format="%.2f")
        
        input_notes = st.text_area("備註")
        
        submitted = st.form_submit_button("💾 提交交易")
        
        if submitted:
            try:
                add_transaction(
                    input_date, input_stock_id, input_stock_name, 
                    input_action, input_qty, input_price, 
                    input_account, input_notes
                )
                st.success(f"成功新增 {input_stock_name} {input_action} 紀錄！")
            except Exception as e:
                st.error(f"寫入失敗: {e}")

# --- 5. 主畫面：顯示資料 ---
try:
    df = load_data()
    
    # 簡單的統計指標
    st.metric("總交易筆數", len(df))
    
    st.subheader("📋 最近交易紀錄 (最新 10 筆)")
    # 依照日期排序顯示
    if not df.empty and '交易日期' in df.columns:
        df['交易日期'] = pd.to_datetime(df['交易日期'])
        df = df.sort_values(by='交易日期', ascending=False)
        
    st.dataframe(df.head(10))

except Exception as e:
    st.error(f"讀取資料失敗，請檢查金鑰或試算表權限: {e}")
