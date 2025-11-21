import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, datetime, timedelta # 新增 timedelta 處理時區

import database
import logic
import market_data

st.set_page_config(page_title="股票資產管理", layout="wide")
st.title('📊 股票資產管理系統 (Streamlit Cloud)')

# --- 預先讀取 ---
try:
    stock_map = database.get_stock_info_map()
except:
    stock_map = {}

try:
    account_settings = database.get_account_settings()
    account_list = list(account_settings.keys())
except:
    account_settings = {"預設帳戶": 0.6}
    account_list = ["預設帳戶"]

# --- Session State 初始化 ---
if "txn_date" not in st.session_state: st.session_state["txn_date"] = date.today()
if "txn_account" not in st.session_state: 
    st.session_state["txn_account"] = account_list[0] if account_list else ""
if st.session_state["txn_account"] not in account_list:
     st.session_state["txn_account"] = account_list[0] if account_list else ""
if "txn_stock_id" not in st.session_state: st.session_state["txn_stock_id"] = ""
if "txn_stock_name" not in st.session_state: st.session_state["txn_stock_name"] = ""
if "txn_qty" not in st.session_state: st.session_state["txn_qty"] = 0
if "txn_price" not in st.session_state: st.session_state["txn_price"] = 0.0
if "txn_notes" not in st.session_state: st.session_state["txn_notes"] = ""
if "form_msg" not in st.session_state: st.session_state["form_msg"] = None 
if "realtime_prices" not in st.session_state: st.session_state["realtime_prices"] = {}
if "price_update_time" not in st.session_state: st.session_state["price_update_time"] = None

# --- Callback ---
def submit_callback():
    s_date = st.session_state.txn_date
    s_account = st.session_state.txn_account
    s_id = st.session_state.txn_stock_id
    s_name = st.session_state.txn_stock_name
    s_action = st.session_state.txn_action
    s_qty = st.session_state.txn_qty
    s_price = st.session_state.txn_price
    s_notes = st.session_state.txn_notes
    s_discount = account_settings.get(s_account, 0.6)

    error_msgs = []
    if not s_account: error_msgs.append("❌ 請選擇「交易帳戶」")
    is_cash_flow = s_action in ['入金', '出金']
    if not is_cash_flow:
        if not s_id: error_msgs.append("❌ 請輸入「股票代號」")
        if not s_name: error_msgs.append("❌ 未輸入「股票名稱」")
    if s_action != '現金股利' and s_qty <= 0: error_msgs.append("❌ 「股數/數量」必須大於 0")
    if s_action in ['買進', '賣出', '入金', '出金'] and s_price <= 0: error_msgs.append("❌ 「單價/金額」必須大於 0")

    if error_msgs:
        st.session_state["form_msg"] = {"type": "error", "content": error_msgs}
    else:
        try:
            database.save_transaction(s_date, s_id, s_name, s_action, s_qty, s_price, s_account, s_notes, s_discount)
            st.session_state.txn_stock_id = ""
            st.session_state.txn_stock_name = ""
            st.session_state.txn_qty = 0
            st.session_state.txn_price = 0.0
            st.session_state.txn_notes = ""
            if is_cash_flow:
                amount = int(s_qty * s_price)
                st.session_state["form_msg"] = {"type": "success", "content": f"✅ 成功記錄：{s_action} ${amount:,} (帳戶: {s_account})"}
            else:
                st.session_state["form_msg"] = {"type": "success", "content": f"✅ 成功新增：{s_name} ({s_id}) {s_action} (折數: {s_discount})"}
        except Exception as e:
            st.session_state["form_msg"] = {"type": "error", "content": [f"寫入失敗: {e}"]}

