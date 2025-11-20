import streamlit as st
import pandas as pd
from datetime import date

# 匯入自定義模組
import database
import logic

# 頁面設定
st.set_page_config(page_title="股票資產管理", layout="wide")
st.title('📊 股票資產管理系統 (Streamlit Cloud)')

# --- 預先讀取資料 (股票代碼表 & 帳戶清單) ---
try:
    stock_map = database.get_stock_info_map()
except Exception as e:
    st.toast(f"⚠️ 無法讀取 INDEX 表: {e}")
    stock_map = {}

try:
    # 讀取帳戶清單
    account_options = database.get_account_options()
except Exception as e:
    st.toast(f"⚠️ 無法讀取帳戶設定: {e}")
    account_options = ["預設帳戶"]

# --- 初始化 Session State ---
if "txn_date" not in st.session_state: st.session_state["txn_date"] = date.today()

# 帳戶初始化：預設使用清單中的第一個帳戶 (如果之前沒選過)
if "txn_account" not in st.session_state: 
    st.session_state["txn_account"] = account_options[0] if account_options else ""

# 確保 session 中的帳戶值有效 (防止清單變更後，舊的 session 值不在清單中報錯)
if st.session_state["txn_account"] not in account_options:
     st.session_state["txn_account"] = account_options[0] if account_options else ""

if "txn_stock_id" not in st.session_state: st.session_state["txn_stock_id"] = ""
if "txn_stock_name" not in st.session_state: st.session_state["txn_stock_name"] = ""
if "txn_qty" not in st.session_state: st.session_state["txn_qty"] = 0
if "txn_price" not in st.session_state: st.session_state["txn_price"] = 0.0
if "txn_notes" not in st.session_state: st.session_state["txn_notes"] = ""
if "form_msg" not in st.session_state: st.session_state["form_msg"] = None 

# --- 定義提交按鈕的 Callback ---
def submit_callback():
    s_date = st.session_state.txn_date
    s_account = st.session_state.txn_account # 這裡會讀到 selectbox 選中的值
    s_id = st.session_state.txn_stock_id
    s_name = st.session_state.txn_stock_name
    s_action = st.session_state.txn_action
    s_qty = st.session_state.txn_qty
    s_price = st.session_state.txn_price
    s_notes = st.session_state.txn_notes

    # 2. 資料驗證
    error_msgs = []
    if not s_account: error_msgs.append("❌ 請選擇「交易帳戶」")
    if not s_id: error_msgs.append("❌ 請輸入「股票代號」")
    if not s_name: error_msgs.append("❌ 未輸入「股票名稱」")
    
    if s_action != '現金股利' and s_qty <= 0: 
        error_msgs.append("❌ 「股數」必須大於 0")
    if s_action in ['買進', '賣出'] and s_price <= 0: 
        error_msgs.append("❌ 「單價」必須大於 0")

    if error_msgs:
        st.session_state["form_msg"] = {"type": "error", "content": error_msgs}
    else:
        try:
            # 3. 寫入資料庫
            database.save_transaction(
                s_date, s_id, s_name, s_action, s_qty, s_price, s_account, s_notes
            )
            
            # 4. 寫入成功：清空輸入欄位 (保留日期與帳戶)
            st.session_state.txn_stock_id = ""
            st.session_state.txn_stock_name = ""
            st.session_state.txn_qty = 0
            st.session_state.txn_price = 0.0
            st.session_state.txn_notes = ""
            
            st.session_state["form_msg"] = {
                "type": "success", 
                "content": f"✅ 成功新增：{s_name} ({s_id}) {s_action}"
            }
            
        except Exception as e:
            st.session_state["form_msg"] = {"type": "error", "content": [f"寫入失敗: {e}"]}


# --- 1. 側邊欄：輸入區 ---
with st.sidebar:
    st.header("📝 新增交易")
    
    col1, col2 = st.columns(2)
    
    # 1. 日期
    col1.date_input("交易日期", key="txn_date")
    
    # 2. 帳戶 (改為下拉選單)
    # 注意：這裡直接使用讀取到的 account_options
    col2.selectbox("交易帳戶", options=account_options, key="txn_account")
    
    # 3. 股票代號
    input_stock_id = col1.text_input("股票代號", placeholder="例如 2330", key="txn_stock_id")
    
    # --- 自動查詢邏輯 ---
    if input_stock_id:
        clean_id = str(input_stock_id).strip()
        found_name = stock_map.get(clean_id, "")
        if found_name and st.session_state["txn_stock_name"] != found_name:
            st.session_state["txn_stock_name"] = found_name
            st.rerun()

    # 4. 股票名稱
    col2.text_input("股票名稱", placeholder="自動帶入或手動輸入", key="txn_stock_name")
    
    # 5. 交易類別
    st.selectbox("交易類別", ['買進', '賣出', '現金股利', '股票股利'], key="txn_action")
    
    col3, col4 = st.columns(2)
    
    # 6. 股數與單價
    col3.number_input("股數", min_value=0, step=1000, key="txn_qty")
    col4.number_input("單價", min_value=0.0, step=0.5, format="%.2f", key="txn_price")
    
    st.text_area("備註", placeholder="選填", key="txn_notes")
    
    # --- C. 送出按鈕 ---
    st.button("💾 提交交易", on_click=submit_callback)

    # --- D. 顯示訊息 ---
    if st.session_state["form_msg"]:
        msg = st.session_state["form_msg"]
        if msg["type"] == "success":
            st.success(msg["content"])
        elif msg["type"] == "error":
            for err in msg["content"]:
                st.error(err)

# --- 2. 主畫面：顯示區 (維持不變) ---
tab1, tab2 = st.tabs(["📊 資產庫存 (FIFO)", "📋 原始交易紀錄"])

try:
    df_raw = database.load_data()

    with tab1:
        st.subheader("庫存損益試算 (FIFO)")
        if not df_raw.empty:
            df_fifo = logic.calculate_fifo_report(df_raw)
            if not df_fifo.empty:
                total_cost = df_fifo['總持有成本 (FIFO)'].sum()
                st.metric("目前總持有成本 (FIFO)", f"${total_cost:,.0f}")
                
                cols_order = ['股票代號', '股票名稱', '庫存股數', '平均成本', '總持有成本 (FIFO)']
                final_cols = [c for c in cols_order if c in df_fifo.columns]
                
                st.dataframe(
                    df_fifo[final_cols].style.format({
                        "庫存股數": "{:,.0f}",
                        "總持有成本 (FIFO)": "${:,.0f}",
                        "平均成本": "${:,.2f}"
                    }),
                    use_container_width=True
                )
            else:
                st.info("目前沒有庫存。")
        else:
            st.warning("目前沒有交易紀錄。")

    with tab2:
        st.subheader("最近交易紀錄")
        if not df_raw.empty and '交易日期' in df_raw.columns:
            df_display = df_raw.copy()
            df_display['交易日期'] = pd.to_datetime(df_display['交易日期'])
            df_display = df_display.sort_values(by='交易日期', ascending=False)
            st.dataframe(df_display)
        else:
            st.write("無資料")

except Exception as e:
    st.error(f"系統發生錯誤: {e}")
