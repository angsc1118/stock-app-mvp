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
# 放在最外層，讓它只執行一次讀取
try:
    stock_map = database.get_stock_info_map()
except Exception as e:
    st.toast(f"⚠️ 無法讀取 INDEX 表: {e}")
    stock_map = {}

# --- 1. 側邊欄：輸入區 ---
with st.sidebar:
    st.header("📝 新增交易")
    
    # 使用 form 表單，避免輸入一個字就重跑一次
    with st.form("add_txn_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        # 日期 (維持預設今天，因日期必填)
        input_date = col1.date_input("交易日期", date.today())
        
        # 帳戶 (移除預設值，改用 placeholder 提示)
        input_account = col2.text_input("交易帳戶", placeholder="請輸入帳戶名稱")
        
        # 股票代號 (輸入後按 Enter 觸發重跑，才能查名稱)
        input_stock_id = col1.text_input("股票代號", placeholder="例如 2330")
        
        # --- 自動查詢邏輯 ---
        suggested_name = ""
        if input_stock_id:
            # 去除空白並轉字串
            clean_id = str(input_stock_id).strip()
            suggested_name = stock_map.get(clean_id, "")
        
        # 股票名稱 (如果有查到，自動帶入 value)
        input_stock_name = col2.text_input("股票名稱", value=suggested_name, placeholder="自動帶入或手動輸入")
        
        # 交易類別
        input_action = st.selectbox("交易類別", ['買進', '賣出', '現金股利', '股票股利'])
        
        col3, col4 = st.columns(2)
        
        # 股數 (預設為 0)
        input_qty = col3.number_input("股數", min_value=0, value=0, step=1000)
        
        # 單價 (預設為 0.0)
        input_price = col4.number_input("單價", min_value=0.0, value=0.0, step=0.5, format="%.2f")
        
        input_notes = st.text_area("備註", placeholder="選填")
        
        # 送出按鈕
        submitted = st.form_submit_button("💾 提交交易")
        
        # --- 送出後的邏輯 ---
        if submitted:
            # 1. 資料驗證 (Validation)
            error_msgs = []
            
            if not input_account:
                error_msgs.append("❌ 請輸入「交易帳戶」")
            if not input_stock_id:
                error_msgs.append("❌ 請輸入「股票代號」")
            if not input_stock_name:
                error_msgs.append("❌ 未輸入「股票名稱」，且代號查無對應資料")
            
            # 邏輯檢查：除了現金股利外，股數通常要 > 0
            # (視您的需求，若現金股利也需要紀錄持股數，則統一檢查 > 0)
            if input_qty <= 0:
                error_msgs.append("❌ 「股數」必須大於 0")
                
            # 邏輯檢查：買進賣出價格要 > 0，股票股利成本為 0 (允許價格0)
            if input_action in ['買進', '賣出'] and input_price <= 0:
                error_msgs.append("❌ 「單價」必須大於 0")

            # 2. 顯示錯誤或執行寫入
            if error_msgs:
                for msg in error_msgs:
                    st.error(msg)
            else:
                try:
                    database.save_transaction(
                        input_date, input_stock_id, input_stock_name, 
                        input_action, input_qty, input_price, 
                        input_account, input_notes
                    )
                    st.success(f"✅ 成功新增：{input_stock_name} ({input_stock_id}) {input_action}")
                    st.rerun() # 強制重新整理以顯示最新資料
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
            # 呼叫 Logic 層進行運算
            df_fifo = logic.calculate_fifo_report(df_raw)
            
            if not df_fifo.empty:
                # 計算總成本
                total_cost = df_fifo['總持有成本 (FIFO)'].sum()
                st.metric("目前總持有成本 (FIFO)", f"${total_cost:,.0f}")
                
                # 顯示表格
                st.dataframe(
                    df_fifo.style.format({
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
