# Interview Assistant

自動化 Gmail 面試邀請處理系統，使用 AI 智能生成回信草稿。

## 專案目的

現代求職過程中，面試邀請郵件處理繁瑣且重複。本專案旨在自動化這個流程：

- **自動監控** - 連接 Gmail 自動抓取新郵件
- **智能識別** - 使用 AI 準確識別面試邀請信件
- **資訊提取** - 自動提取公司、職位、時間、地點等關鍵資訊
- **回信生成** - 根據提取資訊生成專業禮貌的回信草稿
- **多語言支援** - 同時支援中文和英文郵件處理

透過自動化減少重複性工作，讓求職者能專注於面試準備而非郵件處理。

## 技術選型

### 後端架構
- **FastAPI** - 現代 Python Web 框架，提供自動 API 文檔和高效能
- **SQLAlchemy** - Python ORM，支援多種資料庫並提供類型安全
- **SQLite/PostgreSQL** - 開發使用 SQLite，生產環境可切換至 PostgreSQL

### 外部服務整合
- **Gmail API** - Google 官方 API，安全可靠的郵件存取
- **Google OAuth 2.0** - 標準認證流程，確保用戶資料安全
- **OpenAI GPT-4o-mini** - 成本效益高的 AI 模型，專門處理文字理解和生成

### 設計考量
- **RESTful API** - 標準化介面設計，易於擴展和整合
- **模組化架構** - 服務分離，便於維護和測試
- **支援容器化** - 使用 Docker 簡化部署流程
- **環境配置分離** - 使用環境變數管理敏感資訊

此技術組合確保系統既能處理複雜的 AI 任務，又能保持良好的可維護性和擴展性。

## 專案架構

```
interview-assistant/
├── backend/                       # Python FastAPI 後端
│   ├── main.py                    # FastAPI 應用入口
│   ├── config.py                  # 環境配置
│   ├── database.py                # 資料庫連接
│   ├── models.py                  # 資料模型
│   ├── gmail_service.py           # Gmail API 服務
│   ├── openai_service.py          # OpenAI API 服務
│   ├── email_processor.py         # 郵件處理邏輯
│   ├── auth.py                    # Google 認證
│   ├── requirements.txt           # Python 依賴
│   └── Dockerfile                 # 容器化
│
├── frontend/                      # 簡單前端
│   ├── index.html                 # 主頁面
│   ├── style.css                  # 樣式
│   ├── script.js                  # 前端邏輯
│   ├── login.html                 # 登入頁面
│   └── dashboard.html             # 儀表板頁面
│
├── database/                      # 資料庫檔案
│   ├── schema.sql                 # 資料庫結構
│   └── init_data.sql              # 初始資料
│
├── deployment/                    # 部署配置
│   ├── vercel.json                # Vercel 部署
│   ├── railway.json               # Railway 部署
│   └── docker-compose.yml         # 本地開發環境
│
├── docs/                          # 必要文檔
│   ├── setup.md                   # 設定指南
│   ├── api.md                     # API 說明
│   └── deployment.md              # 部署說明
│
├── .env.example                   # 環境變數範例
├── .gitignore                     # Git 忽略檔案
├── README.md                      # 專案說明
└── run.sh                         # 快速啟動腳本
```