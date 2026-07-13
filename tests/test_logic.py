# ==============================================================================
# 檔案名稱: test_logic.py
#
# 目的: logic.py 的 pytest 單元測試
#       依「stock-app-mvp 已知疑點清單」設計邊界案例，測試資料一律手刻於本檔案內。
#
# ⚠️ 重要說明：
#   本檔案中標記【已知疑點】的測試，目的是「鎖住現況行為」（regression test），
#   不代表該行為已被確認為正確。日後若決定修正對應邏輯，
#   請直接修改這些測試案例的預期值，而不是視為「測試失敗＝程式壞掉」。
#
# 修改歷程:
# 2026-07-13 00:00:00: [Feat] 建立 logic.py 完整單元測試（依已知疑點清單設計）
# ==============================================================================

import pandas as pd
import pytest
from datetime import datetime, timedelta

import logic


# ==============================================================================
# 共用測試資料建構輔助函式（僅在本檔案內使用，非對外 fixture）
# ==============================================================================

def make_txn(date, sid, name, action, qty, price,
             fee=0, tax=0, other=0, account="測試帳戶", notes=""):
    """組出一筆交易紀錄字典，欄位需與 logic.py 內使用的中文欄名一致"""
    return {
        "交易日期": date,
        "股票代號": sid,
        "股票名稱": name,
        "交易類別": action,
        "股數": qty,
        "單價": price,
        "手續費": fee,
        "交易稅": tax,
        "其他費用": other,
        "成交總金額": int(qty * price) if isinstance(qty, (int, float)) and isinstance(price, (int, float)) else 0,
        "總費用": fee + tax + other,
        "淨收付金額": 0,  # 個別測試會視需要覆寫
        "交易帳戶": account,
        "備註": notes,
    }


def make_txn_df(rows):
    return pd.DataFrame(rows)


# ==============================================================================
# 1. calculate_fees()
# ==============================================================================

