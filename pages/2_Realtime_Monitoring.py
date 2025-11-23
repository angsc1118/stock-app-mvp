# ==============================================================================
# 檔案名稱: pages/2_Realtime_Monitoring.py
# 
# 修改歷程:
# 2025-11-23 20:35:00: [Update] 10日均量改為千張(無條件進位)；調整欄位寬度(small/medium)
# 2025-11-23 19:53:00: [Update] 調整盤中戰情監控；現價移除$；格式套用千分位
# ==============================================================================

import streamlit as st
import pandas as pd
import time
import math # 新增 math 模組用於無條件進位
from datetime import datetime, timedelta

import database
import logic
import market_data

st.set_page_config(page_title="盤中監控", layout="wide", page_icon="🚀")
st.title("🚀 盤中戰情監控")

# ==============================================================================
# 1. 資料準備
# ==============================================================================

# 讀取庫存
try:
    df_txn = database.load_data()
    df_fifo = logic.calculate_fifo_report(df_txn)
    inventory_stocks = df_fifo['股票代號'].unique().tolist() if not df_fifo.empty else []
except:
    inventory_stocks = []

# 讀取自選股
try:
    df_watch = database.load_watchlist()
    if not df_watch.empty and '股票代號' in df_watch.columns:
        df_watch['股票代號'] = df_watch['股票代號'].astype(str).str.strip()
        groups = ["全部", "庫存持股"]
        if '群組' in df_watch.columns:
            groups += df_watch['群組'].unique().tolist()
        groups = list(set(groups))
        groups.sort()
    else:
        groups = ["全部", "庫存持股"]
        df_watch = pd.DataFrame(columns=['群組', '股票代號', '股票名稱', '警示價_高', '警示價_低', '備註'])
except:
    groups = ["全部", "庫存持股"]
    df_watch = pd.DataFrame(columns=['群組', '股票代號', '股票名稱', '警示價_高', '警示價_低', '備註'])

try:
    df_mp = database.load_mp_table()
except:
    df_mp = pd.DataFrame()

# ==============================================================================
# 2. 側邊欄設定
# ==============================================================================
with st.sidebar:
    st.header("⚙️ 監控設定")
    selected_group = st.selectbox("選擇監控群組", groups)
    
    auto_refresh = st.toggle("啟用自動刷新 (30秒)", value=False)
    st.caption("⚠️ 注意：頻繁刷新會消耗 API 額度")
    
    st.divider()
    st.markdown("### 💡 警示圖示說明")
    st.markdown("""
    - 🔥 **爆量**: 量比 > 2.0
    - 🟢 **增量**: 量比 > 1.5
    - 🔴 **突破**: 現價 >= 警示價(高)
    - 📉 **跌破**: 現價 <= 警示價(低)
    - ⚠️ **乖離**: 月線乖離率 > 20%
    """)

# ==============================================================================
# 3. 核心監控邏輯 (Fragment)
# ==============================================================================

