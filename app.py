# ==============================================================================
# 檔案名稱: app.py
# 
# 修改歷程:
# 2025-12-01 11:10:00: [Feat] 新增資金水位試算 (子彈計算機)
# 2025-11-27 15:30:00: [UI] 復原圓餅圖帳戶細節；優化圖例位置
# 2025-11-27 13:45:00: [UI] 優化首頁 UX (行動版更新按鈕、台股紅漲綠跌 Metric、Toast 回饋)
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, datetime, timedelta
import time
import math

import database
import logic
import market_data

# 設定頁面配置
st.set_page_config(page_title="股票資產戰情室", layout="wide", page_icon="📈")

# 1. 初始化
if "realtime_prices" not in st.session_state: st.session_state["realtime_prices"] = {}
if "price_update_time" not in st.session_state: st.session_state["price_update_time"] = None
if "ta_data" not in st.session_state: st.session_state["ta_data"] = {}

try:
    df_raw = database.load_data()
except:
    df_raw = pd.DataFrame()

# ==============================================================================
# 2. 側邊欄 (保留導航與被動資訊，主動操作移至主畫面)
# ==============================================================================
with st.sidebar:
    st.header("戰情室導航")
    st.info("💡 提示：如需「新增交易」或「查詢明細」，請點擊左側頁籤前往 **帳務管理**。")
    
    st.divider()
    
    # 顯示最後更新時間 (被動資訊)
    if st.session_state["price_update_time"]:
        st.caption(f"🕒 最後更新: {st.session_state['price_update_time']}")
    else:
        st.caption("🕒 尚未更新 (顯示庫存成本)")

# ==============================================================================
# 3. 主畫面 Dashboard
# ==============================================================================

# --- [UI優化] 頂部區塊：標題 + 快速更新按鈕 (Mobile Friendly) ---
col_header, col_btn = st.columns([3, 1], gap="small")

with col_header:
    st.title("📈 股票資產戰情室")

with col_btn:
    # 增加垂直留白，讓按鈕對齊標題文字
    st.write("") 
    st.write("")
    if st.button("🔄 更新股價", use_container_width=True, help="連線 API 取得最新報價"):
        if not df_raw.empty:
            temp_fifo = logic.calculate_fifo_report(df_raw)
            if not temp_fifo.empty:
                stock_ids = temp_fifo['股票代號'].unique().tolist()
                
                # [UI優化] 使用 status 顯示詳細進度，取代 spinner
                with st.status("🚀 連線交易所主機中...", expanded=True) as status:
                    st.write("1. 正在抓取即時報價 (Fugle API)...")
                    prices = market_data.get_realtime_prices(stock_ids)
                    
                    st.write("2. 計算技術指標 (均線/量能)...")
                    ta_data = market_data.get_batch_technical_analysis(stock_ids)
                    
                    status.update(label="✅ 資料更新完成！", state="complete", expanded=False)
                
                st.session_state["realtime_prices"] = prices
                st.session_state["ta_data"] = ta_data
                tw_time = datetime.utcnow() + timedelta(hours=8)
                st.session_state["price_update_time"] = tw_time.strftime("%Y-%m-%d %H:%M:%S")
                
                # [UI優化] 使用 toast 進行輕量化通知
                st.toast("已更新最新股價資訊！", icon="🎉")
                time.sleep(1) # 稍作停留讓使用者看到 status 變綠
                st.rerun()
            else:
                st.toast("目前無庫存可更新", icon="ℹ️")

