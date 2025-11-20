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
# 嘗試從 database 取得 {代號: 名稱} 的對照表
try:
    stock_map = database.get_stock_info_map()
except Exception as e:
    st.toast(f"⚠️ 無法讀取 INDEX 表: {e}")
    stock_map = {}

# --- 1. 側邊欄：輸入區 (即時互動模式) ---
with st.sidebar:
    st.header("📝 新增交易")
    
    # --- A. 初始化 Session State ---
    # 這些變數用來暫存使用者的輸入值
    if "txn_date" not in st.session_state: st.session_state["txn_date"] = date.today()
    if "txn_account" not in st.session_state: st.session_state["txn_account"] = ""
    if "txn_stock_id" not in st.session_state: st.session_state["txn_stock_id"] = ""
    if "txn_stock_name" not in st.session_state: st.session_state["txn_stock_name"] = ""
    if "txn_qty" not in st.session_state: st.session_state["txn_qty"] = 0
    if "txn_price" not in st.session_state: st.session_state["txn_price"] = 0.0
    if "txn_notes" not in st.session_state: st.session_state["txn_notes"] = ""
    # 交易類別保留預設值，不需特別清空
    
    col1, col2 = st.columns(2)
    
    # 1. 日期
    input_date = col1.date_input("交易日期", key="txn_date")
    
    # 2. 帳戶
    input_account = col2.text_input("交易帳戶", placeholder="請輸入帳戶名稱", key="txn_account")
    
    # 3. 股票代號 (輸入後按 Enter，Streamlit 會重新執行此腳本)
    input_stock_id = col1.text_input("股票代號", placeholder="例如 2330", key="txn_stock_id")
    
    # --- B. 自動查詢邏輯 (在顯示「股票名稱」輸入框之前執行) ---
    # 檢查目前的 ID 是否有對應名稱
    if input_stock_id:
        clean_id = str(input_stock_id).strip()
        found_name = stock_map.get(clean_id, "")
        
        # 如果查到了，就自動更新 Session State 中的股票名稱
        if found_name:
            st.session_state["txn_stock_name"] = found_name

    # 4. 股票名稱 (因為 Session State 被更新了，這裡會自動顯示查到的名稱)
    input_stock_name = col2.text_input("股票名稱", placeholder="自動帶入或手動輸入", key="txn_stock_name")
    
    # 5. 交易類別
    input_action = st.selectbox("交易類別", ['買進', '賣出', '現金股利', '股票股利'], key="txn_action")
    
    col3, col4 = st.columns(2)
    
    # 6. 股數
    input_qty = col3.number_input("股數", min_value=0, step=1000, key="txn_qty")
    
    # 7. 單價
    input_price = col4.number_input("單價", min_value=0.0, step=0.5, format="%.2f", key="txn_price")
    
    input_notes = st.text_area("備註", placeholder="選填", key="txn_notes")
    
    # --- C. 送出按鈕 ---
    if st.button("💾 提交交易"):
        # --- 資料驗證 (Validation) ---
        error_msgs = []
        if not input_account: error_msgs.append("❌ 請輸入「交易帳戶」")
        if not input_stock_id: error_msgs.append("❌ 請輸入「股票代號」")
        if not input_stock_name: error_msgs.append("❌ 未輸入「股票名稱」")
        
        # 針對數值做邏輯檢查
        # 若是現金股利，有時可能只記錄金額而不記錄股數變動，故放寬限制
        if input_action != '現金股利' and input_qty <= 0: 
            error_msgs.append("❌ 「股數」必須大於 0")
            
        # 買進賣出必須有價格，股票股利成本為0
        if input_action in ['買進', '賣出'] and input_price <= 0: 
            error_msgs.append("❌ 「單價」必須大於 0")

        # --- 顯示錯誤或執行寫入 ---
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
                
                # --- D. 清空輸入欄位 ---
                # 將 Session State 重設為空值
                st.session_state["txn_stock_id"] = ""
                st.session_state["txn_stock_name"] = ""
                st.session_state["txn_qty"] = 0
                st.session_state["txn_price"] = 0.0
                st.session_state["txn_notes"] = ""
                # 日期與帳戶保留，方便連續記帳
                
                # 強制 Rerun 讓畫面更新回空白狀態
                st.rerun()
                
            except Exception as e:
                st.error(f"寫入失敗: {e}")

# --- 2. 主畫面：顯示區 ---
tab1, tab2 = st.tabs(["📊 資產庫存 (FIFO)", "📋 原始交易紀錄"])

try:
    # 從 Database 載入資料
    df_raw = database.load_data()

    with tab1:
        st.subheader("庫存損益試算 (FIFO)")
        if not df_raw.empty:
            # 呼叫 Logic 層進行運算 (包含名稱處理)
            df_fifo = logic.calculate_fifo_report(df_raw)
            
            if not df_fifo.empty:
                total_cost = df_fifo['總持有成本 (FIFO)'].sum()
                st.metric("目前總持有成本 (FIFO)", f"${total_cost:,.0f}")
                
                # 調整顯示欄位順序
                cols_order = ['股票代號', '股票名稱', '庫存股數', '平均成本', '總持有成本 (FIFO)']
                # 確保欄位存在才排序
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
            # 依照日期降序排列 (最新的在上面)
            df_display = df_display.sort_values(by='交易日期', ascending=False)
            st.dataframe(df_display)
        else:
            st.write("無資料")

except Exception as e:
    st.error(f"系統發生錯誤: {e}")