@st.fragment(run_every=30 if auto_refresh else None)
def render_monitor_table(selected_group, inventory_list, df_watch, df_mp):
    
    target_stocks = []
    if selected_group == "全部":
        watch_list = df_watch['股票代號'].tolist() if not df_watch.empty else []
        target_stocks = list(set(inventory_list + watch_list))
    elif selected_group == "庫存持股":
        target_stocks = inventory_list
    else:
        if not df_watch.empty:
            target_stocks = df_watch[df_watch['群組'] == selected_group]['股票代號'].tolist()
    
    if not target_stocks:
        st.info("此群組無股票可監控。")
        return

    try:
        quotes = market_data.get_batch_detailed_quotes(target_stocks)
        ta_data = st.session_state.get("ta_data", {})
    except Exception as e:
        st.error(f"資料抓取失敗: {e}")
        return

    tw_now = datetime.utcnow() + timedelta(hours=8)
    current_time_str = tw_now.strftime("%H:%M")
    multiplier = logic.get_volume_multiplier(current_time_str, df_mp)

    table_rows = []
    alerts = []
    debug_list = []

    for symbol in target_stocks:
        quote = quotes.get(symbol, {})
        price = quote.get('price', 0)
        chg = quote.get('change_pct', 0)
        vol = quote.get('volume', 0)
        
        ta = ta_data.get(symbol, {})
        signal = ta.get('Signal', '-')
        ma20 = ta.get('MA20', 0)
        bias = ta.get('Bias', 0)
        vol_10ma = ta.get('Vol10', 0)
        
        if 'debug_info' in ta:
            debug_list.append({
                '股票代號': symbol,
                '10日均量(原始)': vol_10ma,
                '歷史資料(末3筆)': ta['debug_info']
            })
        
        est_vol, vol_ratio = logic.calculate_volume_ratio(vol, vol_10ma, multiplier)

        name = ""
        high_limit = 0
        low_limit = 0
        watch_info = df_watch[df_watch['股票代號'] == symbol]
        if not watch_info.empty:
            name = watch_info.iloc[0]['股票名稱']
            try: high_limit = float(watch_info.iloc[0]['警示價_高'])
            except: high_limit = 0
            try: low_limit = float(watch_info.iloc[0]['警示價_低'])
            except: low_limit = 0
        
        if not name:
            stock_map = database.get_stock_info_map()
            name = stock_map.get(symbol, symbol)

        status_icon = ""
        if high_limit > 0 and price >= high_limit:
            alerts.append(f"🔴 **{name} ({symbol})** 突破目標價 {high_limit} (現價 {price})")
            status_icon += "🔴"
        if low_limit > 0 and price > 0 and price <= low_limit:
            alerts.append(f"📉 **{name} ({symbol})** 跌破支撐價 {low_limit} (現價 {price})")
            status_icon += "📉"
            
        if vol_ratio > 2.0: status_icon += "🔥"
        elif vol_ratio > 1.5: status_icon += "🟢"
        if bias > 20: status_icon += "⚠️"
        
        # --- 格式化處理 ---
        
        price_str = f"{price:,.2f}"
        
        # 漲跌幅
        chg_str = f"{chg*100:.2f}%" if abs(chg) < 1 else f"{chg:.2f}%"

        # 成交量
        vol_str = f"{vol:,}"
        est_vol_str = f"{est_vol:,}"
        
        # 10MA 量：除以 1000 並無條件進位 (轉為張數)
        vol_10ma_lots = math.ceil(vol_10ma / 1000) if vol_10ma else 0
        vol_10ma_str = f"{vol_10ma_lots:,}"

        table_rows.append({
            "代號": symbol,
            "名稱": name,
            "現價": price_str,
            "漲跌幅": chg_str,
            "成交量": vol_str,
            "預估量": est_vol_str,
            "10日均量": vol_10ma_str,
            "量比": f"{vol_ratio:.2f}",
            "月線乖離率": f"{bias:.2f}%",
            "技術訊號": signal,
            "警示": status_icon
        })

    st.caption(f"最後更新: {tw_now.strftime('%H:%M:%S')} | 預估倍數: {multiplier}")

    if alerts:
        for alert in alerts:
            st.error(alert)
    
    if table_rows:
        df_display = pd.DataFrame(table_rows)
        
        # 使用 column_config 控制寬度
        st.dataframe(
            df_display,
            column_config={
                "代號": st.column_config.TextColumn("代號", width="small"),
                "名稱": st.column_config.TextColumn("名稱", width="small"),
                "現價": st.column_config.TextColumn("現價", width="small"),
                "漲跌幅": st.column_config.TextColumn("漲跌幅", width="small"),
                "成交量": st.column_config.TextColumn("成交量", width="small"),
                "預估量": st.column_config.TextColumn("預估量", width="small"),
                "10日均量": st.column_config.TextColumn("10日均量", width="small"),
                "量比": st.column_config.TextColumn("量比", width="small"),
                "月線乖離率": st.column_config.TextColumn("月線乖離率", width="small"),
                "技術訊號": st.column_config.TextColumn("技術訊號", width="medium"),
                "警示": st.column_config.TextColumn("警示", width="small"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        if st.button("🔄 更新技術指標 (均線/均量)"):
            with st.spinner("計算技術指標中..."):
                new_ta = market_data.get_batch_technical_analysis(target_stocks)
                current_ta = st.session_state.get("ta_data", {})
                current_ta.update(new_ta)
                st.session_state["ta_data"] = current_ta
                st.rerun()
                
        with st.expander("🛠️ 技術指標除錯資訊 (查看 Vol10 來源)"):
            st.markdown("API 原始資料 (單位: 股，上方表格已轉為張):")
            st.write(debug_list)

# ==============================================================================
# 4. 執行渲染
# ==============================================================================

if not groups:
    st.warning("無法讀取「自選股清單」或「交易紀錄」。請確認 Google Sheet 設定。")
else:
    render_monitor_table(selected_group, inventory_stocks, df_watch, df_mp)