import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, datetime, timedelta
import time

import database
import logic
import market_data

# 設定頁面配置
st.set_page_config(page_title="股票資產戰情室", layout="wide", page_icon="📈")

# ==============================================================================
# 1. 資料讀取與初始化
# ==============================================================================

if "realtime_prices" not in st.session_state: st.session_state["realtime_prices"] = {}
if "price_update_time" not in st.session_state: st.session_state["price_update_time"] = None
if "ta_data" not in st.session_state: st.session_state["ta_data"] = {}

try:
    df_raw = database.load_data()
except:
    df_raw = pd.DataFrame()

# ==============================================================================
# 2. 側邊欄：全域快速動作
# ==============================================================================
with st.sidebar:
    st.title("🚀 戰情室控制台")
    
    # 1. 更新股價
    if st.button("🔄 更新即時股價 (Fugle)", use_container_width=True):
        if not df_raw.empty:
            # 找出庫存股
            temp_fifo = logic.calculate_fifo_report(df_raw)
            if not temp_fifo.empty:
                stock_ids = temp_fifo['股票代號'].unique().tolist()
                with st.spinner('連線 API 更新報價中...'):
                    prices = market_data.get_realtime_prices(stock_ids)
                    # 順便更新技術指標
                    ta_data = market_data.get_batch_technical_analysis(stock_ids)
                
                st.session_state["realtime_prices"] = prices
                st.session_state["ta_data"] = ta_data
                tw_time = datetime.utcnow() + timedelta(hours=8)
                st.session_state["price_update_time"] = tw_time.strftime("%Y-%m-%d %H:%M:%S")
                st.rerun()
    
    if st.session_state["price_update_time"]:
        st.caption(f"🕒 最後更新: {st.session_state['price_update_time']}")
    else:
        st.caption("🕒 尚未更新 (顯示庫存成本)")

    st.divider()

    # 2. 記錄資產
    if not df_raw.empty:
        # 簡易計算當前總資產
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
                st.success(f"已記錄: ${_tot_asset:,}")
            except Exception as e:
                st.error(f"記錄失敗: {e}")

    st.info("💡 提示：如需「新增交易」或「查詢明細」，請點擊左側側邊欄的 **帳務管理** 頁面。")

# ==============================================================================
# 3. Dashboard 顯示邏輯 (Fragment)
# ==============================================================================

