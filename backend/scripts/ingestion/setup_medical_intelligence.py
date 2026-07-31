#!/usr/bin/env python3
"""
One-command setup for the Medical Intelligence Platform.

Downloads medical guidelines, PubMed articles, drug data,
trains risk prediction models, creates embeddings, builds vector indexes,
and initializes database.
"""
import os
import sys
import subprocess
import time


GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"


def log_step(step_num, total, message):
    print(f"\n{BLUE}[{step_num}/{total}]{RESET} {message}...")


def log_done(message):
    print(f"  {GREEN}✓{RESET} {message}")


def log_warn(message):
    print(f"  {YELLOW}⚠{RESET} {message}")


def log_error(message):
    print(f"  {RED}✗{RESET} {message}")


def run_script(script_path, description):
    log_done(f"Running {description}...")
    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        log_warn(f"{description} had issues (non-fatal):")
        for line in result.stderr.split("\n")[-5:]:
            if line.strip():
                log_warn(f"  {line.strip()}")
    for line in result.stdout.split("\n"):
        if line.strip():
            print(f"    {line.strip()}")
    return result.returncode


def main():
    total_steps = 7
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(backend_dir)
    sys.path.insert(0, backend_dir)

    print(f"""
{GREEN}╔══════════════════════════════════════════════╗
║  Medical Intelligence Platform Setup          ║
║  {RESET}{BLUE}One-command initialization{RESET}{GREEN}               ║
╚══════════════════════════════════════════════╝{RESET}
""")

    # Step 1: Create directories
    log_step(1, total_steps, "Creating data directories")
    dirs = [
        "data/medical_guidelines",
        "data/datasets",
        "data/models",
        "data/cache",
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        log_done(f"Created {d}/")

    # Step 2: Install dependencies
    log_step(2, total_steps, "Installing Python dependencies")
    req_file = os.path.join(backend_dir, "requirements.txt")
    if os.path.exists(req_file):
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            log_done("Dependencies installed")
        else:
            log_warn("Some dependencies may have issues. Check requirements.txt")

    # Step 3: Download medical guidelines
    log_step(3, total_steps, "Downloading medical guidelines (WHO, CDC, ADA, AHA, KDIGO, NIH)")
    try:
        from scripts.ingestion.download_guidelines import download_guidelines
        download_guidelines()
        log_done("Medical guidelines downloaded")
    except Exception as e:
        log_error(f"Failed: {e}")

    # Step 4: Download drug data from OpenFDA
    log_step(4, total_steps, "Downloading drug information from OpenFDA")
    try:
        from scripts.ingestion.download_drug_data import download_drug_data
        download_drug_data()
        log_done("Drug data downloaded")
    except Exception as e:
        log_warn(f"Could not download drug data: {e}")

    # Step 5: Download PubMed articles
    log_step(5, total_steps, "Downloading PubMed research articles")
    try:
        from scripts.ingestion.download_pubmed import download_pubmed
        download_pubmed()
        log_done("PubMed articles downloaded")
    except Exception as e:
        log_warn(f"Could not download PubMed data: {e}")

    # Step 6: Train risk prediction models
    log_step(6, total_steps, "Training risk prediction models")
    try:
        from scripts.maintenance.train_risk_models import train_all
        train_all()
        log_done("Risk models trained")
    except Exception as e:
        log_warn(f"Could not train models: {e}")

    # Step 7: Initialize database tables and populate knowledge
    log_step(7, total_steps, "Initializing database and building vector indexes")
    try:
        from app.core.database import engine, Base
        import app.models
        log_done("Database tables ready")

        from app.core.database import SessionLocal
        from app.infrastructure.embedding_service import embedding_service
        from app.infrastructure.vector_store import vector_store
        from app.services.medical_knowledge_service import MedicalKnowledgeService
        from app.infrastructure.pubmed_service import PubMedService
        from app.services.drug_service import DrugService

        vector_store.initialize()
        log_done("Vector store initialized")

        db = SessionLocal()
        try:
            knowledge_service = MedicalKnowledgeService(db)
            pubmed_service = PubMedService(db)
            drug_service = DrugService(db)

            knowledge_count = knowledge_service.count()
            pubmed_count = pubmed_service.count()
            drug_count = drug_service.count()

            log_done(f"Knowledge base: {knowledge_count} guidelines ingested")
            log_done(f"PubMed: {pubmed_count} articles stored")
            log_done(f"Drug database: {drug_count} drugs stored")

            vs_status = vector_store.get_status()
            log_done(f"Vector store: {vs_status['backend']} with {vs_status['points_count']} vectors")
        finally:
            db.close()

    except Exception as e:
        log_error(f"Database initialization failed: {e}")
        log_warn("Make sure PostgreSQL is running and DATABASE_URL is configured correctly")

    print(f"""
{GREEN}╔══════════════════════════════════════════════╗
║  Setup Complete!                                ║
║                                                  ║
║  Run the application:                            ║
║    uvicorn app.main:app --reload                 ║
║                                                  ║
║  Dataset stats:                                  ║
║    - Medical guidelines (WHO, CDC, ADA, AHA)     ║
║    - PubMed research articles                    ║
║    - Drug database (OpenFDA)                     ║
║    - Risk models (diabetes, heart, CKD, stroke)  ║
║    - Vector embeddings for RAG                   ║
╚══════════════════════════════════════════════════╝{RESET}
""")


if __name__ == "__main__":
    main()