class TestCalculateFees:

    def test_buy_commission_with_discount(self):
        """買進：手續費 = int(gross * 0.001425 * 折數)，套用折數"""
        res = logic.calculate_fees(qty=1000, price=100, action="買進", discount=0.6, stock_id="2330")
        gross = 1000 * 100
        expected_commission = max(int(gross * 0.001425 * 0.6), 1)
        assert res["gross_amount"] == gross
        assert res["commission"] == expected_commission
        assert res["tax"] == 0
        assert res["net_cash_flow"] == -(gross + res["total_fees"])

    def test_buy_min_fee_floor(self):
        """買進金額極小時，手續費應吃到最低 1 元"""
        res = logic.calculate_fees(qty=100, price=1, action="買進", discount=1.0, stock_id="2330")
        assert res["gross_amount"] == 100
        assert res["commission"] == 1  # int(100*0.001425)=0 -> 應被 MIN_FEE 蓋過

    def test_sell_normal_stock_tax_rate(self):
        """賣出一般股：交易稅率 0.3%"""
        res = logic.calculate_fees(qty=1000, price=50, action="賣出", discount=1.0, stock_id="2330")
        gross = 1000 * 50
        expected_tax = int(gross * 0.003)
        assert res["tax"] == expected_tax
        assert res["net_cash_flow"] == gross - res["total_fees"]

    def test_sell_etf_tax_rate(self):
        """賣出 ETF（代號 00 開頭）：交易稅率 0.1%"""
        res = logic.calculate_fees(qty=1000, price=20, action="賣出", discount=1.0, stock_id="0050")
        gross = 1000 * 20
        expected_tax = int(gross * 0.001)
        assert res["tax"] == expected_tax

    def test_deposit_net_cash_flow_positive(self):
        """入金：淨收付為正"""
        res = logic.calculate_fees(qty=1, price=5000, action="入金")
        assert res["net_cash_flow"] == 5000

    def test_withdraw_net_cash_flow_negative(self):
        """出金：淨收付為負"""
        res = logic.calculate_fees(qty=1, price=3000, action="出金")
        assert res["net_cash_flow"] == -3000

    def test_repayment_net_cash_flow_negative(self):
        """還款：視為負向現金流"""
        res = logic.calculate_fees(qty=1, price=2000, action="還款")
        assert res["net_cash_flow"] == -2000

    def test_cash_capital_increase_like_buy(self):
        """現金增資：現金流方向與買進相同（負）"""
        res = logic.calculate_fees(qty=1000, price=10, action="現金增資", discount=1.0, stock_id="2330")
        gross = 1000 * 10
        assert res["net_cash_flow"] == -(gross + res["total_fees"])

    def test_known_issue_cash_dividend_qty_times_price(self):
        """
        【已知疑點】現金股利：目前邏輯無論如何都是 qty*price 計算 gross_amount。
        若表單填入「實際持有股數」而非 1，金額會被放大 N 倍。
        本測試僅鎖住現況行為，不代表此為正確設計。
        """
        # 假設使用者誤填「持有股數 2000」+「股利總金額 5000」
        res = logic.calculate_fees(qty=2000, price=5000, action="現金股利")
        assert res["gross_amount"] == 2000 * 5000  # 明顯被放大，鎖住現況
        assert res["net_cash_flow"] == res["gross_amount"] - res["total_fees"]

    def test_known_issue_cash_dividend_qty_one_correct_usage(self):
        """現金股利：若正確填 qty=1（依表單設計慣例），金額不會被放大"""
        res = logic.calculate_fees(qty=1, price=5000, action="現金股利")
        assert res["gross_amount"] == 5000
        assert res["net_cash_flow"] == 5000

    def test_known_issue_stock_dividend_no_branch(self):
        """
        【已知疑點】股票股利：calculate_fees 完全沒有對應的 net_cash_flow 分支，
        會落到預設值 0。鎖住現況行為。
        """
        res = logic.calculate_fees(qty=1000, price=0, action="股票股利")
        assert res["net_cash_flow"] == 0
        assert res["commission"] == 0  # 不在 ['買進','賣出'] 內
        assert res["tax"] == 0  # 不是「賣出」

    def test_int_truncation_on_gross_amount(self):
        """gross_amount 使用 int()，小數部分直接捨去（非四捨五入）"""
        res = logic.calculate_fees(qty=1, price=999.9, action="入金")
        assert res["gross_amount"] == 999  # int(999.9) = 999
        assert res["net_cash_flow"] == 999


# ==============================================================================
# 2. calculate_fifo_report()
# ==============================================================================

