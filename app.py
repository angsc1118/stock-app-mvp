import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, datetime, timedelta

import database
import logic
import market_data

# 設定頁面配置
st.set_page_config(page_title="股票資產戰情室", layout="wide", page_icon="📈")

# ==============================================================================
# 1. 系統初始化與資料讀取
# ==============================================================================

# 讀取設定檔
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

# 初始化 Session State
if "txn_date" not in st.session_state: st.session_state["txn_date"] = date.today()
if "txn_account" not in st.session_state: 
    st.session_state["txn_account"] = account_list[0] if account_list else ""
# 確保帳戶有效性
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

# 提交交易的回調函式
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
            # 清空欄位
            st.session_state.txn_stock_id = ""
            st.session_state.txn_stock_name = ""
            st.session_state.txn_qty = 0
            st.session_state.txn_price = 0.0
            st.session_state.txn_notes = ""
            
            if is_cash_flow:
                amount = int(s_qty * s_price)
                st.session_state["form_msg"] = {"type": "success", "content": f"✅ 成功記錄：{s_action} ${amount:,} (帳戶: {s_account})"}
            else:
                st.session_state["form_msg"] = {"type": "success", "content": f"✅ 成功新增：{s_name} ({s_id}) {s_action}"}
        except Exception as e:
            st.session_state["form_msg"] = {"type": "error", "content": [f"寫入失敗: {e}"]}

# ==============================================================================
# 2. 側邊欄 (Sidebar)：全域操作中心
# ==============================================================================
try:
    # 讀取資料以供計算 (為了按鈕邏輯)
    df_raw = database.load_data()
except:
    df_raw = pd.DataFrame()

with st.sidebar:
    st.title("🛠️ 操作面板")
    
    # --- A. 全域功能按鈕區 ---
    with st.expander("⚡ 快速動作", expanded=True):
        # 1. 更新股價按鈕
        if st.button("🔄 更新即時股價 (Fugle API)", use_container_width=True):
             if not df_raw.empty:
                temp_fifo = logic.calculate_fifo_report(df_raw)
                if not temp_fifo.empty:
                    stock_ids = temp_fifo['股票代號'].unique().tolist()
                    with st.spinner('正在連線 API 取得報價...'):
                        prices = market_data.get_realtime_prices(stock_ids)
                    st.session_state["realtime_prices"] = prices
                    tw_time = datetime.utcnow() + timedelta(hours=8)
                    st.session_state["price_update_time"] = tw_time.strftime("%Y-%m-%d %H:%M:%S")
                    st.rerun()
        
        # 顯示更新時間
        if st.session_state["price_update_time"]:
            st.caption(f"🕒 最後更新: {st.session_state['price_update_time']}")
        else:
            st.caption("🕒 尚未更新 (顯示庫存成本)")

        # 2. 記錄資產按鈕
        # 需先簡單計算當前總資產 (預估值)
        if not df_raw.empty:
            # 簡易計算，詳細在 Main Area
            _acc_bals = logic.calculate_account_balances(df_raw)
            _tot_cash = sum(_acc_bals.values())
            _fifo_tmp = logic.calculate_fifo_report(df_raw)
            _curr_prices = st.session_state.get("realtime_prices", {})
            _df_pnl = logic.calculate_unrealized_pnl(_fifo_tmp, _curr_prices)
            _tot_stock = _df_pnl['股票市值'].sum() if not _df_pnl.empty else 0
            _tot_asset = _tot_cash + _tot_stock
            
            if st.button("📝 記錄今日資產", use_container_width=True):
                try:
                    today_tw = (datetime.utcnow() + timedelta(hours=8)).date()
                    database.save_asset_history(today_tw, int(_tot_asset), int(_tot_cash), int(_tot_stock))
                    st.success(f"已記錄資產: ${_tot_asset:,}")
                except Exception as e:
                    st.error(f"記錄失敗: {e}")

    st.divider()

    # --- B. 交易與校正 ---
    mode = st.radio("選擇功能", ["📝 新增交易", "🔧 帳戶餘額校正"], horizontal=True)
    
    if mode == "📝 新增交易":
        col1, col2 = st.columns(2)
        col1.date_input("交易日期", key="txn_date")
        col2.selectbox("交易帳戶", options=account_list, key="txn_account")
        input_action = st.selectbox("交易類別", ['買進', '賣出', '現金股利', '股票股利', '入金', '出金'], key="txn_action")
        is_cash_op = input_action in ['入金', '出金']

        if is_cash_op:
            st.info("💡 資金操作：請輸入金額，代號可留空")
            input_stock_id = st.text_input("股票代號", placeholder="(可留空)", key="txn_stock_id")
        else:
            input_stock_id = st.text_input("股票代號", placeholder="例如 2330", key="txn_stock_id")
            if input_stock_id:
                clean_id = str(input_stock_id).strip()
                found_name = stock_map.get(clean_id, "")
                if found_name and st.session_state["txn_stock_name"] != found_name:
                    st.session_state["txn_stock_name"] = found_name
                    st.rerun()

        if is_cash_op:
            st.text_input("股票名稱", placeholder="(可留空)", key="txn_stock_name")
        else:
            st.text_input("股票名稱", placeholder="自動帶入或手動", key="txn_stock_name")

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
# 3. 戰情室主畫面 (Dashboard)
# ==============================================================================

