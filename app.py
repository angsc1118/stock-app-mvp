# ==============================================================================
# 檔案名稱: app.py
# 
# 修改歷程:
# 2025-12-05 14:00:00: [UI] 重大改版：仿照 Global Asset Overview 暗色儀表板風格
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
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        height: 100%;
    }
    
    /* KPI 卡片標題條 */
    .card-header-bar {
        height: 5px;
        width: 100%;
        border-radius: 5px 5px 0 0;
        margin-bottom: 10px;
    }
    
    /* 字體樣式 */
    .metric-label { font-size: 14px; color: #A0A0A0; font-weight: 500; }
    .metric-value { font-size: 28px; font-weight: 700; color: #FFFFFF; margin: 5px 0; }
    .metric-delta { font-size: 14px; font-weight: 500; }
    
    /* 表格樣式微調 */
    .stDataFrame { border: none !important; }
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
        delta_html = f'<span class="metric-delta" style="color: {color_hex};">{delta_text}</span>'
        
    html_code = f"""
    <div class="dashboard-card">
        <div class="card-header-bar" style="background-color: {bar_color};"></div>
        <div class="metric-label">{title}</div>
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
# 4. 側邊欄 (保持原樣，功能不變)
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

# 頂部標題與更新按鈕
c_head, c_btn = st.columns([6, 1])
with c_head:
    st.markdown("## 🌐 Global Asset Overview")
with c_btn:
    st.write("")
    if st.button("🔄 更新", use_container_width=True):
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
    
    # 報酬率
    unrealized_ret = (total_unrealized_pnl / total_cost * 100) if total_cost != 0 else 0
    # 總資產
    total_assets = total_cash + total_market_value
    # 現金水位
    cash_ratio = (total_cash / total_assets * 100) if total_assets > 0 else 0
    
    # 本金估算 (為了填補 Liabilities 空缺，我們改顯示總投入成本)
    total_invested = total_cost + total_cash # 粗略估算

    # --- ROW 1: KPI Cards (仿圖中的彩色卡片) ---
    k1, k2, k3, k4 = st.columns(4)
    
    with k1:
        # 藍色卡片: Total Net Worth
        dashboard_card(
            title="Total Net Worth (總資產)",
            value=f"${int(total_assets):,}",
            delta_text=f"↗ +${int(total_unrealized_pnl):,} (PnL)" if total_unrealized_pnl > 0 else f"↘ ${int(total_unrealized_pnl):,}",
            delta_color="green" if total_unrealized_pnl > 0 else "red",
            bar_color="#29B6F6" # Blue
        )
        
    with k2:
        # 綠色卡片: YTD Return (這裡暫用未實現報酬率代替)
        dashboard_card(
            title="Portfolio Return (報酬率)",
            value=f"{unrealized_ret:+.2f}%",
            delta_text="(Unrealized)",
            delta_color="green" if unrealized_ret > 0 else "red",
            bar_color="#66BB6A" # Green
        )

    with k3:
        # 紫色卡片: Liquidity / Cash
        dashboard_card(
            title="Liquidity / Cash (現金)",
            value=f"${int(total_cash):,}",
            delta_text=f"{cash_ratio:.1f}% of Portfolio",
            delta_color="green", # Neutral
            bar_color="#AB47BC" # Purple
        )

    with k4:
        # 灰色卡片: Total Cost (總成本/本金) - 取代 Liabilities
        dashboard_card(
            title="Invested Cost (持股成本)",
            value=f"${int(total_cost):,}",
            delta_text="Stock Only",
            delta_color="green",
            bar_color="#78909C" # Grey
        )
    
    st.markdown("<br>", unsafe_allow_html=True)

    # --- ROW 2: Charts (Donut + Line) ---
    c_left, c_right = st.columns([1, 2]) # 比例 1:2，右邊線圖寬一點
    
    # 左側：Asset Allocation (仿圖中甜甜圈圖)
    with c_left:
        with st.container(border=True): # 使用 Streamlit 原生 border container 模擬卡片
            st.markdown("##### Asset Allocation")
            if total_assets > 0:
                # 準備資料
                pie_data = []
                if total_cash > 0:
                    pie_data.append({'Type': 'Cash', 'Value': total_cash, 'Color': '#AB47BC'})
                if not df_unrealized.empty:
                    # 為了簡化，這裡將股票合併為 Stock，或者您可以依產業分類
                    # 這裡為了仿圖，我們將前三大持股列出，其餘合併
                    sorted_stocks = df_unrealized.sort_values('股票市值', ascending=False)
                    for i, row in sorted_stocks.iterrows():
                         pie_data.append({'Type': row['股票名稱'], 'Value': row['股票市值']})

                df_pie = pd.DataFrame(pie_data)
                
                # 使用 Plotly 畫甜甜圈
                fig_pie = px.pie(df_pie, values='Value', names='Type', hole=0.6)
                fig_pie.update_traces(textinfo='percent', textposition='inside')
                fig_pie.update_layout(
                    template="plotly_dark", # 關鍵：暗色主題
                    showlegend=True,
                    legend=dict(orientation="h", y=-0.1),
                    margin=dict(t=0, b=0, l=0, r=0),
                    height=300,
                    paper_bgcolor='rgba(0,0,0,0)', # 透明背景
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("無資產資料")

    # 右側：Performance Trend (仿圖中發光線圖)
    with c_right:
        with st.container(border=True):
            st.markdown("##### Performance Trend (Asset History)")
            df_history = database.load_asset_history()
            if not df_history.empty:
                df_history['日期'] = pd.to_datetime(df_history['日期'])
                df_history = df_history.sort_values('日期').drop_duplicates(subset=['日期'], keep='last')
                
                # 使用 Plotly Graph Objects 製作更精細的線圖 (Area Chart 模擬發光感)
                fig_line = go.Figure()
                fig_line.add_trace(go.Scatter(
                    x=df_history['日期'], 
                    y=df_history['總資產'],
                    fill='tozeroy', # 填充下方區域
                    mode='lines',
                    line=dict(color='#00E676', width=3), # 螢光綠線條
                    name='Total Asset'
                ))
                
                fig_line.update_layout(
                    template="plotly_dark",
                    margin=dict(l=0, r=0, t=20, b=0),
                    height=300,
                    xaxis=dict(showgrid=False), # 隱藏網格
                    yaxis=dict(showgrid=True, gridcolor='#333333'),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.info("尚無歷史資產紀錄，請點擊上方「更新」後並至流水帳頁面紀錄。")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- ROW 3: Bottom Sections (Top Movers & Alerts) ---
    # 原圖有 Map，我們資料沒有地理位置，改放 Top Movers 和 Alerts
    
    b1, b2, b3 = st.columns(3)
    
    # 左下：Top Gainers (取代 Map)
    with b1:
        with st.container(border=True):
            st.markdown("##### 🚀 Top Movers (Gainers)")
            if not df_unrealized.empty:
                # 依報酬率排序
                top_gainers = df_unrealized.sort_values('報酬率 (%)', ascending=False).head(5)
                for _, row in top_gainers.iterrows():
                    col_name, col_val = st.columns([2, 1])
                    with col_name:
                        st.markdown(f"**{row['股票名稱']}**")
                    with col_val:
                        st.markdown(f"<span style='color:#00E676'>+{row['報酬率 (%)']:.2f}%</span>", unsafe_allow_html=True)
                    st.divider()
            else:
                st.caption("No Data")

    # 中下：Holdings List (取代 Top Movers list of image)
    with b2:
        with st.container(border=True):
            st.markdown("##### 📉 Top Losers / Risk")
            if not df_unrealized.empty:
                # 依報酬率倒序
                top_losers = df_unrealized.sort_values('報酬率 (%)', ascending=True).head(5)
                for _, row in top_losers.iterrows():
                    val = row['報酬率 (%)']
                    color = "#FF5252" if val < 0 else "#00E676"
                    col_name, col_val = st.columns([2, 1])
                    with col_name:
                        st.markdown(f"**{row['股票名稱']}**")
                    with col_val:
                        st.markdown(f"<span style='color:{color}'>{val:.2f}%</span>", unsafe_allow_html=True)
                    st.divider()
            else:
                st.caption("No Data")

    # 右下：Alerts & Actions
    with b3:
        with st.container(border=True):
            st.markdown("##### ⚠️ Alerts & Actions")
            
            # 1. 資金水位警示
            if cash_ratio < 10:
                st.markdown("🔴 **Risk (Cash):** Low liquidity (<10%)")
            elif cash_ratio > 80:
                st.markdown("🟡 **Action:** High cash position (>80%)")
            else:
                st.markdown("🟢 **Liquidity:** Healthy")
            
            st.write("")
            
            # 2. 停損警示 (簡單版)
            if not df_unrealized.empty:
                danger_count = len(df_unrealized[df_unrealized['報酬率 (%)'] < -20])
                if danger_count > 0:
                    st.markdown(f"🔴 **Stop Loss:** {danger_count} stocks < -20%")
                else:
                    st.markdown("🟢 **Stop Loss:** No active alerts")
            
            st.write("")
            
            # 3. 功能連結
            st.caption("Quick Links:")
            st.page_link("pages/1_📝_帳務管理.py", label="Go to Ledger", icon="📝")
            st.page_link("pages/2_🚀_盤中監控.py", label="Live Monitor", icon="🚀")

# 6. 主程式執行
if df_raw.empty:
    st.info("目前沒有任何交易資料，請前往「帳務管理」頁面新增第一筆交易。")
else:
    render_dashboard(df_raw)
