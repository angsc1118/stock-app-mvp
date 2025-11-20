# ... (保留原本所有的 import 和函式)

# ... (保留 calculate_unrealized_pnl)

# --- 新增：計算各帳戶現金餘額 ---
def calculate_account_balances(df):
    """
    統計各帳戶的現金餘額
    Input: 交易紀錄 DataFrame
    Output: { '元大': 50000, '富邦': 120000 }
    """
    if df.empty:
        return {}

    # 確保欄位名稱正確 (對應 database save_transaction 的順序)
    # 假設您的 Sheet 欄位名稱為 '交易帳戶' 和 '淨收付金額'
    col_account = '交易帳戶'
    col_net_cash = '淨收付金額'

    if col_account not in df.columns or col_net_cash not in df.columns:
        return {}

    # 轉型並填補空值
    df[col_net_cash] = pd.to_numeric(df[col_net_cash], errors='coerce').fillna(0)
    
    # GroupBy 加總
    balances = df.groupby(col_account)[col_net_cash].sum().to_dict()
    
    return balances