st.title('📊 投資戰情室')

if df_raw.empty:
    st.info("目前沒有任何交易資料，請從左側新增第一筆交易 (如：入金)。")
else:
    # --- 資料準備 ---
    # 1. 現金
    acc_balances = logic.calculate_account_balances(df_raw)
    total_cash = sum(acc_balances.values())
    
    # 2. 庫存與未實現
    df_fifo = logic.calculate_fifo_report(df_raw)
    current_prices = st.session_state.get("realtime_prices", {})
    df_unrealized = logic.calculate_unrealized_pnl(df_fifo, current_prices)
    
    total_market_value = df_unrealized['股票市值'].sum() if not df_unrealized.empty else 0
    total_unrealized_pnl = df_unrealized['未實現損益'].sum() if not df_unrealized.empty else 0
    total_cost = df_unrealized['總持有成本 (FIFO)'].sum() if not df_unrealized.empty else 0
    unrealized_ret = (total_unrealized_pnl / total_cost * 100) if total_cost != 0 else 0
    
    # 3. 本年度已實現損益
    df_realized_all = logic.calculate_realized_report(df_raw)
    this_year = date.today().year
    if not df_realized_all.empty:
        df_realized_ytd = df_realized_all[df_realized_all['年'] == this_year]
        total_realized_ytd = df_realized_ytd['已實現損益'].sum()
    else:
        total_realized_ytd = 0

    # 4. 總資產
    total_assets = total_cash + total_market_value
    cash_ratio = (total_cash / total_assets * 100) if total_assets > 0 else 0

    # --- A. KPI 指標列 ---
    k1, k2, k3, k4 = st.columns(4)
    
    k1.metric("💰 總資產淨值", f"${int(total_assets):,}", help="現金 + 股票市值")
    
    # 未實現損益 (顏色)
    k2.metric("📈 未實現損益", f"${int(total_unrealized_pnl):,}", delta=f"{unrealized_ret:.2f}%")
    
    # 本年度已實現 (顏色)
    k3.metric(f"📅 {this_year} 已實現損益", f"${int(total_realized_ytd):,}", delta=None, help="包含賣出獲利與股息")
    
    # 現金水位 (顏色邏輯)
    if cash_ratio > 90: ratio_color = "#FF4B4B" # 紅
    elif 80 <= cash_ratio < 90: ratio_color = "#FFA500" # 橘
    elif 70 <= cash_ratio < 80: ratio_color = "#1E90FF" # 藍
    elif 60 <= cash_ratio < 70: ratio_color = "#FFD700" # 黃
    else: ratio_color = "#09AB3B" # 綠
    
    k4.markdown(f"""
        <div style="text-align: left;">
            <div style="font-size: 14px; color: rgba(49, 51, 63, 0.6); margin-bottom: 4px;">現金水位</div>
            <div style="font-size: 32px; font-weight: 600; color: {ratio_color};">{cash_ratio:.2f}%</div>
        </div>
    """, unsafe_allow_html=True)

    st.divider()

    # --- B. 圖表區 (上層：趨勢，下層：配置) ---
    
    # 1. 資產趨勢圖 (Load History)
    df_history = database.load_asset_history()
    if not df_history.empty:
        df_history['日期'] = pd.to_datetime(df_history['日期'])
        df_history = df_history.sort_values('日期').drop_duplicates(subset=['日期'], keep='last')
        
        st.subheader("📈 資產成長趨勢")
        fig_trend = px.line(df_history, x='日期', y='總資產', markers=True)
        fig_trend.update_traces(line_color='#2E86C1', line_width=3)
        fig_trend.update_layout(xaxis_title=None, yaxis_title=None, yaxis=dict(tickformat=",.0f"), height=350)
        st.plotly_chart(fig_trend, use_container_width=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

    # 2. 資產配置圓餅圖 (左右並排)
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("🍰 現金配置 (各帳戶) vs 持股")
        if total_assets > 0:
            # 準備資料：每個帳戶的現金 + 總持股市值
            pie_data = []
            # 加入各帳戶現金
            for acc_name, amount in acc_balances.items():
                if amount > 0:
                    pie_data.append({'類別': f'現金-{acc_name}', '金額': amount, 'Type': 'Cash'})
            
            # 加入總股票市值
            if total_market_value > 0:
                pie_data.append({'類別': '股票部位', '金額': total_market_value, 'Type': 'Stock'})
            
            df_pie_alloc = pd.DataFrame(pie_data)
            
            # 繪圖
            if not df_pie_alloc.empty:
                fig_alloc = px.pie(
                    df_pie_alloc, values='金額', names='類別', 
                    hole=0.4, 
                    color='類別',
                    # 這裡不指定固定顏色映射，讓 Plotly 自動分配，但可以透過 Type 做區分優化
                )
                fig_alloc.update_traces(textinfo='percent+label')
                st.plotly_chart(fig_alloc, use_container_width=True)
            else:
                st.info("資產為 0")

    with col_chart2:
        st.subheader("📊 持股分佈 (依市值)")
        if not df_unrealized.empty and total_market_value > 0:
            fig_stock_pie = px.pie(df_unrealized, values='股票市值', names='股票', hole=0.4)
            fig_stock_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_stock_pie.update_layout(showlegend=True) # 顯示圖例
            st.plotly_chart(fig_stock_pie, use_container_width=True)
        else:
            if total_market_value == 0:
                st.info("目前無持股部位 (全現金)")
            else:
                st.info("尚無持股資料")

    # ==========================================================================
    # 4. 功能分頁 (Tab 區)
    # ==========================================================================
    
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["📋 持股庫存 (明細)", "📉 獲利分析 (已實現)", "📂 原始資料庫"])

    # --- Tab 1: 持股庫存 (純表格) ---
    with tab1:
        if not df_unrealized.empty:
            def color_pnl(val):
                if isinstance(val, (int, float)):
                    return f'color: {"red" if val > 0 else "green" if val < 0 else "black"}'
                return ''

            display_cols = ['股票', '庫存股數', '平均成本', '目前市價', '股票市值', '未實現損益', '報酬率 (%)', '佔總資產比例 (%)', '賣出額外費用', '配息金額']
            format_dict = {
                "庫存股數": "{:,.0f}", "平均成本": "{:,.2f}", "目前市價": "{:,.2f}",
                "股票市值": "{:,.0f}", "未實現損益": "{:,.0f}", "報酬率 (%)": "{:,.2f}%",
                "佔總資產比例 (%)": "{:,.2f}%", "配息金額": "{:,.0f}"
            }
            st.dataframe(
                df_unrealized[display_cols].style.format(format_dict).map(color_pnl, subset=['未實現損益', '報酬率 (%)']), 
                use_container_width=True, height=500
            )
        else:
            st.info("目前沒有庫存。")

    # --- Tab 2: 獲利分析 (已實現) ---
    with tab2:
        if not df_realized_all.empty:
            # 年度篩選
            all_years = sorted(df_realized_all['年'].unique().tolist(), reverse=True)
            year_options = ["全部"] + all_years
            col_filter, _ = st.columns([1, 4])
            selected_year = col_filter.selectbox("📅 選擇檢視年度", year_options)
            
            if selected_year == "全部":
                df_view = df_realized_all
            else:
                df_view = df_realized_all[df_realized_all['年'] == selected_year]
            
            if not df_view.empty:
                # 指標
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
                
                # 圖表
                g1, g2 = st.columns(2)
                with g1:
                    st.markdown("##### 月度損益")
                    m_pnl = df_view.groupby('月')['已實現損益'].sum().reset_index()
                    if selected_year == "全部": m_pnl = m_pnl.sort_values('月').tail(12)
                    else: m_pnl = m_pnl.sort_values('月')
                    
                    m_pnl['Color'] = m_pnl['已實現損益'].apply(lambda x: 'Profit' if x >= 0 else 'Loss')
                    fig_m = px.bar(m_pnl, x='月', y='已實現損益', color='Color', 
                                   color_discrete_map={'Profit': '#E53935', 'Loss': '#26a69a'}, text_auto='.2s')
                    fig_m.update_layout(showlegend=False, xaxis_title=None)
                    st.plotly_chart(fig_m, use_container_width=True)
                
                with g2:
                    st.markdown("##### 個股貢獻 (Top 8 賺/賠)")
                    all_stocks = df_view['股票'].unique()
                    sel_stocks = st.multiselect("查詢特定個股", options=all_stocks)
                    s_pnl = df_view.groupby('股票')['已實現損益'].sum().reset_index()
                    
                    if sel_stocks:
                        s_pnl = s_pnl[s_pnl['股票'].isin(sel_stocks)]
                        h = 400 + len(sel_stocks)*20
                    else:
                        h = 400
                        if len(s_pnl) > 16:
                            s_pnl = pd.concat([s_pnl.nlargest(8,'已實現損益'), s_pnl.nsmallest(8,'已實現損益')]).drop_duplicates()
                    
                    s_pnl = s_pnl.sort_values('已實現損益', ascending=True)
                    s_pnl['Color'] = s_pnl['已實現損益'].apply(lambda x: 'Profit' if x >= 0 else 'Loss')
                    fig_s = px.bar(s_pnl, y='股票', x='已實現損益', orientation='h', color='Color',
                                   color_discrete_map={'Profit': '#E53935', 'Loss': '#26a69a'}, text_auto='.2s')
                    fig_s.update_layout(showlegend=False, yaxis_title=None, height=h)
                    st.plotly_chart(fig_s, use_container_width=True)
            else:
                st.info("無資料")
        else:
            st.info("尚無已實現損益。")

    # --- Tab 3: 原始資料庫 ---
    with tab3:
        st.markdown("##### 📋 交易流水帳")
        if not df_raw.empty:
            # 日期格式化
            df_display = df_raw.copy()
            df_display['交易日期'] = pd.to_datetime(df_display['交易日期']).dt.date
            st.dataframe(df_display.sort_values('交易日期', ascending=False), use_container_width=True)
        
        st.markdown("##### 📜 資產歷史紀錄")
        if not df_history.empty:
            df_h_disp = df_history.copy()
            df_h_disp['日期'] = df_h_disp['日期'].dt.date
            st.dataframe(df_h_disp.sort_values('日期', ascending=False), use_container_width=True)
