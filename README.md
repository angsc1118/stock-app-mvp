# stock-app-mvp
stock-app-mvp/
├── app.py             # 【表現層】只負責 UI：按鈕、表格、側邊欄
├── logic.py           # 【邏輯層】純數學運算：FIFO 算法、手續費計算
├── database.py        # 【資料層】負責跟 Google Sheets 溝通
├── requirements.txt   # 套件清單 (維持不變)
└── .streamlit/        # (本地開發用，Cloud 上是用 Secrets 設定)
