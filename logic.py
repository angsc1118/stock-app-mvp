# ==============================================================================
# 檔案名稱: logic.py
# 
# 修改歷程:
# 2025-11-23: [Update] 新增 get_volume_multiplier 與 calculate_volume_ratio 動能計算邏輯
# ==============================================================================

import pandas as pd
from collections import deque
import uuid
from datetime import datetime

# --- 常數設定 ---
COMMISSION_RATE = 0.001425
MIN_FEE = 1
TAX_RATE = 0.003       # 一般股票交易稅
ETF_TAX_RATE = 0.001   # ETF 交易稅

# ... (保留原本的 calculate_fees, generate_txn_id, _safe_float, calculate_fifo_report, calculate_unrealized_pnl, calculate_realized_report, calculate_account_balances 函式，為節省篇幅此處省略重複部分，請確保沒有刪除舊有程式碼) ...

# 在 logic.py 檔案的最後面加入以下程式碼：

# ------------------------------------------------------------------------------
#  [新增功能] 盤中動能相關邏輯
# ------------------------------------------------------------------------------

def get_volume_multiplier(current_time_str, mp_df):
    """
    根據當前時間查表取得預估量倍數
    current_time_str: "09:30" (HH:MM)
    mp_df: DataFrame，包含欄位 ["時間點迄 (HH:MM)", "量能倍數"]
    """
    if mp_df.empty:
        return 1.0
    
    # 確保欄位名稱去空白
    mp_df.columns = mp_df.columns.str.strip()
    col_time = "時間點迄 (HH:MM)"
    col_mult = "量能倍數"
    
    if col_time not in mp_df.columns or col_mult not in mp_df.columns:
        return 1.0

    # 尋找第一個「大於等於」當前時間的列
    # 假設 mp_table 是按時間排序的
    try:
        # 將時間轉為字串比較 (HH:MM 格式字串比較是有效的)
        for index, row in mp_df.iterrows():
            limit_time = str(row[col_time]).strip()
            # 格式化為 HH:MM 確保比較正確 (例如 9:05 -> 09:05)
            if ':' in limit_time:
                h, m = limit_time.split(':')
                limit_time = f"{int(h):02d}:{int(m):02d}"
            
            if current_time_str <= limit_time:
                multiplier = float(row[col_mult])
                return multiplier
        
        # 如果時間超過最後一筆 (例如 13:30 以後)，通常倍數為 1
        return 1.0
        
    except Exception as e:
        print(f"Multiplier calc error: {e}")
        return 1.0

def calculate_volume_ratio(current_vol, vol_10ma, multiplier):
    """
    計算動能指標
    current_vol: 目前成交量
    vol_10ma: 10日均量
    multiplier: 時間倍數
    
    Return:
        est_vol: 預估今日成交量
        ratio: 量比
    """
    if vol_10ma is None or vol_10ma == 0:
        return 0, 0
    
    # 預估量 = 目前量 * 倍數
    est_vol = current_vol * multiplier
    
    # 量比 = 預估量 / 10日均量
    ratio = est_vol / vol_10ma
    
    return int(est_vol), round(ratio, 2)
