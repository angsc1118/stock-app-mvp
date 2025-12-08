# ==============================================================================
# 檔案名稱: pages/4_🔎_交易回顧.py
# 
# 功能: 
# 1. 驗證 yfinance 資料抓取與代號轉換 (.TW/.TWO)
# 2. 驗證 mplfinance 繪圖與買賣點標記邏輯
# 3. 作為未來產製 PDF 報表的原型 (Prototype)
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
# 1. 輔助函式 (僅在此頁面使用)
# ==============================================================================

@st.cache_data(ttl=3600)
def get_yahoo_data(symbol, start_date, end_date):
    """
    嘗試取得 Yahoo Finance 資料
    自動判斷上市 (.TW) 或上櫃 (.TWO)
    """
    # 1. 先嘗試上市 (.TW)
    ticker = f"{symbol}.TW"
    df = yf.download(ticker, start=start_date, end=end_date, progress=False)
    
    # 檢查是否有資料 (Yahoo有時會回傳空DataFrame)
    if df.empty:
        # 2. 若失敗，嘗試上櫃 (.TWO)
        ticker = f"{symbol}.TWO"
        df = yf.download(ticker, start=start_date, end=end_date, progress=False)
    
    if df.empty:
        return None, None
        
    # 處理 MultiIndex Column 問題 (yfinance 新版特性)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    return df, ticker

