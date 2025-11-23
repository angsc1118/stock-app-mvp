# ==============================================================================
# 檔案名稱: pages/1_Account_Management.py
# 
# 修改歷程:
# 2025-11-23: [Update] 調整版面配置，將交易帳戶與交易日期分開顯示
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, datetime

import database
import logic
import market_data

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
            if is_cash_flow:
                amount = int(s_qty * s_price)
                st.session_state["form_msg"] = {"type": "success", "content": f"✅ 成功記錄：{s_action} ${amount:,} (帳戶: {s_account})"}
            else:
                st.session_state["form_msg"] = {"type": "success", "content": f"✅ 成功新增：{s_name} ({s_id}) {s_action} (折數: {s_discount})"}
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
    st.title("🛠️ 帳務操作")
    
    mode = st.radio("選擇功能", ["📝 新增交易", "🔧 帳戶餘額校正"], horizontal=True)
    
    if mode == "📝 新增交易":
        # [修改] 調整佈局：日期獨佔一行
        st.date_input("交易日期", key="txn_date")
        
        # [修改] 帳戶與類別放同一行 (或是獨佔一行也可，這裡示範獨佔一行更清楚)
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

        # 股票名稱欄位
        if is_cash_op:
            st.text_input("股票名稱", placeholder="(可留空)", key="txn_stock_name")
        else:
            st.text_input("股票名稱", placeholder="自動帶入", key="txn_stock_name")

        # 股數與價格並排
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
        # 校正模式下，帳戶選擇已經是獨佔一行，無需調整
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
                    st.success(f"已校正：{action_type} ${abs(diff):,}")
                    st.rerun()
                except Exception as e:
                    st.error(f"校正失敗: {e}")

    if st.session_state["form_msg"]:
        msg = st.session_state["form_msg"]
        if msg["type"] == "success": st.success(msg["content"])
        elif msg["type"] == "error": 
            for err in msg["content"]: st.error(err)

# ==============================================================================
# 3. 主畫面：分頁檢視
# ==============================================================================

tab1, tab2, tab3 = st.tabs(["📋 持股庫存 (明細)", "📉 獲利分析 (已實現)", "📂 原始資料庫"])

# --- Tab 1: 持股庫存 ---
with tab1:
    if not df_raw.empty:
        df_fifo = logic.calculate_fifo_report(df_raw)
        current_prices = st.session_state.get("realtime_prices", {})
        ta_data = st.session_state.get("ta_data", {})
        df_unrealized = logic.calculate_unrealized_pnl(df_fifo, current_prices)
        
        if not df_unrealized.empty:
            # 技術指標
            df_unrealized['技術訊號'] = df_unrealized['股票代號'].map(lambda x: ta_data.get(x, {}).get('Signal', '-'))
            df_unrealized['月線(20MA)'] = df_unrealized['股票代號'].map(lambda x: ta_data.get(x, {}).get('MA20', 0))

            # 虧損警示
            loss_threshold = -20.0
            danger_stocks = df_unrealized[df_unrealized['報酬率 (%)'] < loss_threshold]
            if not danger_stocks.empty:
                st.error(f"⚠️ 警示：共有 {len(danger_stocks)} 檔股票虧損超過 {abs(loss_threshold)}%！")
            
            def color_pnl(val):
                if isinstance(val, (int, float)):
                    return f'color: {"red" if val > 0 else "green" if val < 0 else "black"}'
                return ''
            
            def highlight_danger(val):
                if isinstance(val, (int, float)):
                    color = "red" if val > 0 else "green" if val < 0 else "black"
                    bg = "background-color: #FFCDD2" if val < -20 else ""
                    return f'color: {color}; {bg}'
                return ''

            display_cols = ['股票', '庫存股數', '平均成本', '目前市價', '月線(20MA)', '技術訊號', '股票市值', '未實現損益', '報酬率 (%)', '佔總資產比例 (%)', '賣出額外費用']
            final_cols = [c for c in display_cols if c in df_unrealized.columns]

            format_dict = {
                "庫存股數": "{:,.0f}", "平均成本": "{:,.2f}", "目前市價": "{:,.2f}",
                "月線(20MA)": "{:,.2f}",
                "股票市值": "{:,.0f}", "未實現損益": "{:,.0f}", "報酬率 (%)": "{:,.2f}%",
                "佔總資產比例 (%)": "{:,.2f}%"
            }
            
            st.dataframe(
                df_unrealized[final_cols].style
                .format(format_dict)
                .map(color_pnl, subset=['未實現損益']) 
                .map(highlight_danger, subset=['報酬率 (%)']), 
                use_container_width=True, height=600
            )
        else:
            st.info("目前沒有庫存。")
    else:
        st.warning("無交易紀錄。")

