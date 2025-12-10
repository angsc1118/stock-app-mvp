# ==============================================================================
# 檔案名稱: app.py
# 
# 修改歷程:
# 2025-12-10 13:30:00: [UI] 引入 utils.render_sidebar_status 統一狀態列
# 2025-12-05 16:30:00: [UI] Fix: 修正更新按鈕顏色與圓餅圖圖例
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
import utils # [New] 匯入工具庫

# 1. 設定頁面配置
st.set_page_config(page_title="Global Asset Overview", layout="wide", page_icon="📊")

# --- CSS 樣式 (維持不變) ---
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    .dashboard-card {
        background-color: #1E2130; border-radius: 10px; padding: 20px;
        margin-bottom: 0px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        height: 100%; display: flex; flex-direction: column; justify-content: center;
    }
    .card-header-bar { height: 4px; width: 100%; border-radius: 4px 4px 0 0; margin-bottom: 12px; opacity: 0.8; }
    .metric-label { font-size: 14px; color: #B0B0B0; font-weight: 500; letter-spacing: 0.5px; }
    .metric-value { font-size: 32px; font-weight: 700; color: #FFFFFF; margin: 4px 0; }
    .metric-delta { font-size: 13px; font-weight: 500; margin-top: 4px; }
    .tight-list-item {
        display: flex; justify-content: space-between; padding: 8px 0;
        border-bottom: 1px solid #333333; font-size: 14px;
    }
    .tight-list-item:last-child { border-bottom: none; }
    .stock-name { font-weight: 600; color: #E0E0E0; }
    div.stButton > button {
        background-color: #29B6F6; color: white; border: none; border-radius: 6px;
        font-weight: 600; height: 42px; transition: all 0.3s ease;
    }
    div.stButton > button:hover { background-color: #039BE5; color: white; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
    div.stButton > button:active { background-color: #0277BD; }
    .g-gtitle, .g-xtitle, .g-ytitle { fill: #E0E0E0 !important; }
</style>
""", unsafe_allow_html=True)

# 2. 輔助函式 (維持不變)
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

# 3. 初始化 Session
if "realtime_prices" not in st.session_state: st.session_state["realtime_prices"] = {}
if "price_update_time" not in st.session_state: st.session_state["price_update_time"] = None
if "ta_data" not in st.session_state: st.session_state["ta_data"] = {}

try:
    df_raw = database.load_data()
except:
    df_raw = pd.DataFrame()

# ==============================================================================
# 4. 側邊欄 (修改處)
# ==============================================================================
# [UI Update] 呼叫共用狀態列
utils.render_sidebar_status()

with st.sidebar:
    st.header("戰情室導航")
    st.info("💡 提示：如需「新增交易」或「查詢明細」，請點擊左側頁籤前往 **帳務管理**。")
    # 移除原本底部的更新時間顯示，因為已經由 utils 統一在上方顯示了

# ==============================================================================
# 5. Dashboard 渲染核心 (維持不變)
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

@st.fragment(run_every=60)
def render_dashboard(df_raw):
    # (此處邏輯與上一版完全相同，為節省篇幅，保留原有的渲染邏輯)
    # --- 計算核心數據 ---
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

    # --- ROW 1: KPI Cards ---
    k1, k2, k3 = st.columns(3)
    
    with k1:
        dashboard_card("Total Net Worth", f"${int(total_assets):,}", f"Unrealized: ${int(total_unrealized_pnl):+,}", "green" if total_unrealized_pnl > 0 else "red", "#29B6F6")
    with k2:
        dashboard_card("Liquidity / Cash", f"${int(total_cash):,}", f"{cash_ratio:.1f}% of Portfolio", "green", "#AB47BC")
    with k3:
        dashboard_card("Invested Cost", f"${int(total_cost):,}", "Total Cost Basis", "green", "#78909C")
    
    st.markdown("<br>", unsafe_allow_html=True)

    # --- ROW 2: Charts & Alerts ---
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

    # --- ROW 3: Top Movers & Losers ---
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

# 6. 主程式執行
if df_raw.empty:
    st.info("目前沒有任何交易資料，請前往「帳務管理」頁面新增第一筆交易。")
else:
    render_dashboard(df_raw)
