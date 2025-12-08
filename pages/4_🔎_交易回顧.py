# ==============================================================================
# 檔案名稱: pages/4_🔎_交易回顧.py
# 
# 修改歷程:
# 2025-12-08 12:30:00: [Feat] 新增動態區間選擇 (1/2/3/4/6個月)，並優化均線計算邏輯
# ==============================================================================

import streamlit as st
import pandas as pd
import yfinance as yf
import mplfinance as mpf
from datetime import datetime, timedelta
import logic
import database

st.set_page_config(page_title="交易回顧", layout="wide", page_icon="🔎")
st.title("🔎 交易回顧與檢討")

# ==============================================================================
# 1. 輔助函式
# ==============================================================================

@st.cache_data(ttl=3600)
def get_yahoo_data(symbol, start_date, end_date):
    """
    嘗試取得 Yahoo Finance 資料 (.TW/.TWO)
    """
    ticker = f"{symbol}.TW"
    df = yf.download(ticker, start=start_date, end=end_date, progress=False)
    
    if df.empty:
        ticker = f"{symbol}.TWO"
        df = yf.download(ticker, start=start_date, end=end_date, progress=False)
    
    if df.empty:
        return None, None
        
    # 處理 MultiIndex (yfinance 新版特性)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    return df, ticker

def calculate_mas(df):
    """預先計算均線，避免切片後 MA 失真"""
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA10'] = df['Close'].rolling(window=10).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    return df

def create_trade_chart(df_slice, df_txns, symbol):
    """
    繪製 K 線圖 (MA 已預算在 df_slice 中，透過 addplot 加入)
    """
    # 1. 準備買賣標記點
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

    # 2. 設定 AddPlots (包含 標記 與 預算的均線)
    add_plots = []
    
    # 加入均線 (使用 dataframe 中的欄位)
    # 檢查切片後的資料是否包含足夠的均線數據 (避免全 NaN 報錯)
    if not df_slice['MA10'].isnull().all():
        add_plots.append(mpf.make_addplot(df_slice['MA10'], color='cyan', width=0.8)) # 10MA
    if not df_slice['MA20'].isnull().all():
        add_plots.append(mpf.make_addplot(df_slice['MA20'], color='orange', width=1.0)) # 20MA
    if not df_slice['MA60'].isnull().all():
        add_plots.append(mpf.make_addplot(df_slice['MA60'], color='green', width=1.2)) # 60MA

    # 加入買賣點
    if has_buy:
        add_plots.append(mpf.make_addplot(buy_signals, type='scatter', markersize=100, marker='^', color='r', panel=0))
    if has_sell:
        add_plots.append(mpf.make_addplot(sell_signals, type='scatter', markersize=100, marker='v', color='g', panel=0))
    
    # 3. 繪圖風格
    mc = mpf.make_marketcolors(up='r', down='g', inherit=True)
    s = mpf.make_mpf_style(marketcolors=mc, base_mpf_style='yahoo')

    # 4. 繪製
    fig, ax = mpf.plot(
        df_slice,
        type='candle',
        volume=True,
        style=s,
        addplot=add_plots,
        returnfig=True,
        title=f'\n{symbol} Review',
        figsize=(12, 6)
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

with st.sidebar:
    st.header("🔍 回顧設定")
    
    # A. 選擇股票
    df_realized = logic.calculate_realized_report(df_raw)
    if df_realized.empty:
        stock_list = df_raw['股票代號'].unique().tolist()
    else:
        df_realized = df_realized.sort_values('交易日期', ascending=False)
        stock_list = df_realized['股票代號'].unique().tolist()

    selected_stock_id = st.selectbox("1. 選擇股票代號", stock_list)
    
    # B. [New] 選擇時間區間
    st.write("---")
    time_range_options = {
        "1 個月 (細節)": 30,
        "2 個月": 60,
        "3 個月 (一季)": 90,
        "4 個月": 120,
        "6 個月 (半年)": 180
    }
    selected_range_label = st.radio(
        "2. 設定 K 線顯示範圍 (以最後交易日推算)",
        options=list(time_range_options.keys()),
        index=2 # 預設 3 個月
    )
    days_lookback = time_range_options[selected_range_label]

    # 顯示股票資訊
    if selected_stock_id:
        stock_txns = df_raw[df_raw['股票代號'].astype(str) == str(selected_stock_id)].copy()
        stock_txns['交易日期'] = pd.to_datetime(stock_txns['交易日期'])
        stock_name = stock_txns.iloc[0]['股票名稱']
        
        last_tx_date = stock_txns['交易日期'].max() # 作為錨點
        
        st.divider()
        st.markdown(f"**{stock_name} ({selected_stock_id})**")
        st.caption(f"最後交易日: {last_tx_date.strftime('%Y-%m-%d')}")

# ==============================================================================
# 4. 主畫面
# ==============================================================================

if selected_stock_id:
    
    # 1. 抓取資料策略 (Fetch Strategy)
    # 為了確保 MA60 計算正確，我們往前多抓 365 天 (Buffer)
    # 顯示範圍：[最後交易日 - 選定天數 : 最後交易日 + 10天]
    
    view_end_date = last_tx_date + timedelta(days=10)
    view_start_date = last_tx_date - timedelta(days=days_lookback)
    
    # 實際抓取起點 (為了 MA 計算)
    fetch_start_date = view_start_date - timedelta(days=300) 
    
    # 限制不要抓太久以前 (Yahoo 限制)
    if (datetime.now() - fetch_start_date).days > 3000:
        fetch_start_date = datetime.now() - timedelta(days=3000)

    # 2. 執行抓取
    with st.spinner(f"正在下載並計算 {selected_stock_id} 技術指標..."):
        df_full, ticker_name = get_yahoo_data(selected_stock_id, fetch_start_date, view_end_date)

    if df_full is None or df_full.empty:
        st.error("無法取得 K 線資料。")
    else:
        # 3. 計算均線 (在完整資料上算，保證準確)
        df_full = calculate_mas(df_full)
        
        # 4. 資料切片 (Slicing) - 只取使用者想看的範圍
        # 使用字串日期索引進行切片比較穩健
        slice_start_str = view_start_date.strftime('%Y-%m-%d')
        slice_end_str = view_end_date.strftime('%Y-%m-%d')
        
        df_view = df_full.loc[slice_start_str:slice_end_str]
        
        if df_view.empty:
            st.warning("選定的區間內無 K 線資料 (可能是很久以前的交易)。")
        else:
            # 5. 繪圖
            try:
                target_txns = df_raw[df_raw['股票代號'].astype(str) == str(selected_stock_id)]
                target_txns['交易日期'] = pd.to_datetime(target_txns['交易日期'])
                
                fig = create_trade_chart(df_view, target_txns, f"{ticker_name}")
                st.pyplot(fig)
                
                # 圖例
                st.markdown("""
                <small>
                圖例：🔺 買進 | 🔻 賣出 | 
                <span style='color:cyan'>— 10MA</span> | 
                <span style='color:orange'>— 20MA</span> | 
                <span style='color:green'>— 60MA</span>
                </small>
                """, unsafe_allow_html=True)
                
            except Exception as e:
                st.error(f"繪圖錯誤: {e}")

    # 6. 交易明細表
    st.divider()
    st.subheader(f"📝 交易明細")
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