# --- Sidebar ---
with st.sidebar:
    mode = st.radio("功能選擇", ["📝 新增交易", "🔧 帳戶餘額校正"], horizontal=True)
    
    if mode == "📝 新增交易":
        st.header("📝 新增交易")
        col1, col2 = st.columns(2)
        col1.date_input("交易日期", key="txn_date")
        col2.selectbox("交易帳戶", options=account_list, key="txn_account")
        input_action = st.selectbox("交易類別", ['買進', '賣出', '現金股利', '股票股利', '入金', '出金'], key="txn_action")
        is_cash_op = input_action in ['入金', '出金']

        if is_cash_op:
            st.info("💡 資金操作模式：請在「單價」欄位輸入金額，股票代號可留空。")
            input_stock_id = st.text_input("股票代號", placeholder="(可留空)", key="txn_stock_id", disabled=False)
        else:
            input_stock_id = st.text_input("股票代號", placeholder="例如 2330", key="txn_stock_id")
            if input_stock_id:
                clean_id = str(input_stock_id).strip()
                found_name = stock_map.get(clean_id, "")
                if found_name and st.session_state["txn_stock_name"] != found_name:
                    st.session_state["txn_stock_name"] = found_name
                    st.rerun()

        col2 = st.empty()
        if is_cash_op:
            st.text_input("股票名稱", placeholder="(可留空)", key="txn_stock_name")
        else:
            st.text_input("股票名稱", placeholder="自動帶入或手動輸入", key="txn_stock_name")

        col3, col4 = st.columns(2)
        qty_label = "數量 (預設1)" if is_cash_op else "股數"
        price_label = "金額" if is_cash_op else "單價"
        if is_cash_op and st.session_state["txn_qty"] == 0: st.session_state["txn_qty"] = 1

        col3.number_input(qty_label, min_value=0, step=1000, key="txn_qty")
        col4.number_input(price_label, min_value=0.0, step=0.5, format="%.2f", key="txn_price")
        st.text_area("備註", placeholder="選填", key="txn_notes")
        st.button("💾 提交交易", on_click=submit_callback)
        
    else:
        st.header("🔧 帳戶餘額校正")
        st.info("自動計算差額並產生修正交易。")
        adj_account = st.selectbox("選擇校正帳戶", options=account_list)
        try:
            df_temp = database.load_data()
            balances = logic.calculate_account_balances(df_temp)
            current_sys_bal = int(balances.get(adj_account, 0))
        except:
            current_sys_bal = 0
        st.metric("💻 系統目前帳面餘額", f"${current_sys_bal:,}")
        actual_bal = st.number_input("💰 輸入實際餘額", value=current_sys_bal, step=1000)
        diff = actual_bal - current_sys_bal
        if diff == 0:
            st.success("✅ 帳目吻合。")
        else:
            if diff > 0: st.warning(f"少記 ${diff:,} (需補入)")
            else: st.warning(f"多記 ${abs(diff):,} (需扣除)")
            if st.button("⚡ 執行強制校正"):
                try:
                    note = f"餘額校正: 系統(${current_sys_bal:,}) -> 實際(${actual_bal:,})"
                    action_type = "入金" if diff > 0 else "出金"
                    database.save_transaction(date.today(), "", "", action_type, 1, abs(diff), adj_account, note, 0.6)
                    st.success(f"已新增校正紀錄：{action_type} ${abs(diff):,}")
                    st.rerun()
                except Exception as e:
                    st.error(f"校正失敗: {e}")

    if st.session_state["form_msg"]:
        msg = st.session_state["form_msg"]
        if msg["type"] == "success": st.success(msg["content"])
        elif msg["type"] == "error": 
            for err in msg["content"]: st.error(err)

# ============================
# Main Content
# ============================
tab1, tab3, tab4, tab2 = st.tabs(["📊 資產庫存 (FIFO)", "📉 已實現損益", "📈 資產趨勢", "📋 原始交易"])

