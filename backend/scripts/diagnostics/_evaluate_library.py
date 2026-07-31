"""
Medical Library RAG System Evaluation
Tests retrieval, reranking, citation quality, and cross-collection routing.
Searches ALL collections per query to evaluate routing correctness.
"""
import sys, os, time, json, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(level=logging.WARNING)
logging.getLogger("medical_library").setLevel(logging.WARNING)

from app.domain.medical_library.retriever import search, format_citation
from app.domain.medical_library import indexer
from app.domain.medical_library.embedder import embed_query
from qdrant_client import QdrantClient

QDRANT_PATH = "backend/data/library_qdrant"

# Pre-warm models
print("Warming up models...")
_ = embed_query("test")
print("Models ready.\n")

EXPECTED_BOOK_LABELS = {
    "diseases": ["Harrison", "Current Medical Diagnosis", "Merck Manual"],
    "laboratory": ["Oxford Handbook of Clinical and Laboratory"],
    "pharmacology": ["Goodman", "Basic & Clinical Pharmacology"],
    "clinical_practice": ["Oxford Handbook of Clinical Medicine"],
}

COLLECTION_MAP = {
    "diseases": "diseases",
    "laboratory": "laboratory",
    "pharmacology": "pharmacology",
    "clinical_practice": "clinical_practice",
}

ALL_COLLECTIONS = ["diseases", "laboratory", "pharmacology", "clinical_practice"]

