# 使用 Python 3.11 官方映像
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統相依性
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 複製 requirements.txt 並安裝 Python 套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案檔案
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# 注意：生產環境不使用 .env 文件
# 所有環境變數透過 Cloud Run 設定

# 建立資料庫目錄（用於持久化）
RUN mkdir -p /app/data

# 設定環境變數（使用絕對路徑）
ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:////app/data/interview_assistant.db

# 暴露端口（只需要一個）
EXPOSE 8000

# 切換到 backend 目錄執行（保持與你目前的執行方式一致）
WORKDIR /app/backend

# 啟動指令（只啟動 FastAPI，它會同時服務前後端）
CMD ["python", "main.py"]