# ==============================================================================
# 檔案名稱: pages/4_🔎_交易回顧.py
# 
# 修改歷程:
# 2025-12-10 12:50:00: [UI] 側邊欄優化(階段一)：圖例說明移至 Sidebar Expander
# 2025-12-09 13:45:00: [UI] 分離配色：K線維持標準紅綠，僅交易量套用淺色系
# ==============================================================================

import streamlit as st
import pandas as pd
import yfinance as yf
import mplfinance as mpf
from datetime import datetime, timedelta
import logic
import database
import utils

st.set_page_config(page_title="交易回顧", layout="wide", page_icon="🔎")
st.title("🔎 交易回顧與檢討")

# ==============================================================================
# 1. 輔助函式
# ==============================================================================

@st.cache_data(ttl=3600)
def get_yahoo_data(symbol, start_date, end_date):
    """嘗試取得 Yahoo Finance 資料 (.TW/.TWO)"""
    ticker = f"{symbol}.TW"
    df = yf.download(ticker, start=start_date, end=end_date, progress=False)
    
    if df.empty:
        ticker = f"{symbol}.TWO"
        df = yf.download(ticker, start=start_date, end=end_date, progress=False)
    
    if df.empty:
        return None, None
        
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    return df, ticker

def calculate_mas(df):
    """預先計算均線"""
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA10'] = df['Close'].rolling(window=10).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    return df

def create_trade_chart(df_slice, df_txns, symbol):
    """繪製 K 線圖"""
    # 標記準備
    buy_signals = [float('nan')] * len(df_slice)
    sell_signals = [float('nan')] * len(df_slice)
    slice_dates = df_slice.index.strftime('%Y-%m-%d').tolist()
    
    has_buy = False
    has_sell = False

    for _, row in df_txns.iterrows():
        txn_date = row['交易日期'].strftime('%Y-%m-%d')
        action = row['交易類別']
        
        if txn_date in slice_dates:
            idx = slice_dates.index(txn_date)
            low_val = df_slice.iloc[idx]['Low']
            high_val = df_slice.iloc[idx]['High']
            
            if action in ['買進', '現金增資', '股票股利']:
                buy_signals[idx] = low_val * 0.98
                has_buy = True
            elif action == '賣出':
                sell_signals[idx] = high_val * 1.02
                has_sell = True

    # 設定 AddPlots
    add_plots = []
    
    # 均線
    if not df_slice['MA10'].isnull().all():
        add_plots.append(mpf.make_addplot(df_slice['MA10'], color='cyan', width=0.8))
    if not df_slice['MA20'].isnull().all():
        add_plots.append(mpf.make_addplot(df_slice['MA20'], color='orange', width=1.0))
    if not df_slice['MA60'].isnull().all():
        add_plots.append(mpf.make_addplot(df_slice['MA60'], color='green', width=1.2))

    # 買賣點
    if has_buy:
        add_plots.append(mpf.make_addplot(buy_signals, type='scatter', markersize=100, marker='^', color='#2962FF', panel=0))
    if has_sell:
        add_plots.append(mpf.make_addplot(sell_signals, type='scatter', markersize=100, marker='v', color='#D500F9', panel=0))
    
    # 繪圖風格
    mc = mpf.make_marketcolors(
        up='r', down='g', 
        edge='inherit', wick='inherit', 
        volume={'up': '#ffab8c', 'down': '#beff99'}, 
        inherit=True
    )
    s = mpf.make_mpf_style(marketcolors=mc, base_mpf_style='yahoo')

    fig, ax = mpf.plot(
        df_slice, type='candle', volume=True, style=s,
        addplot=add_plots, returnfig=True,
        title=f'\n{symbol} Trade Review', figsize=(12, 6)
    )
    return fig

# ==============================================================================
# 2. 資料載入
# ==============================================================================

try:
    df_raw = database.load_data()
except:
    st.error("無法讀取資料庫")
    st.stop()

if df_raw.empty:
    st.info("尚無交易紀錄")
    st.stop()

