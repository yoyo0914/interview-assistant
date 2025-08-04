import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./interview_assistant.db")

# 🔧 修復：配置更好的連線池設定
if "sqlite" in DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        connect_args={
            "check_same_thread": False,
            "timeout": 20  # 增加超時時間
        },
        poolclass=StaticPool,  # SQLite使用靜態連線池
        pool_size=1,           # SQLite只需要1個連線
        max_overflow=0,        # 不允許溢出
        pool_pre_ping=True,    # 檢查連線有效性
        echo=False             # 生產環境關閉SQL日誌
    )
else:
    # PostgreSQL 等其他資料庫的配置
    engine = create_engine(
        DATABASE_URL,
        pool_size=3,           # 減少連線池大小
        max_overflow=2,        # 減少溢出連線
        pool_timeout=30,       # 連線等待時間
        pool_pre_ping=True,    # 檢查連線有效性
        pool_recycle=3600,     # 每小時回收連線
        echo=False
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def upgrade_database():
    """升級資料庫結構，添加新欄位"""
    try:
        with engine.connect() as conn:
            # 檢查是否為 SQLite
            if "sqlite" in DATABASE_URL:
                # 檢查 last_sync_at 欄位是否存在
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
            else:
                # PostgreSQL 等其他資料庫的處理
                try:
                    conn.execute(
                        text("ALTER TABLE users ADD COLUMN last_sync_at TIMESTAMP")
                    )
                    conn.commit()
                    logger.info("已添加 last_sync_at 欄位到 users 表")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        logger.info("last_sync_at 欄位已存在")
                    else:
                        logger.warning(f"添加欄位時發生警告: {e}")

    except Exception as e:
        logger.error(f"資料庫升級失敗: {e}")


def create_tables():
    """創建資料庫表格"""
    try:
        # 🔧 修復：從models模組導入Base
        from models import Base
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        raise


# 🔧 修復：改進FastAPI的資料庫依賴注入
def get_db():
    """FastAPI的資料庫依賴注入（推薦使用）"""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


# 🔧 修復：確保連線正確關閉的直接session獲取
def get_db_session() -> Session:
    """直接獲取資料庫session（請謹慎使用，確保手動關閉）"""
    return SessionLocal()


# 🔧 新增：安全的資料庫操作上下文管理器
def get_db_context():
    """安全的資料庫操作上下文管理器"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        logger.error(f"Database context error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def init_database():
    """初始化資料庫"""
    logger.info("Initializing database...")
    create_tables()
    upgrade_database()

    try:
        with get_db_context() as db:
            db.execute(text("SELECT 1"))
        logger.info("Database connection test successful")
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        raise

    logger.info("Database initialization complete")


if __name__ == "__main__":
    init_database()
    print("Database setup complete")
    print(f"Database location: {DATABASE_URL}")

    # 從models導入Base來顯示表格
    from models import Base
    print("\nCreated tables:")
    for table_name in Base.metadata.tables.keys():
        print(f"  - {table_name}")

    print("\nDatabase ready for use")