@st.fragment(run_every=60)
def render_dashboard(df_raw, auto_refresh=False):
    
    # 自動更新邏輯
    if auto_refresh and not df_raw.empty:
        temp_fifo = logic.calculate_fifo_report(df_raw)
        if not temp_fifo.empty:
            stock_ids = temp_fifo['股票代號'].unique().tolist()
            try:
                new_prices = market_data.get_realtime_prices(stock_ids)
                st.session_state["realtime_prices"] = new_prices
                tw_time = datetime.utcnow() + timedelta(hours=8)
                st.session_state["price_update_time"] = tw_time.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass # 自動更新失敗不報錯，避免干擾

    # --- 計算數據 ---
    acc_balances = logic.calculate_account_balances(df_raw)
    total_cash = sum(acc_balances.values())
    
    df_fifo = logic.calculate_fifo_report(df_raw)
    current_prices = st.session_state.get("realtime_prices", {})
    
    df_unrealized = logic.calculate_unrealized_pnl(df_fifo, current_prices)
    
    total_market_value = df_unrealized['股票市值'].sum() if not df_unrealized.empty else 0
    total_unrealized_pnl = df_unrealized['未實現損益'].sum() if not df_unrealized.empty else 0
    total_cost = df_unrealized['總持有成本 (FIFO)'].sum() if not df_unrealized.empty else 0
    unrealized_ret = (total_unrealized_pnl / total_cost * 100) if total_cost != 0 else 0
    
    df_realized_all = logic.calculate_realized_report(df_raw)
    this_year = date.today().year
    if not df_realized_all.empty:
        df_realized_ytd = df_realized_all[df_realized_all['年'] == this_year]
        total_realized_ytd = df_realized_ytd['已實現損益'].sum()
    else:
        total_realized_ytd = 0

    total_assets = total_cash + total_market_value
    cash_ratio = (total_cash / total_assets * 100) if total_assets > 0 else 0

    # --- 顯示 UI ---
    if auto_refresh:
        st.caption(f"⚡ 自動更新中... 最後更新: {st.session_state.get('price_update_time', 'N/A')}")
    
    # 1. KPI Cards
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("💰 總資產淨值", f"${int(total_assets):,}", help="現金 + 股票市值")
    k2.metric("📈 未實現損益", f"${int(total_unrealized_pnl):,}", delta=f"{unrealized_ret:.2f}%")
    k3.metric(f"📅 {this_year} 已實現損益", f"${int(total_realized_ytd):,}", delta=None)
    
    if cash_ratio > 90: ratio_color = "#FF4B4B"
    elif 80 <= cash_ratio < 90: ratio_color = "#FFA500"
    elif 70 <= cash_ratio < 80: ratio_color = "#1E90FF"
    elif 60 <= cash_ratio < 70: ratio_color = "#FFD700"
    else: ratio_color = "#09AB3B"
    
    k4.markdown(f"""
        <div style="text-align: left;">
            <div style="font-size: 14px; color: rgba(49, 51, 63, 0.6); margin-bottom: 4px;">現金水位</div>
            <div style="font-size: 32px; font-weight: 600; color: {ratio_color};">{cash_ratio:.2f}%</div>
        </div>
    """, unsafe_allow_html=True)

    st.divider()

    # 2. 圖表區
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

    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.subheader("🍰 現金配置 (各帳戶) vs 持股")
        if total_assets > 0:
            pie_data = []
            for acc_name, amount in acc_balances.items():
                if amount > 0:
                    pie_data.append({'類別': f'現金-{acc_name}', '金額': amount, 'Type': 'Cash'})
            if total_market_value > 0:
                pie_data.append({'類別': '股票部位', '金額': total_market_value, 'Type': 'Stock'})
            
            df_pie_alloc = pd.DataFrame(pie_data)
            
            with st.expander("查看詳細數值 (Debug)"):
                st.write(df_pie_alloc)

            df_pie_chart = df_pie_alloc[df_pie_alloc['金額'] > 0] if not df_pie_alloc.empty else pd.DataFrame()

            if not df_pie_chart.empty:
                fig_alloc = px.pie(df_pie_chart, values='金額', names='類別', hole=0.4, color='類別')
                fig_alloc.update_traces(textinfo='percent+label')
                fig_alloc.update_layout(hoverlabel=dict(font_size=20))
                st.plotly_chart(fig_alloc, use_container_width=True)
            else:
                st.warning("所有資產數值皆為 0 或負數。")
        else:
            st.info("資產為 0")

    with col_chart2:
        st.subheader("📊 持股分佈 (依市值)")
        if not df_unrealized.empty and total_market_value > 0:
            fig_stock_pie = px.pie(df_unrealized, values='股票市值', names='股票', hole=0.4)
            fig_stock_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_stock_pie.update_layout(showlegend=True, hoverlabel=dict(font_size=20)) 
            st.plotly_chart(fig_stock_pie, use_container_width=True)
        else:
            st.info("尚無持股資料")

# ==============================================================================
# 4. 主程式執行
# ==============================================================================

st.title('📊 投資戰情室')

if df_raw.empty:
    st.info("目前沒有任何交易資料，請前往「帳務管理」頁面新增第一筆交易。")
else:
    col_toggle, _ = st.columns([2, 8])
    auto_refresh_on = col_toggle.toggle("啟用盤中自動更新 (每60秒)", value=False)
    
    render_dashboard(df_raw, auto_refresh=auto_refresh_on)
