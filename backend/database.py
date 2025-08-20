import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from models import Base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_database_url():
    """安全地取得資料庫 URL，包含容錯機制"""
    database_url = os.getenv("DATABASE_URL", "sqlite:///./interview_assistant.db")
    
    if database_url.startswith("postgresql"):
        logger.info("檢測到 PostgreSQL 連接...")
        logger.info(f"連接到 Neon: {database_url.split('@')[1].split('/')[0] if '@' in database_url else 'unknown'}")
        return database_url
    else:
        logger.info("使用 SQLite 資料庫（本地開發）")
        return database_url

DATABASE_URL = get_database_url()

def create_engine_with_fallback():
    """建立資料庫引擎，包含 Neon 最佳化設定"""
    try:
        if DATABASE_URL.startswith("postgresql"):
            # Neon PostgreSQL 設定，針對 Serverless 最佳化
            engine = create_engine(
                DATABASE_URL,
                pool_pre_ping=True,           # 檢查連接是否有效
                pool_recycle=300,             # 5 分鐘後重新建立連接
                pool_size=5,                  # 連接池大小
                max_overflow=10,              # 最大溢出連接
                connect_args={
                    "connect_timeout": 10,    # 10 秒連接超時
                    "sslmode": "require",     # Neon 需要 SSL
                }
            )
            
            # 測試連接
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version()"))
                version = result.fetchone()[0]
                logger.info(f"Neon PostgreSQL 連接成功！版本: {version[:50]}...")
            
            return engine
            
        else:
            # SQLite 設定（備用）
            engine = create_engine(
                DATABASE_URL,
                connect_args={"check_same_thread": False},
            )
            logger.info("SQLite 連接成功！")
            return engine
            
    except Exception as e:
        logger.error(f"PostgreSQL 連接失敗: {e}")
        logger.warning("回退到 SQLite...")
        
        # 容錯：回退到 SQLite
        fallback_url = "sqlite:///./interview_assistant.db"
        engine = create_engine(
            fallback_url,
            connect_args={"check_same_thread": False},
        )
        logger.info("使用 SQLite 作為備用資料庫")
        return engine

# 建立引擎
engine = create_engine_with_fallback()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def upgrade_database():
    """升級資料庫結構，添加新欄位"""
    try:
        with engine.connect() as conn:
            # 檢查實際使用的是什麼資料庫
            if "postgresql" in str(engine.url):
                # PostgreSQL (Neon) 處理
                try:
                    conn.execute(
                        text("ALTER TABLE users ADD COLUMN last_sync_at TIMESTAMP")
                    )
                    conn.commit()
                    logger.info("已添加 last_sync_at 欄位到 users 表 (Neon PostgreSQL)")
                except Exception as e:
                    if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                        logger.info("last_sync_at 欄位已存在 (Neon PostgreSQL)")
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
        
        # 記錄使用的資料庫類型
        if "postgresql" in str(engine.url):
            logger.info("🎉 使用 Neon PostgreSQL - 資料將永久保存！")
        else:
            logger.warning("⚠️ 使用 SQLite - 資料會在部署時丟失")
            
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
    logger.info("初始化資料庫...")
    logger.info(f"目標資料庫: {DATABASE_URL.split('@')[1].split('/')[0] if '@' in DATABASE_URL and DATABASE_URL.startswith('postgresql') else 'SQLite'}")
    
    create_tables()
    upgrade_database()

    try:
        db = get_db_session()
        db.execute(text("SELECT 1"))
        db.close()
        logger.info("資料庫連接測試成功 ✅")
    except Exception as e:
        logger.error(f"資料庫連接測試失敗: {e}")
        raise

    logger.info("資料庫初始化完成 🚀")

if __name__ == "__main__":
    init_database()
    print("Database setup complete")
    print(f"Database type: {'Neon PostgreSQL' if 'postgresql' in str(engine.url) else 'SQLite'}")

    print("\nCreated tables:")
    for table_name in Base.metadata.tables.keys():
        print(f"  - {table_name}")

    print("\nDatabase ready for use")