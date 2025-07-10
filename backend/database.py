import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from models import Base
import logging

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 資料庫 URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./interview_assistant.db")

# 建立引擎
engine = create_engine(
    DATABASE_URL,
    # SQLite 特殊設置
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# 建立 SessionLocal
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_tables():
    """建立所有資料表"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ 資料表建立成功")
    except Exception as e:
        logger.error(f"❌ 資料表建立失敗: {e}")
        raise

def get_database():
    """取得資料庫 session - 用於 FastAPI 依賴注入"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_session() -> Session:
    """直接取得資料庫 session - 用於一般用途"""
    return SessionLocal()

# 初始化函數
def init_database():
    """初始化資料庫"""
    logger.info("🔧 初始化資料庫...")
    
    # 建立資料表
    create_tables()
    
    # 檢查資料庫連接
    try:
        db = get_db_session()
        db.execute(text("SELECT 1"))
        db.close()
        logger.info("✅ 資料庫連接測試成功")
    except Exception as e:
        logger.error(f"❌ 資料庫連接測試失敗: {e}")
        raise
    
    logger.info("🎉 資料庫初始化完成")

if __name__ == "__main__":
    # 直接執行時初始化資料庫
    init_database()
    print("📊 資料庫設置完成！")
    print(f"📍 資料庫位置: {DATABASE_URL}")
    
    # 顯示資料表結構
    print("\n📋 建立的資料表:")
    for table_name in Base.metadata.tables.keys():
        print(f"  - {table_name}")
    
    print("\n🚀 可以開始使用資料庫了！")