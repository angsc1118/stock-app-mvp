import streamlit as st
import pandas as pd
import time
from datetime import datetime

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
    # 確保欄位存在
    if not df_watch.empty and '股票代號' in df_watch.columns:
        # 清理代號
        df_watch['股票代號'] = df_watch['股票代號'].astype(str).str.strip()
        
        # 取得所有群組選項
        groups = ["全部", "庫存持股"]
        if '群組' in df_watch.columns:
            groups += df_watch['群組'].unique().tolist()
        groups = list(set(groups)) # 去重
        groups.sort()
    else:
        groups = ["全部", "庫存持股"]
        df_watch = pd.DataFrame(columns=['群組', '股票代號', '股票名稱', '警示價_高', '警示價_低', '備註'])
except:
    groups = ["全部", "庫存持股"]
    df_watch = pd.DataFrame(columns=['群組', '股票代號', '股票名稱', '警示價_高', '警示價_低', '備註'])

# ==============================================================================
# 2. 側邊欄設定
# ==============================================================================
with st.sidebar:
    st.header("⚙️ 監控設定")
    selected_group = st.selectbox("選擇監控群組", groups)
    
    auto_refresh = st.toggle("啟用自動刷新 (30秒)", value=False)
    st.caption("⚠️ 注意：頻繁刷新會消耗 API 額度")

# ==============================================================================
# 3. 核心監控邏輯 (Fragment)
# ==============================================================================

@st.fragment(run_every=30 if auto_refresh else None)
def render_monitor_table(selected_group, inventory_list, df_watch):
    
    # 1. 決定要監控的股票清單
    target_stocks = []
    
    if selected_group == "全部":
        # 合併庫存與自選，去重
        watch_list = df_watch['股票代號'].tolist() if not df_watch.empty else []
        target_stocks = list(set(inventory_list + watch_list))
    
    elif selected_group == "庫存持股":
        target_stocks = inventory_list
        
    else:
        # 特定自選群組
        if not df_watch.empty:
            target_stocks = df_watch[df_watch['群組'] == selected_group]['股票代號'].tolist()
    
    if not target_stocks:
        st.info("此群組無股票可監控。")
        return

    # 2. 抓取資料 (即時報價 + 技術指標)
    # 為了效能，這裡不顯示 spinner
    try:
        # 若 session 中沒有 TA 資料，或是手動強制更新時才抓 TA (因為 TA 很慢)
        # 這裡簡化策略：每次刷新只抓報價，TA 資料沿用 Session (需在首頁或手動按鈕更新)
        # 或者：我們只抓報價，TA 欄位顯示「需更新」
        
        quotes = market_data.get_batch_detailed_quotes(target_stocks)
        
        # 嘗試從 session 取得 TA 資料 (由首頁更新)，若無則不顯示或顯示舊的
        ta_data = st.session_state.get("ta_data", {})
        
    except Exception as e:
        st.error(f"資料抓取失敗: {e}")
        return

    # 3. 組裝表格資料
    table_rows = []
    alerts = [] # 警示清單

    for symbol in target_stocks:
        quote = quotes.get(symbol, {})
        price = quote.get('price', 0)
        chg = quote.get('change_pct', 0)
        vol = quote.get('volume', 0)
        
        # 取得 TA
        ta = ta_data.get(symbol, {})
        signal = ta.get('Signal', '-')
        ma20 = ta.get('MA20', 0)
        bias = ta.get('Bias', 0)
        
        # 取得基本資料 (名稱、警示設定)
        name = ""
        high_limit = 0
        low_limit = 0
        
        # 先找自選名單設定
        watch_info = df_watch[df_watch['股票代號'] == symbol]
        if not watch_info.empty:
            name = watch_info.iloc[0]['股票名稱']
            try: high_limit = float(watch_info.iloc[0]['警示價_高'])
            except: high_limit = 0
            try: low_limit = float(watch_info.iloc[0]['警示價_低'])
            except: low_limit = 0
        
        # 若自選沒名稱，找庫存名稱，再沒有就找 map
        if not name:
            # 嘗試從庫存找
            if symbol in inventory_list:
                # 這裡簡化，直接用 database map
                pass
        
        # 若還是沒名稱，從 mapping 找
        if not name:
            stock_map = database.get_stock_info_map()
            name = stock_map.get(symbol, symbol)

        # 警示判斷
        status_icon = ""
        if high_limit > 0 and price >= high_limit:
            alerts.append(f"🔴 **{name} ({symbol})** 突破目標價 {high_limit} (現價 {price})")
            status_icon += "🔥"
        if low_limit > 0 and price > 0 and price <= low_limit:
            alerts.append(f"🟢 **{name} ({symbol})** 跌破支撐價 {low_limit} (現價 {price})")
            status_icon += "📉"
            
        # 乖離率警示
        if bias > 20: status_icon += "⚠️乖離過大"
        
        table_rows.append({
            "代號": symbol,
            "名稱": name,
            "現價": price,
            "漲跌幅": chg / 100, # format 需要小數
            "成交量": vol,
            "技術訊號": signal,
            "乖離率": f"{bias}%",
            "月線": ma20,
            "警示": status_icon
        })

    # 4. 顯示警示區
    if alerts:
        for alert in alerts:
            st.error(alert)
    
    # 5. 顯示表格
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
                "成交量": st.column_config.NumberColumn(
                    "成交量",
                    format="%d",
                ),
            },
            use_container_width=True,
            hide_index=True
        )
        
        st.caption(f"最後更新: {datetime.now().strftime('%H:%M:%S')}")
        
        # 手動更新 TA 按鈕 (放在表格下方)
        if st.button("🔄 更新此清單技術指標 (耗時)"):
            with st.spinner("計算技術指標中..."):
                new_ta = market_data.get_batch_technical_analysis(target_stocks)
                # 更新 session
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
    render_monitor_table(selected_group, inventory_stocks, df_watch)