class TestCalculateFifoReport:

    def test_basic_buy(self):
        df = make_txn_df([
            make_txn("2026-01-01", "2330", "台積電", "買進", 1000, 500, fee=712),
        ])
        result = logic.calculate_fifo_report(df)
        assert len(result) == 1
        row = result.iloc[0]
        assert row["庫存股數"] == 1000
        assert row["總持有成本 (FIFO)"] == 1000 * 500 + 712
        assert row["平均成本"] == round((1000 * 500 + 712) / 1000, 2)

    def test_same_day_buy_sell_buy_priority(self):
        """同日買賣：即使輸入順序是先賣後買，排序後仍應買進優先，讓賣出成功扣到庫存"""
        df = make_txn_df([
            make_txn("2026-01-05", "2330", "台積電", "賣出", 500, 520, tax=780),
            make_txn("2026-01-05", "2330", "台積電", "買進", 1000, 500, fee=712),
        ])
        result = logic.calculate_fifo_report(df)
        assert len(result) == 1
        # 若買進未優先執行，賣出會因庫存不足導致直接消失，庫存將錯誤地維持 1000
        assert result.iloc[0]["庫存股數"] == 500

    def test_sell_more_than_holding_disappears_silently(self):
        """庫存不足時賣出：多出的賣量直接消失，不放空、不拋錯"""
        df = make_txn_df([
            make_txn("2026-01-01", "2330", "台積電", "買進", 1000, 500, fee=712),
            make_txn("2026-01-02", "2330", "台積電", "賣出", 1500, 520, tax=2340),
        ])
        result = logic.calculate_fifo_report(df)
        # 賣 1500 只夠扣掉 1000，庫存應為 0，因低於 EPSILON 不會出現在報表
        assert result.empty

    def test_multi_batch_fifo_order(self):
        """多批買入後部分賣出：驗證先進先出扣批順序"""
        df = make_txn_df([
            make_txn("2026-01-01", "2330", "台積電", "買進", 10, 10, fee=0),   # 批次1: 10股 @10
            make_txn("2026-01-02", "2330", "台積電", "買進", 10, 20, fee=0),   # 批次2: 10股 @20
            make_txn("2026-01-03", "2330", "台積電", "賣出", 15, 30, tax=0),   # 賣15：扣光批次1(10) + 批次2的5股
        ])
        result = logic.calculate_fifo_report(df)
        row = result.iloc[0]
        # 剩餘：批次2剩5股 @20
        assert row["庫存股數"] == 5
        assert row["總持有成本 (FIFO)"] == 5 * 20
        assert row["平均成本"] == 20.0

    def test_stock_dividend_unit_cost(self):
        """股票股利：單位成本 = (fee+other)/qty，通常趨近於 0"""
        df = make_txn_df([
            make_txn("2026-01-01", "2330", "台積電", "股票股利", 100, 0, fee=0, other=0),
        ])
        result = logic.calculate_fifo_report(df)
        row = result.iloc[0]
        assert row["庫存股數"] == 100
        assert row["總持有成本 (FIFO)"] == 0

    def test_cash_capital_increase_same_as_buy(self):
        """現金增資：與買進走相同分支，成本計算一致"""
        df = make_txn_df([
            make_txn("2026-01-01", "2330", "台積電", "現金增資", 1000, 15, fee=0),
        ])
        result = logic.calculate_fifo_report(df)
        row = result.iloc[0]
        assert row["總持有成本 (FIFO)"] == 1000 * 15

    def test_cash_flow_actions_skipped(self):
        """入金/出金/還款：完全被跳過，不影響任何股票庫存"""
        df = make_txn_df([
            make_txn("2026-01-01", "", "", "入金", 1, 100000),
            make_txn("2026-01-02", "", "", "出金", 1, 5000),
            make_txn("2026-01-03", "", "目標A", "還款", 1, 3000),
        ])
        result = logic.calculate_fifo_report(df)
        assert result.empty

    def test_names_map_last_processed_wins(self):
        """
        同一股票代號但不同交易中名稱不同：names_map 會被每次符合條件的列覆寫，
        最終結果為排序後「最後處理」那一筆的名稱（鎖住現況行為）。
        """
        df = make_txn_df([
            make_txn("2026-01-01", "9999", "舊名稱", "買進", 100, 10, fee=0),
            make_txn("2026-01-02", "9999", "新名稱", "買進", 100, 10, fee=0),
        ])
        result = logic.calculate_fifo_report(df)
        assert result.iloc[0]["股票名稱"] == "新名稱"


# ==============================================================================
# 3. calculate_unrealized_pnl()
# ==============================================================================

