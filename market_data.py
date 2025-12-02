# ==============================================================================
# 檔案名稱: market_data.py
# 
# 修改歷程:
# 2025-12-02 08:30:00: [Fix] 新增「昨收價回退機制 (Fallback)」。若盤前現價為0，自動使用 previousClose 計算市值。
# 2025-11-23 19:53:00: [Update] 調整盤中戰情監控；現價移除$；格式套用千分位
# ==============================================================================

import streamlit as st
import requests
import time
import pandas as pd
from datetime import datetime, timedelta

def get_price_from_fugle(symbol, api_key):
    """
    單純取得價格 (用於計算資產總值)
    修正邏輯：若現價為 0 (盤前/休市)，自動回退使用昨收價 (previousClose)
    """
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}"
    headers = {"X-API-KEY": api_key}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200: return None
        data = response.json()
        
        last_price = None
        
        # 1. 嘗試取得即時成交價
        if 'total' in data and data['total'].get('price') is not None: last_price = data['total']['price']
        elif 'quote' in data and data['quote'].get('close') is not None: last_price = data['quote']['close']
        elif 'trade' in data and data['trade'].get('price') is not None: last_price = data['trade']['price']
        elif data.get('price') is not None: last_price = data['price']
        
        # 若上述都沒抓到，嘗試 root level 的 lastPrice
        if last_price is None or last_price == 0: 
            last_price = data.get('lastPrice', 0)
            
        # 2. [關鍵修正] 昨收價回退機制 (Fallback)
        # 如果現價仍為 0 (通常發生在盤前 08:30-09:00 或休市期間 API 歸零)
        # 則讀取 previousClose 作為計算基準，避免資產歸零
        if float(last_price) == 0:
            previous_close = data.get('previousClose', 0)
            if previous_close and float(previous_close) > 0:
                return float(previous_close)
                
        return float(last_price)
    except: return None

def get_realtime_prices(stock_list):
    """批次取得價格 (搭配 Progress Bar)"""
    if "fugle_api_key" not in st.secrets: return {}
    api_key = st.secrets["fugle_api_key"]
    prices = {}
    
    # 建立進度條
    progress_bar = st.progress(0)
    total = len(stock_list)
    
    for i, symbol in enumerate(stock_list):
        price = get_price_from_fugle(symbol, api_key)
        if price is not None: prices[symbol] = price
        # 更新進度
        progress_bar.progress((i + 1) / total)
        time.sleep(0.1) # 避免觸發 API Rate Limit
        
    progress_bar.empty()
    return prices

def get_detailed_quote(symbol, api_key):
    """
    取得詳細即時報價 (含漲跌幅、成交量)
    修正邏輯：若現價為 0，使用昨收價，並將漲跌幅設為 0
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
        
        # 2. 取得漲跌幅與成交量
        change_percent = 0
        if 'quote' in data: change_percent = data['quote'].get('changePercent', 0)
        elif 'changePercent' in data: change_percent = data['changePercent']
            
        volume = 0
        if 'total' in data: volume = data['total'].get('tradeVolume', 0)
        elif 'trade' in data: volume = data['trade'].get('volume', 0)
        
        # 3. [關鍵修正] 昨收價回退機制 (Fallback)
        # 若現價為 0，改用 previousClose，並強制將漲跌幅設為 0 (代表尚未開盤)
        if float(last_price) == 0:
            previous_close = data.get('previousClose', 0)
            if previous_close and float(previous_close) > 0:
                last_price = previous_close
                change_percent = 0.0 # 使用昨收價時，當日漲跌幅應視為 0
        
        return {
            "price": float(last_price),
            "change_pct": float(change_percent),
            "volume": int(volume),
            "last_updated": datetime.now().strftime('%H:%M:%S')
        }
    except: return None

def get_batch_detailed_quotes(stock_list):
    """批次取得詳細報價 (用於盤中監控)"""
    if "fugle_api_key" not in st.secrets: return {}
    api_key = st.secrets["fugle_api_key"]
    results = {}
    for symbol in stock_list:
        res = get_detailed_quote(symbol, api_key)
        if res: results[symbol] = res
        time.sleep(0.1)
    return results

def get_technical_analysis(symbol, api_key):
    """
    抓取歷史資料並計算技術指標
    修正：排除今日盤中資料計算均量 (維持原邏輯)
    """
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
        
        # --- 準備 Debug 資訊 ---
        last_3_rows = df.tail(3)[['date', 'close', 'volume']].copy()
        last_3_rows['date'] = last_3_rows['date'].dt.strftime('%Y-%m-%d')
        debug_info = last_3_rows.to_dict('records') 
        # ---------------------

        # 1. 排除今日資料 (避免盤中波動影響歷史均線計算)
        today_str = datetime.now().strftime('%Y-%m-%d')
        last_date_str = df.iloc[-1]['date'].strftime('%Y-%m-%d')
        
        df_calc = df.copy()
        if last_date_str == today_str:
            df_calc = df.iloc[:-1] # 排除最後一筆
        
        # 2. 計算技術指標
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

        return {
            'MA20': round(ma20, 2) if pd.notna(ma20) else 0,
            'Vol10': int(vol10) if pd.notna(vol10) else 0,
            'Bias': round(bias, 2),
            'Signal': " ".join(signals) if signals else "盤整",
            'debug_info': debug_info
        }
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
