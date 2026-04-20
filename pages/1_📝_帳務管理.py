# ==============================================================================
# 檔案名稱: pages/1_📝_帳務管理.py
# 
# 修改歷程:
# 2025-12-11 13:30:00: [Feat] 第三階段：交易輸入整合 (支援還款 + 目標選擇)
# 2025-12-11 11:45:00: [Fix] 修正 Session State 修改錯誤
# ==============================================================================

import streamlit as st
import pandas as pd
from datetime import date
import time

import database
import logic
import utils

# 設定頁面
st.set_page_config(page_title="帳務管理", layout="wide", page_icon="📝")
st.title("📝 帳務管理中心")

# ==============================================================================
# 1. 資料讀取與初始化
# ==============================================================================

try:
    df_raw = database.load_data()
except:
    df_raw = pd.DataFrame()

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

# [New] 預先讀取目標設定 (供還款選單使用)
try:
    df_goals = database.load_goals()
    goal_list = df_goals['目標名稱'].unique().tolist() if not df_goals.empty else []
except:
    goal_list = []

# 初始化 Session State
if "txn_date" not in st.session_state: st.session_state["txn_date"] = date.today()
if "txn_account" not in st.session_state: st.session_state["txn_account"] = account_list[0] if account_list else ""
if st.session_state["txn_account"] not in account_list: st.session_state["txn_account"] = account_list[0] if account_list else ""
if "txn_stock_id" not in st.session_state: st.session_state["txn_stock_id"] = ""
if "txn_stock_name" not in st.session_state: st.session_state["txn_stock_name"] = ""
if "txn_qty" not in st.session_state: st.session_state["txn_qty"] = 0
if "txn_price" not in st.session_state: st.session_state["txn_price"] = 0.0
if "txn_notes" not in st.session_state: st.session_state["txn_notes"] = ""
default_notes_template = """進場理由: 
                                        出場理由: 
                                        損益結果: 
                                        當下心情: 
                                        下次改進方式: """
# --- 呼叫全域狀態列 ---
utils.render_sidebar_status()

# ==============================================================================
# 2. 側邊欄邏輯
# ==============================================================================

def submit_callback():
    s_date = st.session_state.txn_date
    s_account = st.session_state.txn_account
    s_action = st.session_state.get("_temp_action", "買進") 
    s_id = st.session_state.txn_stock_id
    s_name = st.session_state.txn_stock_name
    s_qty = st.session_state.txn_qty
    s_price = st.session_state.txn_price
    s_notes = st.session_state.txn_notes
    s_discount = account_settings.get(s_account, 0.6)

    error_msgs = []
    if not s_account: error_msgs.append("❌ 請選擇「交易帳戶」")
    
    # [Logic Update] 資金操作類別增加 '還款'
    is_cash_flow = s_action in ['入金', '出金', '還款']
    
    if not is_cash_flow:
        if not s_id: error_msgs.append("❌ 請輸入「股票代號」")
        if not s_name: error_msgs.append("❌ 請輸入「股票名稱」")
    elif s_action == '還款' and not s_name:
        # [New] 若是還款，必須有目標名稱
        error_msgs.append("❌ 請選擇「還款目標」")
    
    if s_action != '現金股利' and s_qty <= 0: error_msgs.append("❌ 「股數/數量」必須大於 0")
    
    # 金額檢查
    if s_action in ['買進', '賣出', '入金', '出金', '還款'] and s_price <= 0:
        error_msgs.append("❌ 「單價/金額」必須大於 0")

    if error_msgs:
        st.session_state["_form_errors"] = error_msgs
    else:
        try:
            database.save_transaction(s_date, s_id, s_name, s_action, s_qty, s_price, s_account, s_notes, s_discount)
            
            st.session_state.txn_stock_id = ""
            st.session_state.txn_stock_name = ""
            st.session_state.txn_qty = 0
            st.session_state.txn_price = 0.0
            st.session_state.txn_notes = ""
            st.session_state["_form_errors"] = []
            
            if is_cash_flow:
                amount = int(s_qty * s_price)
                st.toast(f"✅ 成功記錄：{s_action} ${amount:,} (帳戶: {s_account})", icon="💾")
            else:
                st.toast(f"✅ 成功新增：{s_name} ({s_id}) {s_action}", icon="💾")
            
        except Exception as e:
            st.session_state["_form_errors"] = [f"寫入失敗: {e}"]

