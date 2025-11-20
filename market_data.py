import streamlit as st
import requests
import time

def get_price_from_fugle(symbol, api_key):
    """
    針對單一股票代號向 Fugle API 查詢股價
    邏輯移植自原本的 GAS _fetchQuoteFromFugleAPI
    """
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}"
    headers = {
        "X-API-KEY": api_key
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5) # 設定超時避免卡住
        
        if response.status_code != 200:
            print(f"Error fetching {symbol}: Status {response.status_code}")
            return None
            
        data = response.json()
        
        # --- 價格擷取邏輯 (對應 GAS 邏輯) ---
        last_price = None
        
        # 1. total.price
        if 'total' in data and data['total'].get('price') is not None:
            last_price = data['total']['price']
        # 2. quote.close
        elif 'quote' in data and data['quote'].get('close') is not None:
            last_price = data['quote']['close']
        # 3. trade.price
        elif 'trade' in data and data['trade'].get('price') is not None:
            last_price = data['trade']['price']
        # 4. root price
        elif data.get('price') is not None:
            last_price = data['price']
        
        # 5. lastPrice fallback
        if last_price is None:
            last_price = data.get('lastPrice', 0)
            
        return float(last_price)

    except Exception as e:
        print(f"Exception fetching {symbol}: {e}")
        return None

def get_realtime_prices(stock_list):
    """
    接收股票代號列表，回傳 { '2330': 1050.0, ... }
    """
    # 1. 從 Secrets 讀取 Key
    if "fugle_api_key" not in st.secrets:
        st.error("❌ 未設定 fugle_api_key，請至 Secrets 設定。")
        return {}

    api_key = st.secrets["fugle_api_key"]
    
    prices = {}
    
    # 建立進度條 (因為 API 是一筆一筆查，給使用者一點反饋)
    progress_bar = st.progress(0)
    total = len(stock_list)
    
    for i, symbol in enumerate(stock_list):
        # 呼叫上面的單一查詢函式
        price = get_price_from_fugle(symbol, api_key)
        
        if price is not None:
            prices[symbol] = price
        
        # 更新進度條
        progress_bar.progress((i + 1) / total)
        
        # (選用) 稍微延遲避免觸發 API Rate Limit，Fugle 免費版有限制頻率
        time.sleep(0.1) 
        
    progress_bar.empty() # 跑完隱藏進度條
    return prices
