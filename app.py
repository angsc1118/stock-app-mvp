import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# 設定頁面標題
st.title('📊 股票資產實驗 (Streamlit Cloud)')

# 定義連線函式 (使用 st.cache_data 避免每次操作都重連)
@st.cache_data(ttl=600)
def load_data():
    # 1. 從 Streamlit Secrets 讀取金鑰 (這比較安全！)
    # 我們稍後會在後台設定這個 'gcp_service_account'
    creds_dict = st.secrets["gcp_service_account"]

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)

    # 2. 開啟試算表 (請修改這裡的 URL 為您的試算表連結)
    # 注意：這是一個變數，請確認您的 secrets.toml 或直接在這裡貼上 URL 測試
    # 為了方便，我們先寫死 URL，請替換下面這行：
    sheet_url = "https://docs.google.com/spreadsheets/d/1H0qIDR1cQdLaPkr2cQLiISP-wUgwy2y45AxhetnZ0zo/edit" 

    sheet = client.open_by_url(sheet_url)
    worksheet = sheet.worksheet('交易紀錄')
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

try:
    st.write("正在連線到 Google Sheets...")
    df = load_data()
    st.success(f"✅ 成功讀取！共有 {len(df)} 筆資料")

    st.subheader("前 5 筆交易紀錄：")
    st.dataframe(df.head(30))

except Exception as e:
    st.error(f"❌ 發生錯誤: {e}")
