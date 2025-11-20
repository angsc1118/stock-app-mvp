import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import date
import uuid

# --- 設定與常數 ---
SHEET_NAME = '交易紀錄'
COMMISSION_RATE = 0.001425
DISCOUNT = 0.6
MIN_FEE = 1
TAX_RATE = 0.003

st.set_page_config(page_title="股票資產管理", layout="wide")
st.title('📊 股票資產管理系統 (Streamlit Cloud)')

# --- 1. 連線設定 ---
@st.cache_resource
def get_worksheet():
    # A. 檢查 Secrets 是否設定了金鑰
    if "gcp_service_account" not in st.secrets:
        st.error("❌ 未設定 gcp_service_account 金鑰！")
        st.stop()
    
    # B. 檢查 Secrets 是否設定了試算表網址 (這是本次新增的)
    if "spreadsheet_url" not in st.secrets:
        st.error("❌ 未設定 spreadsheet_url！請至 Streamlit 後台 Secrets 新增此欄位。")
        st.stop()

    # C. 建立連線
    creds_dict = st.secrets["gcp_service_account"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # D. 使用設定檔中的網址開啟試算表
    sheet_url = st.secrets["spreadsheet_url"]
    try:
        sheet = client.open_by_url(sheet_url)
        return sheet.worksheet(SHEET_NAME)
    except Exception as e:
        st.error(f"❌ 無法開啟試算表，請檢查網址權限或名稱: {e}")
        st.stop()

# --- 2. 讀取資料 ---
def load_data():
    ws = get_worksheet()
    data = ws.get_all_records()
    return pd.DataFrame(data)

# --- 3. 寫入資料函式 ---
def add_transaction(date_val, stock_id, stock_name, action, qty, price, account, notes):
    ws = get_worksheet()
    
    # 運算邏輯
    gross_amount = int(qty * price)
    
    raw_commission = int(gross_amount * COMMISSION_RATE * DISCOUNT)
    commission = max(raw_commission, MIN_FEE) if gross_amount > 0 else 0
    
    tax = int(gross_amount * TAX_RATE) if action == '賣出' else 0
    other_fees = 0
    total_fees = commission + tax + other_fees
    
    net_cash_flow = 0
    if action in ['買進', '現金增資']:
        net_cash_flow = -(gross_amount + total_fees)
    elif action == '賣出':
        net_cash_flow = gross_amount - total_fees
    elif action == '現金股利':
        net_cash_flow = gross_amount - total_fees
    
    txn_id = f"TXN-{str(uuid.uuid4())[:8].upper()}"
    
    # 準備寫入資料
    row_data = [
        txn_id, str(date_val), str(stock_id), stock_name, action, qty, price,
        commission, tax, other_fees, gross_amount, total_fees, net_cash_flow,
        False, account, notes
    ]
    
    ws.append_row(row_data)
    st.cache_data.clear()

# --- 4. 側邊欄：新增交易表單 ---
with st.sidebar:
    st.header("📝 新增交易")
    with st.form("add_txn_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        input_date = col1.date_input("交易日期", date.today())
        input_account = col2.text_input("交易帳戶", "帳戶A")
        
        input_stock_id = col1.text_input("股票代號", "2330")
        input_stock_name = col2.text_input("股票名稱", "台積電")
        
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
                # 強制重新執行以顯示最新資料
                st.rerun()
            except Exception as e:
                st.error(f"寫入失敗: {e}")

# --- 5. 主畫面：顯示資料 ---
try:
    df = load_data()
    
    col_a, col_b = st.columns(2)
    col_a.metric("總交易筆數", len(df))
    
    st.subheader("📋 最近交易紀錄 (最新 10 筆)")
    if not df.empty and '交易日期' in df.columns:
        df['交易日期'] = pd.to_datetime(df['交易日期'])
        df = df.sort_values(by='交易日期', ascending=False)
        
    st.dataframe(df.head(10))

except Exception as e:
    st.error(f"讀取資料失敗: {e}")