# Dashboard Fragment
@st.fragment(run_every=60)
def render_dashboard(df_raw, auto_refresh=False):
    # 計算基礎數據
    acc_balances = logic.calculate_account_balances(df_raw)
    total_cash = sum(acc_balances.values())
    
    df_fifo = logic.calculate_fifo_report(df_raw)
    current_prices = st.session_state.get("realtime_prices", {})
    df_unrealized = logic.calculate_unrealized_pnl(df_fifo, current_prices)
    
    total_market_value = df_unrealized['股票市值'].sum() if not df_unrealized.empty else 0
    total_unrealized_pnl = df_unrealized['未實現損益'].sum() if not df_unrealized.empty else 0
    total_cost = df_unrealized['總持有成本 (FIFO)'].sum() if not df_unrealized.empty else 0
    unrealized_ret = (total_unrealized_pnl / total_cost * 100) if total_cost != 0 else 0
    
    total_assets = total_cash + total_market_value
    cash_ratio = (total_cash / total_assets * 100) if total_assets > 0 else 0

    if auto_refresh: st.caption(f"⚡ 自動更新中... 最後更新: {st.session_state.get('price_update_time', 'N/A')}")
    
    # --- A. KPI 指標列 ---
    st.markdown("###") # 增加一點間距
    k1, k2, k3, k4 = st.columns(4)
    
    k1.metric("💰 總資產淨值", f"${int(total_assets):,}")
    k2.metric("💵 總現金餘額", f"${int(total_cash):,}")
    
    # 現金水位
    ratio_label = "💧 現金水位"
    k3.metric(ratio_label, f"{cash_ratio:.1f}%") 
    
    # [UI優化] 未實現損益：套用 delta_color="inverse" (台股紅漲綠跌)
    k4.metric(
        "📈 未實現損益", 
        f"${int(total_unrealized_pnl):,}", 
        delta=f"{unrealized_ret:.2f}%", 
        delta_color="inverse"
    )

    # --- [New Feature] 資金水位試算 (子彈計算機) ---
    with st.expander("🧮 資金水位試算 / 子彈計算機", expanded=False):
        st.markdown("##### 🎯 設定目標與試算")
        
        # 1. 計算當前水位 (作為 Slider 預設值)
        current_ratio_int = int(cash_ratio) if not math.isnan(cash_ratio) else 0
        
        # 2. 互動滑桿
        target_ratio = st.slider(
            "設定目標現金水位 (%)", 
            min_value=0, 
            max_value=100, 
            value=current_ratio_int, 
            step=5,
            help="拉動滑桿以計算該水位下，可動用的資金多寡"
        )
        
        # 3. 核心公式: X = 現金 - (總資產 * 目標比例)
        # 若 total_assets 為 0，保護除法
        if total_assets > 0:
            bullets = total_cash - (total_assets * (target_ratio / 100))
        else:
            bullets = 0
        
        # 4. 顯示結果 (區分 加碼 vs 減碼)
        c_calc1, c_calc2 = st.columns(2)
        
        with c_calc1:
            if bullets > 0:
                st.metric("🔫 可加碼投入 (子彈)", f"${int(bullets):,}", delta="Buy")
            elif bullets < 0:
                # 需賣出回收資金
                st.metric("🛑 需減碼回收 (賣出)", f"${int(abs(bullets)):,}", delta="Sell", delta_color="inverse")
            else:
                st.info("目前已達目標水位")
                
        with c_calc2:
            # 顯示試算後的預期狀態
            expected_cash = total_assets * (target_ratio / 100)
            expected_stock = total_assets - expected_cash
            st.caption(f"試算後現金: ${int(expected_cash):,}")
            st.caption(f"試算後持股: ${int(expected_stock):,}")

    st.divider()

    # B. 圖表區 (資產趨勢)
    # [UI優化] 記錄資產按鈕區塊 (放在圖表旁或上方)
    col_chart_header, col_record_btn = st.columns([4, 1])
    with col_chart_header:
        st.subheader("📈 資產成長趨勢")
    with col_record_btn:
        if st.button("📝 記錄今日資產", use_container_width=True, help="將當前資產寫入歷史紀錄"):
             try:
                today_tw = (datetime.utcnow() + timedelta(hours=8)).date()
                database.save_asset_history(today_tw, int(total_assets), int(total_cash), int(total_market_value))
                st.toast(f"✅ 已記錄今日資產: ${total_assets:,}", icon="💾")
             except Exception as e:
                st.toast(f"❌ 記錄失敗: {e}", icon="⚠️")

    df_history = database.load_asset_history()
    if not df_history.empty:
        df_history['日期'] = pd.to_datetime(df_history['日期'])
        df_history = df_history.sort_values('日期').drop_duplicates(subset=['日期'], keep='last')
        
        # [UI優化] 線圖顏色調整
        fig_trend = px.line(df_history, x='日期', y='總資產', markers=True)
        fig_trend.update_traces(line_color='#1E88E5', line_width=3, marker_size=8)
        fig_trend.update_layout(
            xaxis_title=None, 
            yaxis_title=None, 
            yaxis=dict(tickformat=",.0f"), 
            height=300,
            margin=dict(l=20, r=20, t=20, b=20)
        )
        st.plotly_chart(fig_trend, use_container_width=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

    # C. 圓餅圖
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.subheader("🍰 資產配置 (各帳戶現金 vs 持股)")
        if total_assets > 0:
            pie_data = []
            
            # [復原邏輯] 1. 遍歷顯示個別帳戶現金
            for acc_name, amount in acc_balances.items():
                if amount > 0:
                    pie_data.append({
                        '類別': f'現金-{acc_name}', 
                        '金額': amount,
                        'Group': 'Cash'
                    })
            
            # 2. 加入股票部位
            if total_market_value > 0:
                pie_data.append({
                    '類別': '股票部位', 
                    '金額': total_market_value,
                    'Group': 'Stock'
                })
            
            df_pie_alloc = pd.DataFrame(pie_data)
            
            if not df_pie_alloc.empty:
                # 讓 Plotly 自動分配顏色以區分不同帳戶
                fig_alloc = px.pie(df_pie_alloc, values='金額', names='類別', hole=0.5)
                fig_alloc.update_traces(textinfo='percent+label', textposition='inside')
                
                # 圖例移到底部
                fig_alloc.update_layout(
                    showlegend=True, 
                    margin=dict(t=20, b=20, l=20, r=20),
                    legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
                )
                st.plotly_chart(fig_alloc, use_container_width=True)
            else:
                st.info("無資產資料")

    with col_chart2:
        st.subheader("📊 持股分佈 (依市值)")
        if not df_unrealized.empty and total_market_value > 0:
            # 自動顯示前幾大持股
            fig_stock_pie = px.pie(df_unrealized, values='股票市值', names='股票', hole=0.5)
            fig_stock_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_stock_pie.update_layout(
                showlegend=True, 
                margin=dict(t=20, b=20, l=20, r=20),
                legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
            ) 
            st.plotly_chart(fig_stock_pie, use_container_width=True)
        else:
            st.info("尚無持股資料")

# 4. 主程式執行
if df_raw.empty:
    st.info("目前沒有任何交易資料，請前往「帳務管理」頁面新增第一筆交易。")
else:
    col_toggle, _ = st.columns([2, 8])
    auto_refresh_on = col_toggle.toggle("啟用盤中自動更新 (每60秒)", value=False)
    render_dashboard(df_raw, auto_refresh=auto_refresh_on)
