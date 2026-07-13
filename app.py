# ==============================================================================
# 檔案名稱: app.py
# 
# 修改歷程:
# 2026-07-13 10:00:00: [Feat] 盤中戰情室改版：Alerts & Actions 改為戰情警示牆 (呼叫 logic.generate_alerts)，更新按鈕改抓 detailed quotes 以支援爆量/乖離告警
# 2025-12-11 15:52:00: [Refactor] 方案 A 實作：將 Dashboard 拆分為 KPI(動)、Goals(靜)、Charts(動) 三區塊
# 2025-12-11 15:00:00: [UI] Fix: 強力修正 Expander 標題列背景變白問題
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime, timedelta
import time
import math

import database
import logic
import market_data
import utils

# 1. 設定頁面配置
st.set_page_config(page_title="Global Asset Overview", layout="wide", page_icon="📊")

# --- [UI] 注入自定義 CSS ---
st.markdown("""
<style>
    /* 全局背景與字體 */
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    
    /* Expander 樣式修正 */
    div[data-testid="stExpander"] {
        border: none !important;
        box-shadow: none !important;
        background-color: transparent !important;
        color: #FAFAFA !important;
    }
    div[data-testid="stExpander"] > details > summary {
        background-color: #1E2130 !important;
        color: #FAFAFA !important;
        border: 1px solid #333333 !important;
        border-radius: 8px !important;
        padding-left: 10px !important;
    }
    div[data-testid="stExpander"] > details > summary:hover {
        background-color: #262A3B !important;
        color: #29B6F6 !important;
    }
    div[data-testid="stExpanderDetails"] {
        background-color: #0E1117 !important;
        border-top: none !important;
    }
    
    /* 卡片容器樣式 */
    .dashboard-card {
        background-color: #1E2130; border-radius: 10px; padding: 20px;
        margin-bottom: 0px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        height: 100%; display: flex; flex-direction: column; justify-content: center;
    }
    .card-header-bar { height: 4px; width: 100%; border-radius: 4px 4px 0 0; margin-bottom: 12px; opacity: 0.8; }
    
    /* Metric 字體 */
    .metric-label { font-size: 14px; color: #B0B0B0; font-weight: 500; letter-spacing: 0.5px; }
    .metric-value { font-size: 32px; font-weight: 700; color: #FFFFFF; margin: 4px 0; }
    .metric-delta { font-size: 13px; font-weight: 500; margin-top: 4px; }
    
    /* 進度條樣式 */
    .goal-container {
        background-color: #1E2130; border-radius: 8px; padding: 15px 20px;
        margin-bottom: 15px; border: 1px solid #333333; position: relative;
    }
    .goal-header { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 15px; font-weight: 600; color: #E0E0E0; }
    .goal-stats { font-size: 13px; color: #A0A0A0; margin-bottom: 5px; display: flex; justify-content: space-between; }
    .progress-bg { width: 100%; height: 10px; background-color: #333333; border-radius: 5px; overflow: hidden; position: relative; }
    .progress-fill { height: 100%; border-radius: 5px; transition: width 0.5s ease; }
    .time-marker { position: absolute; top: -3px; height: 16px; width: 2px; background-color: #FFFFFF; box-shadow: 0 0 4px rgba(255,255,255,0.8); z-index: 10; }
    .goal-alert { color: #FF5252; font-weight: bold; margin-left: 10px; font-size: 13px; }
    .goal-advice { font-size: 12px; color: #FFAB91; margin-top: 5px; font-style: italic; }

    /* 其他元件 */
    .tight-list-item { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #333333; font-size: 14px; }
    .tight-list-item:last-child { border-bottom: none; }
    .stock-name { font-weight: 600; color: #E0E0E0; }

    /* 戰情警示牆卡片 */
    .alert-card {
        background-color: #1E2130; border-radius: 8px; padding: 12px 14px;
        margin-bottom: 10px; border: 1px solid #333333; border-left: 4px solid #333333;
    }
    .alert-card.critical { border-left-color: #FF5252; }
    .alert-card.warn { border-left-color: #FFB74D; }
    .alert-card.info { border-left-color: #29B6F6; }
    .alert-card .ac-row { display: flex; justify-content: space-between; align-items: center; font-size: 13.5px; font-weight: 600; color: #E0E0E0; margin-bottom: 5px; }
    .alert-card .ac-badge { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px; }
    .alert-card.critical .ac-badge { color: #FF5252; background: rgba(255,82,82,0.12); }
    .alert-card.warn .ac-badge { color: #FFB74D; background: rgba(255,183,77,0.12); }
    .alert-card.info .ac-badge { color: #29B6F6; background: rgba(41,182,246,0.12); }
    .alert-card .ac-msg { font-size: 12px; color: #B0B0B0; line-height: 1.5; }
    div.stButton > button { background-color: #29B6F6; color: white; border: none; border-radius: 6px; font-weight: 600; height: 42px; transition: all 0.3s ease; }
    div.stButton > button:hover { background-color: #039BE5; color: white; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
    div.stButton > button:active { background-color: #0277BD; }
    .g-gtitle, .g-xtitle, .g-ytitle { fill: #E0E0E0 !important; }
</style>
""", unsafe_allow_html=True)

