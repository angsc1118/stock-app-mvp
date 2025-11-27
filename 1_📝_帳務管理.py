# ==============================================================================
# 檔案名稱: pages/1_📝_帳務管理.py
# 
# 修改歷程:
# 2025-11-27 14:00:00: [Refactor] 拆分頁面：移除績效分析功能 (移至獨立頁面)
# 2025-11-27 13:30:00: [UI] 修正 UI/UX 規範 (紅漲綠跌、千分位)
# ==============================================================================

import streamlit as st
import pandas as pd
from datetime import date

import database
import logic

# 設定頁面
st.set_page_config(page_title="帳務管理", layout="wide", page_icon="📝")
st.title("📝 帳務管理中心")

# ==============================================================================
# 1. 資料讀取與初始化
# ==============================================================================

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

# Session State (Form 相關)
if "txn_date" not in st.session_state: st.session_state["txn_date"] = date.today()
if "txn_account" not in st.session_state: st.session_state["txn_account"] = account_list[0] if account_list else ""
if st.session_state["txn_account"] not in account_list: st.session_state["txn_account"] = account_list[0] if account_list else ""
if "txn_stock_id" not in st.session_state: st.session_state["txn_stock_id"] = ""
if "txn_stock_name" not in st.session_state: st.session_state["txn_stock_name"] = ""
if "txn_qty" not in st.session_state: st.session_state["txn_qty"] = 0
if "txn_price" not in st.session_state: st.session_state["txn_price"] = 0.0
if "txn_notes" not in st.session_state: st.session_state["txn_notes"] = ""
if "form_msg" not in st.session_state: st.session_state["form_msg"] = None 

# Callback for Submit
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
    if s_action != '現金股利' and s_qty <= 0: error_msgs.append("❌ 「股數/數量」必須大於 0")
    if s_action in ['買進', '賣出', '入金', '出金'] and s_price <= 0: error_msgs.append("❌ 「單價/金額」必須大於 0")

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
            
            # 使用 toast 取代 msg
            if is_cash_flow:
                amount = int(s_qty * s_price)
                st.toast(f"✅ 成功記錄：{s_action} ${amount:,} (帳戶: {s_account})", icon="💾")
            else:
                st.toast(f"✅ 成功新增：{s_name} ({s_id}) {s_action}", icon="💾")
            
            st.session_state["form_msg"] = None # 清除錯誤狀態
            
        except Exception as e:
            st.session_state["form_msg"] = {"type": "error", "content": [f"寫入失敗: {e}"]}

# ==============================================================================
# 2. 側邊欄：操作區
# ==============================================================================
try:
    df_raw = database.load_data()
except:
    df_raw = pd.DataFrame()

with st.sidebar:
    st.header("🛠️ 帳務操作")
    
    mode = st.radio("選擇功能", ["📝 新增交易", "🔧 帳戶餘額校正"], horizontal=True)
    
    if mode == "📝 新增交易":
        st.date_input("交易日期", key="txn_date")
        st.selectbox("交易帳戶", options=account_list, key="txn_account")
        input_action = st.selectbox("交易類別", ['買進', '賣出', '現金股利', '股票股利', '入金', '出金'], key="txn_action")
        is_cash_op = input_action in ['入金', '出金']

        if is_cash_op:
            st.info("💡 資金操作：請輸入金額")
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
            st.text_input("股票名稱", placeholder="自動帶入", key="txn_stock_name")

        col3, col4 = st.columns(2)
        qty_label = "數量 (1)" if is_cash_op else "股數"
        price_label = "金額" if is_cash_op else "單價"
        if is_cash_op and st.session_state["txn_qty"] == 0: st.session_state["txn_qty"] = 1

        col3.number_input(qty_label, min_value=0, step=1000, key="txn_qty")
        col4.number_input(price_label, min_value=0.0, step=0.5, format="%.2f", key="txn_price")
        st.text_area("備註", placeholder="選填", key="txn_notes")
        st.button("💾 提交交易", on_click=submit_callback, use_container_width=True)
        
    else:
        st.info("自動計算差額並產生修正交易")
        adj_account = st.selectbox("選擇校正帳戶", options=account_list)
        try:
            if not df_raw.empty:
                balances = logic.calculate_account_balances(df_raw)
                current_sys_bal = int(balances.get(adj_account, 0))
            else:
                current_sys_bal = 0
        except:
            current_sys_bal = 0
        st.metric("💻 系統目前餘額", f"${current_sys_bal:,}")
        actual_bal = st.number_input("💰 輸入實際餘額", value=current_sys_bal, step=1000)
        diff = actual_bal - current_sys_bal
        if diff == 0:
            st.success("✅ 帳目吻合")
        else:
            if diff > 0: st.warning(f"少記 ${diff:,} (補入)")
            else: st.warning(f"多記 ${abs(diff):,} (扣除)")
            if st.button("⚡ 執行強制校正", use_container_width=True):
                try:
                    note = f"餘額校正: 系統(${current_sys_bal:,}) -> 實際(${actual_bal:,})"
                    action_type = "入金" if diff > 0 else "出金"
                    database.save_transaction(date.today(), "", "", action_type, 1, abs(diff), adj_account, note, 0.6)
                    st.toast(f"✅ 已校正：{action_type} ${abs(diff):,}", icon="⚡")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"校正失敗: {e}")

    if st.session_state["form_msg"]:
        msg = st.session_state["form_msg"]
        if msg["type"] == "error": 
            for err in msg["content"]: st.error(err)

