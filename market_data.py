--- START OF FILE market_data.py ---

# ==============================================================================
# 檔案名稱: market_data.py
# 
# 修改歷程:
# 2025-11-24 15:45:00: [Fix] 修正語法結構，確保時區處理與字典閉合正確
# 2025-11-24 15:30:00: [Fix] 修正 get_technical_analysis 時區問題 (改用 UTC+8)
# ==============================================================================

import streamlit as st
import requests
import time
import pandas as pd
from datetime import datetime, timedelta

def get_price_from_fugle(symbol, api_key):
    """單純取得價格"""
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
    """批次取得價格"""
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
    """取得詳細即時報價"""
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}"
    headers = {"X-API-KEY": api_key}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200: return None
        data = response.json()
        
        last_price = 0
        if 'total' in data: last_price = data['total'].get('price', 0)
        elif 'quote' in data: last_price = data['quote'].get('close', 0)
        elif 'trade' in data: last_price = data['trade'].get('price', 0)
        if last_price == 0: last_price = data.get('lastPrice', 0)
        
        change_percent = 0
        if 'quote' in data: change_percent = data['quote'].get('changePercent', 0)
        elif 'changePercent' in data: change_percent = data['changePercent']
            
        volume = 0
        if 'total' in data: volume = data['total'].get('tradeVolume', 0)
        elif 'trade' in data: volume = data['trade'].get('volume', 0)
        
        return {
            "price": float(last_price),
            "change_pct": float(change_percent),
            "volume": int(volume), # 單位: 股 (Shares)
            "last_updated": datetime.now().strftime('%H:%M:%S')
        }
    except: return None

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
    """
    抓取歷史資料並計算技術指標
    修正：排除今日盤中資料計算均量 (使用 UTC+8 判斷日期)
    """
    # 設定台灣時間
    tw_now = datetime.utcnow() + timedelta(hours=8)
    to_date = tw_now.strftime('%Y-%m-%d')
    from_date = (tw_now - timedelta(days=120)).strftime('%Y-%m-%d')
    
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

        # 1. 排除今日資料 (使用台灣時間判斷)
        today_str = tw_now.strftime('%Y-%m-%d')
        last_date_str = df.iloc[-1]['date'].strftime('%Y-%m-%d')
        
        df_calc = df.copy()
        if last_date_str == today_str:
            df_calc = df.iloc[:-1] # 排除最後一筆 (因為是今日盤中資料)
        
        # 2. 計算技術指標
        df_calc['MA5'] = df_calc['close'].rolling(window=5).mean()
        df_calc['MA10'] = df_calc['close'].rolling(window=10).mean()
        df_calc['MA20'] = df_calc['close'].rolling(window=20).mean()
        df_calc['MA60'] = df_calc['close'].rolling(window=60).mean()
        df_calc['Vol10'] = df_calc['volume'].rolling(window=10).mean()
        
        if len(df_calc) < 1: 
            return {'Signal': '資料不足', 'MA20': 0, 'Vol10': 0, 'debug_info': debug_info}

        last = df_calc.iloc[-1]
        price = last['close']
        ma5 = last['MA5']
        ma10 = last['MA10']
        ma20 = last['MA20']
        ma60 = last['MA60']
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
            'Vol10': int(vol10) if pd.notna(vol10) else 0, # 單位: 股 (Shares)
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
