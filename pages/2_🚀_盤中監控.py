# ==============================================================================
# 檔案名稱: pages/2_🚀_盤中監控.py
# 
# 修改歷程:
# 2025-12-02 12:00:00: [UI] 漲跌幅欄位改為紅底/綠底；全面優化欄寬配置
# 2025-11-27 14:50:00: [Feat] 新增「自選股管理」編輯器
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
# 1. 資料準備與自選股管理
# ==============================================================================

# 讀取庫存
try:
    df_txn = database.load_data()
    df_fifo = logic.calculate_fifo_report(df_txn)
    inventory_stocks = df_fifo['股票代號'].unique().tolist() if not df_fifo.empty else []
except:
    inventory_stocks = []

# 自選股管理區塊 (維持原樣，省略部分重複代碼以節省篇幅，確保您有包含上一版的編輯器代碼)
with st.expander("⚙️ 管理自選股清單 (新增/刪除/設定警示)", expanded=False):
    # ... (請保留您上一版修正過後的編輯器程式碼) ...
    # 這裡為確保完整性，還是提供完整區塊
    st.caption("💡 操作說明：直接在下方表格修改。新增請點最後一列；刪除請選取列後按 Delete。完成後請務必點擊「💾 儲存變更」。")
    try:
        current_watchlist = database.load_watchlist()
    except:
        current_watchlist = pd.DataFrame(columns=['群組', '股票代號', '股票名稱', '警示價_高', '警示價_低', '備註'])
    column_order = ['群組', '股票代號', '股票名稱', '警示價_高', '警示價_低', '備註']
    for col in column_order:
        if col not in current_watchlist.columns: current_watchlist[col] = ""
    text_cols = ['群組', '股票代號', '股票名稱', '備註']
    for col in text_cols:
        current_watchlist[col] = current_watchlist[col].astype(str).replace('nan', '')
    num_cols = ['警示價_高', '警示價_低']
    for col in num_cols:
        current_watchlist[col] = pd.to_numeric(current_watchlist[col], errors='coerce')
    edited_watchlist = st.data_editor(
        current_watchlist[column_order],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "群組": st.column_config.SelectboxColumn("群組", options=["自選", "觀察", "短線", "長線", "動能" , "大戶" , "產業班" ], required=True),
            "股票代號": st.column_config.TextColumn("股票代號", required=True, validate="^[0-9A-Za-z]+$"),
            "股票名稱": st.column_config.TextColumn("股票名稱", required=True),
            "警示價_高": st.column_config.NumberColumn("警示價_高 (突破)", min_value=0, step=0.1, format="%.2f"),
            "警示價_低": st.column_config.NumberColumn("警示價_低 (跌破)", min_value=0, step=0.1, format="%.2f"),
            "備註": st.column_config.TextColumn("備註"),
        },
        key="watchlist_editor"
    )
    if st.button("💾 儲存變更至資料庫", type="primary"):
        try:
            database.save_watchlist(edited_watchlist)
            st.toast("✅ 自選股清單已更新！", icon="💾")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"儲存失敗: {e}")

# 重新整理資料
try:
    df_watch = database.load_watchlist()
    if not df_watch.empty and '股票代號' in df_watch.columns:
        df_watch['股票代號'] = df_watch['股票代號'].astype(str).str.strip()
        groups = ["全部", "庫存持股"]
        if '群組' in df_watch.columns: 
            valid_groups = [g for g in df_watch['群組'].unique().tolist() if g]
            groups += valid_groups
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
# 3. 側邊欄設定
# ==============================================================================
with st.sidebar:
    st.header("⚙️ 監控設定")
    selected_group = st.selectbox("選擇監控群組", groups)
    auto_refresh = st.toggle("啟用自動刷新 (30秒)", value=False)
    st.caption("⚠️ 注意：頻繁刷新會消耗 API 額度")
    st.divider()
    st.markdown("### 💡 警示圖示說明")
    st.markdown("- 🔥 **爆量**: 量比 > 2.0\n- 🟢 **增量**: 量比 > 1.5\n- 🔴 **突破**: 現價 >= 高\n- 📉 **跌破**: 現價 <= 低\n- ⚠️ **乖離**: > 20%")

# ==============================================================================
# 4. 核心監控邏輯 (Fragment)
# ==============================================================================

