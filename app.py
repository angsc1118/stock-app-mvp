import streamlit as st
import pandas as pd
from datetime import date

# 匯入自定義模組
import database
import logic
import market_data # 新增：匯入市場數據模組

# 頁面設定
st.set_page_config(page_title="股票資產管理", layout="wide")
st.title('📊 股票資產管理系統 (Streamlit Cloud)')

# ... (保留原本的 預先讀取資料 Try-Catch 區塊) ...
try:
    stock_map = database.get_stock_info_map()
except Exception as e:
    st.toast(f"⚠️ 無法讀取 INDEX 表: {e}")
    stock_map = {}

try:
    account_options = database.get_account_options()
except Exception as e:
    st.toast(f"⚠️ 無法讀取帳戶設定: {e}")
    account_options = ["預設帳戶"]

# ... (保留原本的 Session State 初始化區塊) ...
if "txn_date" not in st.session_state: st.session_state["txn_date"] = date.today()
if "txn_account" not in st.session_state: 
    st.session_state["txn_account"] = account_options[0] if account_options else ""
if st.session_state["txn_account"] not in account_options:
     st.session_state["txn_account"] = account_options[0] if account_options else ""
if "txn_stock_id" not in st.session_state: st.session_state["txn_stock_id"] = ""
if "txn_stock_name" not in st.session_state: st.session_state["txn_stock_name"] = ""
if "txn_qty" not in st.session_state: st.session_state["txn_qty"] = 0
if "txn_price" not in st.session_state: st.session_state["txn_price"] = 0.0
if "txn_notes" not in st.session_state: st.session_state["txn_notes"] = ""
if "form_msg" not in st.session_state: st.session_state["form_msg"] = None 

# ... (保留 submit_callback 函式) ...
def submit_callback():
    s_date = st.session_state.txn_date
    s_account = st.session_state.txn_account
    s_id = st.session_state.txn_stock_id
    s_name = st.session_state.txn_stock_name
    s_action = st.session_state.txn_action
    s_qty = st.session_state.txn_qty
    s_price = st.session_state.txn_price
    s_notes = st.session_state.txn_notes

    error_msgs = []
    if not s_account: error_msgs.append("❌ 請選擇「交易帳戶」")
    if not s_id: error_msgs.append("❌ 請輸入「股票代號」")
    if not s_name: error_msgs.append("❌ 未輸入「股票名稱」")
    if s_action != '現金股利' and s_qty <= 0: error_msgs.append("❌ 「股數」必須大於 0")
    if s_action in ['買進', '賣出'] and s_price <= 0: error_msgs.append("❌ 「單價」必須大於 0")

    if error_msgs:
        st.session_state["form_msg"] = {"type": "error", "content": error_msgs}
    else:
        try:
            database.save_transaction(s_date, s_id, s_name, s_action, s_qty, s_price, s_account, s_notes)
            st.session_state.txn_stock_id = ""
            st.session_state.txn_stock_name = ""
            st.session_state.txn_qty = 0
            st.session_state.txn_price = 0.0
            st.session_state.txn_notes = ""
            st.session_state["form_msg"] = {"type": "success", "content": f"✅ 成功新增：{s_name} ({s_id}) {s_action}"}
        except Exception as e:
            st.session_state["form_msg"] = {"type": "error", "content": [f"寫入失敗: {e}"]}

# ... (保留 側邊欄 Sidebar UI 區塊) ...
with st.sidebar:
    st.header("📝 新增交易")
    col1, col2 = st.columns(2)
    col1.date_input("交易日期", key="txn_date")
    col2.selectbox("交易帳戶", options=account_options, key="txn_account")
    input_stock_id = col1.text_input("股票代號", placeholder="例如 2330", key="txn_stock_id")
    
    if input_stock_id:
        clean_id = str(input_stock_id).strip()
        found_name = stock_map.get(clean_id, "")
        if found_name and st.session_state["txn_stock_name"] != found_name:
            st.session_state["txn_stock_name"] = found_name
            st.rerun()

    col2.text_input("股票名稱", placeholder="自動帶入或手動輸入", key="txn_stock_name")
    st.selectbox("交易類別", ['買進', '賣出', '現金股利', '股票股利'], key="txn_action")
    col3, col4 = st.columns(2)
    col3.number_input("股數", min_value=0, step=1000, key="txn_qty")
    col4.number_input("單價", min_value=0.0, step=0.5, format="%.2f", key="txn_price")
    st.text_area("備註", placeholder="選填", key="txn_notes")
    st.button("💾 提交交易", on_click=submit_callback)
    if st.session_state["form_msg"]:
        msg = st.session_state["form_msg"]
        if msg["type"] == "success": st.success(msg["content"])
        elif msg["type"] == "error": 
            for err in msg["content"]: st.error(err)


# --- 主畫面：顯示區 ---
tab1, tab2 = st.tabs(["📊 資產庫存 (FIFO)", "📋 原始交易紀錄"])

try:
    df_raw = database.load_data()

    with tab1:
        st.subheader("庫存損益試算 (FIFO)")
        
        # 更新即時股價按鈕
        if st.button("🔄 更新即時股價 (Fugle API)"):
            st.cache_data.clear() 
            st.rerun()

        if not df_raw.empty:
            # 1. 基礎 FIFO 計算
            df_fifo = logic.calculate_fifo_report(df_raw)
            
            if not df_fifo.empty:
                # 2. 取得庫存代號列表
                stock_ids = df_fifo['股票代號'].unique().tolist()
                
                # 3. 呼叫市場數據模組 (Real Logic)
                # 注意：這裡改用 market_data 模組
                price_map = market_data.get_realtime_prices(stock_ids)
                
                # 4. 結合 FIFO 與 市價 算出最終損益
                df_final = logic.calculate_unrealized_pnl(df_fifo, price_map)
                
                # --- 顯示區塊 ---
                
                # 總計指標
                total_cost = df_final['總持有成本 (FIFO)'].sum()
                total_market_value = df_final['股票市值'].sum()
                total_pnl = df_final['未實現損益'].sum()
                total_return = (total_pnl / total_cost * 100) if total_cost != 0 else 0
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("總持有成本", f"${total_cost:,.0f}")
                m2.metric("總股票市值", f"${total_market_value:,.0f}")
                m3.metric("未實現損益", f"${total_pnl:,.0f}", delta=f"{total_return:.2f}%")
                
                def color_pnl(val):
                    color = 'red' if val > 0 else 'green' if val < 0 else 'black'
                    return f'color: {color}'

                display_cols = [
                    '股票代號', '股票名稱', '庫存股數', '平均成本', 
                    '目前市價', '股票市值', '未實現損益', '報酬率 (%)'
                ]
                
                # 檢查是否有缺漏股價 (若 price_map 沒有該股票，目前市價會是 0)
                missing_prices = [sid for sid in stock_ids if sid not in price_map]
                if missing_prices:
                    st.warning(f"⚠️ 以下股票無法取得即時報價 (顯示為 0)：{', '.join(missing_prices)}")

                st.dataframe(
                    df_final[display_cols].style
                    .format({
                        "庫存股數": "{:,.0f}",
                        "平均成本": "{:,.2f}",
                        "目前市價": "{:,.2f}",
                        "股票市值": "{:,.0f}",
                        "未實現損益": "{:,.0f}",
                        "報酬率 (%)": "{:,.2f}%"
                    })
                    .map(color_pnl, subset=['未實現損益', '報酬率 (%)']), 
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
