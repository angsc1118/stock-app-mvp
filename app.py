# ==============================================================================
# 檔案名稱: app.py
# 
# 修改歷程:
# 2025-12-05 15:20:00: [Fix] 修正 f-string 格式化順序錯誤 (:,+ -> :+,)
# 2025-12-05 15:15:00: [UI] V2 改版：調整三欄式佈局
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

# 1. 設定頁面配置 (必須在第一行)
st.set_page_config(page_title="Global Asset Overview", layout="wide", page_icon="📊")

# --- [UI] 注入自定義 CSS (仿 Dashboard 風格) ---
st.markdown("""
<style>
    /* 全局背景與字體 */
    .stApp {
        background-color: #0E1117; /* 深色背景 */
        color: #FAFAFA;
    }
    
    /* 卡片容器樣式 */
    .dashboard-card {
        background-color: #1E2130; /* 卡片背景色 */
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 0px; /* 減少底部間距 */
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    
    /* KPI 卡片標題條 */
    .card-header-bar {
        height: 4px;
        width: 100%;
        border-radius: 4px 4px 0 0;
        margin-bottom: 12px;
        opacity: 0.8;
    }
    
    /* 字體樣式 */
    .metric-label { font-size: 14px; color: #B0B0B0; font-weight: 500; letter-spacing: 0.5px; }
    .metric-value { font-size: 32px; font-weight: 700; color: #FFFFFF; margin: 4px 0; }
    .metric-delta { font-size: 13px; font-weight: 500; margin-top: 4px; }
    
    /* 緊湊列表樣式 (用於 Movers/Losers) */
    .tight-list-item {
        display: flex;
        justify-content: space-between;
        padding: 8px 0;
        border-bottom: 1px solid #333333;
        font-size: 14px;
    }
    .tight-list-item:last-child { border-bottom: none; }
    .stock-name { font-weight: 600; color: #E0E0E0; }
    
    /* 按鈕樣式微調 */
    div.stButton > button {
        border-radius: 6px;
        font-weight: 600;
        height: 42px; /* 與標題高度對齊 */
    }
    
    /* Plotly 圖表文字顏色強制修正 */
    .g-gtitle, .g-xtitle, .g-ytitle { fill: #E0E0E0 !important; }
</style>
""", unsafe_allow_html=True)

# 2. 輔助函式：產生 HTML 卡片
def dashboard_card(title, value, delta_text, delta_color, bar_color):
    """
    生成仿圖中的 KPI 卡片 HTML
    """
    delta_html = ""
    if delta_text:
        color_hex = "#00E676" if delta_color == "green" else "#FF5252"
        delta_html = f'<div class="metric-delta" style="color: {color_hex};">{delta_text}</div>'
    
    # 使用 min-height 確保卡片高度一致
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
# 4. 側邊欄
# ==============================================================================
with st.sidebar:
    st.header("戰情室導航")
    st.info("💡 提示：如需「新增交易」或「查詢明細」，請點擊左側頁籤前往 **帳務管理**。")
    st.divider()
    if st.session_state["price_update_time"]:
        st.caption(f"🕒 最後更新: {st.session_state['price_update_time']}")
    else:
        st.caption("🕒 尚未更新 (顯示庫存成本)")

# ==============================================================================
# 5. Dashboard 渲染核心
# ==============================================================================

# 頂部標題與更新按鈕 (對齊優化)
c_head, c_btn = st.columns([7, 1])
with c_head:
    st.markdown("## 🌐 Global Asset Overview")