# ==============================================================================
# 3. 主畫面：分頁檢視 (僅庫存與流水帳)
# ==============================================================================

# 定義樣式函數
def style_tw_stock_profit_loss(val):
    if not isinstance(val, (int, float)): return ''
    if val > 0: return 'color: #E53935' # 紅漲
    elif val < 0: return 'color: #26a69a' # 綠跌
    return ''

def highlight_severe_loss(val):
    if not isinstance(val, (int, float)): return ''
    if val < -20: return 'background-color: #E8F5E9; color: #2e7d32; font-weight: bold;'
    elif val < 0: return 'color: #26a69a'
    elif val > 0: return 'color: #E53935'
    return ''

tab1, tab2 = st.tabs(["📋 持股庫存 (Overview)", "📂 交易流水帳 (Database)"])

# --- Tab 1: 持股庫存 ---
with tab1:
    if not df_raw.empty:
        df_fifo = logic.calculate_fifo_report(df_raw)
        current_prices = st.session_state.get("realtime_prices", {})
        ta_data = st.session_state.get("ta_data", {})
        df_unrealized = logic.calculate_unrealized_pnl(df_fifo, current_prices)
        
        if not df_unrealized.empty:
            # 技術指標 (如果 Session 有資料)
            df_unrealized['技術訊號'] = df_unrealized['股票代號'].map(lambda x: ta_data.get(x, {}).get('Signal', '-'))
            df_unrealized['月線(20MA)'] = df_unrealized['股票代號'].map(lambda x: ta_data.get(x, {}).get('MA20', 0))

            display_cols = ['股票', '庫存股數', '平均成本', '目前市價', '月線(20MA)', '技術訊號', '股票市值', '未實現損益', '報酬率 (%)', '佔總資產比例 (%)']
            final_cols = [c for c in display_cols if c in df_unrealized.columns]

            format_dict = {
                "庫存股數": "{:,.0f}", "平均成本": "{:,.2f}", "目前市價": "{:,.2f}",
                "月線(20MA)": "{:,.2f}", "股票市值": "{:,.0f}", "未實現損益": "{:,.0f}", 
                "報酬率 (%)": "{:,.2f}%", "佔總資產比例 (%)": "{:,.2f}%"
            }
            
            st_df = df_unrealized[final_cols].style\
                .format(format_dict)\
                .map(style_tw_stock_profit_loss, subset=['未實現損益'])\
                .map(highlight_severe_loss, subset=['報酬率 (%)'])
                
            st.dataframe(st_df, use_container_width=True, height=600)
            st.caption("💡 提示：如需查看已實現損益分析，請前往左側「📊 績效分析」頁面。")
        else:
            st.info("目前沒有庫存。")
    else:
        st.warning("無交易紀錄。")

# --- Tab 2: 原始資料庫 ---
with tab2:
    if not df_raw.empty:
        st.subheader("📋 交易原始紀錄")
        df_display = df_raw.copy()
        df_display['交易日期'] = pd.to_datetime(df_display['交易日期']).dt.date
        
        st.dataframe(
            df_display.sort_values('交易日期', ascending=False),
            column_config={
                "交易日期": st.column_config.DateColumn("交易日期", format="YYYY-MM-DD"),
                "股數": st.column_config.NumberColumn("股數", format="%d"),
                "單價": st.column_config.NumberColumn("單價", format="$%.2f"),
                "手續費": st.column_config.NumberColumn("手續費", format="$%d"),
                "交易稅": st.column_config.NumberColumn("交易稅", format="$%d"),
                "成交總金額": st.column_config.NumberColumn("成交總金額", format="$%d"),
                "淨收付金額": st.column_config.NumberColumn("淨收付金額", format="$%d"),
            },
            use_container_width=True,
            hide_index=True
        )