# 2. 輔助函式
def dashboard_card(title, value, delta_text, delta_color, bar_color):
    delta_html = ""
    if delta_text:
        color_hex = "#00E676" if delta_color == "green" else "#FF5252"
        delta_html = f'<div class="metric-delta" style="color: {color_hex};">{delta_text}</div>'
    
    html_code = f"""
    <div class="dashboard-card" style="min-height: 140px;">
        <div class="card-header-bar" style="background-color: {bar_color};"></div>
        <div class="metric-label">{title.upper()}</div>
        <div class="metric-value">{value}</div>
        {delta_html}
    </div>
    """
    st.markdown(html_code, unsafe_allow_html=True)

def alert_card(alert):
    """渲染單一戰情警示卡片 (呼叫 logic.generate_alerts() 產生的告警字典)"""
    severity = alert.get("severity", "info")
    type_label_map = {
        "cash_level": "現金水位", "stop_loss": "停損", "breakout": "突破",
        "breakdown": "跌破", "volume_spike": "爆量", "bias": "乖離過大", "best_performer": "最佳表現"
    }
    badge_text = type_label_map.get(alert.get("type", ""), alert.get("type", ""))
    title = alert["name"] if not alert.get("symbol") else f"{alert['name']} ({alert['symbol']})"
    html = f"""
    <div class="alert-card {severity}">
        <div class="ac-row">
            <span>{alert.get('icon','')} {title}</span>
            <span class="ac-badge">{badge_text}</span>
        </div>
        <div class="ac-msg">{alert['message']}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def goal_progress_bar(name, current, target, percent, time_info, zen_mode):
    if percent < 30: bar_color = "linear-gradient(90deg, #FF5252, #FF8A65)" 
    elif percent < 70: bar_color = "linear-gradient(90deg, #FFB74D, #FFD54F)" 
    else: bar_color = "linear-gradient(90deg, #66BB6A, #00E676)" 
    
    time_marker_html = ""
    alert_html = ""
    advice_html = ""
    
    if not zen_mode and time_info['has_date']:
        t_pct = min(max(time_info['time_pct'], 0), 100)
        time_marker_html = f'<div class="time-marker" style="left: {t_pct}%;" title="目前時間進度: {t_pct:.1f}%"></div>'
        
        if time_info['status'] == 'behind':
            alert_html = '<span class="goal-alert">🔴 落後進度</span>'
            needed = time_info['monthly_needed']
            if needed > 0:
                advice_html = f'<div class="goal-advice">💡 為準時達成，建議月存：${int(needed):,}</div>'
        elif time_info['status'] == 'ahead':
            alert_html = '<span style="color:#00E676; margin-left:10px; font-size:13px;">🚀 超前進度</span>'

    html = f"""
    <div class="goal-container">
        <div class="goal-header">
            <span>🎯 {name} {alert_html}</span>
            <span>{percent:.1f}%</span>
        </div>
        <div class="goal-stats">
            <span>目前: ${int(current):,}</span>
            <span>目標: ${int(target):,}</span>
        </div>
        <div class="progress-bg">
            <div class="progress-fill" style="width: {percent}%; background: {bar_color};"></div>
            {time_marker_html}
        </div>
        {advice_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# 3. 初始化 Session
if "realtime_prices" not in st.session_state: st.session_state["realtime_prices"] = {}
if "realtime_quotes" not in st.session_state: st.session_state["realtime_quotes"] = {}  # detailed quotes (含成交量)，供戰情警示牆使用
if "price_update_time" not in st.session_state: st.session_state["price_update_time"] = None
if "ta_data" not in st.session_state: st.session_state["ta_data"] = {}

try:
    df_raw = database.load_data()
except:
    df_raw = pd.DataFrame()

# ==============================================================================
# 4. 側邊欄
# ==============================================================================
utils.render_sidebar_status()

with st.sidebar:
    zen_mode = st.toggle("🧘 專注模式 (Zen Mode)", value=False, help="開啟後將隱藏進度落後警示與時間壓力，只專注於累積金額。")

# ==============================================================================
# 5. Dashboard 分區渲染邏輯 (Split Rendering)
# ==============================================================================

# 頂部標題與更新按鈕
c_head, c_btn = st.columns([7, 1])
with c_head:
    st.markdown("## 🌐 Global Asset Overview")
with c_btn:
    if st.button("🔄 更新數據", use_container_width=True):
        if not df_raw.empty:
            temp_fifo = logic.calculate_fifo_report(df_raw)
            if not temp_fifo.empty:
                stock_ids = temp_fifo['股票代號'].unique().tolist()

                # 納入設有警示價的自選股 (非庫存)，讓突破/跌破告警也能涵蓋這些股票
                try:
                    df_watch_for_update = database.load_watchlist()
                    if not df_watch_for_update.empty and '股票代號' in df_watch_for_update.columns:
                        has_limit = pd.to_numeric(df_watch_for_update.get('警示價_高'), errors='coerce').fillna(0) > 0
                        has_limit |= pd.to_numeric(df_watch_for_update.get('警示價_低'), errors='coerce').fillna(0) > 0
                        watch_ids = df_watch_for_update.loc[has_limit, '股票代號'].astype(str).str.strip().tolist()
                        stock_ids = list(set(stock_ids + watch_ids))
                except:
                    pass

                with st.status("🚀 連線交易所主機中...", expanded=True) as status:
                    st.write("1. 抓取即時報價 (含成交量，供戰情警示牆使用)...")
                    quotes = market_data.get_batch_detailed_quotes(stock_ids)
                    st.write("2. 計算技術指標...")
                    ta_data = market_data.get_batch_technical_analysis(stock_ids)
                    status.update(label="✅ 更新完成", state="complete", expanded=False)
                st.session_state["realtime_quotes"] = quotes
                st.session_state["realtime_prices"] = {k: v.get('price', 0) for k, v in quotes.items()}
                st.session_state["ta_data"] = ta_data
                tw_time = datetime.utcnow() + timedelta(hours=8)
                st.session_state["price_update_time"] = tw_time.strftime("%Y-%m-%d %H:%M:%S")
                st.rerun()

# --- PART A: KPI 卡片 (動態, 60s) ---
@st.fragment(run_every=60)
def render_kpi_section(df_raw):
    # 重複必要的計算 (Fragment 獨立性)
    acc_balances = logic.calculate_account_balances(df_raw)
    total_cash = sum(acc_balances.values())
    df_fifo = logic.calculate_fifo_report(df_raw)
    current_prices = st.session_state.get("realtime_prices", {})
    df_unrealized = logic.calculate_unrealized_pnl(df_fifo, current_prices)
    
    total_market_value = df_unrealized['股票市值'].sum() if not df_unrealized.empty else 0
    total_unrealized_pnl = df_unrealized['未實現損益'].sum() if not df_unrealized.empty else 0
    total_cost = df_unrealized['總持有成本 (FIFO)'].sum() if not df_unrealized.empty else 0
    
    total_assets = total_cash + total_market_value
    cash_ratio = (total_cash / total_assets * 100) if total_assets > 0 else 0

    k1, k2, k3 = st.columns(3)
    with k1:
        dashboard_card("Total Net Worth", f"${int(total_assets):,}", f"Unrealized: ${int(total_unrealized_pnl):+,}", "green" if total_unrealized_pnl > 0 else "red", "#29B6F6")
    with k2:
        dashboard_card("Liquidity / Cash", f"${int(total_cash):,}", f"{cash_ratio:.1f}% of Portfolio", "green", "#AB47BC")
    with k3:
        dashboard_card("Invested Cost", f"${int(total_cost):,}", "Total Cost Basis", "green", "#78909C")

# --- PART B: Financial Goals (靜態, 不自動刷新) ---
def render_goals_section(df_raw, zen_mode):
    df_goals = database.load_goals()
    if not df_goals.empty:
        goals_progress = logic.calculate_goal_progress(df_goals, df_raw)
        
        if goals_progress:
            expander_title = "🎯 Financial Goals (目標累積)" if zen_mode else "🎯 Financial Goals (進度與配速)"
            
            with st.expander(expander_title, expanded=True):
                g_cols = st.columns(2)
                for i, goal in enumerate(goals_progress):
                    with g_cols[i % 2]:
                        goal_progress_bar(
                            goal['name'], 
                            goal['current'], 
                            goal['target'], 
                            goal['percent'],
                            goal['time_info'],
                            zen_mode
                        )

# --- PART C: Alert Wall & Charts (動態, 60s) ---
@st.fragment(run_every=60)
def render_charts_section(df_raw):
    # 重複必要的計算
    acc_balances = logic.calculate_account_balances(df_raw)
    total_cash = sum(acc_balances.values())
    df_fifo = logic.calculate_fifo_report(df_raw)
    current_prices = st.session_state.get("realtime_prices", {})
    df_unrealized = logic.calculate_unrealized_pnl(df_fifo, current_prices)
    
    total_market_value = df_unrealized['股票市值'].sum() if not df_unrealized.empty else 0
    total_assets = total_cash + total_market_value
    cash_ratio = (total_cash / total_assets * 100) if total_assets > 0 else 0

    # --- 戰情警示牆 (Hero) ---
    st.markdown("##### ⚠️ 戰情警示牆")
    quotes = st.session_state.get("realtime_quotes", {})
    ta_data = st.session_state.get("ta_data", {})
    try:
        df_watch = database.load_watchlist()
    except:
        df_watch = pd.DataFrame(columns=['群組', '股票代號', '股票名稱', '警示價_高', '警示價_低', '備註'])
    try:
        df_mp = database.load_mp_table()
    except:
        df_mp = pd.DataFrame()
    tw_now = datetime.utcnow() + timedelta(hours=8)
    current_time_str = tw_now.strftime("%H:%M")

    alerts = logic.generate_alerts(df_unrealized, cash_ratio, quotes, df_watch, ta_data, df_mp, current_time_str)

    if not alerts:
        st.caption("✅ 目前無告警，一切正常。")
    else:
        if not quotes:
            st.caption("💡 尚未取得含成交量的即時報價，突破/跌破/爆量/乖離告警可能不完整，請點擊上方「🔄 更新數據」。")
        n_cols = 3
        for i in range(0, len(alerts), n_cols):
            row_alerts = alerts[i:i + n_cols]
            cols = st.columns(n_cols)
            for col, a in zip(cols, row_alerts):
                with col:
                    alert_card(a)

    st.markdown("<br>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    # Asset Allocation
    with c1:
        with st.container(border=True):
            st.markdown("##### Stock Allocation")
            if not df_unrealized.empty and total_market_value > 0:
                sorted_stocks = df_unrealized.sort_values('股票市值', ascending=False)
                fig_pie = px.pie(sorted_stocks, values='股票市值', names='股票名稱', hole=0.6)
                fig_pie.update_traces(textinfo='percent', textposition='inside')
                fig_pie.update_layout(template="plotly_dark", showlegend=True, legend=dict(orientation="h", y=-0.2, font=dict(color="#E0E0E0")), margin=dict(t=10, b=10, l=10, r=10), height=250, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#E0E0E0'))
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("尚無持股資料")
                st.write(""); st.write("")

    # Cash by Account
    with c2:
        with st.container(border=True):
            st.markdown("##### Cash by Account")
            if total_cash > 0:
                pie_data = [{'Account': k, 'Value': v} for k, v in acc_balances.items() if v > 0]
                df_cash = pd.DataFrame(pie_data)
                fig_cash = px.pie(df_cash, values='Value', names='Account', hole=0.6, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_cash.update_traces(textinfo='percent', textposition='inside')
                fig_cash.update_layout(template="plotly_dark", showlegend=True, legend=dict(orientation="h", y=-0.2, font=dict(color="#E0E0E0")), margin=dict(t=10, b=10, l=10, r=10), height=250, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#E0E0E0'))
                st.plotly_chart(fig_cash, use_container_width=True)
            else:
                st.info("無現金餘額")
                st.write(""); st.write("")

    st.markdown("<br>", unsafe_allow_html=True)

    # Top Movers & Losers
    b1, b2 = st.columns(2)
    with b1:
        with st.container(border=True):
            st.markdown("##### 🚀 Top Gainers")
            if not df_unrealized.empty:
                top_gainers = df_unrealized[df_unrealized['報酬率 (%)'] > 0].sort_values('報酬率 (%)', ascending=False).head(5)
                if not top_gainers.empty:
                    html_list = ""
                    for _, row in top_gainers.iterrows():
                        html_list += f"<div class='tight-list-item'><span class='stock-name'>{row['股票名稱']} ({row['股票代號']})</span><span style='color:#00E676; font-weight:bold;'>+{row['報酬率 (%)']:.2f}%</span></div>"
                    st.markdown(html_list, unsafe_allow_html=True)
                else: st.caption("No positive returns yet.")
            else: st.caption("No Data")

    with b2:
        with st.container(border=True):
            st.markdown("##### 📉 Top Losers")
            if not df_unrealized.empty:
                top_losers = df_unrealized[df_unrealized['報酬率 (%)'] < 0].sort_values('報酬率 (%)', ascending=True).head(5)
                if not top_losers.empty:
                    html_list = ""
                    for _, row in top_losers.iterrows():
                        html_list += f"<div class='tight-list-item'><span class='stock-name'>{row['股票名稱']} ({row['股票代號']})</span><span style='color:#FF5252; font-weight:bold;'>{row['報酬率 (%)']:.2f}%</span></div>"
                    st.markdown(html_list, unsafe_allow_html=True)
                else: st.caption("No negative returns.")
            else: st.caption("No Data")

# 6. 主程式執行 (依序呼叫三個區塊)
if df_raw.empty:
    st.info("目前沒有任何交易資料，請前往「帳務管理」頁面新增第一筆交易。")
else:
    # 區塊 1: KPI (動態)
    render_kpi_section(df_raw)
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 區塊 2: Goals (靜態 - 解決閃爍問題)
    render_goals_section(df_raw, zen_mode)
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 區塊 3: Charts (動態)
    render_charts_section(df_raw)