def create_trade_chart(df_kline, df_txns, symbol, period_months=6):
    """
    使用 mplfinance 繪製 K 線圖並標記買賣點
    """
    # 1. 準備標記點 (Markers)
    # 建立與 K 線圖 index 等長的 series，預設為 NaN
    buy_signals = [float('nan')] * len(df_kline)
    sell_signals = [float('nan')] * len(df_kline)
    
    # 為了對齊日期，將 index 轉為字串 set 加速比對
    kline_dates = df_kline.index.strftime('%Y-%m-%d').tolist()
    
    has_buy = False
    has_sell = False

    for _, row in df_txns.iterrows():
        txn_date = row['交易日期'].strftime('%Y-%m-%d')
        action = row['交易類別']
        price = row['單價']
        
        if txn_date in kline_dates:
            idx = kline_dates.index(txn_date)
            # 為了避免標記重疊，買進畫在 Low 下方，賣出畫在 High 上方
            # 使用 K 線當日的 High/Low 做定位
            low_val = df_kline.iloc[idx]['Low']
            high_val = df_kline.iloc[idx]['High']
            
            if action in ['買進', '現金增資', '股票股利']:
                buy_signals[idx] = low_val * 0.98 # 畫在下方 2%
                has_buy = True
            elif action == '賣出':
                sell_signals[idx] = high_val * 1.02 # 畫在上方 2%
                has_sell = True

    # 2. 設定 mplfinance 附加圖表 (AddPlots)
    add_plots = []
    
    if has_buy:
        add_plots.append(mpf.make_addplot(buy_signals, type='scatter', markersize=100, marker='^', color='r', panel=0))
    if has_sell:
        add_plots.append(mpf.make_addplot(sell_signals, type='scatter', markersize=100, marker='v', color='g', panel=0))
        
    # 加入均線 (MA) - 這裡示範 10MA, 20MA, 60MA
    # mplfinance 內建 mav 參數，可以直接用
    
    # 3. 繪圖風格設定
    # 建立自定義風格以符合台股習慣 (紅漲綠跌)
    mc = mpf.make_marketcolors(up='r', down='g', inherit=True)
    s = mpf.make_mpf_style(marketcolors=mc, base_mpf_style='yahoo')

    # 4. 繪製並回傳 Figure
    fig, ax = mpf.plot(
        df_kline,
        type='candle',
        mav=(10, 20, 60),
        volume=True,
        style=s,
        addplot=add_plots,
        returnfig=True,
        title=f'\n{symbol} Trade Review',
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
# 3. 側邊欄：選擇交易
# ==============================================================================

with st.sidebar:
    st.header("🔍 篩選條件")
    
    # 取得所有有「賣出」紀錄的股票 (代表已實現損益，值得檢討)
    df_realized = logic.calculate_realized_report(df_raw)
    
    if df_realized.empty:
        st.warning("尚無已實現損益的交易可供回顧。")
        # 為了測試，允許選擇庫存股
        stock_list = df_raw['股票代號'].unique().tolist()
    else:
        # 依日期排序，最近的在上面
        df_realized = df_realized.sort_values('交易日期', ascending=False)
        stock_list = df_realized['股票代號'].unique().tolist()

    selected_stock_id = st.selectbox("選擇股票代號", stock_list)
    
    # 顯示該股票的基本統計
    if selected_stock_id:
        stock_txns = df_raw[df_raw['股票代號'].astype(str) == str(selected_stock_id)].copy()
        stock_txns['交易日期'] = pd.to_datetime(stock_txns['交易日期'])
        stock_name = stock_txns.iloc[0]['股票名稱']
        
        st.divider()
        st.markdown(f"**{stock_name} ({selected_stock_id})**")
        
        last_date = stock_txns['交易日期'].max()
        first_date = stock_txns['交易日期'].min()
        
        st.caption(f"📅 首次交易: {first_date.strftime('%Y-%m-%d')}")
        st.caption(f"📅 最近交易: {last_date.strftime('%Y-%m-%d')}")

# ==============================================================================
# 4. 主畫面：K線圖與詳細紀錄
# ==============================================================================

if selected_stock_id:
    # 1. 定義抓取區間
    # 預設抓取：第一筆交易前 30 天 ~ 最後一筆交易後 10 天
    # 若區間過長，可限制只看最近 1 年
    start_fetch = first_date - timedelta(days=60)
    end_fetch = last_date + timedelta(days=10)
    
    # 若超過 2 年，限制在最近 2 年以免資料量過大
    if (datetime.now() - start_fetch).days > 730:
        start_fetch = datetime.now() - timedelta(days=730)

    # 2. 抓取資料 (yfinance)
    with st.spinner(f"正在從 Yahoo Finance 下載 {selected_stock_id} 歷史資料..."):
        df_kline, ticker_name = get_yahoo_data(selected_stock_id, start_fetch, end_fetch)

    if df_kline is None or df_kline.empty:
        st.error(f"❌ 無法在 Yahoo Finance 找到代號 {selected_stock_id} (.TW 或 .TWO) 的資料。")
        st.info("可能原因：代號錯誤、新股上市無歷史資料、或 Yahoo API 暫時異常。")
    else:
        st.success(f"✅ 成功取得資料: {ticker_name} (共 {len(df_kline)} 筆 K 線)")
        
        # 3. 繪製圖表
        try:
            # 篩選該股票的所有交易紀錄 (用於標記)
            target_txns = df_raw[df_raw['股票代號'].astype(str) == str(selected_stock_id)]
            target_txns['交易日期'] = pd.to_datetime(target_txns['交易日期'])
            
            fig = create_trade_chart(df_kline, target_txns, f"{ticker_name}")
            st.pyplot(fig)
            
            st.caption("圖例說明：🔺 紅色三角 = 買進/股利 | 🔻 綠色三角 = 賣出")
            
        except Exception as e:
            st.error(f"繪圖失敗: {e}")
            st.write(e)

    # 4. 顯示該股交易明細表格
    st.subheader(f"📝 {selected_stock_id} 交易明細")
    
    # 整理表格欄位
    display_df = stock_txns.sort_values('交易日期', ascending=False).copy()
    display_df['交易日期'] = display_df['交易日期'].dt.date
    
    st.dataframe(
        display_df[['交易日期', '交易類別', '股數', '單價', '手續費', '交易稅', '淨收付金額', '備註']],
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
