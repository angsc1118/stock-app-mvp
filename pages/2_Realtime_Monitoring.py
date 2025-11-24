# ==============================================================================
# 檔案名稱: pages/2_Realtime_Monitoring.py
# 
# 修改歷程:
# 2025-11-24 17:00:00: [Debug] 新增詳細的量比計算參數除錯表 (檢查現量、倍數、均量)
# 2025-11-24 14:50:00: [Fix] 修正量比顯示問題；優化 Vol10 與量比的格式化邏輯
# ==============================================================================

import streamlit as st
import pandas as pd
import time
import math
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
        if '群組' in df_watch.columns: groups += df_watch['群組'].unique().tolist()
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
    - 🔴 **突破**: 現價 >= 高
    - 📉 **跌破**: 現價 <= 低
    - ⚠️ **乖離**: > 20%
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
        # 從 Session 讀取 TA 資料
        ta_data = st.session_state.get("ta_data", {})
    except Exception as e:
        st.error(f"資料抓取失敗: {e}")
        return

    # 3. 取得當前時間與倍數 (使用台灣時間)
    tw_now = datetime.utcnow() + timedelta(hours=8)
    current_time_str = tw_now.strftime("%H:%M")
    
    # 查表取得 multiplier
    multiplier = logic.get_volume_multiplier(current_time_str, df_mp)

    # 4. 組裝表格資料
    table_rows = []
    alerts = []
    debug_ta_list = []      # 原有的 TA Debug
    debug_calc_list = []    # [新增] 量比計算 Debug
    
    # 檢查是否有 TA 資料
    if not ta_data:
        st.warning("⚠️ 尚未取得「10日均量」資料，量比無法計算。請點擊下方「🔄 更新技術指標」按鈕。")

    for symbol in target_stocks:
        quote = quotes.get(symbol, {})
        price = quote.get('price', 0)
        chg = quote.get('change_pct', 0)
        vol = quote.get('volume', 0) # 盤中量 (張)
        
        # TA 資料
        ta = ta_data.get(symbol, {})
        signal = ta.get('Signal', '-')
        ma20 = ta.get('MA20', 0)
        bias = ta.get('Bias', 0)
        vol_10ma = ta.get('Vol10', 0) # 10日均量 (張)
        
        # 收集 TA Debug 資訊
        if 'debug_info' in ta:
            debug_ta_list.append({
                '股票代號': symbol,
                '10日均量(Vol10)': vol_10ma,
                '歷史資料(末3筆)': ta['debug_info']
            })
        
        # 計算動能
        est_vol, vol_ratio = logic.calculate_volume_ratio(vol, vol_10ma, multiplier)

        # 收集 Calculation Debug 資訊 [新增]
        debug_calc_list.append({
            '股票代號': symbol,
            '現量 (Vol)': vol,
            '倍數 (Mult)': multiplier,
            '預估量 (Est)': est_vol,
            '10日均量 (MA10)': vol_10ma,
            '量比 (Ratio)': vol_ratio
        })

        # 取得基本資料
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
            
        # B. 動能警示
        if vol_ratio > 2.0: status_icon += "🔥"
        elif vol_ratio > 1.5: status_icon += "🟢"
            
        # C. 技術警示
        if bias > 20: status_icon += "⚠️"
        
        # 格式化處理
        price_str = f"{price:,.2f}"
        
        # 漲跌幅
        chg_str = f"{chg*100:.2f}%" if abs(chg) < 1 else f"{chg:.2f}%"

        # 成交量
        vol_str = f"{vol:,}"
        est_vol_str = f"{est_vol:,}"
        
        # 10MA 量顯示邏輯
        if vol_10ma > 0:
            vol_10ma_lots = math.ceil(vol_10ma / 1000)
            vol_10ma_str = f"{vol_10ma_lots:,}"
            
            # 量比顯示邏輯
            if vol == 0:
                vol_ratio_str = "0.00 (無量)" # 明確標示現量為0
            else:
                vol_ratio_str = f"{vol_ratio:.2f}"
        else:
            vol_10ma_str = "N/A"
            vol_ratio_str = "-" # 無法計算

        table_rows.append({
            "代號": symbol,
            "名稱": name,
            "現價": price_str,
            "漲跌幅": chg_str,
            "成交量": vol_str,
            "預估量": est_vol_str,
            "10日均量": vol_10ma_str,
            "量比": vol_ratio_str,
            "月線乖離率": f"{bias:.2f}%",
            "技術訊號": signal,
            "警示": status_icon
        })

    # 5. 顯示內容
    st.caption(f"最後更新: {tw_now.strftime('%H:%M:%S')} | 量能倍數: {multiplier}")

    if alerts:
        for alert in alerts:
            st.error(alert)
    
    if table_rows:
        df_display = pd.DataFrame(table_rows)
        
        st.dataframe(
            df_display,
            column_config={
                "代號": st.column_config.TextColumn("代號", width="small"),
                "名稱": st.column_config.TextColumn("名稱", width="small"),
                "現價": st.column_config.TextColumn("現價", width="small"),
                "漲跌幅": st.column_config.TextColumn("漲跌幅", width="small"),
                "成交量": st.column_config.TextColumn("現量", width="small"),
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
        
        # 手動更新 TA 按鈕
        if st.button("🔄 更新技術指標 (均線/均量)"):
            with st.spinner("計算技術指標中 (抓取歷史K線)..."):
                new_ta = market_data.get_batch_technical_analysis(target_stocks)
                # 更新 session
                current_ta = st.session_state.get("ta_data", {})
                current_ta.update(new_ta)
                st.session_state["ta_data"] = current_ta
                st.rerun()
                
        # 除錯資訊區塊
        with st.expander("🛠️ 除錯資訊 (量比計算來源)"):
            st.info("若量比顯示 0.00，請檢查「現量」或「倍數」是否為 0。若 10日均量 為 N/A，請按上方更新按鈕。")
            
            tab_debug1, tab_debug2 = st.tabs(["🔢 量比計算參數明細", "📊 歷史資料 (Vol10來源)"])
            
            with tab_debug1:
                st.dataframe(pd.DataFrame(debug_calc_list), use_container_width=True)
                
            with tab_debug2:
                st.markdown("API 抓取到的**歷史 K 線末 3 筆資料** (檢查是否包含今日導致均量失真)：")
                st.write(debug_ta_list)

# ==============================================================================
# 4. 執行渲染
# ==============================================================================

if not groups:
    st.warning("無法讀取「自選股清單」或「交易紀錄」。請確認 Google Sheet 設定。")
else:
    render_monitor_table(selected_group, inventory_stocks, df_watch, df_mp)