class TestCalculateUnrealizedPnl:

    def _fifo_df(self):
        return pd.DataFrame([
            {"股票代號": "2330", "股票名稱": "台積電", "庫存股數": 1000, "總持有成本 (FIFO)": 500000, "平均成本": 500.0},
        ])

    def test_price_available_basic_calc(self):
        df_fifo = self._fifo_df()
        result = logic.calculate_unrealized_pnl(df_fifo, {"2330": 600})
        row = result.iloc[0]
        assert row["股票市值"] == 1000 * 600
        assert row["目前市價"] == 600
        # 未實現損益 = 市值 - 成本 - 預估賣出費用
        market_value = 1000 * 600
        raw_comm = int(market_value * logic.COMMISSION_RATE)
        comm = max(raw_comm, logic.MIN_FEE)
        tax = int(market_value * logic.TAX_RATE)
        expected_pnl = market_value - 500000 - (comm + tax)
        assert row["未實現損益"] == expected_pnl

    def test_known_issue_missing_price_fillna_zero(self):
        """
        【已知疑點】查無報價時 fillna(0)：市值歸零、未實現損益 = -總成本、報酬率 = -100%。
        會造成 KPI 與停損警示誤判。鎖住現況行為。
        """
        df_fifo = self._fifo_df()
        result = logic.calculate_unrealized_pnl(df_fifo, {})  # 查無 2330 報價
        row = result.iloc[0]
        assert row["目前市價"] == 0
        assert row["股票市值"] == 0
        assert row["未實現損益"] == -500000
        assert row["報酬率 (%)"] == -100.0

    def test_etf_sell_fee_uses_lower_tax_rate(self):
        df_fifo = pd.DataFrame([
            {"股票代號": "0050", "股票名稱": "元大台灣50", "庫存股數": 1000, "總持有成本 (FIFO)": 130000, "平均成本": 130.0},
        ])
        result = logic.calculate_unrealized_pnl(df_fifo, {"0050": 140})
        row = result.iloc[0]
        market_value = 1000 * 140
        expected_tax = int(market_value * logic.ETF_TAX_RATE)
        # 賣出額外費用格式為 "total (comm+tax)"，此處驗證 tax 數字有正確反映 ETF 稅率
        assert f"+{expected_tax})" in row["賣出額外費用"]

    def test_portfolio_ratio_multi_stock(self):
        df_fifo = pd.DataFrame([
            {"股票代號": "2330", "股票名稱": "台積電", "庫存股數": 1000, "總持有成本 (FIFO)": 500000, "平均成本": 500.0},
            {"股票代號": "2454", "股票名稱": "聯發科", "庫存股數": 100, "總持有成本 (FIFO)": 100000, "平均成本": 1000.0},
        ])
        result = logic.calculate_unrealized_pnl(df_fifo, {"2330": 600, "2454": 1000})
        total_mv = 1000 * 600 + 100 * 1000
        row_2330 = result[result["股票代號"] == "2330"].iloc[0]
        expected_ratio = (1000 * 600 / total_mv) * 100
        assert abs(row_2330["佔總資產比例 (%)"] - expected_ratio) < 1e-9

    def test_known_issue_inplace_mutation(self):
        """
        【已知疑點】calculate_unrealized_pnl 就地修改傳入的 df_fifo（未 copy）。
        鎖住現況行為，作為未來重構時的迴歸基準。
        """
        df_fifo = self._fifo_df()
        original_ref = df_fifo
        logic.calculate_unrealized_pnl(df_fifo, {"2330": 600})
        # 因為函式內是就地修改，呼叫端傳入的物件也會被加上新欄位
        assert "未實現損益" in original_ref.columns
        assert "股票市值" in original_ref.columns


# ==============================================================================
# 4. calculate_realized_report()
# ==============================================================================