TEST_QUERIES = {
    "diseases": [
        "What is Type 2 Diabetes?",
        "What are symptoms of heart failure?",
        "Management of COPD",
        "Diagnostic criteria for CKD",
        "Causes of liver cirrhosis",
        "Hypertension treatment guidelines",
        "Stroke risk factors and prevention",
        "Asthma management in adults",
        "Pneumonia diagnosis and treatment",
        "Acute coronary syndrome management",
        "Chronic kidney disease staging",
        "Heart failure with preserved ejection fraction",
        "Diabetes mellitus complications",
        "Chronic obstructive pulmonary disease exacerbation",
        "Community acquired pneumonia antibiotics",
        "Atrial fibrillation management",
        "Deep vein thrombosis treatment",
        "Pulmonary embolism diagnosis",
        "Rheumatoid arthritis treatment",
        "Osteoporosis screening guidelines",
        "Inflammatory bowel disease management",
        "Cirrhosis complications ascites",
        "Acute kidney injury causes",
        "HIV antiretroviral therapy",
        "Tuberculosis diagnosis and treatment",
        "Malaria treatment guidelines",
        "Cushing syndrome diagnosis",
        "Parkinson disease treatment",
        "Epilepsy management first line therapy",
        "Cancer chemotherapy principles",
        "Acute pancreatitis management",
        "Cholecystitis diagnosis and treatment",
        "Diverticulitis management",
        "Gastroesophageal reflux disease treatment",
        "Peptic ulcer disease causes",
        "Anemia of chronic disease",
        "Sickle cell disease management",
        "Hemophilia treatment",
        "Thyroid disorders hyperthyroidism",
        "Adrenal insufficiency diagnosis",
        "Pituitary tumors management",
        "Meningitis bacterial vs viral",
        "Encephalitis treatment",
        "Cellulitis antibiotic therapy",
        "Osteomyelitis diagnosis and treatment",
        "Septic arthritis management",
        "Gout treatment acute vs chronic",
        "Systemic lupus erythematosus management",
        "Vasculitis classification",
        "Sarcoidosis diagnosis and treatment",
    ],
    "laboratory": [
        "Interpret HbA1c of 8.5%",
        "Normal creatinine range",
        "CBC interpretation anemia",
        "Liver function test interpretation",
        "Lipid profile analysis",
        "Ferritin interpretation iron deficiency",
        "Vitamin B12 deficiency markers",
        "D-dimer significance pulmonary embolism",
        "TSH interpretation thyroid",
        "Urinalysis findings interpretation",
        "Complete blood count white cell differential",
        "Basic metabolic panel interpretation",
        "Coagulation studies PT INR PTT",
        "Arterial blood gas interpretation",
        "Cardiac troponin interpretation",
        "BNP and NT-proBNP interpretation",
        "Serum protein electrophoresis",
        "C-reactive protein and ESR",
        "Thyroid function tests",
        "Iron studies interpretation",
        "Vitamin D level interpretation",
        "Folate deficiency testing",
        "Hemoglobin electrophoresis",
        "Blood culture interpretation",
        "CSF analysis interpretation",
        "Pleural fluid analysis Light criteria",
        "Ascitic fluid analysis SAAG",
        "Urine protein electrophoresis",
        "Creatinine clearance calculation",
        "eGFR interpretation",
    ],
    "pharmacology": [
        "Metformin adverse effects",
        "Mechanism of action of aspirin",
        "Contraindications of warfarin",
        "ACE inhibitor side effects",
        "Statin toxicity and monitoring",
        "Insulin pharmacology types",
        "Beta blocker indications",
        "Amoxicillin dosing",
        "Drug interactions of clopidogrel",
        "NSAID complications GI bleeding",
        "Digoxin toxicity management",
        "Calcium channel blocker classification",
        "Diuretic mechanism of action",
        "Methotrexate adverse effects",
        "Prednisone tapering schedule",
        "Heparin induced thrombocytopenia",
        "Opioid analgesic equianalgesic dosing",
        "Benzodiazepine mechanism of action",
        "SSRI side effects",
        "Lithium monitoring toxicity",
        "Vancomycin dosing and monitoring",
        "Aminoglycoside nephrotoxicity",
        "Macrolide antibiotic spectrum",
        "Fluoroquinolone adverse effects",
        "Antifungal drug classification",
        "Antiviral mechanism acyclovir",
        "Chemotherapy alkylating agents",
        "Immunosuppressant cyclosporine",
        "Local anesthetic mechanism",
        "Inhalational anesthetic agents",
    ],
    "clinical_practice": [
        "Approach to chest pain",
        "Approach to anemia",
        "Approach to fever of unknown origin",
        "Approach to weight loss",
        "Approach to dizziness",
        "Approach to syncope",
        "Approach to chronic cough",
        "Approach to abdominal pain",
        "Approach to fatigue",
        "Approach to edema",
        "Approach to dyspnea",
        "Approach to hemoptysis",
        "Approach to jaundice",
        "Approach to lymphadenopathy",
        "Approach to joint pain",
        "Approach to back pain",
        "Approach to headache",
        "Approach to altered mental status",
        "Approach to seizures",
        "Approach to acute visual loss",
        "Approach to dysphagia",
        "Approach to nausea and vomiting",
        "Approach to diarrhea",
        "Approach to constipation",
        "Approach to gastrointestinal bleeding",
        "Approach to hematuria",
        "Approach to proteinuria",
        "Approach to hypertension",
        "Approach to hypotension",
        "Approach to polyuria",
    ],
}


def get_qdrant_stats():
    client = QdrantClient(path=QDRANT_PATH)
    stats = {}
    for coll in ALL_COLLECTIONS:
        info = client.get_collection(coll)
        stats[coll] = info.points_count
    return stats


