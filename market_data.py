# ==============================================================================
# 檔案名稱: market_data.py
# 
# 修改歷程:
# 2025-12-04 16:30:00: [UI] 導入視覺優化方案：使用紅綠圓形(🔴/🟢)、天氣符號(🌤️/🌧️)與火箭(🚀)
# 2025-12-03 14:10:00: [Feat] 新增「月線趨勢判斷」：比較末兩日 MA20
# 2025-12-02 08:30:00: [Fix] 新增「昨收價回退機制 (Fallback)」
# ==============================================================================

import streamlit as st
import requests
import time
import pandas as pd
from datetime import datetime, timedelta

# --- 視覺規範定義 (Design System) ---
ICONS = {
    "MA_UP": "🔴",       # 月線上彎 (強支撐)
    "MA_FLAT": "➖",     # 月線走平 (無方向)
    "MA_DOWN": "🟢",     # 月線下彎 (強壓力)
    "ABOVE_MA": "🌤️",    # 站上月線 (晴)
    "BELOW_MA": "🌧️",    # 跌破月線 (雨)
    "BULL_FULL": "🚀",   # 多頭排列 (噴出)
    "MA_CROSS_UP": "🆗", # 黃金交叉 (保留)
    "MA_CROSS_DOWN": "📉" # 死亡交叉 (保留)
}

def get_price_from_fugle(symbol, api_key):
    """取得單一價格 (含盤前昨收回退機制)"""
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
            
        # Fallback
        if float(last_price) == 0:
            previous_close = data.get('previousClose', 0)
            if previous_close and float(previous_close) > 0:
                return float(previous_close)
                
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
    """取得詳細報價 (含昨收回退)"""
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
        
        # Fallback
        if float(last_price) == 0:
            previous_close = data.get('previousClose', 0)
            if previous_close and float(previous_close) > 0:
                last_price = previous_close
                change_percent = 0.0
        
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
    for symbol in stock_list:
        res = get_detailed_quote(symbol, api_key)
        if res: results[symbol] = res
        time.sleep(0.1)
    return results

def get_technical_analysis(symbol, api_key):
    """
    抓取歷史資料並計算技術指標 (含視覺優化邏輯)
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
        
        # Debug info
        last_3_rows = df.tail(3)[['date', 'close', 'volume']].copy()
        last_3_rows['date'] = last_3_rows['date'].dt.strftime('%Y-%m-%d')
        debug_info = last_3_rows.to_dict('records') 

        # 排除今日
        today_str = datetime.now().strftime('%Y-%m-%d')
        last_date_str = df.iloc[-1]['date'].strftime('%Y-%m-%d')
        
        df_calc = df.copy()
        if last_date_str == today_str:
            df_calc = df.iloc[:-1] 
        
        # 計算指標
        df_calc['MA5'] = df_calc['close'].rolling(window=5).mean()
        df_calc['MA10'] = df_calc['close'].rolling(window=10).mean()
        df_calc['MA20'] = df_calc['close'].rolling(window=20).mean()
        df_calc['MA60'] = df_calc['close'].rolling(window=60).mean()
        df_calc['Vol10'] = df_calc['volume'].rolling(window=10).mean()
        
        if len(df_calc) < 2: return {'Signal': '資料不足', 'MA20': 0, 'Vol10': 0, 'debug_info': debug_info}

        # 取值
        last = df_calc.iloc[-1]
        prev = df_calc.iloc[-2]
        
        price = last['close']
        ma5, ma10, ma20, ma60 = last['MA5'], last['MA10'], last['MA20'], last['MA60']
        vol10 = last['Vol10']
        
        signals = []
        
        # A. 判斷月線趨勢 (斜率計算)
        if pd.notna(ma20) and pd.notna(prev['MA20']):
            prev_ma20 = prev['MA20']
            # 計算變化率 %
            pct_change = (ma20 - prev_ma20) / prev_ma20 * 100
            
            # 設定 0.05% 為走平的容忍範圍
            FLAT_THRESHOLD = 0.05
            
            if pct_change > FLAT_THRESHOLD:
                signals.append(f"{ICONS['MA_UP']}上彎")
            elif pct_change < -FLAT_THRESHOLD:
                signals.append(f"{ICONS['MA_DOWN']}下彎")
            else:
                signals.append(f"{ICONS['MA_FLAT']}走平")

        # B. 判斷站上/跌破月線 (狀態)
        if pd.notna(ma20):
            if price > ma20: signals.append(f"{ICONS['ABOVE_MA']}站上") 
            elif price < ma20: signals.append(f"{ICONS['BELOW_MA']}破線")

        # C. 判斷多頭排列 (動能)
        if pd.notna(ma5) and ma5 > ma10 > ma20 > ma60: 
            signals.append(f"{ICONS['BULL_FULL']}多排")
        
        bias = 0
        if pd.notna(ma20) and ma20 > 0:
            bias = (price - ma20) / ma20 * 100

        return {
            'MA20': round(ma20, 2) if pd.notna(ma20) else 0,
            'Vol10': int(vol10) if pd.notna(vol10) else 0,
            'Bias': round(bias, 2),
            'Signal': " ".join(signals) if signals else "-",
            'debug_info': debug_info
        }
    except Exception as e:
        return {'Signal': 'Error', 'MA20': 0, 'Vol10': 0, 'debug_info': str(e)}

def get_batch_technical_analysis(stock_list):
    """批次更新"""
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