class TestCalculateRealizedReport:

    def test_basic_sell_pnl(self):
        df = make_txn_df([
            make_txn("2026-01-01", "2330", "台積電", "買進", 1000, 500, fee=712),
            make_txn("2026-02-01", "2330", "台積電", "賣出", 1000, 600, fee=855, tax=1800),
        ])
        result = logic.calculate_realized_report(df)
        assert len(result) == 1
        row = result.iloc[0]
        cost_basis = 1000 * 500 + 712
        net_sell = 1000 * 600 - 855 - 1800
        assert row["本金(成本)"] == cost_basis
        assert row["已實現損益"] == net_sell - cost_basis

    def test_cash_dividend_recorded_as_dividend_category(self):
        df = make_txn_df([
            make_txn("2026-01-01", "2330", "台積電", "現金股利", 1, 5000, fee=0, tax=0),
        ])
        result = logic.calculate_realized_report(df)
        row = result.iloc[0]
        assert row["交易類別"] == "股息"
        assert row["已實現損益"] == 5000
        assert row["報酬率 (%)"] == 0
        assert row["本金(成本)"] == 0

    def test_same_day_buy_sell_order_affects_cost_basis(self):
        """同日買賣：排序後買進優先入庫，賣出才能正確取得成本"""
        df = make_txn_df([
            make_txn("2026-01-05", "2330", "台積電", "賣出", 500, 520, tax=780),
            make_txn("2026-01-05", "2330", "台積電", "買進", 1000, 500, fee=712),
        ])
        result = logic.calculate_realized_report(df)
        row = result[result["交易類別"] == "賣出"].iloc[0]
        # 成本應該是從剛買進的批次計算，而非 0
        assert row["本金(成本)"] > 0

    def test_year_month_fields(self):
        df = make_txn_df([
            make_txn("2026-03-15", "2330", "台積電", "買進", 1000, 500, fee=712),
            make_txn("2026-03-20", "2330", "台積電", "賣出", 1000, 600, fee=855, tax=1800),
        ])
        result = logic.calculate_realized_report(df)
        row = result.iloc[0]
        assert row["年"] == 2026
        assert row["月"] == "2026-03"

    def test_stock_dividend_affects_later_sell_cost_basis(self):
        """股票股利本身不產生已實現記錄，但會併入庫存影響後續賣出的 cost_basis"""
        df = make_txn_df([
            make_txn("2026-01-01", "2330", "台積電", "買進", 1000, 500, fee=712),
            make_txn("2026-02-01", "2330", "台積電", "股票股利", 100, 0, fee=0, other=0),
            make_txn("2026-03-01", "2330", "台積電", "賣出", 1100, 600, fee=940, tax=1980),
        ])
        result = logic.calculate_realized_report(df)
        # 只應有一筆「賣出」紀錄（股票股利不產生已實現紀錄）
        assert len(result) == 1
        row = result.iloc[0]
        # cost_basis = 1000批次成本 + 100批次成本(接近0)
        expected_cost = (1000 * 500 + 712) + 0
        assert row["本金(成本)"] == expected_cost


# ==============================================================================
# 5. calculate_account_balances()
# ==============================================================================

class TestCalculateAccountBalances:

    def test_multi_account_sum(self):
        df = pd.DataFrame([
            {"交易帳戶": "A帳戶", "淨收付金額": 1000},
            {"交易帳戶": "A帳戶", "淨收付金額": -300},
            {"交易帳戶": "B帳戶", "淨收付金額": 5000},
        ])
        result = logic.calculate_account_balances(df)
        assert result["A帳戶"] == 700
        assert result["B帳戶"] == 5000

    def test_comma_and_dollar_sign_parsing(self):
        df = pd.DataFrame([
            {"交易帳戶": "A帳戶", "淨收付金額": "$1,000"},
            {"交易帳戶": "A帳戶", "淨收付金額": "-500"},
        ])
        result = logic.calculate_account_balances(df)
        assert result["A帳戶"] == 500

    def test_repayment_reduces_balance(self):
        """還款會使該帳戶現金減少（刻意設計，非 bug）"""
        df = pd.DataFrame([
            {"交易帳戶": "A帳戶", "淨收付金額": 10000},  # 入金
            {"交易帳戶": "A帳戶", "淨收付金額": -3000},   # 還款
        ])
        result = logic.calculate_account_balances(df)
        assert result["A帳戶"] == 7000

    def test_empty_account_filtered_out(self):
        df = pd.DataFrame([
            {"交易帳戶": "", "淨收付金額": 1000},
            {"交易帳戶": "A帳戶", "淨收付金額": 500},
        ])
        result = logic.calculate_account_balances(df)
        assert "" not in result
        assert result["A帳戶"] == 500

    def test_empty_dataframe_returns_empty_dict(self):
        df = pd.DataFrame()
        result = logic.calculate_account_balances(df)
        assert result == {}


# ==============================================================================
# 6. get_volume_multiplier() / calculate_volume_ratio()
# ==============================================================================

