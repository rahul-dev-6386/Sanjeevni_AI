from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.medical_library import indexer
from app.domain.medical_library.answer_generator import AnswerGenerator
from app.schemas.library import (
    LibrarySearchParams,
    LibraryQueryRequest,
    LibrarySearchResponse,
    LibrarySourcesResponse,
    LibraryBooksResponse,
    LibraryTopicsResponse,
    LibraryCollectionInfo,
    BookInfo,
    TopicInfo,
)

router = APIRouter(prefix="/api/library", tags=["Medical Library"])

BOOK_MAP = {
    "diseases": [
        ("Harrison's Principles of Internal Medicine", "Disease Knowledge/Harrisons-Principles-of-Internal-Medicine-20th-Edition-Vol.1-Vol.2-Part-1.pdf"),
        ("Davidson's Principles and Practice of Medicine", "Disease Knowledge/Davidsons-Principles-Practice-of-Medicine-PDFDrive.com-.pdf"),
        ("Current Medical Diagnosis and Treatment 2025", "Disease Knowledge/current-medical-diagnosis-and-treatment-2025-1.pdf"),
        ("The Merck Manual of Diagnosis and Therapy", "Report Intelligence/The_Merck_Manual_of_Diagnosis_and_Therapy_2011_-_19th_Edn........pdf"),
    ],
    "laboratory": [
        ("Oxford Handbook of Clinical and Laboratory Investigation", "Report Intelligence/Oxford-Handbook-of-Clinical-and-Laboratory-Investigation.pdf"),
        ("The Merck Manual of Diagnosis and Therapy", "Report Intelligence/The_Merck_Manual_of_Diagnosis_and_Therapy_2011_-_19th_Edn........pdf"),
    ],
    "pharmacology": [
        ("Goodman & Gilman's The Pharmacological Basis of Therapeutics", "Pharmacology/Goodman-Gilmans-The-Pharmacological-Basis-of-Therapeutics-11th-Edition-2006.pdf"),
        ("Basic & Clinical Pharmacology", "Pharmacology/Basic-Clinical-Pharmacology-2018.pdf"),
    ],
    "clinical_practice": [
        ("Oxford Handbook of Clinical Medicine", "Clinical Practice/8205Oxford Handbook of Clinical Medicine 10th 2017 Edition_SamanSarKo - Copy.pdf"),
    ],
}


@router.get("/search", response_model=LibrarySearchResponse)
def library_search(
    q: str = Query(..., min_length=1),
    collection: str = Query(None),
    top_k: int = Query(5, ge=1, le=20),
    mode: str = Query("search_with_ai", pattern="^(search_only|search_with_ai)$"),
    db: Session = Depends(get_db),
):
    generator = AnswerGenerator(db=db)
    if mode == "search_only":
        result = generator.search_only(q, collection=collection, top_k=top_k)
    else:
        result = generator.search_with_ai(q, collection=collection, top_k=top_k)

    return LibrarySearchResponse(
        query=q,
        collection=collection,
        mode=result["mode"],
        intent=result.get("intent"),
        answer=result.get("answer"),
        references=result.get("references", []),
        follow_up_questions=result.get("follow_up_questions", []),
        sources=result["sources"],
    )


@router.get("/sources", response_model=LibrarySourcesResponse)
def library_sources(
    db: Session = Depends(get_db),
):
    client = indexer.get_client()
    stats = indexer.get_stats(client)
    collections = [
        LibraryCollectionInfo(name=name, chunk_count=count)
        for name, count in stats.items()
    ]
    return LibrarySourcesResponse(collections=collections)


@router.get("/books", response_model=LibraryBooksResponse)
def library_books(
    db: Session = Depends(get_db),
):
    books = []
    for collection, book_list in BOOK_MAP.items():
        for name, path in book_list:
            books.append(BookInfo(name=name, collection=collection, path=path))
    return LibraryBooksResponse(books=books)


@router.get("/topics", response_model=LibraryTopicsResponse)
def library_topics(
    db: Session = Depends(get_db),
):
    topics_map = {
        "Diabetes Mellitus": {"count": 0, "collections": ["diseases", "clinical_practice"]},
        "Hypertension": {"count": 0, "collections": ["diseases", "clinical_practice"]},
        "Cardiovascular Disease": {"count": 0, "collections": ["diseases", "clinical_practice"]},
        "Infectious Diseases": {"count": 0, "collections": ["diseases"]},
        "Renal Disorders": {"count": 0, "collections": ["diseases", "laboratory"]},
        "Hepatic Disorders": {"count": 0, "collections": ["diseases", "laboratory"]},
        "Respiratory Disorders": {"count": 0, "collections": ["diseases", "clinical_practice"]},
        "Endocrinology": {"count": 0, "collections": ["diseases", "laboratory"]},
        "Hematology": {"count": 0, "collections": ["diseases", "laboratory"]},
        "Clinical Pharmacology": {"count": 0, "collections": ["pharmacology"]},
        "Drug Interactions": {"count": 0, "collections": ["pharmacology"]},
        "Laboratory Values": {"count": 0, "collections": ["laboratory"]},
        "Diagnostic Criteria": {"count": 0, "collections": ["clinical_practice", "laboratory"]},
    }

    topics = [
        TopicInfo(name=name, count=data["count"], collections=data["collections"])
        for name, data in topics_map.items()
    ]
    return LibraryTopicsResponse(topics=topics)


@router.post("/query", response_model=LibrarySearchResponse)
def library_query(
    body: LibraryQueryRequest,
    db: Session = Depends(get_db),
):
    generator = AnswerGenerator(db=db)
    if body.mode == "search_only":
        result = generator.search_only(body.query, collection=body.collection, top_k=body.top_k)
    else:
        result = generator.search_with_ai(body.query, collection=body.collection, top_k=body.top_k)

    return LibrarySearchResponse(
        query=body.query,
        collection=body.collection,
        mode=result["mode"],
        intent=result.get("intent"),
        answer=result.get("answer"),
        references=result.get("references", []),
        follow_up_questions=result.get("follow_up_questions", []),
        sources=result["sources"],
    )
