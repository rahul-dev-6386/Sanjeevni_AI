from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

from app.api.v1.endpoints import (
    auth,
    profiles,
    chat,
    memory,
    metrics,
    analytics,
    medications,
    reports,
    routines,
    voice,
    notifications,
    intelligence,
    library,
    bot,
    drugs,
    unified_rag,
)

try:
    from app.api.v1.endpoints import knowledge
    _has_knowledge = True
except Exception:
    _has_knowledge = False
    import logging
    logging.getLogger(__name__).warning("knowledge router unavailable (LangChain broken)")

app = FastAPI(
    title="AI Health Assistant API",
    description="Backend API for the AI-powered Personal Health Assistant with Medical Intelligence Platform",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(profiles.router)
app.include_router(chat.router)
app.include_router(memory.router)
app.include_router(metrics.router)
app.include_router(analytics.router)
app.include_router(medications.router)
app.include_router(reports.router)
if _has_knowledge:
    app.include_router(knowledge.router)
app.include_router(routines.router)
app.include_router(voice.router)
app.include_router(notifications.router)
app.include_router(intelligence.router)
app.include_router(library.router)
app.include_router(bot.router)
app.include_router(drugs.router)
app.include_router(unified_rag.router)


@app.on_event("startup")
def startup():
    from app.core.database import engine, Base
    try:
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully")
    except Exception as e:
        print(f"Warning: Could not connect to database: {e}")

    # Add verified column to users table if not exists (dev migration helper)
    try:
        from sqlalchemy import text as sa_text
        with engine.connect() as conn:
            conn.execute(sa_text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE;"))
            conn.execute(sa_text("ALTER TABLE users ALTER COLUMN verified SET DEFAULT FALSE;"))
            conn.commit()
            print("Migration: added 'verified' column to users table")
    except Exception as e:
        print(f"Warning: could not migrate users table: {e}")

    # Auto-verify pre-existing accounts that have no EmailVerification records
    try:
        from app.core.database import SessionLocal
        from app.models.user import User
        from app.models.email_verification import EmailVerification
        db = SessionLocal()
        pre_existing = db.query(User).filter(
            User.verified == False,
            ~User.email.in_(
                db.query(EmailVerification.email).filter(
                    EmailVerification.verified == True
                )
            )
        ).all()
        for u in pre_existing:
            u.verified = True
            u.is_active = True
        if pre_existing:
            db.commit()
            print(f"Migration: auto-verified {len(pre_existing)} pre-existing accounts")
        db.close()
    except Exception as e:
        print(f"Warning: could not auto-verify pre-existing accounts: {e}")

    # Schedule cleanup of expired OTP records (every 5 minutes)
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from datetime import datetime
        from app.core.database import SessionLocal
        from app.models.email_verification import EmailVerification

        def cleanup_expired_otps():
            try:
                db = SessionLocal()
                expired = db.query(EmailVerification).filter(
                    EmailVerification.expires_at < datetime.utcnow(),
                    EmailVerification.verified == False,
                ).all()
                for rec in expired:
                    rec.verified = True
                db.commit()
                if expired:
                    print(f"Cleaned up {len(expired)} expired OTP records")
                db.close()
            except Exception:
                pass

        scheduler = BackgroundScheduler()
        scheduler.add_job(cleanup_expired_otps, "interval", minutes=5)
        scheduler.start()
        print("OTP cleanup scheduler started")
    except Exception as e:
        print(f"Warning: could not start OTP cleanup scheduler: {e}")
        print("The app will start but database operations will fail until the DB is available.")

from app.infrastructure.vector_store import vector_store
try:
    vector_store.initialize()
    print(f"Vector store initialized: {vector_store.get_status()}")
except Exception as e:
    print(f"Warning: Could not initialize vector store: {e}")

from app.domain.medical_library import indexer as lib_indexer
try:
    lib_client = lib_indexer.get_client()
    lib_indexer.init_collections(lib_client)
    # Ensure keyword payload index exists on every collection so that
    # content_type filters work without a 400 "Index required" error.
    lib_indexer.ensure_payload_indexes(lib_client)
    stats = lib_indexer.get_stats(lib_client)
    print(f"Medical Library initialized: {stats}")
except Exception as e:
    print(f"Warning: Could not initialize Medical Library: {e}")

try:
    from app.domain.medical_library.reranker import _get_direct_reranker
    _get_direct_reranker()
    print("Reranker model pre-warmed")
except Exception as e:
    print(f"Warning: Could not pre-warm reranker model: {e}")


@app.get("/api/health")
def health_check():
    from app.core.database import SessionLocal
    db_ok = False
    try:
        db = SessionLocal()
        db.execute(
            __import__("sqlalchemy", fromlist=["text"]).text("SELECT 1")
        )
        db.close()
        db_ok = True
    except Exception:
        pass
    return {"status": "healthy", "database": db_ok, "version": "1.0.0"}