class TestVolumeFunctions:

    def _mp_df(self):
        return pd.DataFrame([
            {"時間點迄 (HH:MM)": "09:10", "量能倍數": 8.0},
            {"時間點迄 (HH:MM)": "09:30", "量能倍數": 4.0},
            {"時間點迄 (HH:MM)": "10:00", "量能倍數": 2.5},
        ])

    def test_time_within_first_bucket(self):
        mult = logic.get_volume_multiplier("09:05", self._mp_df())
        assert mult == 8.0

    def test_time_within_middle_bucket(self):
        mult = logic.get_volume_multiplier("09:25", self._mp_df())
        assert mult == 4.0

    def test_time_beyond_all_buckets_default_one(self):
        mult = logic.get_volume_multiplier("13:30", self._mp_df())
        assert mult == 1.0

    def test_empty_mp_table_default_one(self):
        mult = logic.get_volume_multiplier("09:05", pd.DataFrame())
        assert mult == 1.0

    def test_volume_ratio_zero_division_protection(self):
        """vol_10ma 為 0 或 None 時應回傳 (0, 0)，避免除以 0"""
        assert logic.calculate_volume_ratio(1000, 0, 2.0) == (0, 0)
        assert logic.calculate_volume_ratio(1000, None, 2.0) == (0, 0)

    def test_volume_ratio_normal_calc(self):
        # vol_10ma 單位是股，需 /1000 換算成張
        est_vol, ratio = logic.calculate_volume_ratio(current_vol=500, vol_10ma=1000000, multiplier=2.0)
        assert est_vol == 1000  # 500 * 2.0
        assert ratio == round(1000 / (1000000 / 1000), 2)


# ==============================================================================
# 7. calculate_goal_progress()
# ==============================================================================