with c_btn:
    # 使用 primary type 讓按鈕在深色模式下更顯眼
    if st.button("🔄 更新數據", type="primary", use_container_width=True):
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
    # --- 計算核心數據 ---
    acc_balances = logic.calculate_account_balances(df_raw)
    total_cash = sum(acc_balances.values())
    
    df_fifo = logic.calculate_fifo_report(df_raw)
    current_prices = st.session_state.get("realtime_prices", {})
    df_unrealized = logic.calculate_unrealized_pnl(df_fifo, current_prices)
    
    total_market_value = df_unrealized['股票市值'].sum() if not df_unrealized.empty else 0
    total_unrealized_pnl = df_unrealized['未實現損益'].sum() if not df_unrealized.empty else 0
    total_cost = df_unrealized['總持有成本 (FIFO)'].sum() if not df_unrealized.empty else 0
    
    # 總資產
    total_assets = total_cash + total_market_value
    # 現金水位
    cash_ratio = (total_cash / total_assets * 100) if total_assets > 0 else 0

    # --- ROW 1: KPI Cards (調整為 3 欄) ---
    k1, k2, k3 = st.columns(3)
    
    with k1:
        # [Fix] 修正格式化字串為 :+, (先符號再千分位)
        dashboard_card(
            title="Total Net Worth",
            value=f"${int(total_assets):,}",
            delta_text=f"Unrealized: ${int(total_unrealized_pnl):+,}", 
            delta_color="green" if total_unrealized_pnl > 0 else "red",
            bar_color="#29B6F6" # Light Blue
        )
        
    with k2:
        # 紫色: 現金
        dashboard_card(
            title="Liquidity / Cash",
            value=f"${int(total_cash):,}",
            delta_text=f"{cash_ratio:.1f}% of Portfolio",
            delta_color="green", 
            bar_color="#AB47BC" # Purple
        )

    with k3:
        # 灰色: 持股成本
        dashboard_card(
            title="Invested Cost",
            value=f"${int(total_cost):,}",
            delta_text="Total Cost Basis",
            delta_color="green", # Neutral
            bar_color="#78909C" # Blue Grey
        )
    
    st.markdown("<br>", unsafe_allow_html=True)

    # --- ROW 2: Charts & Alerts (3 欄配置) ---
    # Col 1: 持股配置, Col 2: 帳戶資金, Col 3: Alerts
    c1, c2, c3 = st.columns(3)
    
    # 1. Asset Allocation (持股)
    with c1:
        with st.container(border=True):
            st.markdown("##### Stock Allocation")
            if not df_unrealized.empty and total_market_value > 0:
                # 準備資料
                sorted_stocks = df_unrealized.sort_values('股票市值', ascending=False)
                fig_pie = px.pie(sorted_stocks, values='股票市值', names='股票名稱', hole=0.6)
                fig_pie.update_traces(textinfo='percent', textposition='inside')
                fig_pie.update_layout(
                    template="plotly_dark",
                    showlegend=True,
                    legend=dict(orientation="h", y=-0.2), # 圖例在下方
                    margin=dict(t=10, b=10, l=10, r=10),
                    height=250,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#E0E0E0') # 強制字體為亮色
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("尚無持股資料")
                st.write("")
                st.write("") # 佔位

    # 2. Account Cash (帳戶資金 - 取代原本的趨勢圖)
    with c2:
        with st.container(border=True):
            st.markdown("##### Cash by Account")
            if total_cash > 0:
                pie_data = []
                for acc_name, amount in acc_balances.items():
                    if amount > 0:
                        pie_data.append({'Account': acc_name, 'Value': amount})
                
                df_cash = pd.DataFrame(pie_data)
                
                fig_cash = px.pie(df_cash, values='Value', names='Account', hole=0.6,
                                  color_discrete_sequence=px.colors.qualitative.Pastel) # 使用柔和色系
                fig_cash.update_traces(textinfo='percent', textposition='inside')
                fig_cash.update_layout(
                    template="plotly_dark",
                    showlegend=True,
                    legend=dict(orientation="h", y=-0.2),
                    margin=dict(t=10, b=10, l=10, r=10),
                    height=250,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#E0E0E0') # 強制字體為亮色
                )
                st.plotly_chart(fig_cash, use_container_width=True)
            else:
                st.info("無現金餘額")
                st.write("")
                st.write("")

    # 3. Alerts & Actions (移至此層)
    with c3:
        # 使用自訂高度使其與圓餅圖區塊等高
        with st.container(border=True):
            st.markdown("##### ⚠️ Alerts & Actions")
            
            # 使用 HTML 列表來控制間距
            alerts_html = ""
            
            # (A) 資金水位
            if cash_ratio < 10:
                alerts_html += f"<div class='tight-list-item'><span class='stock-name'>🔴 Cash Level</span><span>Critical (&lt;10%)</span></div>"
            elif cash_ratio > 80:
                alerts_html += f"<div class='tight-list-item'><span class='stock-name'>🟡 Cash Level</span><span>High (&gt;80%)</span></div>"
            else:
                alerts_html += f"<div class='tight-list-item'><span class='stock-name'>🟢 Cash Level</span><span>Healthy ({cash_ratio:.0f}%)</span></div>"
            
            # (B) 停損監控
            if not df_unrealized.empty:
                danger_count = len(df_unrealized[df_unrealized['報酬率 (%)'] < -20])
                if danger_count > 0:
                    alerts_html += f"<div class='tight-list-item'><span class='stock-name'>🔴 Stop Loss</span><span>{danger_count} stocks &lt; -20%</span></div>"
                else:
                    alerts_html += f"<div class='tight-list-item'><span class='stock-name'>🟢 Stop Loss</span><span>All Clear</span></div>"
            
            # (C) 獲利領頭羊
            if not df_unrealized.empty:
                best_stock = df_unrealized.sort_values('報酬率 (%)', ascending=False).iloc[0]
                if best_stock['報酬率 (%)'] > 0:
                     alerts_html += f"<div class='tight-list-item'><span class='stock-name'>🏆 Best Performer</span><span>{best_stock['股票名稱']} (+{best_stock['報酬率 (%)']:.1f}%)</span></div>"

            st.markdown(alerts_html, unsafe_allow_html=True)
            
            # 填補高度 (Spacer)
            st.write("")
            st.write("")
            st.write("")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- ROW 3: Top Movers & Losers (間距優化版) ---
    b1, b2 = st.columns(2)
    
    # Left: Top Movers (Gainers)
    with b1:
        with st.container(border=True):
            st.markdown("##### 🚀 Top Gainers")
            if not df_unrealized.empty:
                top_gainers = df_unrealized.sort_values('報酬率 (%)', ascending=False).head(5)
                # 只顯示賺錢的
                top_gainers = top_gainers[top_gainers['報酬率 (%)'] > 0]
                
                if not top_gainers.empty:
                    html_list = ""
                    for _, row in top_gainers.iterrows():
                        html_list += f"""
                        <div class='tight-list-item'>
                            <span class='stock-name'>{row['股票名稱']} ({row['股票代號']})</span>
                            <span style='color:#00E676; font-weight:bold;'>+{row['報酬率 (%)']:.2f}%</span>
                        </div>
                        """
                    st.markdown(html_list, unsafe_allow_html=True)
                else:
                    st.caption("No positive returns yet.")
            else:
                st.caption("No Data")

    # Right: Top Losers
    with b2:
        with st.container(border=True):
            st.markdown("##### 📉 Top Losers")
            if not df_unrealized.empty:
                top_losers = df_unrealized.sort_values('報酬率 (%)', ascending=True).head(5)
                # 只顯示賠錢的
                top_losers = top_losers[top_losers['報酬率 (%)'] < 0]
                
                if not top_losers.empty:
                    html_list = ""
                    for _, row in top_losers.iterrows():
                        html_list += f"""
                        <div class='tight-list-item'>
                            <span class='stock-name'>{row['股票名稱']} ({row['股票代號']})</span>
                            <span style='color:#FF5252; font-weight:bold;'>{row['報酬率 (%)']:.2f}%</span>
                        </div>
                        """
                    st.markdown(html_list, unsafe_allow_html=True)
                else:
                    st.caption("No negative returns.")
            else:
                st.caption("No Data")

# 6. 主程式執行
if df_raw.empty:
    st.info("目前沒有任何交易資料，請前往「帳務管理」頁面新增第一筆交易。")
else:
    render_dashboard(df_raw)