# --- 側邊欄 UI ---
with st.sidebar:
    if "_form_errors" in st.session_state and st.session_state["_form_errors"]:
        for err in st.session_state["_form_errors"]: st.error(err)
        st.session_state["_form_errors"] = []

    page_mode = st.radio("🛠️ 操作模式", ["🔍 瀏覽查詢", "📝 新增交易"], horizontal=True)
    st.markdown("---")

    if page_mode == "🔍 瀏覽查詢":
        st.subheader("🔍 篩選條件")
        filter_keyword = st.text_input("搜尋代號或名稱", placeholder="例如: 2330 或 台積電")
        st.info("💡 在此模式下，右側表格會即時過濾顯示結果。")
        
    else:
        st.subheader("📝 新增交易")
        
        st.date_input("日期", key="txn_date")
        st.selectbox("帳戶", options=account_list, key="txn_account")
        
        txn_category = st.radio("類別", ["📈 股票買賣", "💸 資金存提", "🎁 股利/其他"], horizontal=True)
        st.write("") 

        if txn_category == "📈 股票買賣":
            action = st.selectbox("動作", ["買進", "賣出"], key="_ui_action_stock")
            st.session_state["_temp_action"] = action
            
            stock_id_input = st.text_input("代號", key="txn_stock_id", placeholder="2330")
            if stock_id_input:
                clean_id = str(stock_id_input).strip()
                found_name = stock_map.get(clean_id, "")
                if found_name and st.session_state.txn_stock_name != found_name:
                    st.session_state.txn_stock_name = found_name
                    st.rerun()
            st.text_input("名稱", key="txn_stock_name", placeholder="自動帶入")
            st.number_input("股數", min_value=0, step=1000, key="txn_qty")
            st.number_input("單價", min_value=0.0, step=0.5, format="%.2f", key="txn_price")
            
        elif txn_category == "💸 資金存提":
            # [UI Update] 增加「還款」選項
            action = st.selectbox("動作", ["入金", "出金", "還款"], key="_ui_action_cash")
            st.session_state["_temp_action"] = action
            
            if action == "還款":
                # [New] 還款目標選擇
                if goal_list:
                    target_goal = st.selectbox("🎯 選擇還款目標", goal_list)
                    # 自動將目標名稱綁定到 stock_name 欄位
                    st.session_state.txn_stock_name = target_goal
                    
                    st.caption(f"💡 金額將計入「{target_goal}」的進度條")
                else:
                    st.warning("⚠️ 尚無進行中的目標。請先至 Google Sheet 建立目標。")
                    st.text_input("或手動輸入名稱", key="txn_stock_name")
            else:
                # 一般出入金，清空名稱以免誤導
                st.session_state.txn_stock_name = ""
            
            st.number_input("金額 ($)", min_value=0.0, step=1000.0, format="%.2f", key="txn_price")
            
            if st.session_state.txn_qty == 0: st.session_state.txn_qty = 1
            st.session_state.txn_qty = 1 
            
            if action != "還款":
                with st.expander("🔧 餘額校正工具"):
                    try:
                        if not df_raw.empty:
                            balances = logic.calculate_account_balances(df_raw)
                            sys_bal = int(balances.get(st.session_state.txn_account, 0))
                        else: sys_bal = 0
                    except: sys_bal = 0
                    st.caption(f"系統餘額: ${sys_bal:,}")
                    real_bal = st.number_input("實際餘額", value=sys_bal, step=1000)
                    diff = real_bal - sys_bal
                    if diff != 0:
                        if st.button("⚡ 自動填入差額"):
                            st.session_state["_temp_action"] = "入金" if diff > 0 else "出金"
                            st.session_state.txn_price = float(abs(diff))
                            st.session_state.txn_qty = 1
                            st.session_state.txn_notes = f"餘額校正: 系統({sys_bal})->實際({real_bal})"
                            st.rerun()
                    else: st.caption("✅ 帳目吻合")

        elif txn_category == "🎁 股利/其他":
            action = st.selectbox("動作", ["現金股利", "股票股利", "現金增資"], key="_ui_action_div")
            st.session_state["_temp_action"] = action
            
            stock_id_input = st.text_input("代號", key="txn_stock_id")
            if stock_id_input:
                clean_id = str(stock_id_input).strip()
                found_name = stock_map.get(clean_id, "")
                if found_name and st.session_state.txn_stock_name != found_name:
                    st.session_state.txn_stock_name = found_name
                    st.rerun()
            st.text_input("名稱", key="txn_stock_name")
            
            if action == "現金股利":
                st.number_input("除息時持有股數 (參考用)", min_value=0, step=1000, key="txn_qty")
                st.number_input("股利總金額 ($)", min_value=0.0, step=100.0, format="%.2f", key="txn_price")
            else:
                st.number_input("股數", min_value=0, step=1000, key="txn_qty")
                st.number_input("單價/成本", min_value=0.0, step=0.5, format="%.2f", key="txn_price")
            with st.expander("📝 交易心得與備註 (必填)", expanded=True):
                # 如果 txn_notes 目前是空的，就帶入預設模板
                if not st.session_state.txn_notes:
                    st.session_state.txn_notes = default_notes_template
        
                    st.text_area("內容", key="txn_notes", height=180)
            
        st.button("💾 提交交易", type="primary", use_container_width=True, on_click=submit_callback)

