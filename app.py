import streamlit as st
import pandas as pd
from datetime import date, datetime

import database
import logic
import market_data

st.set_page_config(page_title="股票資產管理", layout="wide")
st.title('📊 股票資產管理系統 (Streamlit Cloud)')

# --- 預先讀取 ---
try:
    stock_map = database.get_stock_info_map()
except:
    stock_map = {}

try:
    account_settings = database.get_account_settings()
    account_list = list(account_settings.keys())
except:
    account_settings = {"預設帳戶": 0.6}
    account_list = ["預設帳戶"]

# --- Session State 初始化 ---
if "txn_date" not in st.session_state: st.session_state["txn_date"] = date.today()

if "txn_account" not in st.session_state: 
    st.session_state["txn_account"] = account_list[0] if account_list else ""
if st.session_state["txn_account"] not in account_list:
     st.session_state["txn_account"] = account_list[0] if account_list else ""

if "txn_stock_id" not in st.session_state: st.session_state["txn_stock_id"] = ""
if "txn_stock_name" not in st.session_state: st.session_state["txn_stock_name"] = ""
if "txn_qty" not in st.session_state: st.session_state["txn_qty"] = 0
if "txn_price" not in st.session_state: st.session_state["txn_price"] = 0.0
if "txn_notes" not in st.session_state: st.session_state["txn_notes"] = ""
if "form_msg" not in st.session_state: st.session_state["form_msg"] = None 

if "realtime_prices" not in st.session_state: st.session_state["realtime_prices"] = {}
if "price_update_time" not in st.session_state: st.session_state["price_update_time"] = None

# --- 新增交易 Callback ---
def submit_callback():
    s_date = st.session_state.txn_date
    s_account = st.session_state.txn_account
    s_id = st.session_state.txn_stock_id
    s_name = st.session_state.txn_stock_name
    s_action = st.session_state.txn_action
    s_qty = st.session_state.txn_qty
    s_price = st.session_state.txn_price
    s_notes = st.session_state.txn_notes
    
    s_discount = account_settings.get(s_account, 0.6)

    error_msgs = []
    if not s_account: error_msgs.append("❌ 請選擇「交易帳戶」")
    
    is_cash_flow = s_action in ['入金', '出金']
    
    if not is_cash_flow:
        if not s_id: error_msgs.append("❌ 請輸入「股票代號」")
        if not s_name: error_msgs.append("❌ 未輸入「股票名稱」")
    
    if s_action != '現金股利' and s_qty <= 0: 
        error_msgs.append("❌ 「股數/數量」必須大於 0")
    if s_action in ['買進', '賣出', '入金', '出金'] and s_price <= 0: 
        error_msgs.append("❌ 「單價/金額」必須大於 0")

    if error_msgs:
        st.session_state["form_msg"] = {"type": "error", "content": error_msgs}
    else:
        try:
            database.save_transaction(s_date, s_id, s_name, s_action, s_qty, s_price, s_account, s_notes, s_discount)
            
            st.session_state.txn_stock_id = ""
            st.session_state.txn_stock_name = ""
            st.session_state.txn_qty = 0
            st.session_state.txn_price = 0.0
            st.session_state.txn_notes = ""
            
            if is_cash_flow:
                amount = int(s_qty * s_price)
                st.session_state["form_msg"] = {"type": "success", "content": f"✅ 成功記錄：{s_action} ${amount:,} (帳戶: {s_account})"}
            else:
                st.session_state["form_msg"] = {"type": "success", "content": f"✅ 成功新增：{s_name} ({s_id}) {s_action} (折數: {s_discount})"}
                
        except Exception as e:
            st.session_state["form_msg"] = {"type": "error", "content": [f"寫入失敗: {e}"]}

