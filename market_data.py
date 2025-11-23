# ==============================================================================
# 檔案名稱: market_data.py
# 
# 修改歷程:
# 2025-11-23: [Fix] 修正 Vol10 計算邏輯 (排除當日、單位檢查)；加入除錯 Log
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
            "volume": int(volume),
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

# --- [修改] 技術分析 (加入 Vol10 與 Debug) ---
def get_technical_analysis(symbol, api_key):
    """
    抓取歷史資料並計算技術指標
    修正：排除今日盤中資料計算均量，避免數據被拉低
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
            print(f"DEBUG: {symbol} API error or no data.")
            return {'Signal': '無資料', 'MA20': 0, 'Vol10': 0}
            
        df = pd.DataFrame(data['data'])
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # --- DEBUG LOG START ---
        # 印出最後 3 筆資料，確認是否包含今日 (盤中)
        print(f"\n=== DEBUG: {symbol} 歷史資料 (末3筆) ===")
        print(df.tail(3)[['date', 'close', 'volume']])
        
        # 檢查單位：Fugle 歷史量通常是「張」(board_lot) 還是「股」(shares)?
        # 觀察 log 數值：如果是 2,000,000 這種大數字就是股，如果是 2,000 就是張
        last_vol_raw = df.iloc[-1]['volume']
        print(f"DEBUG: 最新一筆成交量數值為 {last_vol_raw}")
        # --- DEBUG LOG END ---

        # 1. 排除今日資料 (如果這筆資料的日期是今天，代表是盤中即時 K 線)
        today_str = datetime.now().strftime('%Y-%m-%d')
        last_date_str = df.iloc[-1]['date'].strftime('%Y-%m-%d')
        
        df_calc = df.copy()
        if last_date_str == today_str:
            print(f"DEBUG: 偵測到今日 ({today_str}) 資料，計算均量時排除此筆。")
            df_calc = df.iloc[:-1] # 排除最後一筆 (今日)
        
        # 2. 計算技術指標
        df_calc['MA5'] = df_calc['close'].rolling(window=5).mean()
        df_calc['MA10'] = df_calc['close'].rolling(window=10).mean()
        df_calc['MA20'] = df_calc['close'].rolling(window=20).mean()
        df_calc['MA60'] = df_calc['close'].rolling(window=60).mean()
        
        # [修正] 10日均量
        # Fugle 歷史資料 volume 單位通常是「張」(但有時會變，需觀察 Log)
        # 假設單位是「張」，如果不對請告知 Log 數值
        df_calc['Vol10'] = df_calc['volume'].rolling(window=10).mean()
        
        if len(df_calc) < 1: return {'Signal': '資料不足', 'MA20': 0, 'Vol10': 0}

        # 取出計算結果 (昨收基準)
        last = df_calc.iloc[-1]
        price = last['close'] # 這是昨收價
        ma5, ma10, ma20, ma60 = last['MA5'], last['MA10'], last['MA20'], last['MA60']
        vol10 = last['Vol10']
        
        # 訊號判斷需要用「現價」(盤中) 跟「昨收均線」比嗎？
        # 或是用「昨收」跟「昨收均線」比？
        # 通常技術分析看盤軟體是： (今日即時價) vs (昨日算出來的 MA數值)
        # 但均線本身數值也會隨今日收盤價變動。
        # 這裡我們回傳的是「昨日收盤後的 MA 與 Vol10」，這是最穩定的基準。

        signals = []
        # 簡單均線訊號 (參考用)
        if pd.notna(ma20):
            # 這裡的 price 是昨收，若要即時訊號，前端會拿 realtime price 來比
            pass 
        
        if pd.notna(ma5) and ma5 > ma10 > ma20 > ma60: signals.append("🔥多頭排列")
        
        bias = 0
        if pd.notna(ma20) and ma20 > 0:
            bias = (price - ma20) / ma20 * 100

        print(f"DEBUG: 計算結果 Vol10 = {vol10}")
        
        # 如果發現 Vol10 數值過大 (例如幾百萬)，可能是「股」，需除以 1000 轉「張」
        # 簡單防呆：如果 10日均量 > 10萬張 (且不是權值股)，可能就是單位問題
        # 但像長榮航可能有幾十萬張。
        # 比較保險的做法：Fugle Historical API 預設是「張」。除非您用的是 odd lot。
        
        return {
            'MA20': round(ma20, 2) if pd.notna(ma20) else 0,
            'Vol10': int(vol10) if pd.notna(vol10) else 0,
            'Bias': round(bias, 2),
            'Signal': " ".join(signals) if signals else "盤整"
        }
    except Exception as e:
        print(f"TA Error {symbol}: {e}")
        return {'Signal': 'Error', 'MA20': 0, 'Vol10': 0}

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