try:
    df_raw = database.load_data()

    # ------------------------------------------------
    # Tab 1: 庫存損益
    # ------------------------------------------------
    with tab1:
        st.subheader("庫存損益試算 (FIFO)")
        col_btn, col_time = st.columns([1.5, 4])
        if col_btn.button("🔄 更新即時股價 (Fugle API)"):
             if not df_raw.empty:
                temp_fifo = logic.calculate_fifo_report(df_raw)
                if not temp_fifo.empty:
                    stock_ids = temp_fifo['股票代號'].unique().tolist()
                    prices = market_data.get_realtime_prices(stock_ids)
                    st.session_state["realtime_prices"] = prices
                    # 修改 1: 強制加上 8 小時 (UTC+8 台灣時間)
                    tw_time = datetime.utcnow() + timedelta(hours=8)
                    st.session_state["price_update_time"] = tw_time.strftime("%Y-%m-%d %H:%M:%S")
                    st.rerun()
        
        if st.session_state["price_update_time"]:
            col_time.write(f"🕒 最後更新: **{st.session_state['price_update_time']}** (台灣時間)")
        else:
            col_time.write("🕒 尚未更新股價 (顯示為庫存成本)")

        if not df_raw.empty:
            acc_balances = logic.calculate_account_balances(df_raw)
            total_cash = sum(acc_balances.values())
            df_fifo = logic.calculate_fifo_report(df_raw)
            total_market_value = 0
            df_final = pd.DataFrame()

            if not df_fifo.empty:
                current_prices = st.session_state.get("realtime_prices", {})
                df_final = logic.calculate_unrealized_pnl(df_fifo, current_prices)
                total_market_value = df_final['股票市值'].sum()
            
            total_assets = total_cash + total_market_value
            cash_ratio = (total_cash / total_assets * 100) if total_assets > 0 else 0

            st.markdown("#### 💰 資產配置概況")
            
            # [新增] 記錄資產歷史的按鈕
            col_assets, col_record_btn = st.columns([4, 1])
            with col_assets:
                k1, k2, k3 = st.columns(3)
                k1.metric("總資產 (現金+持股)", f"${int(total_assets):,}")
                k2.metric("總現金餘額", f"${int(total_cash):,}")
                k3.metric("現金水位", f"{cash_ratio:.2f}%")
            
            with col_record_btn:
                if st.button("📝 記錄今日資產"):
                    try:
                        # 記錄時也使用台灣時間的日期
                        today_tw = (datetime.utcnow() + timedelta(hours=8)).date()
                        database.save_asset_history(today_tw, int(total_assets), int(total_cash), int(total_market_value))
                        st.success("已記錄！")
                    except Exception as e:
                        st.error(f"記錄失敗: {e}")

            st.divider()
            
            # 資產圓餅圖
            if total_assets > 0:
                chart_col1, chart_col2 = st.columns(2)
                with chart_col1:
                    alloc_df = pd.DataFrame({
                        '類別': ['現金', '股票'],
                        '金額': [total_cash, total_market_value]
                    })
                    fig_alloc = px.pie(alloc_df, values='金額', names='類別', hole=0.4, color='類別', color_discrete_map={'現金': '#00CC96', '股票': '#EF553B'})
                    fig_alloc.update_traces(textinfo='percent+label')
                    st.plotly_chart(fig_alloc, use_container_width=True)

                with chart_col2:
                    if not df_final.empty and total_market_value > 0:
                        fig_stock_pie = px.pie(df_final, values='股票市值', names='股票', hole=0.4)
                        fig_stock_pie.update_traces(textposition='inside', textinfo='percent+label')
                        fig_stock_pie.update_layout(showlegend=False)
                        st.plotly_chart(fig_stock_pie, use_container_width=True)
                    else:
                        st.info("目前無持股部位")

            st.divider()

            if not df_final.empty:
                total_stock_cost = df_final['總持有成本 (FIFO)'].sum()
                total_stock_pnl = df_final['未實現損益'].sum()
                total_stock_return = (total_stock_pnl / total_stock_cost * 100) if total_stock_cost != 0 else 0
                
                st.caption("股票部位損益")
                m1, m2, m3 = st.columns(3)
                m1.metric("總持有成本", f"${total_stock_cost:,.0f}")
                m2.metric("總股票市值", f"${total_market_value:,.0f}")
                m3.metric("未實現損益", f"${total_stock_pnl:,.0f}", delta=f"{total_stock_return:.2f}%")
                
                def color_pnl(val):
                    if isinstance(val, (int, float)):
                        return f'color: {"red" if val > 0 else "green" if val < 0 else "black"}'
                    return ''

                display_cols = ['股票', '庫存股數', '平均成本', '目前市價', '股票市值', '未實現損益', '報酬率 (%)', '佔總資產比例 (%)', '賣出額外費用', '配息金額']
                format_dict = {
                    "庫存股數": "{:,.0f}", "平均成本": "{:,.2f}", "目前市價": "{:,.2f}",
                    "股票市值": "{:,.0f}", "未實現損益": "{:,.0f}", "報酬率 (%)": "{:,.2f}%",
                    "佔總資產比例 (%)": "{:,.2f}%", "配息金額": "{:,.0f}"
                }
                st.dataframe(df_final[display_cols].style.format(format_dict).map(color_pnl, subset=['未實現損益', '報酬率 (%)']), use_container_width=True)
            else:
                st.info("目前沒有庫存。")
        else:
            st.warning("目前沒有交易紀錄。")

    # ------------------------------------------------
    # Tab 3: 已實現損益
    # ------------------------------------------------
    with tab3:
        st.subheader("已實現損益分析 (Realized P&L)")
        if not df_raw.empty:
            df_realized = logic.calculate_realized_report(df_raw)
            
            if not df_realized.empty:
                # 修改 2: 對 df_realized 的交易日期進行格式化
                df_realized['交易日期'] = pd.to_datetime(df_realized['交易日期']).dt.date

                all_years = sorted(df_realized['年'].unique().tolist(), reverse=True)
                year_options = ["全部"] + all_years
                col_filter, _ = st.columns([1, 3])
                selected_year = col_filter.selectbox("📅 選擇檢視年度", year_options)
                
                if selected_year == "全部":
                    df_view = df_realized
                else:
                    df_view = df_realized[df_realized['年'] == selected_year]
                
                if df_view.empty:
                    st.info(f"{selected_year} 年度尚無已實現損益紀錄。")
                else:
                    total_realized_pnl = df_view['已實現損益'].sum()
                    sell_trades = df_view[df_view['交易類別'] == '賣出']
                    win_trades = sell_trades[sell_trades['已實現損益'] > 0]
                    win_rate = (len(win_trades) / len(sell_trades) * 100) if not sell_trades.empty else 0
                    total_div = df_view[df_view['交易類別'] == '股息']['已實現損益'].sum()
                    
                    kp1, kp2, kp3, kp4 = st.columns(4)
                    kp1.metric("已實現損益 (區間)", f"${total_realized_pnl:,.0f}")
                    kp2.metric("交易獲利 (不含息)", f"${sell_trades['已實現損益'].sum():,.0f}")
                    kp3.metric("現金股利總額", f"${total_div:,.0f}")
                    kp4.metric("交易勝率", f"{win_rate:.1f}%", help=f"獲利 {len(win_trades)} 筆 / 總計 {len(sell_trades)} 筆")
                    
                    st.divider()
                    
                    chart_col1, chart_col2 = st.columns(2)
                    
                    with chart_col1:
                        st.markdown(f"##### 📅 月度損益趨勢 ({selected_year})")
                        monthly_pnl = df_view.groupby('月')['已實現損益'].sum().reset_index()
                        if selected_year == "全部": monthly_pnl = monthly_pnl.sort_values('月').tail(12)
                        else: monthly_pnl = monthly_pnl.sort_values('月')
                        
                        monthly_pnl['Color'] = monthly_pnl['已實現損益'].apply(lambda x: 'Profit' if x >= 0 else 'Loss')
                        fig_month = px.bar(monthly_pnl, x='月', y='已實現損益', color='Color', color_discrete_map={'Profit': '#E53935', 'Loss': '#26a69a'}, text_auto='.2s')
                        fig_month.update_traces(hovertemplate='<b>%{x}</b><br>已實現損益: %{y:,.0f}<extra></extra>')
                        fig_month.update_layout(showlegend=False, xaxis_title=None, yaxis=dict(tickformat=".2s"))
                        st.plotly_chart(fig_month, use_container_width=True)

                    with chart_col2:
                        st.markdown("##### 🏆 個股貢獻度")
                        all_view_stocks = df_view['股票'].unique()
                        selected_stocks = st.multiselect("🔍 查詢特定個股 (留空顯示 Top 8)", options=all_view_stocks)
                        stock_pnl = df_view.groupby('股票')['已實現損益'].sum().reset_index()
                        
                        if selected_stocks:
                            stock_pnl = stock_pnl[stock_pnl['股票'].isin(selected_stocks)]
                            chart_height = 400 + (len(selected_stocks) * 20)
                        else:
                            chart_height = 400
                            if len(stock_pnl) > 16:
                                stock_pnl_sorted = stock_pnl.sort_values(by='已實現損益', ascending=False)
                                top_8 = stock_pnl_sorted.head(8)
                                bottom_8 = stock_pnl_sorted.tail(8)
                                stock_pnl = pd.concat([top_8, bottom_8]).drop_duplicates()
                        
                        stock_pnl = stock_pnl.sort_values(by='已實現損益', ascending=True)
                        stock_pnl['Color'] = stock_pnl['已實現損益'].apply(lambda x: 'Profit' if x >= 0 else 'Loss')
                        fig_stock = px.bar(stock_pnl, y='股票', x='已實現損益', color='Color', orientation='h', color_discrete_map={'Profit': '#E53935', 'Loss': '#26a69a'}, text_auto='.2s')
                        fig_stock.update_traces(hovertemplate='<b>%{y}</b><br>已實現損益: %{x:,.0f}<extra></extra>')
                        fig_stock.update_layout(showlegend=False, yaxis_title=None, xaxis=dict(tickformat=".2s"), height=chart_height)
                        st.plotly_chart(fig_stock, use_container_width=True)

                    st.markdown("##### 🗓️ 年度損益統計")
                    yearly_pnl = df_view.groupby('年')['已實現損益'].sum().reset_index()
                    yearly_pnl['累積損益'] = yearly_pnl['已實現損益'].cumsum()
                    st.dataframe(yearly_pnl.style.format({"已實現損益": "${:,.0f}", "累積損益": "${:,.0f}"}), use_container_width=True, hide_index=True)

                    with st.expander("查看詳細交易紀錄"):
                        st.dataframe(df_view[['交易日期', '股票', '交易類別', '已實現損益', '報酬率 (%)', '本金(成本)']].style.format({"已實現損益": "{:,.0f}", "本金(成本)": "{:,.0f}", "報酬率 (%)": "{:,.2f}%"}).map(lambda x: f'color: {"red" if x > 0 else "green" if x < 0 else "black"}', subset=['已實現損益', '報酬率 (%)']), use_container_width=True)
            else:
                st.info("尚無已實現損益紀錄。")
        else:
            st.warning("目前沒有交易紀錄。")

    # ------------------------------------------------
    # Tab 4: 資產趨勢 (新增)
    # ------------------------------------------------
    with tab4:
        st.subheader("📈 資產淨值歷史曲線")
        df_history = database.load_asset_history()
        
        if not df_history.empty:
            # 資料處理
            df_history['日期'] = pd.to_datetime(df_history['日期'])
            # 每個日期只保留最後一筆 (避免一天多次記錄造成圖表混亂)
            df_history = df_history.sort_values('日期').drop_duplicates(subset=['日期'], keep='last')
            
            # 1. 總資產折線圖
            fig_trend = px.line(df_history, x='日期', y='總資產', title="總資產成長趨勢", markers=True)
            fig_trend.update_traces(line_color='#2E86C1', line_width=3)
            fig_trend.update_layout(xaxis_title=None, yaxis_title=None, yaxis=dict(tickformat=",.0f"))
            st.plotly_chart(fig_trend, use_container_width=True)
            
            # 2. 結構堆疊圖 (現金 vs 股票)
            st.markdown("##### 📊 資產結構變化")
            # 轉換為長格式以便堆疊繪圖
            df_melt = df_history.melt(id_vars=['日期'], value_vars=['總現金', '總持股市值'], var_name='資產類別', value_name='金額')
            
            fig_stack = px.area(df_melt, x='日期', y='金額', color='資產類別', 
                                color_discrete_map={'總現金': '#00CC96', '總持股市值': '#EF553B'})
            fig_stack.update_layout(xaxis_title=None, yaxis_title=None, yaxis=dict(tickformat=",.0f"))
            st.plotly_chart(fig_stack, use_container_width=True)
            
            with st.expander("查看歷史紀錄數據"):
                # 修改 2: 對歷史紀錄的日期進行格式化
                df_history_display = df_history.copy()
                df_history_display['日期'] = df_history_display['日期'].dt.date
                st.dataframe(df_history_display.sort_values('日期', ascending=False), use_container_width=True)
        else:
            st.info("尚無歷史紀錄。請至「資產庫存」頁面點擊「📝 記錄今日資產」按鈕來開始累積數據。")

    # ------------------------------------------------
    # Tab 2: 原始紀錄
    # ------------------------------------------------
    with tab2:
        st.subheader("最近交易紀錄")
        if not df_raw.empty and '交易日期' in df_raw.columns:
            df_display = df_raw.copy()
            # 修改 2: 將原始紀錄的日期格式化為 YYYY-MM-DD
            df_display['交易日期'] = pd.to_datetime(df_display['交易日期']).dt.date
            df_display = df_display.sort_values(by='交易日期', ascending=False)
            st.dataframe(df_display)
        else:
            st.write("無資料")

except Exception as e:
    st.error(f"系統發生錯誤: {e}")
