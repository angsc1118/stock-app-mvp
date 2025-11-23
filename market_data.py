import streamlit as st
import requests
import time
import pandas as pd
from datetime import datetime, timedelta

def get_price_from_fugle(symbol, api_key):
    """單純取得價格 (給庫存用)"""
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}"
    headers = {"X-API-KEY": api_key}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200: return None
        data = response.json()
        last_price = None
        if 'total' in data and data['total'].get('price') is not None: last_price = data['total']['price']
        elif 'quote' in data and data['quote'].get('close') is not None: last_price = data['quote']['close']
        elif 'trade' in data and data['trade'].get('price') is not None: last_price = data['trade']['price']
        elif data.get('price') is not None: last_price = data['price']
        if last_price is None: last_price = data.get('lastPrice', 0)
        return float(last_price)
    except: return None

def get_realtime_prices(stock_list):
    """批次取得價格 (給庫存用)"""
    if "fugle_api_key" not in st.secrets: return {}
    api_key = st.secrets["fugle_api_key"]
    prices = {}
    progress_bar = st.progress(0)
    total = len(stock_list)
    for i, symbol in enumerate(stock_list):
        price = get_price_from_fugle(symbol, api_key)
        if price is not None: prices[symbol] = price
        progress_bar.progress((i + 1) / total)
        time.sleep(0.1)
    progress_bar.empty()
    return prices

# --- [新增] 取得詳細即時報價 (給盤中監控用) ---
def get_detailed_quote(symbol, api_key):
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}"
    headers = {"X-API-KEY": api_key}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200: return None
        data = response.json()
        
        # 價格
        last_price = 0
        if 'total' in data: last_price = data['total'].get('price', 0)
        elif 'quote' in data: last_price = data['quote'].get('close', 0)
        elif 'trade' in data: last_price = data['trade'].get('price', 0)
        
        if last_price == 0: last_price = data.get('lastPrice', 0)
        
        # 漲跌幅
        change_percent = 0
        if 'quote' in data:
            change_percent = data['quote'].get('changePercent', 0)
        elif 'changePercent' in data:
            change_percent = data['changePercent']
            
        # 成交量
        volume = 0
        if 'total' in data: volume = data['total'].get('tradeVolume', 0)
        elif 'trade' in data: volume = data['trade'].get('volume', 0) # 注意 fugle 欄位可能有異，視 API 版本
        
        return {
            "price": float(last_price),
            "change_pct": float(change_percent),
            "volume": int(volume),
            "last_updated": datetime.now().strftime('%H:%M:%S')
        }
    except: return None

def get_batch_detailed_quotes(stock_list):
    """批次取得詳細報價"""
    if "fugle_api_key" not in st.secrets: return {}
    api_key = st.secrets["fugle_api_key"]
    results = {}
    
    # 這裡不做進度條，因為盤中監控希望安靜更新
    for symbol in stock_list:
        res = get_detailed_quote(symbol, api_key)
        if res: results[symbol] = res
        time.sleep(0.1)
    return results

# --- [修改] 技術分析 (加入量比與乖離率) ---
def get_technical_analysis(symbol, api_key):
    """抓取歷史資料並計算技術指標"""
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=120)).strftime('%Y-%m-%d')
    
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/historical/candles/{symbol}"
    params = {"from": from_date, "to": to_date, "fields": "open,high,low,close,volume"}
    headers = {"X-API-KEY": api_key}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        data = response.json()
        if response.status_code != 200 or 'data' not in data: return {'Signal': '無資料', 'MA20': 0}
            
        df = pd.DataFrame(data['data'])
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 均線
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        df['MA60'] = df['close'].rolling(window=60).mean()
        
        # 成交量均線 (用於計算量比)
        df['Vol5'] = df['volume'].rolling(window=5).mean()
        
        if len(df) < 1: return {'Signal': '資料不足'}

        last = df.iloc[-1]
        price = last['close']
        ma5, ma10, ma20, ma60 = last['MA5'], last['MA10'], last['MA20'], last['MA60']
        vol = last['volume']
        vol5 = last['Vol5']
        
        signals = []
        # 1. 均線訊號
        if pd.notna(ma20):
            if price < ma20: signals.append("📉破月線")
            elif price > ma20: signals.append("🆗站上月線")
        if pd.notna(ma5) and ma5 > ma10 > ma20 > ma60: signals.append("🔥多頭排列")
        
        # 2. 量比 (預估量/5日均量，這裡簡化用昨日收盤後的量)
        # 若是盤中，建議由前端傳入即時量來比較
        vol_ratio = 0
        if pd.notna(vol5) and vol5 > 0:
            vol_ratio = vol / vol5
            if vol_ratio > 2: signals.append("💥爆量")
            
        # 3. 乖離率 (Bias) = (現價 - MA20) / MA20 * 100
        bias = 0
        if pd.notna(ma20) and ma20 > 0:
            bias = (price - ma20) / ma20 * 100

        return {
            'MA20': round(ma20, 2) if pd.notna(ma20) else 0,
            'Bias': round(bias, 2),
            'VolRatio': round(vol_ratio, 1),
            'Signal': " ".join(signals) if signals else "盤整"
        }
    except Exception as e:
        return {'Signal': 'Error', 'MA20': 0}

def get_batch_technical_analysis(stock_list):
    if "fugle_api_key" not in st.secrets: return {}
    api_key = st.secrets["fugle_api_key"]
    results = {}
    total = len(stock_list)
    # 只有在大量時才顯示進度條
    show_progress = total > 5
    if show_progress: bar = st.progress(0)
    
    for i, symbol in enumerate(stock_list):
        res = get_technical_analysis(symbol, api_key)
        results[symbol] = res
        if show_progress: bar.progress((i+1)/total)
        time.sleep(0.2)
    
    if show_progress: bar.empty()
    return results
