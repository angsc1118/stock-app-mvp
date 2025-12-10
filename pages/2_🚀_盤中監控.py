# ==============================================================================
# 檔案名稱: pages/2_🚀_盤中監控.py
# 
# 修改歷程:
# 2025-12-10 12:50:00: [UI] 側邊欄優化(階段一)：圖示說明收入 Expander，標題層級調整
# 2025-12-04 16:30:00: [UI] 導入視覺優化方案：更新量能(⚡)與警示(🔔/💔)圖示
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
    if not df_fifo.empty:
        inventory_data = df_fifo[['股票代號', '股票名稱']].drop_duplicates().to_dict('records')
        inventory_stocks_list = df_fifo['股票代號'].unique().tolist()
    else:
        inventory_data = []
        inventory_stocks_list = []
except:
    inventory_data = []
    inventory_stocks_list = []

# ==============================================================================
# 2. 自選股管理區塊
# ==============================================================================
with st.expander("⚙️ 管理自選股清單 (新增/刪除/設定警示)", expanded=False):
    st.caption("💡 操作說明：系統會**自動帶入庫存股票**。請直接修改下方表格設定警示價，並務必點擊「💾 儲存變更」。")
    
    # A. 讀取
    try:
        current_watchlist = database.load_watchlist()
    except:
        current_watchlist = pd.DataFrame(columns=['群組', '股票代號', '股票名稱', '警示價_高', '警示價_低', '備註'])

    column_order = ['群組', '股票代號', '股票名稱', '警示價_高', '警示價_低', '備註']
    for col in column_order:
        if col not in current_watchlist.columns: 
            current_watchlist[col] = ""

    # B. 注入
    existing_symbols = set(current_watchlist['股票代號'].astype(str).str.strip().tolist())
    
    new_rows = []
    for item in inventory_data:
        symbol = str(item['股票代號']).strip()
        name = str(item['股票名稱']).strip()
        
        if symbol not in existing_symbols and symbol != "":
            new_rows.append({
                '群組': '庫存', 
                '股票代號': symbol,
                '股票名稱': name,
                '警示價_高': '', 
                '警示價_低': '',
                '備註': '自動帶入'
            })
    
    if new_rows:
        df_new = pd.DataFrame(new_rows)
        for col in column_order:
            if col not in df_new.columns: df_new[col] = ""
        current_watchlist = pd.concat([current_watchlist, df_new], ignore_index=True)
        st.info(f"✨ 已自動將 {len(new_rows)} 檔庫存股票帶入下方列表，請設定警示價。", icon="🤖")

    # C. 轉型
    text_cols = ['群組', '股票代號', '股票名稱', '備註']
    for col in text_cols:
        current_watchlist[col] = current_watchlist[col].astype(str).replace('nan', '')

    num_cols = ['警示價_高', '警示價_低']
    for col in num_cols:
        current_watchlist[col] = pd.to_numeric(current_watchlist[col], errors='coerce')

    # D. 編輯器
    edited_watchlist = st.data_editor(
        current_watchlist[column_order],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "群組": st.column_config.SelectboxColumn(
                "群組",
                options=["庫存", "自選", "觀察", "短線", "長線", "動能", "大戶", "產業班"], 
                required=True
            ),
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

# ==============================================================================
# 3. 資料讀取 (監控用)
# ==============================================================================

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
# 4. 側邊欄設定 (UI優化重點)
# ==============================================================================
with st.sidebar:
    # [UI] 降級標題，減少視覺壓迫
    st.subheader("⚙️ 監控設定")
    
    # 核心操作區
    selected_group = st.selectbox("選擇監控群組", groups)
    auto_refresh = st.toggle("啟用自動刷新 (30秒)", value=False)
    st.caption("⚠️ 注意：頻繁刷新會消耗 API 額度")
    
    st.divider()
    
    # [UI] 輔助資訊區：改用 Expander 收合
    with st.expander("💡 視覺圖示與操作說明", expanded=False):
        st.markdown("""
        **【月線趨勢】**
        - 🔴 **上彎**: 趨勢向上
        - ➖ **走平**: 盤整無方向
        - 🟢 **下彎**: 趨勢向下
        
        **【動能與警示】**
        - 🔥 **爆量**: 量比 > 2.0
        - ⚡ **增量**: 量比 > 1.5
        - 🔔 **突破**: 現價 >= 高
        - 💔 **跌破**: 現價 <= 低
        - 🚀 **多排**: 均線多頭排列
        """)

# ==============================================================================
# 5. 核心監控邏輯 (Fragment)
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
    alerts_data = [] 
    debug_ta_list = []      
    debug_calc_list = []    
    
    if not ta_data:
        st.warning("⚠️ 尚未取得「10日均量」資料，量比無法計算。請點擊下方「🔄 更新技術指標」按鈕。")

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
            msg = f"🔔 突破目標價 {high_limit} (現價 {price})"
            stock_alerts.append(msg)
            status_icon += "🔔"
        if low_limit > 0 and price > 0 and price <= low_limit:
            msg = f"💔 跌破支撐價 {low_limit} (現價 {price})"
            stock_alerts.append(msg)
            status_icon += "💔"
            
        if vol_ratio > 2.0: 
            stock_alerts.append(f"🔥 爆量 (量比 {vol_ratio:.2f})")
            status_icon += "🔥"
        elif vol_ratio > 1.5: 
            status_icon += "⚡" 
            
        if bias > 20: 
            stock_alerts.append(f"⚠️ 乖離過大 (BIAS {bias:.2f}%)")
            status_icon += "⚠️"
        
        if stock_alerts:
            alerts_data.append({"symbol": symbol, "name": name, "msgs": stock_alerts})
        
        price_str = f"{price:,.2f}"
        chg_str = f"{chg:.2f}%"
        vol_str = f"{vol:,}"
        est_vol_str = f"{est_vol:,}"
        
        if vol_10ma > 0:
            vol_10ma_lots = math.ceil(vol_10ma / 1000)
            vol_10ma_str = f"{vol_10ma_lots:,}"
            if vol == 0:
                vol_ratio_str = "0.00"
            else:
                vol_ratio_str = f"{vol_ratio:.2f}"
        else:
            vol_10ma_str = "N/A"
            vol_ratio_str = "-" 

        sort_val = vol_ratio if vol_10ma > 0 else -1.0

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
            "警示": status_icon,
            "_sort_ratio": sort_val 
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
        df_display = df_display.sort_values(by="_sort_ratio", ascending=False)
        df_display = df_display.drop(columns=["_sort_ratio"])

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

# ==============================================================================
# 6. 執行渲染
# ==============================================================================

if not groups and not inventory_stocks_list:
    st.warning("目前無自選股設定也無庫存。請使用上方編輯器新增股票。")
else:
    render_monitor_table(selected_group, inventory_stocks_list, df_watch, df_mp)
