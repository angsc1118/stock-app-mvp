import streamlit as st
import pandas as pd
from datetime import date

# 匯入自定義模組
import database
import logic

# 頁面設定
st.set_page_config(page_title="股票資產管理", layout="wide")
st.title('📊 股票資產管理系統 (Streamlit Cloud)')

# --- 0. 預先讀取股票代碼表 ---
try:
    stock_map = database.get_stock_info_map()
except Exception as e:
    st.toast(f"⚠️ 無法讀取 INDEX 表: {e}")
    stock_map = {}

# --- 定義清空函式 (Callback) ---
def clear_form():
    """
    這個函式會在按鈕點擊後、畫面重新整理前執行。
    在這裡修改 session_state 是安全的。
    """
    st.session_state["txn_stock_id"] = ""
    st.session_state["txn_stock_name"] = ""
    st.session_state["txn_qty"] = 0
    st.session_state["txn_price"] = 0.0
    st.session_state["txn_notes"] = ""
    # 日期與帳戶保留，不清空

# --- 1. 側邊欄：輸入區 ---
with st.sidebar:
    st.header("📝 新增交易")
    
    # --- 初始化 Session State ---
    if "txn_date" not in st.session_state: st.session_state["txn_date"] = date.today()
    if "txn_account" not in st.session_state: st.session_state["txn_account"] = ""
    if "txn_stock_id" not in st.session_state: st.session_state["txn_stock_id"] = ""
    if "txn_stock_name" not in st.session_state: st.session_state["txn_stock_name"] = ""
    if "txn_qty" not in st.session_state: st.session_state["txn_qty"] = 0
    if "txn_price" not in st.session_state: st.session_state["txn_price"] = 0.0
    if "txn_notes" not in st.session_state: st.session_state["txn_notes"] = ""
    
    col1, col2 = st.columns(2)
    
    # 1. 日期
    input_date = col1.date_input("交易日期", key="txn_date")
    
    # 2. 帳戶
    input_account = col2.text_input("交易帳戶", placeholder="請輸入帳戶名稱", key="txn_account")
    
    # 3. 股票代號
    input_stock_id = col1.text_input("股票代號", placeholder="例如 2330", key="txn_stock_id")
    
    # --- 自動查詢邏輯 ---
    # 在 Widget 渲染後檢查值，如果有變動且查得到名稱，就更新名稱的 state
    # 注意：這裡修改 txn_stock_name 是安全的，因為它還沒被下一個 text_input 讀取
    if input_stock_id:
        clean_id = str(input_stock_id).strip()
        found_name = stock_map.get(clean_id, "")
        if found_name and st.session_state["txn_stock_name"] != found_name:
            st.session_state["txn_stock_name"] = found_name
            st.rerun() # 強制重跑以顯示名稱

    # 4. 股票名稱
    input_stock_name = col2.text_input("股票名稱", placeholder="自動帶入或手動輸入", key="txn_stock_name")
    
    # 5. 交易類別
    input_action = st.selectbox("交易類別", ['買進', '賣出', '現金股利', '股票股利'], key="txn_action")
    
    col3, col4 = st.columns(2)
    
    # 6. 股數與單價
    input_qty = col3.number_input("股數", min_value=0, step=1000, key="txn_qty")
    input_price = col4.number_input("單價", min_value=0.0, step=0.5, format="%.2f", key="txn_price")
    
    input_notes = st.text_area("備註", placeholder="選填", key="txn_notes")
    
    # --- C. 送出按鈕邏輯修改 ---
    # 我們不使用 on_click 綁定 save，因為我們需要先檢查錯誤。
    # 策略：先檢查，如果通過檢查，寫入資料，然後呼叫 clear_form 並 rerun
    
    if st.button("💾 提交交易"):
        # --- 資料驗證 ---
        error_msgs = []
        if not input_account: error_msgs.append("❌ 請輸入「交易帳戶」")
        if not input_stock_id: error_msgs.append("❌ 請輸入「股票代號」")
        if not input_stock_name: error_msgs.append("❌ 未輸入「股票名稱」")
        
        if input_action != '現金股利' and input_qty <= 0: 
            error_msgs.append("❌ 「股數」必須大於 0")
        if input_action in ['買進', '賣出'] and input_price <= 0: 
            error_msgs.append("❌ 「單價」必須大於 0")

        if error_msgs:
            for msg in error_msgs: st.error(msg)
        else:
            try:
                database.save_transaction(
                    input_date, input_stock_id, input_stock_name, 
                    input_action, input_qty, input_price, 
                    input_account, input_notes
                )
                st.success(f"✅ 成功新增：{input_stock_name} ({input_stock_id}) {input_action}")
                
                # --- 關鍵修改：手動呼叫清空函式 ---
                clear_form()
                st.rerun()
                
            except Exception as e:
                st.error(f"寫入失敗: {e}")

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
