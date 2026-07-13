# ==============================================================================
# 檔案名稱: app.py
# 
# 修改歷程:
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
                with st.status("🚀 連線交易所主機中...", expanded=True) as status:
                    st.write("1. 抓取即時報價...")
                    prices = market_data.get_realtime_prices(stock_ids)
                    st.write("2. 計算技術指標...")
                    ta_data = market_data.get_batch_technical_analysis(stock_ids)
                    status.update(label="✅ 更新完成", state="complete", expanded=False)
                st.session_state["realtime_prices"] = prices
                st.session_state["ta_data"] = ta_data
                tw_time = datetime.utcnow() + timedelta(hours=8)
                st.session_state["price_update_time"] = tw_time.strftime("%Y-%m-%d %H:%M:%S")
                st.rerun()

# --- PART A: KPI 卡片 (動態, 60s) ---
@st.fragment()
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

# --- PART C: Charts & Alerts (動態, 60s) ---
@st.fragment()
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

    c1, c2, c3 = st.columns(3)
    
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

    # Alerts & Actions
    with c3:
        with st.container(border=True):
            st.markdown("##### ⚠️ Alerts & Actions")
            alerts_html = ""
            if cash_ratio < 10: alerts_html += f"<div class='tight-list-item'><span class='stock-name'>🔴 Cash Level</span><span>Critical (&lt;10%)</span></div>"
            elif cash_ratio > 80: alerts_html += f"<div class='tight-list-item'><span class='stock-name'>🟡 Cash Level</span><span>High (&gt;80%)</span></div>"
            else: alerts_html += f"<div class='tight-list-item'><span class='stock-name'>🟢 Cash Level</span><span>Healthy ({cash_ratio:.0f}%)</span></div>"
            
            if not df_unrealized.empty:
                danger_count = len(df_unrealized[df_unrealized['報酬率 (%)'] < -20])
                if danger_count > 0: alerts_html += f"<div class='tight-list-item'><span class='stock-name'>🔴 Stop Loss</span><span>{danger_count} stocks &lt; -20%</span></div>"
                else: alerts_html += f"<div class='tight-list-item'><span class='stock-name'>🟢 Stop Loss</span><span>All Clear</span></div>"
            
            if not df_unrealized.empty:
                best_stock = df_unrealized.sort_values('報酬率 (%)', ascending=False).iloc[0]
                if best_stock['報酬率 (%)'] > 0: alerts_html += f"<div class='tight-list-item'><span class='stock-name'>🏆 Best Performer</span><span>{best_stock['股票名稱']} (+{best_stock['報酬率 (%)']:.1f}%)</span></div>"

            st.markdown(alerts_html, unsafe_allow_html=True)
            st.write(""); st.write(""); st.write("")

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