# ============================
# Sidebar 側邊欄
# ============================
with st.sidebar:
    
    # --- 功能頁籤：新增交易 vs 餘額校正 ---
    mode = st.radio("功能選擇", ["📝 新增交易", "🔧 帳戶餘額校正"], horizontal=True)
    
    if mode == "📝 新增交易":
        st.header("📝 新增交易")
        col1, col2 = st.columns(2)
        col1.date_input("交易日期", key="txn_date")
        col2.selectbox("交易帳戶", options=account_list, key="txn_account")
        
        input_action = st.selectbox("交易類別", ['買進', '賣出', '現金股利', '股票股利', '入金', '出金'], key="txn_action")
        is_cash_op = input_action in ['入金', '出金']

        if is_cash_op:
            st.info("💡 資金操作模式：請在「單價」欄位輸入金額，股票代號可留空。")
            input_stock_id = st.text_input("股票代號", placeholder="(可留空)", key="txn_stock_id", disabled=False)
        else:
            input_stock_id = st.text_input("股票代號", placeholder="例如 2330", key="txn_stock_id")
            if input_stock_id:
                clean_id = str(input_stock_id).strip()
                found_name = stock_map.get(clean_id, "")
                if found_name and st.session_state["txn_stock_name"] != found_name:
                    st.session_state["txn_stock_name"] = found_name
                    st.rerun()

        col2 = st.empty()
        if is_cash_op:
            st.text_input("股票名稱", placeholder="(可留空)", key="txn_stock_name")
        else:
            st.text_input("股票名稱", placeholder="自動帶入或手動輸入", key="txn_stock_name")

        col3, col4 = st.columns(2)
        qty_label = "數量 (預設1)" if is_cash_op else "股數"
        price_label = "金額" if is_cash_op else "單價"
        
        if is_cash_op and st.session_state["txn_qty"] == 0:
            st.session_state["txn_qty"] = 1

        col3.number_input(qty_label, min_value=0, step=1000, key="txn_qty")
        col4.number_input(price_label, min_value=0.0, step=0.5, format="%.2f", key="txn_price")
        
        st.text_area("備註", placeholder="選填", key="txn_notes")
        st.button("💾 提交交易", on_click=submit_callback)
        
    # --- 餘額校正模式 ---
    else:
        st.header("🔧 帳戶餘額校正")
        st.info("此功能會自動計算差額，並產生一筆「入金」或「出金」將系統餘額強制調整為實際餘額。")
        
        # 1. 選擇帳戶
        adj_account = st.selectbox("選擇校正帳戶", options=account_list)
        
        # 2. 取得系統目前餘額 (需即時計算)
        # 這裡需要讀取資料，可能會有一點點延遲
        try:
            df_temp = database.load_data()
            balances = logic.calculate_account_balances(df_temp)
            current_sys_bal = int(balances.get(adj_account, 0))
        except:
            current_sys_bal = 0
            
        st.metric("💻 系統目前帳面餘額", f"${current_sys_bal:,}")
        
        # 3. 輸入實際餘額
        actual_bal = st.number_input("💰 輸入實際餘額", value=current_sys_bal, step=1000)
        
        # 4. 計算差額
        diff = actual_bal - current_sys_bal
        
        if diff == 0:
            st.success("✅ 帳目吻合，無需校正。")
        else:
            if diff > 0:
                st.warning(f"系統少記了 ${diff:,} (需補入)")
                action_type = "入金"
            else:
                st.warning(f"系統多記了 ${abs(diff):,} (需扣除)")
                action_type = "出金"
                
            # 5. 執行校正按鈕
            if st.button("⚡ 執行強制校正"):
                try:
                    # 自動生成備註
                    note = f"餘額校正: 系統(${current_sys_bal:,}) -> 實際(${actual_bal:,})"
                    
                    # 寫入資料庫 (使用 database.save_transaction)
                    # 股數/數量填 1，價格填差額的絕對值
                    database.save_transaction(
                        date.today(), 
                        "", # 股票代號
                        "", # 股票名稱
                        action_type, 
                        1, # 數量
                        abs(diff), # 金額
                        adj_account, 
                        note,
                        0.6 # 折數無所謂
                    )
                    st.success(f"已新增校正紀錄：{action_type} ${abs(diff):,}")
                    st.rerun()
                except Exception as e:
                    st.error(f"校正失敗: {e}")

    # 顯示成功/失敗訊息 (共用)
    if st.session_state["form_msg"]:
        msg = st.session_state["form_msg"]
        if msg["type"] == "success": st.success(msg["content"])
        elif msg["type"] == "error": 
            for err in msg["content"]: st.error(err)


