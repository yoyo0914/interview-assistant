import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from models import Base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔧 修復：優先使用環境變數中的 DATABASE_URL，支援 PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./interview_assistant.db")

# 根據資料庫類型設定連線參數
if DATABASE_URL.startswith("postgresql"):
    # PostgreSQL 設定
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # 檢查連線是否有效
        pool_recycle=300,    # 5 分鐘後重新建立連線
        pool_size=5,         # 連線池大小
        max_overflow=10,     # 最大溢出連線
    )
    logger.info(f"使用 PostgreSQL 資料庫")
else:
    # SQLite 設定（本地開發用）
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    logger.info(f"使用 SQLite 資料庫")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def upgrade_database():
    """升級資料庫結構，添加新欄位"""
    try:
        with engine.connect() as conn:
            if DATABASE_URL.startswith("postgresql"):
                # PostgreSQL 處理
                try:
                    conn.execute(
                        text("ALTER TABLE users ADD COLUMN last_sync_at TIMESTAMP")
                    )
                    conn.commit()
                    logger.info("已添加 last_sync_at 欄位到 users 表 (PostgreSQL)")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        logger.info("last_sync_at 欄位已存在 (PostgreSQL)")
                    else:
                        logger.warning(f"添加欄位時發生警告: {e}")
            else:
                # SQLite 處理
                result = conn.execute(text("PRAGMA table_info(users)"))
                columns = [row[1] for row in result.fetchall()]

                if "last_sync_at" not in columns:
                    conn.execute(
                        text("ALTER TABLE users ADD COLUMN last_sync_at DATETIME")
                    )
                    conn.commit()
                    logger.info("已添加 last_sync_at 欄位到 users 表 (SQLite)")
                else:
                    logger.info("last_sync_at 欄位已存在 (SQLite)")

    except Exception as e:
        logger.error(f"資料庫升級失敗: {e}")


def create_tables():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        raise


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session() -> Session:
    return SessionLocal()


def init_database():
    logger.info("Initializing database...")
    create_tables()
    upgrade_database()

    try:
        db = get_db_session()
        db.execute(text("SELECT 1"))
        db.close()
        logger.info("Database connection test successful")
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        raise

    logger.info("Database initialization complete")


if __name__ == "__main__":
    init_database()
    print("Database setup complete")
    print(f"Database location: {DATABASE_URL}")

    print("\nCreated tables:")
    for table_name in Base.metadata.tables.keys():
        print(f"  - {table_name}")

    print("\nDatabase ready for use")