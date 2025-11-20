# app.py
import streamlit as st
import pandas as pd
from datetime import date

# 匯入我們的模組
import database
import logic

# 頁面設定
st.set_page_config(page_title="股票資產管理", layout="wide")
st.title('📊 股票資產管理系統 (Streamlit Cloud)')

# --- 側邊欄：輸入區 ---
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
        
        if st.form_submit_button("💾 提交交易"):
            try:
                # UI 只負責傳遞參數給 Database，不負責運算
                database.save_transaction(
                    input_date, input_stock_id, input_stock_name, 
                    input_action, input_qty, input_price, 
                    input_account, input_notes
                )
                st.success(f"成功新增 {input_stock_name}！")
                st.rerun()
            except Exception as e:
                st.error(f"寫入失敗: {e}")

# --- 主畫面：顯示區 ---
tab1, tab2 = st.tabs(["📊 資產庫存 (FIFO)", "📋 原始交易紀錄"])

try:
    # 從 Database 拿資料
    df_raw = database.load_data()

    with tab1:
        st.subheader("庫存損益試算 (FIFO)")
        if not df_raw.empty:
            # 把原始資料丟給 Logic 去算 FIFO
            df_fifo = logic.calculate_fifo_report(df_raw)
            
            if not df_fifo.empty:
                total_cost = df_fifo['總持有成本 (FIFO)'].sum()
                st.metric("目前總持有成本 (FIFO)", f"${total_cost:,.0f}")
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
            st.warning("沒有交易紀錄。")

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
    st.error(f"系統錯誤: {e}")