# ============================
# Main Content 主畫面
# ============================
tab1, tab2 = st.tabs(["📊 資產庫存 (FIFO)", "📋 原始交易紀錄"])

try:
    df_raw = database.load_data()

    with tab1:
        st.subheader("庫存損益試算 (FIFO)")
        
        col_btn, col_time = st.columns([1.5, 4])
        
        if col_btn.button("🔄 更新即時股價 (Fugle API)"):
             if not df_raw.empty:
                temp_fifo = logic.calculate_fifo_report(df_raw)
                if not temp_fifo.empty:
                    stock_ids = temp_fifo['股票代號'].unique().tolist()
                    prices = market_data.get_realtime_prices(stock_ids)
                    st.session_state["realtime_prices"] = prices
                    st.session_state["price_update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.rerun()
        
        if st.session_state["price_update_time"]:
            col_time.write(f"🕒 最後更新: **{st.session_state['price_update_time']}**")
        else:
            col_time.write("🕒 尚未更新股價 (顯示為庫存成本)")

        if not df_raw.empty:
            # 顯示帳戶餘額概況 (新增功能)
            st.markdown("#### 💰 各帳戶現金餘額")
            acc_balances = logic.calculate_account_balances(df_raw)
            # 使用 columns 顯示多個帳戶
            b_cols = st.columns(len(acc_balances) if acc_balances else 1)
            for idx, (acc, bal) in enumerate(acc_balances.items()):
                if idx < len(b_cols):
                    b_cols[idx].metric(acc, f"${int(bal):,}")

            st.divider()

            df_fifo = logic.calculate_fifo_report(df_raw)
            
            if not df_fifo.empty:
                current_prices = st.session_state.get("realtime_prices", {})
                df_final = logic.calculate_unrealized_pnl(df_fifo, current_prices)
                
                total_cost = df_final['總持有成本 (FIFO)'].sum()
                total_market_value = df_final['股票市值'].sum()
                total_pnl = df_final['未實現損益'].sum()
                total_return = (total_pnl / total_cost * 100) if total_cost != 0 else 0
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("總持有成本", f"${total_cost:,.0f}")
                m2.metric("總股票市值", f"${total_market_value:,.0f}")
                m3.metric("未實現損益", f"${total_pnl:,.0f}", delta=f"{total_return:.2f}%")
                
                def color_pnl(val):
                    if isinstance(val, (int, float)):
                        color = 'red' if val > 0 else 'green' if val < 0 else 'black'
                        return f'color: {color}'
                    return ''

                display_cols = [
                    '股票', '庫存股數', '平均成本', 
                    '目前市價', '股票市值', '未實現損益', '報酬率 (%)',
                    '佔總資產比例 (%)', '賣出額外費用', '配息金額'
                ]
                
                format_dict = {
                    "庫存股數": "{:,.0f}",
                    "平均成本": "{:,.2f}",
                    "目前市價": "{:,.2f}",
                    "股票市值": "{:,.0f}",
                    "未實現損益": "{:,.0f}",
                    "報酬率 (%)": "{:,.2f}%",
                    "佔總資產比例 (%)": "{:,.2f}%",
                    "配息金額": "{:,.0f}"
                }

                st.dataframe(
                    df_final[display_cols].style
                    .format(format_dict)
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