def evaluate_query(query: str, expected_collection: str) -> dict:
    """Evaluate a query using cross-collection search (no collection filter)."""
    t_start = time.time()
    # Search ALL collections to test routing
    results = search(query, collection=None, top_k=10, use_hybrid=True, use_reranker=True)
    t_elapsed = time.time() - t_start

    record = {
        "query": query,
        "expected_collection": expected_collection,
        "retrieved_count": len(results),
        "latency": round(t_elapsed, 3),
        "sources": [],
        "citations": [],
        "has_page_number": False,
        "has_chapter": False,
        "has_book": False,
        "collection_counts": {},
        "book_counts": {},
        "top_collections": [],
    }

    if not results:
        return record

    for r in results:
        coll = r.get("collection", "")
        book = r.get("source_book", "") or ""
        chapter = r.get("chapter", "") or ""
        page = str(r.get("page_number", "") or "")
        score = r.get("hybrid_score", r.get("score", 0))

        record["sources"].append({
            "collection": coll,
            "book": book[:60],
            "chapter": chapter[:60] if chapter else "",
            "section": (r.get("section", "") or "")[:40],
            "page": page,
            "score": round(score, 4),
        })
        record["citations"].append(format_citation(r))

        record["collection_counts"][coll] = record["collection_counts"].get(coll, 0) + 1
        if book:
            record["book_counts"][book] = record["book_counts"].get(book, 0) + 1

        if page:
            record["has_page_number"] = True
        if chapter:
            record["has_chapter"] = True
        if book:
            record["has_book"] = True

    # Top collections
    sorted_colls = sorted(record["collection_counts"].items(), key=lambda x: -x[1])
    record["top_collections"] = [c for c, _ in sorted_colls]

    # Is the expected collection in the top results?
    coll_rank = 999
    for i, (c, _) in enumerate(sorted_colls):
        if c == expected_collection:
            coll_rank = i + 1
            break
    record["expected_collection_rank"] = coll_rank

    # What fraction of top-N results come from expected collection?
    top5 = results[:5]
    expected_in_top5 = sum(1 for r in top5 if r.get("collection") == expected_collection)
    record["expected_in_top5"] = expected_in_top5
    record["expected_in_top5_pct"] = expected_in_top5 / 5.0

    # Check book match
    expected_book_labels = EXPECTED_BOOK_LABELS.get(expected_collection, [])
    record["book_match_top5"] = 0
    for r in top5:
        book = r.get("source_book", "") or ""
        for label in expected_book_labels:
            if label.lower() in book.lower():
                record["book_match_top5"] += 1
                break
    record["book_match_top5_pct"] = record["book_match_top5"] / 5.0

    return record


def score_result(record: dict) -> dict:
    """Score 0-5 per dimension, total 0-20."""

    # Relevance: based on number of results and whether correct collection is in top
    has_relevant = record["retrieved_count"] > 0
    top5_ratio = record["expected_in_top5_pct"]
    if top5_ratio >= 0.8 and has_relevant:
        relevance = 5
    elif top5_ratio >= 0.6:
        relevance = 4
    elif top5_ratio >= 0.4:
        relevance = 3
    elif top5_ratio >= 0.2:
        relevance = 2
    elif has_relevant:
        relevance = 1
    else:
        relevance = 0

    # Citation quality (book/chapter/page availability)
    has_all = all([record["has_book"], record["has_chapter"], record["has_page_number"]])
    has_book_chapter = all([record["has_book"], record["has_chapter"]])
    if has_all:
        citation = 5
    elif has_book_chapter:
        citation = 3
    elif record["has_book"]:
        citation = 1
    else:
        citation = 0

    # Routing accuracy: how many of top 5 are from expected collection
    routing = round(record["expected_in_top5_pct"] * 5)

    # Book match: how many of top 5 match expected books
    book_match = round(record["book_match_top5_pct"] * 5)

    total = relevance + citation + routing + book_match
    return {"relevance": relevance, "citation": citation, "routing": routing, "book_match": book_match, "total": total}