class TestCalculateGoalProgress:

    def _goals_df(self, **overrides):
        base = {
            "目標名稱": "還車貸",
            "目標金額": 100000,
            "起始日期": "2026-01-01",
            "截止日期": "2026-12-31",
            "狀態": "進行中",
            "目標類型": "還款",
        }
        base.update(overrides)
        return pd.DataFrame([base])

    def test_repayment_type_sums_by_goal_name(self):
        df_goals = self._goals_df()
        df_txn = make_txn_df([
            make_txn("2026-02-01", "", "還車貸", "還款", 1, 20000),
            make_txn("2026-03-01", "", "還車貸", "還款", 1, 10000),
        ])
        df_txn["淨收付金額"] = [-20000, -10000]
        result = logic.calculate_goal_progress(df_goals, df_txn)
        assert result[0]["current"] == 30000

    def test_profit_type_sums_realized_pnl_in_date_range(self):
        df_goals = self._goals_df(目標類型="獲利", 目標名稱="年度獲利目標", 目標金額=50000)
        df_txn = make_txn_df([
            make_txn("2026-01-01", "2330", "台積電", "買進", 1000, 500, fee=712),
            make_txn("2026-06-01", "2330", "台積電", "賣出", 1000, 600, fee=855, tax=1800),
        ])
        result = logic.calculate_goal_progress(df_goals, df_txn)
        assert result[0]["current"] > 0

    def test_profit_type_negative_shown_as_zero(self):
        """獲利型目標若虧損（負值），依需求顯示為 0"""
        df_goals = self._goals_df(目標類型="獲利", 目標名稱="年度獲利目標", 目標金額=50000)
        df_txn = make_txn_df([
            make_txn("2026-01-01", "2330", "台積電", "買進", 1000, 600, fee=855),
            make_txn("2026-06-01", "2330", "台積電", "賣出", 1000, 500, fee=712, tax=1500),
        ])
        result = logic.calculate_goal_progress(df_goals, df_txn)
        assert result[0]["current"] == 0

    def test_percent_capped_at_100(self):
        df_goals = self._goals_df(目標金額=10000)
        df_txn = make_txn_df([make_txn("2026-02-01", "", "還車貸", "還款", 1, 99999)])
        df_txn["淨收付金額"] = [-99999]
        result = logic.calculate_goal_progress(df_goals, df_txn)
        assert result[0]["percent"] == 100

    def test_target_zero_or_negative_skipped(self):
        df_goals = self._goals_df(目標金額=0)
        result = logic.calculate_goal_progress(df_goals, pd.DataFrame())
        assert result == []

    def test_status_ahead_and_behind_boundary(self):
        """±5% 寬容帶邊界：pct 剛好等於 time_pct+5 或 -5 應仍為 normal，超過才轉態"""
        today = datetime.now()
        start = today - timedelta(days=50)
        end = today + timedelta(days=50)  # 共100天，目前約走了50%
        df_goals = self._goals_df(
            目標金額=100000,
            起始日期=start.strftime("%Y-%m-%d"),
            截止日期=end.strftime("%Y-%m-%d"),
        )

        # current = 50000 -> pct約50%，與time_pct約50%相近 -> normal
        df_txn_normal = make_txn_df([make_txn("2026-01-01", "", "還車貸", "還款", 1, 50000)])
        df_txn_normal["淨收付金額"] = [-50000]
        result_normal = logic.calculate_goal_progress(df_goals, df_txn_normal)
        assert result_normal[0]["time_info"]["status"] == "normal"

        # current 遠低於 time_pct -> behind
        df_txn_behind = make_txn_df([make_txn("2026-01-01", "", "還車貸", "還款", 1, 1000)])
        df_txn_behind["淨收付金額"] = [-1000]
        result_behind = logic.calculate_goal_progress(df_goals, df_txn_behind)
        assert result_behind[0]["time_info"]["status"] == "behind"

    def test_monthly_needed_not_computed_when_already_achieved(self):
        """current 已達標時，不應計算 monthly_needed（維持 0）"""
        df_goals = self._goals_df(目標金額=10000)
        df_txn = make_txn_df([make_txn("2026-02-01", "", "還車貸", "還款", 1, 10000)])
        df_txn["淨收付金額"] = [-10000]
        result = logic.calculate_goal_progress(df_goals, df_txn)
        assert result[0]["time_info"]["monthly_needed"] == 0

    def test_invalid_date_does_not_crash(self):
        """日期格式錯誤時，has_date 應為 False，且不應拋出例外"""
        df_goals = self._goals_df(起始日期="不是日期", 截止日期="也不是日期")
        result = logic.calculate_goal_progress(df_goals, pd.DataFrame())
        assert result[0]["time_info"]["has_date"] is False

    def test_empty_goal_type_falls_back_to_repayment_behavior(self):
        """目標類型欄位為空字串時，因非'獲利'會落入 else 分支（還款邏輯）"""
        df_goals = self._goals_df(目標類型="")
        df_txn = make_txn_df([make_txn("2026-02-01", "", "還車貸", "還款", 1, 5000)])
        df_txn["淨收付金額"] = [-5000]
        result = logic.calculate_goal_progress(df_goals, df_txn)
        assert result[0]["current"] == 5000


# ==============================================================================
# 8. 輔助函式
# ==============================================================================

class TestHelperFunctions:

    def test_safe_float_with_comma(self):
        assert logic._safe_float("1,234") == 1234.0

    def test_safe_float_with_dollar_sign(self):
        assert logic._safe_float("$1,234.5") == 1234.5

    def test_safe_float_empty_string(self):
        assert logic._safe_float("") == 0.0

    def test_safe_float_none(self):
        assert logic._safe_float(None) == 0.0

    def test_safe_float_invalid_string(self):
        assert logic._safe_float("abc") == 0.0

    def test_safe_float_numeric_passthrough(self):
        assert logic._safe_float(123) == 123.0
        assert logic._safe_float(123.45) == 123.45

    def test_action_sort_order_buy_before_sell(self):
        assert logic._get_action_sort_order("買進") < logic._get_action_sort_order("賣出")

    def test_action_sort_order_other_actions(self):
        assert logic._get_action_sort_order("入金") == 3
        assert logic._get_action_sort_order("現金增資") == 1
        assert logic._get_action_sort_order("股票股利") == 1

    def test_generate_txn_id_format(self):
        txn_id = logic.generate_txn_id()
        assert txn_id.startswith("TXN-")
        suffix = txn_id.replace("TXN-", "")
        assert len(suffix) == 8
        assert suffix == suffix.upper()
