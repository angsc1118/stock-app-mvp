# ==============================================================================
# 檔案名稱: pages/2_Realtime_Monitoring.py
# 
# 修改歷程:
# 2025-11-23: [Update] 整合動能監測；新增「預估量」、「量比」欄位；使用 mp_table 查表
# ==============================================================================

import streamlit as st
import pandas as pd
import time
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

# 讀取 mp_table (時間倍數表)
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
    
    # 1. 決定要監控的股票清單
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

    # 2. 抓取資料 (即時報價 + 技術指標)
    try:
        quotes = market_data.get_batch_detailed_quotes(target_stocks)
        ta_data = st.session_state.get("ta_data", {})
    except Exception as e:
        st.error(f"資料抓取失敗: {e}")
        return

    # 3. 取得當前時間與倍數 (使用台灣時間)
    # 必須加 8 小時，因為 Streamlit Cloud 是 UTC
    tw_now = datetime.utcnow() + timedelta(hours=8)
    current_time_str = tw_now.strftime("%H:%M")
    
    # 查表取得 multiplier
    multiplier = logic.get_volume_multiplier(current_time_str, df_mp)

    # 4. 組裝表格資料
    table_rows = []
    alerts = []

    for symbol in target_stocks:
        quote = quotes.get(symbol, {})
        price = quote.get('price', 0)
        chg = quote.get('change_pct', 0)
        vol = quote.get('volume', 0) # 這是「張」數
        
        # 取得 TA
        ta = ta_data.get(symbol, {})
        signal = ta.get('Signal', '-')
        ma20 = ta.get('MA20', 0)
        bias = ta.get('Bias', 0)
        vol_10ma = ta.get('Vol10', 0) # 10日均量 (張)
        
        # 計算動能 (量比)
        # 注意：成交量單位要一致 (通常 API 回傳單位是股或張，需確認)
        # Fugle API 成交量單位通常是「張」(board_lot)，若是零股需注意
        # 假設 Vol10 與 vol 單位一致
        est_vol, vol_ratio = logic.calculate_volume_ratio(vol, vol_10ma, multiplier)

        # 取得基本資料 (名稱、警示設定)
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

        # 警示判斷
        status_icon = ""
        
        # A. 價格警示
        if high_limit > 0 and price >= high_limit:
            alerts.append(f"🔴 **{name} ({symbol})** 突破目標價 {high_limit} (現價 {price})")
            status_icon += "🔴"
        if low_limit > 0 and price > 0 and price <= low_limit:
            alerts.append(f"📉 **{name} ({symbol})** 跌破支撐價 {low_limit} (現價 {price})")
            status_icon += "📉"
            
        # B. 動能警示 (量比)
        if vol_ratio > 2.0:
            status_icon += "🔥" # 爆量
        elif vol_ratio > 1.5:
            status_icon += "🟢" # 增量
            
        # C. 技術警示
        if bias > 20: status_icon += "⚠️"
        
        table_rows.append({
            "代號": symbol,
            "名稱": name,
            "現價": price,
            "漲跌幅": chg / 100,
            "成交量": vol,
            "預估量": est_vol,
            "10日均量": int(vol_10ma),
            "量比": vol_ratio,
            "月線乖離率": f"{bias}%",
            "技術訊號": signal,
            "警示": status_icon
        })

    # 5. 顯示內容
    st.caption(f"最後更新: {tw_now.strftime('%H:%M:%S')} | 預估倍數: {multiplier}")

    if alerts:
        for alert in alerts:
            st.error(alert)
    
    if table_rows:
        df_display = pd.DataFrame(table_rows)
        
        st.dataframe(
            df_display,
            column_config={
                "漲跌幅": st.column_config.NumberColumn(
                    "漲跌幅",
                    format="%.2f%%",
                ),
                "現價": st.column_config.NumberColumn(
                    "現價",
                    format="$%.2f",
                ),
                "成交量": st.column_config.NumberColumn("現量", format="%d"),
                "預估量": st.column_config.NumberColumn("預估量", format="%d"),
                "10日均量": st.column_config.NumberColumn("10MA量", format="%d"),
                "量比": st.column_config.NumberColumn(
                    "量比",
                    format="%.2f",
                )
            },
            use_container_width=True,
            hide_index=True
        )
        
        # 手動更新 TA 按鈕
        if st.button("🔄 更新技術指標 (均線/均量)"):
            with st.spinner("計算技術指標中..."):
                new_ta = market_data.get_batch_technical_analysis(target_stocks)
                current_ta = st.session_state.get("ta_data", {})
                current_ta.update(new_ta)
                st.session_state["ta_data"] = current_ta
                st.rerun()

# ==============================================================================
# 4. 執行渲染
# ==============================================================================

if not groups:
    st.warning("無法讀取「自選股清單」或「交易紀錄」。請確認 Google Sheet 設定。")
else:
    render_monitor_table(selected_group, inventory_stocks, df_watch, df_mp)