# ==============================================================================
# 3. 主畫面邏輯
# ==============================================================================

def style_tw_stock_profit_loss(val):
    if not isinstance(val, (int, float)): return ''
    if val > 0: return 'color: #E53935' 
    elif val < 0: return 'color: #26a69a' 
    return ''

def highlight_severe_loss(val):
    if not isinstance(val, (int, float)): return ''
    if val < -20: return 'background-color: #E8F5E9; color: #2e7d32; font-weight: bold;'
    elif val < 0: return 'color: #26a69a'
    elif val > 0: return 'color: #E53935'
    return ''

df_inventory_display = pd.DataFrame()
df_ledger_display = df_raw.copy()

if not df_raw.empty:
    df_fifo = logic.calculate_fifo_report(df_raw)
    current_prices = st.session_state.get("realtime_prices", {})
    ta_data = st.session_state.get("ta_data", {})
    df_unrealized = logic.calculate_unrealized_pnl(df_fifo, current_prices)
    
    if not df_unrealized.empty:
        df_unrealized['技術訊號'] = df_unrealized['股票代號'].map(lambda x: ta_data.get(x, {}).get('Signal', '-'))
        df_unrealized['月線(20MA)'] = df_unrealized['股票代號'].map(lambda x: ta_data.get(x, {}).get('MA20', 0))
        df_inventory_display = df_unrealized

filter_txt = ""
if page_mode == "🔍 瀏覽查詢":
    if 'filter_keyword' in locals() and filter_keyword:
        filter_txt = filter_keyword.strip()
        
        if not df_inventory_display.empty:
            mask_inv = df_inventory_display['股票代號'].astype(str).str.contains(filter_txt, case=False) | \
                       df_inventory_display['股票名稱'].str.contains(filter_txt, case=False)
            df_inventory_display = df_inventory_display[mask_inv]
            
        if not df_ledger_display.empty:
            mask_leg = df_ledger_display['股票代號'].astype(str).str.contains(filter_txt, case=False) | \
                       df_ledger_display['股票名稱'].str.contains(filter_txt, case=False)
            df_ledger_display = df_ledger_display[mask_leg]

# ==============================================================================
# 4. 畫面渲染
# ==============================================================================

tab1, tab2 = st.tabs(["📋 持股庫存 (Overview)", "📂 交易流水帳 (Database)"])

with tab1:
    if not df_inventory_display.empty:
        if not filter_txt: 
            loss_threshold = -20.0
            danger_stocks = df_inventory_display[df_inventory_display['報酬率 (%)'] < loss_threshold].copy()
            if not danger_stocks.empty:
                count = len(danger_stocks)
                with st.expander(f"📉 警示：共 {count} 檔庫存虧損超過 {abs(loss_threshold)}% (點擊展開查看)", expanded=False):
                    st.dataframe(
                        danger_stocks[['股票', '庫存股數', '平均成本', '目前市價', '報酬率 (%)']],
                        column_config={
                            "庫存股數": st.column_config.NumberColumn(format="%d"),
                            "平均成本": st.column_config.NumberColumn(format="%.2f"),
                            "目前市價": st.column_config.NumberColumn(format="%.2f"),
                            "報酬率 (%)": st.column_config.NumberColumn(format="%.2f%%"),
                        },
                        use_container_width=True,
                        hide_index=True
                    )

        display_cols = ['股票', '庫存股數', '平均成本', '目前市價', '月線(20MA)', '技術訊號', '股票市值', '未實現損益', '報酬率 (%)', '佔總資產比例 (%)']
        final_cols = [c for c in display_cols if c in df_inventory_display.columns]

        format_dict = {
            "庫存股數": "{:,.0f}", "平均成本": "{:,.2f}", "目前市價": "{:,.2f}",
            "月線(20MA)": "{:,.2f}", "股票市值": "{:,.0f}", "未實現損益": "{:,.0f}", 
            "報酬率 (%)": "{:,.2f}%", "佔總資產比例 (%)": "{:,.2f}%"
        }
        
        st_df = df_inventory_display[final_cols].style\
            .format(format_dict)\
            .map(style_tw_stock_profit_loss, subset=['未實現損益'])\
            .map(highlight_severe_loss, subset=['報酬率 (%)'])
            
        st.dataframe(st_df, use_container_width=True, height=600)
        
        if filter_txt:
            st.caption(f"🔍 已篩選關鍵字: 「{filter_txt}」")
    else:
        if filter_txt:
            st.info(f"查無符合「{filter_txt}」的庫存。")
        else:
            st.info("目前沒有庫存。")

with tab2:
    if not df_ledger_display.empty:
        if not filter_txt:
            st.subheader("📋 交易原始紀錄 (全部)")
        else:
            st.subheader(f"📋 交易原始紀錄 (篩選: {filter_txt})")
            
        df_display = df_ledger_display.copy()
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
    else:
        st.info("無交易紀錄。")
