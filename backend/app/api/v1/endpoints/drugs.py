from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, String
from typing import Optional

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.models.drug_database import DrugEntry
from app.services.drug_service import DrugService
from app.services.hybrid_drug_service import HybridDrugService
from app.services.drug_consult_service import DrugConsultService

router = APIRouter(prefix="/api/drugs", tags=["Drug Information"])


class ConsultRequest(BaseModel):
    question: str
    patient_mode: bool = False


@router.get("/autocomplete")
def autocomplete_drug(
    q: str = Query(..., description="Prefix to autocomplete"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not q or len(q) < 1:
        return {"drugs": []}
    term = f"{q}%"
    results = (
        db.query(DrugEntry.generic_name, DrugEntry.brand_names)
        .filter(DrugEntry.generic_name.ilike(term))
        .limit(8)
        .all()
    )
    suggestions = list({r[0] for r in results if r[0]})
    if not suggestions:
        results = (
            db.query(DrugEntry.generic_name)
            .filter(func.lower(cast(DrugEntry.brand_names, String)).ilike(term))
            .limit(5)
            .all()
        )
        suggestions = list({r[0] for r in results if r[0]})
    return {"drugs": suggestions}


@router.get("/search")
def search_drug(
    q: str = Query(..., description="Drug name to search for"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = DrugService(db)
    results = service.search_drug(q)
    if results:
        return {"drugs": results, "source": "local"}

    # Not found locally — query all external sources
    merged = service.search_all_sources(q)
    if merged.get("generic_name"):
        stored = service.store_drug(merged)
        if stored:
            return {
                "drugs": [service._entry_to_dict(stored)],
                "source": "multi",
            }

    return {"drugs": [], "source": "none"}


@router.get("/interactions")
def check_interactions(
    drugs: str = Query(..., description="Comma-separated drug names"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    names = [d.strip() for d in drugs.split(",") if d.strip()]
    if len(names) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 drug names")
    service = DrugService(db)
    results = service.get_interactions(names)
    return {"drugs": names, "interactions": results}


@router.get("/count")
def drug_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = DrugService(db)
    return {"count": service.count()}


@router.get("/answer")
def drug_answer(
    q: str = Query(..., description="Drug name to generate answer for"),
    skip_local: bool = Query(False, description="Skip local DB search and use AI directly"),
    patient_mode: bool = Query(False, description="Use patient-friendly language"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = DrugConsultService(db)
    result = service.generate_drug_answer(q, skip_local_search=skip_local)
    result["patient_mode"] = patient_mode
    return result


@router.get("/ai-search")
def ai_search_drug(
    q: str = Query(..., description="Drug name to search via AI"),
    patient_mode: bool = Query(False, description="Use patient-friendly language"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bypass the local database entirely and answer via the AI pipeline.
    This is used when the local DB has no matching drug so the user
    explicitly opts into an AI-generated response.
    """
    service = DrugConsultService(db)
    result = service.generate_drug_answer(q, skip_local_search=True)
    result["patient_mode"] = patient_mode
    return result


@router.post("/consult")
def drug_consult(
    body: ConsultRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = DrugConsultService(db)
    result = service.consult(
        question=body.question,
        patient_mode=body.patient_mode,
    )
    return result
