# ==============================================================================
# 檔案名稱: pages/3_📊_績效分析.py
# 
# 修改歷程:
# 2025-11-27 14:00:00: [Refactor] 新增獨立頁面，從帳務管理拆分
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.express as px
import database
import logic

# 設定頁面
st.set_page_config(page_title="績效分析", layout="wide", page_icon="📊")
st.title("📊 投資績效復盤")

# 1. 讀取資料
try:
    df_raw = database.load_data()
except:
    df_raw = pd.DataFrame()

# 2. 定義樣式函數 (與其他頁面一致)
def style_tw_stock_profit_loss(val):
    if not isinstance(val, (int, float)): return ''
    if val > 0: return 'color: #E53935' # 紅漲
    elif val < 0: return 'color: #26a69a' # 綠跌
    return ''

# 3. 渲染內容
if df_raw.empty:
    st.info("尚無交易紀錄，無法進行分析。")
else:
    df_realized_all = logic.calculate_realized_report(df_raw)
    
    if df_realized_all.empty:
        st.info("尚無「賣出」或「股息」紀錄，目前無已實現損益。")
    else:
        # --- 篩選區塊 ---
        df_realized_all['交易日期'] = pd.to_datetime(df_realized_all['交易日期']).dt.date
        all_years = sorted(df_realized_all['年'].unique().tolist(), reverse=True)
        year_options = ["全部"] + all_years
        
        col_filter, _ = st.columns([2, 8])
        selected_year = col_filter.selectbox("📅 選擇檢視年度", year_options)
        
        if selected_year == "全部": 
            df_view = df_realized_all
        else: 
            df_view = df_realized_all[df_realized_all['年'] == selected_year]

        st.divider()

        if not df_view.empty:
            # --- A. KPI 核心指標 ---
            pnl_sum = df_view['已實現損益'].sum()
            div_sum = df_view[df_view['交易類別'] == '股息']['已實現損益'].sum()
            
            trades = df_view[df_view['交易類別'] == '賣出']
            win_trades = trades[trades['已實現損益'] > 0]
            win_rate = (len(win_trades)/len(trades)*100) if not trades.empty else 0
            
            avg_win = win_trades['已實現損益'].mean() if not win_trades.empty else 0
            loss_trades = trades[trades['已實現損益'] < 0]
            avg_loss = loss_trades['已實現損益'].mean() if not loss_trades.empty else 0
            
            k1, k2, k3, k4 = st.columns(4)
            # 使用 inverse 確保紅色=獲利
            k1.metric("💰 區間總損益", f"${pnl_sum:,.0f}", delta=f"${pnl_sum:,.0f}", delta_color="inverse")
            k2.metric("💸 包含股息", f"${div_sum:,.0f}", help="包含現金股利")
            k3.metric("🎯 交易勝率", f"{win_rate:.1f}%")
            k4.metric("⚖️ 盈虧比", f"獲利 ${avg_win:,.0f} / 虧損 ${avg_loss:,.0f}")
            
            st.divider()
            
            # --- B. 圖表區 ---
            g1, g2 = st.columns(2)
            color_map = {'Profit': '#E53935', 'Loss': '#26a69a'}
            
            with g1:
                st.subheader("📆 月度損益統計")
                m_pnl = df_view.groupby('月')['已實現損益'].sum().reset_index()
                if selected_year == "全部": m_pnl = m_pnl.sort_values('月').tail(12)
                else: m_pnl = m_pnl.sort_values('月')
                
                m_pnl['Color'] = m_pnl['已實現損益'].apply(lambda x: 'Profit' if x >= 0 else 'Loss')
                
                fig_m = px.bar(m_pnl, x='月', y='已實現損益', color='Color', 
                               color_discrete_map=color_map)
                fig_m.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
                fig_m.update_layout(showlegend=False, xaxis_title=None, yaxis=dict(tickformat=",.0f"))
                st.plotly_chart(fig_m, use_container_width=True)
            
            with g2:
                st.subheader("🏆 個股貢獻度排行榜")
                all_view_stocks = df_view['股票'].unique()
                sel_stocks = st.multiselect("🔍 查詢特定個股", options=all_view_stocks)
                
                stock_pnl = df_view.groupby('股票')['已實現損益'].sum().reset_index()
                
                if sel_stocks:
                    stock_pnl = stock_pnl[stock_pnl['股票'].isin(sel_stocks)]
                    df_filtered_view = df_view[df_view['股票'].isin(sel_stocks)]
                    h = 400 + len(sel_stocks)*20
                else:
                    df_filtered_view = df_view
                    h = 400
                    if len(stock_pnl) > 16:
                        stock_pnl = pd.concat([stock_pnl.nlargest(8,'已實現損益'), stock_pnl.nsmallest(8,'已實現損益')]).drop_duplicates()
                
                stock_pnl = stock_pnl.sort_values('已實現損益', ascending=True)
                stock_pnl['Color'] = stock_pnl['已實現損益'].apply(lambda x: 'Profit' if x >= 0 else 'Loss')
                
                fig_s = px.bar(stock_pnl, y='股票', x='已實現損益', orientation='h', color='Color', 
                               color_discrete_map=color_map)
                fig_s.update_traces(texttemplate='%{x:,.0f}', textposition='outside')
                fig_s.update_layout(showlegend=False, yaxis_title=None, xaxis=dict(tickformat=",.0f"), height=h)
                st.plotly_chart(fig_s, use_container_width=True)
            # --- C. 詳細表格 ---
            st.subheader("📜 詳細交易清單")
            with st.expander("展開查看詳細數據", expanded=True):
                # 這裡若要像 Page 2 一樣套用背景色，需重構 Logic 層回傳格式
                # 目前先針對寬度進行優化
                
                # 為了 Styler 能判斷正負顏色，我們需要原始數值
                # 但這裡為了簡化，先使用 column_config 控制寬度即可
                # 因為上面的 style_tw_stock_profit_loss 已經處理了文字顏色
                
                st.dataframe(
                    df_filtered_view[['交易日期', '股票', '交易類別', '已實現損益', '報酬率 (%)', '本金(成本)']]
                    .style.format({
                        "已實現損益": "{:,.0f}", 
                        "本金(成本)": "{:,.0f}", 
                        "報酬率 (%)": "{:,.2f}%"
                    })
                    .map(style_tw_stock_profit_loss, subset=['已實現損益', '報酬率 (%)']),
                    
                    column_config={
                        "交易日期": st.column_config.DateColumn("日期", width="small"),
                        "股票": st.column_config.TextColumn("股票", width="medium"),
                        "交易類別": st.column_config.TextColumn("類別", width="small"),
                        "已實現損益": st.column_config.NumberColumn("損益", width="small"),
                        "報酬率 (%)": st.column_config.NumberColumn("報酬率", width="small"),
                        "本金(成本)": st.column_config.NumberColumn("本金", width="small"),
                    },
                    use_container_width=True
                )

        else:
            st.info(f"{selected_year} 年度無已實現損益資料。")