# ==============================================================================
# 3. 側邊欄：選擇與設定
# ==============================================================================
utils.render_sidebar_status()
with st.sidebar:
    # [UI] 降級標題
    st.subheader("🔍 回顧設定")
    
    # A. 股票選單
    df_realized = logic.calculate_realized_report(df_raw)
    stock_options = {} 
    
    if df_realized.empty:
        unique_stocks = df_raw[['股票代號', '股票名稱']].drop_duplicates()
        for _, row in unique_stocks.iterrows():
            label = f"{row['股票代號']} ({row['股票名稱']})"
            stock_options[label] = row['股票代號']
    else:
        stock_summary = df_realized.groupby(['股票代號', '股票名稱'])['已實現損益'].sum().reset_index()
        stock_summary = stock_summary.sort_values('已實現損益', ascending=False)
        for _, row in stock_summary.iterrows():
            pnl = int(row['已實現損益'])
            sign = "+" if pnl > 0 else ""
            label = f"{row['股票代號']} ({row['股票名稱']}) | 💰 ${sign}{pnl:,}"
            stock_options[label] = row['股票代號']

    if not stock_options:
        st.warning("無資料可選")
        selected_stock_id = None
    else:
        selected_label = st.selectbox("1. 選擇股票 (依損益排序)", list(stock_options.keys()))
        selected_stock_id = stock_options[selected_label]
    
    # B. 時間區間
    st.write("---")
    time_range_options = {"1 個月 (細節)": 30, "3 個月 (一季)": 90, "6 個月 (半年)": 180}
    selected_range_label = st.radio("2. K 線顯示範圍", options=list(time_range_options.keys()), index=1)
    days_lookback = time_range_options[selected_range_label]

    if selected_stock_id:
        stock_txns = df_raw[df_raw['股票代號'].astype(str) == str(selected_stock_id)].copy()
        stock_txns['交易日期'] = pd.to_datetime(stock_txns['交易日期'])
        stock_name = stock_txns.iloc[0]['股票名稱']
        last_tx_date = stock_txns['交易日期'].max()
        
        st.divider()
        st.caption(f"最後交易日: {last_tx_date.strftime('%Y-%m-%d')}")
        
    # [UI] 輔助資訊區：收入 Expander
    st.write("---")
    with st.expander("💡 圖表與標記說明", expanded=False):
        st.markdown("""
        - <span style='color:#2962FF'>▲ 藍色三角</span>：買進點 / 股利
        - <span style='color:#D500F9'>▼ 紫色三角</span>：賣出點
        - <span style='color:cyan'>— 淺藍線</span>：10MA (雙週線)
        - <span style='color:orange'>— 橘色線</span>：20MA (月線)
        - <span style='color:green'>— 綠色線</span>：60MA (季線)
        """, unsafe_allow_html=True)

# ==============================================================================
# 4. 主畫面
# ==============================================================================

if selected_stock_id:
    # 1. 抓取資料策略
    view_end_date = last_tx_date + timedelta(days=10)
    view_start_date = last_tx_date - timedelta(days=days_lookback)
    fetch_start_date = view_start_date - timedelta(days=300) 
    if (datetime.now() - fetch_start_date).days > 3000:
        fetch_start_date = datetime.now() - timedelta(days=3000)

    # 2. 執行抓取
    with st.spinner(f"正在分析 {selected_stock_id} 歷史走勢..."):
        df_full, ticker_name = get_yahoo_data(selected_stock_id, fetch_start_date, view_end_date)

    if df_full is None or df_full.empty:
        st.error("無法取得 K 線資料。")
    else:
        # 3. 計算均線
        df_full = calculate_mas(df_full)
        
        # 4. 資料切片
        slice_start_str = view_start_date.strftime('%Y-%m-%d')
        slice_end_str = view_end_date.strftime('%Y-%m-%d')
        df_view = df_full.loc[slice_start_str:slice_end_str]
        
        if df_view.empty:
            st.warning("選定的區間內無 K 線資料。")
        else:
            # 5. 繪圖
            try:
                target_txns = df_raw[df_raw['股票代號'].astype(str) == str(selected_stock_id)]
                target_txns['交易日期'] = pd.to_datetime(target_txns['交易日期'])
                
                fig = create_trade_chart(df_view, target_txns, f"{ticker_name}")
                st.pyplot(fig)
                # [UI] 移除了主畫面的圖例說明 (因為已經移到 Sidebar)
                
            except Exception as e:
                st.error(f"繪圖錯誤: {e}")

    # 6. 交易明細表
    st.divider()
    st.subheader(f"📝 {selected_stock_id} 交易紀錄")
    display_df = stock_txns.sort_values('交易日期', ascending=False).copy()
    display_df['交易日期'] = display_df['交易日期'].dt.date
    
    st.dataframe(
        display_df[['交易日期', '交易類別', '股數', '單價', '淨收付金額', '備註']],
        column_config={
            "交易日期": st.column_config.DateColumn("日期", format="YYYY-MM-DD"),
            "股數": st.column_config.NumberColumn("股數", format="%d"),
            "單價": st.column_config.NumberColumn("單價", format="%.2f"),
            "淨收付金額": st.column_config.NumberColumn("淨收付", format="$%d"),
        },
        use_container_width=True,
        hide_index=True
    )

else:
    st.info("請從左側選擇一檔股票進行回顧。")