def generate_report(all_records: list, all_scores: list):
    print("\n" + "=" * 100)
    print("MEDICAL LIBRARY RAG SYSTEM - EVALUATION REPORT")
    print("=" * 100)

    total = len(all_records)
    avg_lat = sum(r["latency"] for r in all_records) / max(total, 1)
    avg_rel = sum(s["relevance"] for s in all_scores) / max(total, 1)
    avg_cit = sum(s["citation"] for s in all_scores) / max(total, 1)
    avg_rte = sum(s["routing"] for s in all_scores) / max(total, 1)
    avg_bmk = sum(s["book_match"] for s in all_scores) / max(total, 1)
    avg_tot = sum(s["total"] for s in all_scores) / max(total, 1)

    qdrant_stats = get_qdrant_stats()
    print(f"\n## Index Statistics")
    print(f"Total indexed chunks: {sum(qdrant_stats.values()):,}")
    for coll, cnt in qdrant_stats.items():
        print(f"  {coll}: {cnt:,}")

    print(f"\n## Overall Performance")
    print(f"  Queries evaluated: {total}")
    print(f"  Average latency: {avg_lat*1000:.0f}ms")
    print(f"  Average relevance: {avg_rel:.2f}/5")
    print(f"  Average citation: {avg_cit:.2f}/5")
    print(f"  Average routing: {avg_rte:.2f}/5")
    print(f"  Average book-match: {avg_bmk:.2f}/5")
    print(f"  Average total: {avg_tot:.2f}/20")

    print(f"\n## Per-Collection Breakdown")
    for coll in ALL_COLLECTIONS:
        rs = [r for r in all_records if r["expected_collection"] == coll]
        ss = [s for r, s in zip(all_records, all_scores) if r["expected_collection"] == coll]
        if not rs:
            continue
        c_lat = sum(r["latency"] for r in rs) / len(rs)
        c_rel = sum(s["relevance"] for s in ss) / len(ss)
        c_cit = sum(s["citation"] for s in ss) / len(ss)
        c_rte = sum(s["routing"] for s in ss) / len(ss)
        c_bmk = sum(s["book_match"] for s in ss) / len(ss)
        c_tot = sum(s["total"] for s in ss) / len(ss)
        exp5 = sum(r["expected_in_top5"] for r in rs) / len(rs)
        top_colls = {}
        for r in rs:
            for tc in r["top_collections"][:2]:
                top_colls[tc] = top_colls.get(tc, 0) + 1
        print(f"\n  {coll}:")
        print(f"    Queries: {len(rs)}")
        print(f"    Avg latency: {c_lat*1000:.0f}ms")
        print(f"    Avg relevance: {c_rel:.2f}/5")
        print(f"    Avg citation: {c_cit:.2f}/5")
        print(f"    Avg routing: {c_rte:.2f}/5")
        print(f"    Avg book-match: {c_bmk:.2f}/5")
        print(f"    Avg total: {c_tot:.2f}/20")
        print(f"    Expected collection in top 5: {exp5:.1f}/5")
        print(f"    Dominant collections: {top_colls}")

    # Citation availability
    has_book_pct = sum(1 for r in all_records if r["has_book"]) / max(total, 1) * 100
    has_chap_pct = sum(1 for r in all_records if r["has_chapter"]) / max(total, 1) * 100
    has_page_pct = sum(1 for r in all_records if r["has_page_number"]) / max(total, 1) * 100
    print(f"\n## Citation Availability")
    print(f"  Results with book name: {has_book_pct:.0f}%")
    print(f"  Results with chapter: {has_chap_pct:.0f}%")
    print(f"  Results with page number: {has_page_pct:.0f}%")

    # Routing accuracy
    routing_ok = sum(1 for r in all_records if r["expected_in_top5"] >= 4)
    routing_pct = routing_ok / max(total, 1) * 100
    print(f"\n## Routing Accuracy (expected collection >= 4/5 in top 5)")
    print(f"  {routing_ok}/{total} ({routing_pct:.0f}%)")

    # Failure analysis
    print(f"\n## Failure Analysis")
    failures = []
    for r, s in zip(all_records, all_scores):
        issues = []
        if r["retrieved_count"] == 0:
            issues.append("NO_RESULTS")
        if r["expected_in_top5"] < 2:
            issues.append(f"WRONG_COLLECTION(expected={r['expected_in_top5']}/5)")
        if not r["has_book"]:
            issues.append("NO_BOOK")
        if not r["has_chapter"]:
            issues.append("NO_CHAPTER")
        if not r["has_page_number"]:
            issues.append("NO_PAGE")
        if s["total"] < 12:
            issues.append("LOW_SCORE")
        if issues:
            failures.append({
                "query": r["query"], "collection": r["expected_collection"],
                "issues": issues, "score": s["total"],
                "top_colls": r["top_collections"][:3],
            })

    if failures:
        print(f"  Queries with issues: {len(failures)}/{total}")
        for f in failures[:15]:
            print(f"    [{f['collection']}] score={f['score']}/20 {f['issues']}: \"{f['query'][:60]}\"  top_colls={f['top_colls']}")
        if len(failures) > 15:
            print(f"    ... and {len(failures)-15} more")
    else:
        print("  No failures detected.")

    # Deployment readiness
    print(f"\n{'='*100}")
    print("## DEPLOYMENT READINESS ASSESSMENT")
    print(f"{'='*100}")

    criteria = [
        ("Average relevance > 4.0", avg_rel > 4.0, f"{avg_rel:.2f}"),
        ("Average citation quality > 4.0", avg_cit > 4.0, f"{avg_cit:.2f}"),
        ("Book name in results", has_book_pct > 90, f"{has_book_pct:.0f}%"),
        ("Page numbers available > 50%", has_page_pct > 50, f"{has_page_pct:.0f}%"),
        ("Routing accuracy > 90%", routing_pct > 90, f"{routing_pct:.0f}%"),
        ("Latency < 2s", avg_lat < 2.0, f"{avg_lat*1000:.0f}ms"),
        ("Total avg score > 15/20", avg_tot > 15, f"{avg_tot:.2f}"),
    ]

    all_pass = True
    for label, passed, val in criteria:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {label:55s} (value: {val})")

    print(f"\n  OVERALL: {'PASS' if all_pass else 'FAIL'}")
    if not all_pass:
        print(f"\n  Recommendations:")
        for label, passed, val in criteria:
            if not passed:
                if "relevance" in label.lower():
                    print(f"    - Increase chunk overlap or add cross-collection retrieval")
                if "citation" in label.lower():
                    print(f"    - Propagate book/chapter/page in BM25 keyword results (they lack metadata)")
                if "book" in label.lower() and "page" not in label.lower():
                    print(f"    - Ensure all payloads carry source_book field")
                if "page" in label.lower():
                    print(f"    - Page number extraction: verify page payload population")
                if "routing" in label.lower():
                    print(f"    - Add collection-classifier before search to route queries")
                if "latency" in label.lower():
                    print(f"    - Reduce top_k or optimize BM25 indexing")
                if "score" in label.lower():
                    print(f"    - Improve chunking granularity for targeted queries")
    return all_pass


