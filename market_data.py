import streamlit as st
import requests
import time
import pandas as pd
from datetime import datetime, timedelta

def get_price_from_fugle(symbol, api_key):
    """
    針對單一股票代號向 Fugle API 查詢股價
    """
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}"
    headers = {
        "X-API-KEY": api_key
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code != 200:
            print(f"Error fetching {symbol}: Status {response.status_code}")
            return None
            
        data = response.json()
        
        last_price = None
        
        # 價格擷取邏輯
        if 'total' in data and data['total'].get('price') is not None:
            last_price = data['total']['price']
        elif 'quote' in data and data['quote'].get('close') is not None:
            last_price = data['quote']['close']
        elif 'trade' in data and data['trade'].get('price') is not None:
            last_price = data['trade']['price']
        elif data.get('price') is not None:
            last_price = data['price']
        
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
    if "fugle_api_key" not in st.secrets:
        st.error("❌ 未設定 fugle_api_key，請至 Secrets 設定。")
        return {}

    api_key = st.secrets["fugle_api_key"]
    prices = {}
    
    progress_bar = st.progress(0)
    total = len(stock_list)
    
    for i, symbol in enumerate(stock_list):
        price = get_price_from_fugle(symbol, api_key)
        if price is not None:
            prices[symbol] = price
        
        progress_bar.progress((i + 1) / total)
        time.sleep(0.1) # 避免 API 限制
        
    progress_bar.empty()
    return prices

# --- 以下為新增的技術分析功能 ---

def get_technical_analysis(symbol, api_key):
    """
    抓取歷史資料並計算技術指標訊號
    回傳: { 'MA20': 123.4, 'Signal': '均線多頭' }
    """
    # 設定抓取區間 (抓過去 120 天以確保能算出 MA60)
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=120)).strftime('%Y-%m-%d')
    
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/historical/candles/{symbol}"
    params = {
        "from": from_date,
        "to": to_date,
        "fields": "open,high,low,close,volume"
    }
    headers = {"X-API-KEY": api_key}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        data = response.json()
        
        if response.status_code != 200 or 'data' not in data:
            return {'Signal': '無資料', 'MA20': 0}
            
        # 轉為 DataFrame
        df = pd.DataFrame(data['data'])
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date') # 確保日期由舊到新
        
        # 計算均線
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean() # 月線
        df['MA60'] = df['close'].rolling(window=60).mean() # 季線
        
        # 取得最新一天的數值
        if len(df) < 1:
             return {'Signal': '資料不足', 'MA20': 0}

        last_row = df.iloc[-1]
        
        current_price = last_row['close']
        ma5 = last_row['MA5']
        ma10 = last_row['MA10']
        ma20 = last_row['MA20']
        ma60 = last_row['MA60']
        
        signals = []
        
        # 1. 判斷是否跌破月線
        if pd.notna(ma20):
            if current_price < ma20:
                signals.append("📉 破月線")
            elif current_price > ma20:
                signals.append("🆗 站上月線")
            
        # 2. 判斷均線多頭排列 (短 > 中 > 長)
        if pd.notna(ma5) and pd.notna(ma10) and pd.notna(ma20) and pd.notna(ma60):
            if ma5 > ma10 > ma20 > ma60:
                signals.append("🔥 均線多頭")

        return {
            'MA20': round(ma20, 2) if pd.notna(ma20) else 0,
            'MA60': round(ma60, 2) if pd.notna(ma60) else 0,
            'Signal': " ".join(signals) if signals else "盤整"
        }

    except Exception as e:
        print(f"TA Error {symbol}: {e}")
        return {'Signal': 'Error', 'MA20': 0}

def get_batch_technical_analysis(stock_list):
    """
    批次取得技術指標
    """
    if "fugle_api_key" not in st.secrets:
        return {}

    api_key = st.secrets["fugle_api_key"]
    results = {}
    
    # 這裡使用 status 來顯示進度，避免跟價格更新的進度條打架
    status_text = st.empty()
    total = len(stock_list)
    
    for i, symbol in enumerate(stock_list):
        status_text.text(f"正在分析技術指標 ({i+1}/{total}): {symbol}...")
        res = get_technical_analysis(symbol, api_key)
        results[symbol] = res
        
        time.sleep(0.3) # Fugle 免費版限制較嚴，建議稍微延遲
        
    status_text.empty()
    return results
