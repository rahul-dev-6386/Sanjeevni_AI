# Sanjeevni AI — AI-Powered Personal Health Intelligence Platform

A full-stack personal health platform combining drug information retrieval, medical report analysis, AI chat consultation, health metric tracking, and multi-source RAG-powered intelligence. Built with Next.js 14, FastAPI, PostgreSQL, and Qdrant vector search.

---

## Architecture

```
User → Next.js Frontend → FastAPI Backend → PostgreSQL (structured data)
                                           → Qdrant (vector search — textbooks, drugs, reports)
                                           → pgvector (report chunks)
                                           → LLM (Gemini / OpenRouter)
                                           → Multi-source Drug APIs (DailyMed, OpenFDA, RxNorm, MedlinePlus)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 (App Router), TypeScript, TailwindCSS, Framer Motion, React Markdown |
| Backend | Python 3.11+, FastAPI, SQLAlchemy, Alembic |
| Database | PostgreSQL (Supabase) with pgvector |
| Vector Stores | Qdrant (remote + on-disk), FAISS |
| AI/LLM | Google Gemini API, OpenRouter |
| Embeddings | OpenAI `text-embedding-3-small` via OpenRouter (1536d) |
| Reranker | BAAI/bge-reranker-large (cross-encoder, optional) |
| Auth | JWT dual-token, Google OAuth, email OTP, bcrypt |
| Async Tasks | Redis Queue |
| Voice | Sarvam AI (STT), Google Cloud TTS |
| OCR | Medical document OCR pipeline |
| Infrastructure | Docker Compose |

---

## Features

### 1. Medical Library — RAG over 8 Medical Textbooks

16,000+ textbook chunks ingested into Qdrant across 4 collections:

| Collection | Textbook |
|-----------|----------|
| **Diseases** | Harrison's Principles of Internal Medicine (20th Ed) |
| **Diseases** | Davidson's Principles and Practice of Medicine |
| **Diseases** | Current Medical Diagnosis and Treatment 2025 |
| **Diseases** | The Merck Manual of Diagnosis and Therapy |
| **Laboratory** | Oxford Handbook of Clinical and Laboratory Investigation |
| **Pharmacology** | Goodman & Gilman's The Pharmacological Basis of Therapeutics (11th Ed) |
| **Pharmacology** | Basic & Clinical Pharmacology (2018) |
| **Clinical Practice** | Oxford Handbook of Clinical Medicine (10th Ed, 2017) |

**Search capabilities:**
- Hybrid search (vector + BM25 keyword) with configurable alpha weighting
- Cross-encoder reranker for relevance re-scoring
- Query expansion (140+ medical abbreviations/synonyms)
- Collection filtering and source counting
- Intent classification (symptom_triage, educational, treatment, drug_info, general_medical)

### 2. Drug Information & Consultation

**Drug Search:**
- Full-text PostgreSQL search by generic/brand name
- AI fallback (RAG) when no local match found — semantically retrieves medical chunks and generates grounded answers
- 8-phase search state machine (idle → loading → results → no_match → AI loading → AI result → AI error → answer_view)

**Multi-Source Drug Lookup** (plugin-based architecture):
| Source | Data |
|--------|------|
| **DailyMed (NIH)** | Structured Product Labels — 30+ section types (indications, dosage, adverse reactions, interactions, pregnancy, mechanism, pharmacokinetics, etc.) |
| **OpenFDA** | Drug labeling, NDC data, adverse events |
| **RxNorm (NIH)** | RxCUI lookup, brand/generic names, dose forms, strengths |
| **MedlinePlus (NIH)** | Patient counseling info |

**AI Drug Consult:**
- Q&A interface for medication questions
- Patient mode (plain language) / Professional mode toggle
- Multi-source context building (local DB + drug sources + textbook + vector store)
- Drug interaction detection when multiple drugs referenced
- Cached AI responses (7-day TTL)
- Follow-up question suggestions

**47+ fields** per drug including: generic_name, brand_names, drug_class, pharmacologic_class, therapeutic_class, rxnorm_id, atc_code, unii, indications, mechanism_of_action, pharmacokinetics, dosage forms, side effects (common + serious), interactions (drug/food/alcohol/herbal/disease), monitoring, pregnancy, breastfeeding, overdose, toxicity, antidote, clinical pearls, alternatives.

### 3. Medical Report Analyzer

**Upload & OCR:**
- Accepts PDF, JPEG, JPG, PNG uploads
- OCR extraction from scanned documents
- Automatic classification into 10 types: Blood Test, Prescription, X-Ray, MRI, CT Scan, ECG, Vaccination Record, Discharge Summary, Medical Certificate, General Medical Report

**Intelligence Engine:**
- **Lab value extraction** — 23 regex patterns matching common lab tests (Hemoglobin, WBC, Platelets, Glucose, HbA1c, Cholesterol panel, Creatinine, eGFR, Electrolytes, Liver enzymes, TSH, Vitamin D, Ferritin, B12)
- **Abnormal flagging** — Built-in reference ranges for all 23 lab tests
- **Biomarker tracking** — Longitudinal trends across all user reports
- **Risk scoring** — Abnormal labs decrease score from 100
- **AI insights** — Risk, abnormal, and follow-up type insights
- **Recommendations** — Diet, lifestyle, and doctor consultation suggestions
- **Timeline events** — Generated from structured report data
- **Chunking & embedding** — Report text split into 300-word chunks (50-word overlap), embedded into pgvector
- **Dual mode** — Synchronous processing OR async via Redis Queue + report_worker

**Endpoints:**
- Report summary (document type, AI summary, health score, risk scores)
- Lab values with reference ranges
- Biomarker history across reports
- Cross-report biomarker comparison
- Timeline with date-range filtering
- ML-based risk predictions
- Intelligent query routing

### 4. AI Health Chat

**Frontend:**
- Multi-session management (create, delete, list, pin)
- Streaming responses via Server-Sent Events
- Markdown rendering with citations
- Voice input (Sarvam AI STT → text)
- Suggested prompts (6 pre-built health questions)
- Copy-to-clipboard, typing indicator, auto-scroll

**Backend — Intent Router:**
- **emergency** — Crisis detection and emergency guidance (31 emergency patterns)
- **patient_history** — Profile + medications + reports summary
- **report_analysis** — Lab values, abnormal values, report chunks
- **drug_query** — Drug information via DrugService + PubMed fallback
- **metrics_analysis** — 30-day sleep/water/exercise trends
- **multi_source** — Combines all available sources
- **general_medical** — Citations from guidelines + PubMed + textbook + report chunks

**Context Fusion:** Unified retrieval across textbooks (Qdrant), medical library, and user reports (pgvector) with priority ordering: user data > textbooks > guidelines > PubMed. Deduplication by content fingerprint.

### 5. Health Dashboard & Metrics

**Daily Metrics Logging:**
- Sleep hours, water intake (ml), weight (kg), exercise (min), steps
- Mood (1-10), energy level, blood pressure (sys/dia), blood sugar
- Heart rate, oxygen saturation, symptoms, notes
- Upsert by date, date-range queries, aggregated stats

**Dashboard:**
- Time-based greeting with quick actions (AI Consult, Log Health, Medications, Upload Report)
- Animated SVG metric rings (Sleep, Hydration, Exercise, Steps)
- Today's metrics with progress bars
- Latest report snapshot (health score, risk level, AI summary)
- ML-based risk predictions (diabetes, CVD, CKD, stroke) with color coding
- Health Coach contextual sidebar

**Health Score Engine** (0-100):
- Metrics (35%) — Sleep, water, exercise, BP, blood sugar, heart rate
- Lab Results (25%) — Percentage of normal values
- Medication Adherence (15%) — Percentage of doses taken
- Conditions Management (25%) — Chronic disease burden
- Risk factor identification and level classification (excellent/good/fair/poor)

### 6. ML Risk Prediction

4 trained scikit-learn models:
| Model | Features |
|-------|----------|
| **Diabetes Risk** | Age, BMI, glucose, BP, exercise, sleep |
| **Heart Disease / CVD Risk** | Age, BP, cholesterol, glucose, BMI, smoking, HR, exercise |
| **CKD Risk** | Age, BP, glucose, BMI, hemoglobin, albumin, sodium |
| **Stroke Risk** | Age, BP, glucose, BMI, smoking, HR, exercise, sleep |

Risk levels: low / moderate / high with evidence-based scoring and source citations.

### 7. DailyMed Ingestion Pipeline

Complete ETL pipeline for FDA drug labeling data:

| Stage | Module | Function |
|-------|--------|----------|
| Crawl | `crawler.py` | Discover SPLs by drug name or via update API |
| Download | `downloader.py` | Download SPL XML files |
| Parse | `parser.py` | Parse XML to structured objects |
| Extract | `extractor.py` | Extract 30+ clinical section types |
| Normalize | `normalizer.py` | Normalize into standard formats |
| Build | `builder.py` | Build JSON output |
| Store | `storage.py` | Persist to PostgreSQL + Qdrant |

Supports: targeted ingestion, incremental updates (tracks revision dates), withdrawn label detection, validation, and stats reporting.

### 8. Medication Management

- CRUD for medications (name, dosage, frequency, route, reason, side effects)
- Medication adherence logging (scheduled time, taken/not taken)
- Drug-drug interaction checker
- Active-only filtering and soft-delete

### 9. Health Timeline

- Aggregated chronological view of metrics, medications, and reports
- Type-based icons and colors (metrics=teal, medications=purple, reports=blue)
- AI-powered timeline summarization
- Search across timeline with date-range filtering

### 10. Medical Library Search

- Hybrid search across 16K+ textbook chunks
- Two modes: `search_only` (raw retrieval) and `search_with_ai` (LLM synthesis)
- BM25 keyword + vector search with configurable weighting
- Cross-encoder reranker
- Query expansion (140+ abbreviations/synonyms)
- Collection filtering and source prioritization

### 11. Voice Assistant

- **Speech-to-text:** Sarvam AI API (Saaras v3 model) with webm-to-wav conversion
- **Text-to-speech:** Google Cloud Text-to-Speech (en-US-Neural2-C, MP3)

### 12. Routine Generator

- AI-generated daily health routines (wake time, sleep time, water goals, walking goals, exercise, nutrition)
- AI-generated weekly health plans

### 13. Notifications & Reminders

- Configurable reminders: medication, water, exercise, sleep, health check
- Notification history (last 50)
- Mark as read, upcoming scheduled notifications

### 14. Long-Term Memory

- Key-value memory store per user per category
- Used by chat service for personalized context across sessions

### 15. Authentication & Security

- Email/password registration and login
- Google OAuth
- JWT dual-token auth (access + refresh) with silent auto-refresh
- Singleton refresh interceptor with mutex (prevents concurrent refresh storms)
- Email OTP verification (6-digit code via SMTP)
- Passwordless "Login with OTP"
- Forgot/reset password flow
- Rate limiting on auth endpoints
- bcrypt password hashing
- HTTP-only cookies (SameSite=Lax)

---

## Project Structure

```
├── frontend/                          # Next.js 14 (App Router)
│   ├── src/
│   │   ├── app/
│   │   │   ├── drugs/                # Drug search with state machine
│   │   │   ├── chat/                 # AI health chat with streaming
│   │   │   ├── consult/              # Drug consultation Q&A
│   │   │   ├── dashboard/            # Health metrics dashboard
│   │   │   ├── reports/              # Report analyzer & comparison
│   │   │   ├── library/              # Medical textbook search
│   │   │   ├── timeline/             # Chronological health view
│   │   │   ├── medications/          # Medication management
│   │   │   ├── login/                # Auth (email, OTP, Google)
│   │   │   ├── metrics/              # Daily health logging
│   │   │   ├── settings/             # User profile & settings
│   │   │   └── ...                   # Register, forgot-password, etc.
│   │   ├── components/
│   │   │   ├── drugs/                # Drug search components
│   │   │   ├── auth/                 # Auth UI components
│   │   │   ├── consult/              # Consultation components
│   │   │   └── layout/               # App shell, sidebar, header
│   │   └── lib/
│   │       └── utils.ts              # apiFetch, formatDrugName, auth helpers
│   └── package.json
│
├── backend/                           # FastAPI
│   ├── app/
│   │   ├── api/v1/endpoints/         # 15+ REST endpoint modules
│   │   │   ├── drugs.py              # Search, autocomplete, consult, interactions
│   │   │   ├── auth.py               # Login, register, OTP, OAuth, refresh
│   │   │   ├── chat.py               # Chat sessions + streaming
│   │   │   ├── reports.py            # Upload, list, delete reports
│   │   │   ├── intelligence.py       # Lab values, biomarkers, insights, risks
│   │   │   ├── library.py            # Textbook search + reranker
│   │   │   ├── metrics.py            # Daily health metrics CRUD
│   │   │   ├── medications.py        # Medication CRUD + adherence
│   │   │   ├── rag.py                # Unified RAG with context fusion
│   │   │   └── ...                   # analytics, routines, voice, bot, etc.
│   │   ├── core/                     # Config, database, security
│   │   ├── domain/
│   │   │   ├── dailymed/             # FDA drug label ETL pipeline
│   │   │   └── medical_library/      # Textbook ingestion + search
│   │   ├── infrastructure/           # AI provider, embeddings, vector store, PubMed
│   │   ├── middleware/               # Auth middleware, rate limiting
│   │   ├── models/                   # SQLAlchemy ORM models
│   │   ├── schemas/                  # Pydantic request/response schemas
│   │   ├── services/                 # Business logic layer
│   │   │   ├── drug_service.py       # Multi-source drug lookup
│   │   │   ├── rag_service.py        # FAISS + LLM RAG pipeline
│   │   │   ├── chat_service.py       # Intent routing + context fusion
│   │   │   ├── report_service.py     # OCR + classification + extraction
│   │   │   ├── report_intelligence_service.py  # Lab analysis + biomarkers
│   │   │   ├── health_score_engine.py          # Unified health score
│   │   │   ├── risk_predictor.py     # ML risk models
│   │   │   ├── drug_sources/         # DailyMed, OpenFDA, RxNorm, MedlinePlus
│   │   │   └── ...                   # email, otp, auth, routines, memory
│   │   └── workers/                  # Background task processing (Redis)
│   ├── alembic/                      # Database migrations
│   ├── scripts/                      # Utility scripts
│   │   ├── ingestion/                # Book, drug, guideline ingestion
│   │   ├── enrichment/               # Drug data enrichment
│   │   ├── diagnostics/              # Extraction/quality diagnostics
│   │   └── maintenance/              # Retraining, reprocessing
│   └── requirements.txt
│
├── books/                            # Medical textbooks (PDF)
├── docker-compose.yml
├── start.sh
└── .env.example
```

## Getting Started

### Prerequisites
- Python 3.11+, Node.js 18+
- PostgreSQL with pgvector extension
- Qdrant (vector store)
- Google Gemini API key
- (Optional) Redis for async task processing

### Setup

```bash
# Clone and configure
git clone https://github.com/rahul-dev-6386/Medico.git
cd Medico
cp .env.example .env
# Edit .env with your database URL, API keys, and JWT secret

# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`

### Docker
```bash
docker compose up
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET` | Secret key for JWT signing |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `QDRANT_URL` | Qdrant server URL |
| `NEXT_PUBLIC_API_URL` | Backend API URL |

## License

MIT
