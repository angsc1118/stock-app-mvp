import streamlit as st
import pandas as pd
from collections import deque
import database
import logic
import utils

st.set_page_config(page_title="除錯工具", layout="wide", page_icon="🐞")
st.title("🐞 庫存計算除錯工具")
utils.render_sidebar_status()
# 1. 讀取資料
try:
    df_raw = database.load_data()
except:
    st.error("無法讀取資料庫")
    st.stop()

# 2. 選擇股票
all_stocks = df_raw['股票代號'].unique().tolist()
target_stock = st.selectbox("請選擇要除錯的股票代號", all_stocks, index=all_stocks.index('6567') if '6567' in all_stocks else 0)

if target_stock:
    st.divider()
    st.subheader(f"🔍 {target_stock} 計算過程追蹤")

    # 3. 模擬 logic.py 的前處理 (排序)
    df = df_raw.copy()
    df.columns = df.columns.str.strip()
    col_date = '交易日期'
    col_id = '股票代號'
    col_action = '交易類別'
    
    # 確保日期格式
    df[col_date] = pd.to_datetime(df[col_date])
    
    # 篩選該股票
    df_target = df[df[col_id].astype(str).str.strip() == str(target_stock)].copy()
    
    # [新增] 檢查同日多筆交易
    date_counts = df_target.groupby(col_date)[col_action].nunique()
    multi_action_dates = date_counts[date_counts > 1].index.tolist()
    
    if multi_action_dates:
        st.warning(f"⚠️ 偵測到以下日期同時存在多種交易類別 (如買進+賣出)，系統已自動強制排序 (買進優先)：")
        for d in multi_action_dates:
            st.write(f"- {d.strftime('%Y-%m-%d')}")
    
    # [模擬 Logic 排序]：套用新邏輯
    df_target['sort_order'] = df_target[col_action].apply(logic._get_action_sort_order)
    df_target = df_target.sort_values(by=[col_date, 'sort_order'])
    
    # 顯示原始資料排序
    st.markdown("### 1. 程式邏輯排序後的交易順序 (買進應在賣出前)")
    st.dataframe(df_target[['交易日期', '交易類別', '股數', '單價', '交易帳戶']], use_container_width=True)

    # 4. 逐步執行 FIFO 並顯示 Log
    st.markdown("### 2. 逐步計算日誌")
    
    portfolio = deque()
    log_messages = []
    
    for i, row in df_target.iterrows():
        action = row['交易類別']
        qty = float(str(row['股數']).replace(',', ''))
        date_str = row['交易日期'].strftime('%Y-%m-%d')
        
        msg = f"📅 **{date_str}** - {action} {qty} 股"
        
        if action in ['買進', '現金增資', '股票股利']:
            portfolio.append({'qty': qty, 'date': date_str})
            msg += f" -> ✅ 買入成功。目前庫存: **{sum(x['qty'] for x in portfolio)}** 股"
            log_messages.append(msg)
            
        elif action == '賣出':
            sell_qty = qty
            original_sell_qty = qty
            
            # 檢查庫存是否足夠
            current_holdings = sum(x['qty'] for x in portfolio)
            
            if current_holdings < sell_qty:
                msg += f" -> ⚠️ **庫存不足！** (目前持有: {current_holdings}, 欲賣出: {sell_qty})"
                if current_holdings == 0:
                    msg += " -> ❌ **整筆賣出被忽略** (因為庫存為 0)"
                else:
                    msg += " -> ⚠️ **部分賣出** (只賣得掉現有的)"
            
            while sell_qty > 0 and portfolio:
                batch = portfolio.popleft()
                if batch['qty'] > sell_qty:
                    batch['qty'] -= sell_qty
                    portfolio.appendleft(batch)
                    sell_qty = 0
                else:
                    sell_qty -= batch['qty']
            
            remaining_holdings = sum(x['qty'] for x in portfolio)
            
            if sell_qty > 0:
                 msg += f" -> 最終仍有 {sell_qty} 股無法賣出 (視為放空或資料錯誤)。"
            
            msg += f" -> 結算後庫存: **{remaining_holdings}** 股"
            log_messages.append(msg)

    # 顯示 Log
    for log in log_messages:
        if "❌" in log or "⚠️" in log:
            st.error(log)
        else:
            st.success(log)

    # 5. 最終結果
    final_qty = sum(x['qty'] for x in portfolio)
    st.metric("最終計算庫存", f"{final_qty:,.0f} 股")