def export_json(all_records: list, all_scores: list, path: str = "/tmp/library_eval_report.json"):
    report = {"total_queries": len(all_records), "results": []}
    for r, s in zip(all_records, all_scores):
        report["results"].append({
            "query": r["query"],
            "expected_collection": r["expected_collection"],
            "latency_ms": round(r["latency"] * 1000),
            "retrieved": r["retrieved_count"],
            "has_book": r["has_book"],
            "has_chapter": r["has_chapter"],
            "has_page": r["has_page_number"],
            "expected_in_top5": f"{r['expected_in_top5']}/5",
            "book_match_top5": f"{r['book_match_top5']}/5",
            "top_collections": r["top_collections"][:3],
            "score": s,
        })
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nJSON report saved to {path}")


if __name__ == "__main__":
    total_q = sum(len(v) for v in TEST_QUERIES.values())
    print(f"Evaluating {total_q} queries across all collections...")
    print(f"Each query searches ALL collections to test routing accuracy.")

    all_records = []
    all_scores = []

    for coll, queries in TEST_QUERIES.items():
        print(f"\n--- Evaluating {coll} ({len(queries)} queries) ---")
        for i, q in enumerate(queries):
            record = evaluate_query(q, coll)
            score = score_result(record)
            all_records.append(record)
            all_scores.append(score)
            bar = "█" * int(score["total"] / 20 * 10) + "░" * (10 - int(score["total"] / 20 * 10))
            route = f"top={record['expected_in_top5']}/5" 
            print(f"  [{i+1:2d}/{len(queries)}] {q[:50]:50s} score={score['total']:2d}/20 lat={record['latency']*1000:.0f}ms route={route} {bar}")

    generate_report(all_records, all_scores)
    export_json(all_records, all_scores)
