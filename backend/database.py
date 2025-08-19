import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from models import Base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔧 暫時使用 SQLite，但保留 PostgreSQL 檢測邏輯
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./interview_assistant.db")

# 暫時強制使用 SQLite 以確保穩定性，同時記錄 PostgreSQL URL
if DATABASE_URL.startswith("postgresql"):
    logger.info(f"PostgreSQL URL detected: {DATABASE_URL[:50]}...")
    logger.warning("Temporarily using SQLite for stability testing")
    DATABASE_URL = "sqlite:///./interview_assistant.db"

logger.info(f"實際使用資料庫: {DATABASE_URL}")

# SQLite 設定
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def upgrade_database():
    """升級資料庫結構，添加新欄位"""
    try:
        with engine.connect() as conn:
            # SQLite 處理
            result = conn.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result.fetchall()]

            if "last_sync_at" not in columns:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN last_sync_at DATETIME")
                )
                conn.commit()
                logger.info("已添加 last_sync_at 欄位到 users 表")
            else:
                logger.info("last_sync_at 欄位已存在")

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