# 定義背景色樣式函式 (用於 Pandas Styler)
def highlight_change_bg(val):
    if not isinstance(val, (int, float)): return ''
    if val > 0:
        return 'background-color: #FFCDD2; color: #B71C1C; font-weight: bold;' # 淺紅底深紅字
    elif val < 0:
        return 'background-color: #C8E6C9; color: #1B5E20; font-weight: bold;' # 淺綠底深綠字
    return ''

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

    # 2. 抓取資料
    try:
        quotes = market_data.get_batch_detailed_quotes(target_stocks)
        ta_data = st.session_state.get("ta_data", {})
    except Exception as e:
        st.error(f"資料抓取失敗: {e}")
        return

    tw_now = datetime.utcnow() + timedelta(hours=8)
    current_time_str = tw_now.strftime("%H:%M")
    multiplier = logic.get_volume_multiplier(current_time_str, df_mp)

    # 3. 組裝資料
    table_rows = []
    alerts_data = [] 
    
    debug_ta_list = []      
    debug_calc_list = []    
    
    if not ta_data:
        st.warning("⚠️ 尚未取得「10日均量」資料，量比無法計算。請點擊下方「🔄 更新技術指標」按鈕。")

    for symbol in target_stocks:
        quote = quotes.get(symbol, {})
        price = quote.get('price', 0)
        chg_raw = quote.get('change_pct', 0) # 保持原始小數 (0.05)
        vol = quote.get('volume', 0)
        
        ta = ta_data.get(symbol, {})
        signal = ta.get('Signal', '-')
        ma20 = ta.get('MA20', 0)
        bias = ta.get('Bias', 0)
        vol_10ma = ta.get('Vol10', 0)
        
        if 'debug_info' in ta:
            debug_ta_list.append({'股票代號': symbol, '10日均量(Vol10)': vol_10ma, '歷史資料(末3筆)': ta['debug_info']})
        
        est_vol, vol_ratio = logic.calculate_volume_ratio(vol, vol_10ma, multiplier)

        debug_calc_list.append({'股票代號': symbol, '現量 (Vol)': vol, '倍數 (Mult)': multiplier, '預估量 (Est)': est_vol, '10日均量 (MA10)': vol_10ma, '量比 (Ratio)': vol_ratio})

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
        stock_alerts = []
        
        if high_limit > 0 and price >= high_limit:
            msg = f"🔴 突破目標價 {high_limit} (現價 {price})"
            stock_alerts.append(msg)
            status_icon += "🔴"
        if low_limit > 0 and price > 0 and price <= low_limit:
            msg = f"📉 跌破支撐價 {low_limit} (現價 {price})"
            stock_alerts.append(msg)
            status_icon += "📉"
            
        if vol_ratio > 2.0: 
            stock_alerts.append(f"🔥 爆量 (量比 {vol_ratio:.2f})")
            status_icon += "🔥"
        elif vol_ratio > 1.5: 
            status_icon += "🟢"
            
        if bias > 20: 
            stock_alerts.append(f"⚠️ 乖離過大 (BIAS {bias:.2f}%)")
            status_icon += "⚠️"
        
        if stock_alerts:
            alerts_data.append({"symbol": symbol, "name": name, "msgs": stock_alerts})
        
        # [Refactor] 儲存原始數值，不做字串格式化，讓 column_config 和 Styler 處理
        table_rows.append({
            "代號": symbol,
            "名稱": name,
            "現價": price,
            "漲跌幅": chg_raw, # 保持小數，Styler 需要這個來判斷顏色
            "成交量": vol,
            "預估量": est_vol,
            "10日均量": vol_10ma if vol_10ma > 0 else None, # None 會顯示空白
            "量比": vol_ratio if vol_10ma > 0 else 0,
            "月線乖離率": bias / 100, # 轉為小數以便 format 為 %
            "技術訊號": signal,
            "警示": status_icon
        })

    st.caption(f"最後更新: {tw_now.strftime('%H:%M:%S')} | 量能倍數: {multiplier}")

    if alerts_data:
        count = len(alerts_data)
        with st.expander(f"⚠️ 共有 {count} 檔股票出現異常/告警 (點擊展開查看)", expanded=False):
            for item in alerts_data:
                msgs_str = " | ".join(item['msgs'])
                st.markdown(f"**{item['name']} ({item['symbol']})**: {msgs_str}")
    
    if table_rows:
        df_display = pd.DataFrame(table_rows)
        
        # [UI Optimization] 套用背景色樣式
        st_df = df_display.style.map(highlight_change_bg, subset=['漲跌幅'])
        
        # [UI Optimization] 精細設定欄寬與格式
        st.dataframe(
            st_df,
            column_config={
                "代號": st.column_config.TextColumn("代號", width="small"),
                "名稱": st.column_config.TextColumn("名稱", width="small"),
                "現價": st.column_config.NumberColumn("現價", width="small", format="%.2f"),
                # 漲跌幅：顯示百分比
                "漲跌幅": st.column_config.NumberColumn("漲跌幅", width="small", format="%.2f%"),
                "成交量": st.column_config.NumberColumn("現量", width="small", format="%,d"),
                "預估量": st.column_config.NumberColumn("預估量", width="small", format="%,d"),
                "10日均量": st.column_config.NumberColumn("10日均量", width="small", format="%,d"),
                "量比": st.column_config.NumberColumn("量比", width="small", format="%.2f"),
                "月線乖離率": st.column_config.NumberColumn("乖離", width="small", format="%.2f%"),
                "技術訊號": st.column_config.TextColumn("訊號", width="medium"),
                "警示": st.column_config.TextColumn("警示", width="small"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        if st.button("🔄 更新技術指標 (均線/均量)"):
            with st.spinner("計算技術指標中 (抓取歷史K線)..."):
                new_ta = market_data.get_batch_technical_analysis(target_stocks)
                current_ta = st.session_state.get("ta_data", {})
                current_ta.update(new_ta)
                st.session_state["ta_data"] = current_ta
                st.rerun()
                
        with st.expander("🛠️ 除錯資訊 (量比計算來源)"):
            st.info("若量比顯示 0.00，請檢查「現量」或「倍數」是否為 0。若 10日均量 為 N/A，請按上方更新按鈕。")
            tab_debug1, tab_debug2 = st.tabs(["🔢 量比計算參數明細", "📊 歷史資料 (Vol10來源)"])
            with tab_debug1: st.dataframe(pd.DataFrame(debug_calc_list), use_container_width=True)
            with tab_debug2:
                st.markdown("API 抓取到的**歷史 K 線末 3 筆資料** (檢查是否包含今日導致均量失真)：")
                st.write(debug_ta_list)

if not groups:
    if not inventory_stocks and df_watch.empty:
        st.warning("無法讀取「自選股清單」且無庫存。請嘗試使用上方編輯器新增自選股。")
        render_monitor_table("全部", inventory_stocks, df_watch, df_mp)
    else:
        render_monitor_table(selected_group, inventory_stocks, df_watch, df_mp)
else:
    render_monitor_table(selected_group, inventory_stocks, df_watch, df_mp)
