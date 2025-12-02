# ==============================================================================
# 檔案名稱: market_data.py
# 
# 修改歷程:
# 2025-12-02 12:00:00: [Fix] 強化異常數據過濾；確保 Fallback 時漲跌幅為 0
# 2025-12-02 08:30:00: [Fix] 新增「昨收價回退機制 (Fallback)」
# ==============================================================================

import streamlit as st
import requests
import time
import pandas as pd
from datetime import datetime, timedelta

# ... (get_price_from_fugle 保持不變，或直接使用下方完整版) ...
def get_price_from_fugle(symbol, api_key):
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
        
        if last_price is None or last_price == 0: 
            last_price = data.get('lastPrice', 0)
            
        # Fallback 機制
        if float(last_price) == 0:
            previous_close = data.get('previousClose', 0)
            if previous_close and float(previous_close) > 0:
                return float(previous_close)
                
        return float(last_price)
    except: return None

def get_realtime_prices(stock_list):
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

def get_detailed_quote(symbol, api_key):
    """
    取得詳細即時報價
    修正重點：確保漲跌幅計算邏輯正確，Fallback 時強制歸零
    """
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}"
    headers = {"X-API-KEY": api_key}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200: return None
        data = response.json()
        
        # 1. 取得現價
        last_price = 0
        if 'total' in data: last_price = data['total'].get('price', 0)
        elif 'quote' in data: last_price = data['quote'].get('close', 0)
        elif 'trade' in data: last_price = data['trade'].get('price', 0)
        if last_price == 0: last_price = data.get('lastPrice', 0)
        
        # 2. 取得漲跌幅
        change_percent = 0.0
        if 'quote' in data: change_percent = data['quote'].get('changePercent', 0)
        elif 'changePercent' in data: change_percent = data['changePercent']
            
        volume = 0
        if 'total' in data: volume = data['total'].get('tradeVolume', 0)
        elif 'trade' in data: volume = data['trade'].get('volume', 0)
        
        # 3. 昨收價與 Fallback 邏輯
        previous_close = data.get('previousClose', 0)
        
        # 狀況 A: 現價為 0 -> 強制使用昨收，漲跌幅設為 0
        if float(last_price) == 0:
            if previous_close and float(previous_close) > 0:
                last_price = previous_close
                change_percent = 0.0 
        
        # 狀況 B: 現價不為 0，但 API 回傳的漲跌幅異常 (例如 -100% 或極大值)
        # 有時候 API 資料錯亂會導致 changePercent 為 None 或怪異數字
        # 我們可以自己重算一次以防萬一
        elif float(previous_close) > 0:
             calc_change = (float(last_price) - float(previous_close)) / float(previous_close)
             # 若 API 回傳 0 但我們算出來不是 0，或 API 數值太誇張，可考慮用重算值
             # 這裡我們做一個簡單的 Sanity Check: 若 API 說跌超過 50% 但不是減資，通常是錯的
             if abs(change_percent) > 0.5 and abs(calc_change) < 0.2:
                 change_percent = calc_change
        
        return {
            "price": float(last_price),
            "change_pct": float(change_percent), # 保持小數點格式 (0.05 = 5%)
            "volume": int(volume),
            "last_updated": datetime.now().strftime('%H:%M:%S')
        }
    except: return None

# ... (其餘函式如 get_batch_detailed_quotes, get_technical_analysis 保持不變) ...
def get_batch_detailed_quotes(stock_list):
    if "fugle_api_key" not in st.secrets: return {}
    api_key = st.secrets["fugle_api_key"]
    results = {}
    for symbol in stock_list:
        res = get_detailed_quote(symbol, api_key)
        if res: results[symbol] = res
        time.sleep(0.1)
    return results

def get_technical_analysis(symbol, api_key):
    # ... (維持原版 get_technical_analysis 內容) ...
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=120)).strftime('%Y-%m-%d')
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/historical/candles/{symbol}"
    params = {"from": from_date, "to": to_date, "fields": "open,high,low,close,volume"}
    headers = {"X-API-KEY": api_key}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        data = response.json()
        if response.status_code != 200 or 'data' not in data: 
            return {'Signal': '無資料', 'MA20': 0, 'Vol10': 0, 'debug_info': 'API Error'}
        df = pd.DataFrame(data['data'])
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        last_3_rows = df.tail(3)[['date', 'close', 'volume']].copy()
        last_3_rows['date'] = last_3_rows['date'].dt.strftime('%Y-%m-%d')
        debug_info = last_3_rows.to_dict('records') 
        today_str = datetime.now().strftime('%Y-%m-%d')
        last_date_str = df.iloc[-1]['date'].strftime('%Y-%m-%d')
        df_calc = df.copy()
        if last_date_str == today_str:
            df_calc = df.iloc[:-1] 
        df_calc['MA5'] = df_calc['close'].rolling(window=5).mean()
        df_calc['MA10'] = df_calc['close'].rolling(window=10).mean()
        df_calc['MA20'] = df_calc['close'].rolling(window=20).mean()
        df_calc['MA60'] = df_calc['close'].rolling(window=60).mean()
        df_calc['Vol10'] = df_calc['volume'].rolling(window=10).mean()
        if len(df_calc) < 1: return {'Signal': '資料不足', 'MA20': 0, 'Vol10': 0, 'debug_info': debug_info}
        last = df_calc.iloc[-1]
        price = last['close']
        ma5, ma10, ma20, ma60 = last['MA5'], last['MA10'], last['MA20'], last['MA60']
        vol10 = last['Vol10']
        signals = []
        if pd.notna(ma20):
            if price < ma20: signals.append("📉破月線") 
            elif price > ma20: signals.append("🆗站上月線")
        if pd.notna(ma5) and ma5 > ma10 > ma20 > ma60: signals.append("🔥多頭排列")
        bias = 0
        if pd.notna(ma20) and ma20 > 0:
            bias = (price - ma20) / ma20 * 100
        return {'MA20': round(ma20, 2) if pd.notna(ma20) else 0,'Vol10': int(vol10) if pd.notna(vol10) else 0,'Bias': round(bias, 2),'Signal': " ".join(signals) if signals else "盤整",'debug_info': debug_info}
    except Exception as e:
        return {'Signal': 'Error', 'MA20': 0, 'Vol10': 0, 'debug_info': str(e)}

def get_batch_technical_analysis(stock_list):
    if "fugle_api_key" not in st.secrets: return {}
    api_key = st.secrets["fugle_api_key"]
    results = {}
    total = len(stock_list)
    show_progress = total > 5
    if show_progress: bar = st.progress(0)
    for i, symbol in enumerate(stock_list):
        res = get_technical_analysis(symbol, api_key)
        results[symbol] = res
        if show_progress: bar.progress((i+1)/total)
        time.sleep(0.2)
    if show_progress: bar.empty()
    return results