# --- Tab 2: 獲利分析 ---
with tab2:
    if not df_raw.empty:
        df_realized_all = logic.calculate_realized_report(df_raw)
        if not df_realized_all.empty:
            df_realized_all['交易日期'] = pd.to_datetime(df_realized_all['交易日期']).dt.date
            all_years = sorted(df_realized_all['年'].unique().tolist(), reverse=True)
            year_options = ["全部"] + all_years
            col_filter, _ = st.columns([1, 4])
            selected_year = col_filter.selectbox("📅 選擇檢視年度", year_options)
            
            if selected_year == "全部": df_view = df_realized_all
            else: df_view = df_realized_all[df_realized_all['年'] == selected_year]
            
            if not df_view.empty:
                pnl_sum = df_view['已實現損益'].sum()
                div_sum = df_view[df_view['交易類別'] == '股息']['已實現損益'].sum()
                trades = df_view[df_view['交易類別'] == '賣出']
                win_trades = trades[trades['已實現損益'] > 0]
                win_rate = (len(win_trades)/len(trades)*100) if not trades.empty else 0
                
                c1, c2, c3 = st.columns(3)
                c1.metric("區間總損益", f"${pnl_sum:,.0f}")
                c2.metric("區間股息", f"${div_sum:,.0f}")
                c3.metric("交易勝率", f"{win_rate:.1f}%")
                st.divider()
                
                g1, g2 = st.columns(2)
                with g1:
                    m_pnl = df_view.groupby('月')['已實現損益'].sum().reset_index()
                    if selected_year == "全部": m_pnl = m_pnl.sort_values('月').tail(12)
                    else: m_pnl = m_pnl.sort_values('月')
                    m_pnl['Color'] = m_pnl['已實現損益'].apply(lambda x: 'Profit' if x >= 0 else 'Loss')
                    fig_m = px.bar(m_pnl, x='月', y='已實現損益', color='Color', color_discrete_map={'Profit': '#E53935', 'Loss': '#26a69a'}, text_auto='.2s')
                    fig_m.update_traces(hovertemplate='<b>%{x}</b><br>已實現損益: %{y:,.0f}<extra></extra>')
                    fig_m.update_layout(showlegend=False, xaxis_title=None, yaxis=dict(tickformat=".2s"))
                    st.plotly_chart(fig_m, use_container_width=True)
                with g2:
                    stock_pnl = df_view.groupby('股票')['已實現損益'].sum().reset_index()
                    if len(stock_pnl) > 16:
                        stock_pnl = pd.concat([stock_pnl.nlargest(8,'已實現損益'), stock_pnl.nsmallest(8,'已實現損益')]).drop_duplicates()
                    stock_pnl = stock_pnl.sort_values('已實現損益', ascending=True)
                    stock_pnl['Color'] = stock_pnl['已實現損益'].apply(lambda x: 'Profit' if x >= 0 else 'Loss')
                    fig_s = px.bar(stock_pnl, y='股票', x='已實現損益', orientation='h', color='Color', color_discrete_map={'Profit': '#E53935', 'Loss': '#26a69a'}, text_auto='.2s')
                    fig_s.update_traces(hovertemplate='<b>%{y}</b><br>已實現損益: %{x:,.0f}<extra></extra>')
                    fig_s.update_layout(showlegend=False, yaxis_title=None, xaxis=dict(tickformat=".2s"))
                    st.plotly_chart(fig_s, use_container_width=True)
            else: st.info("無資料")
        else: st.info("尚無已實現損益。")

    # --- Tab 3: 原始資料庫 ---
    with tab3:
        if not df_raw.empty:
            st.markdown("##### 📋 交易流水帳")
            df_display = df_raw.copy()
            df_display['交易日期'] = pd.to_datetime(df_display['交易日期']).dt.date
            st.dataframe(df_display.sort_values('交易日期', ascending=False), use_container_width=True)
        
        df_history = database.load_asset_history()
        if not df_history.empty:
            st.markdown("##### 📜 資產歷史紀錄")
            df_h_disp = df_history.copy()
            df_h_disp['日期'] = pd.to_datetime(df_h_disp['日期']).dt.date
            st.dataframe(df_h_disp.sort_values('日期', ascending=False), use_container_width=True)