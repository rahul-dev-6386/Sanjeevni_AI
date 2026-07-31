import logging
import re
from enum import Enum
from typing import Optional

from app.domain.medical_library import retriever

logger = logging.getLogger("medical_library")


class QueryIntent(str, Enum):
    SYMPTOM_TRIAGE = "symptom_triage"
    EDUCATIONAL = "educational"
    TREATMENT = "treatment"
    DRUG_INFO = "drug_info"
    GENERAL_MEDICAL = "general_medical"


SYMPTOM_PATTERNS = [
    re.compile(r"\b(i('ve| have)?|my|feeling|feels?|hurts?)\b", re.IGNORECASE),
    re.compile(r"\b(pain|ache|sore|burning|cramp|numb|tingl|swollen|itchy|dizzy"
               r"|fatigue|tired|weak|nausea|vomit|diarrhea|constipat|fever"
               r"|headache|cough|sneeze|rash|bloating|indigest|heartburn)\b", re.IGNORECASE),
    re.compile(r"\b(stomach|head|chest|back|joint|muscle|throat|ear|eye|skin"
               r"|leg|arm|foot|hand|neck|abdomen)\s+(pain|ache|hurt|pain)\b", re.IGNORECASE),
]

EDUCATIONAL_PATTERNS = [
    re.compile(r"^(what is|define|explain|tell me about|describe|what (are|does)"
               r"|how does|what causes)", re.IGNORECASE),
    re.compile(r"\bmeaning of\b", re.IGNORECASE),
    re.compile(r"\bdefinition\b", re.IGNORECASE),
]

TREATMENT_PATTERNS = [
    re.compile(r"\b(treat|therapy|management|cure|medication|drug|medicine"
               r"|tablet|pill|prescription|dosage|dose|injection)\b", re.IGNORECASE),
    re.compile(r"\bhow (to|do i|can i) (treat|manage|cure|handle|deal with)\b", re.IGNORECASE),
]

DRUG_NAME_SUFFIXES = (
    r"icin|ium|olol|pril|sartan|azepam|caine|navir|cycline"
    r"|mycin|prazole|tidine|statin|glita|glide|sone|mab|nib|vir"
    r"|prol|pine|zide|afil|oxacin|conazole|dipine|formin|lol"
    r"|cillin|vudine|pam|barbital|thiazide|terol|coxib|oxetine"
    r"|oprazole|tadine|conazole|qualone"
)

DRUG_PATTERNS = [
    re.compile(
        r"\b(what is|tell me about|side effects of|dosage of|interactions? of"
        r"|is\s+\w+\s+(?:a\s+)?drug)\s+\w+(?:" + DRUG_NAME_SUFFIXES + r")\b",
        re.IGNORECASE,
    ),
]


def classify_query_intent(query: str) -> QueryIntent:
    q = query.lower().strip()

    for p in DRUG_PATTERNS:
        if p.search(q):
            return QueryIntent.DRUG_INFO

    has_treatment = any(p.search(q) for p in TREATMENT_PATTERNS)
    has_educational = any(p.search(q) for p in EDUCATIONAL_PATTERNS)
    has_symptom = any(p.search(q) for p in SYMPTOM_PATTERNS)

    if has_treatment:
        return QueryIntent.TREATMENT
    if has_educational:
        return QueryIntent.EDUCATIONAL
    if has_symptom:
        return QueryIntent.SYMPTOM_TRIAGE

    return QueryIntent.GENERAL_MEDICAL


def _significant_overlap(a: str, b: str, threshold: float = 0.35) -> bool:
    if not a or not b:
        return False
    sentences_a = {s.strip().lower() for s in re.split(r'[.!?\n]', a) if len(s.strip()) > 20}
    sentences_b = {s.strip().lower() for s in re.split(r'[.!?\n]', b) if len(s.strip()) > 20}
    if not sentences_a or not sentences_b:
        return False
    overlap = len(sentences_a & sentences_b) / min(len(sentences_a), len(sentences_b))
    return overlap > threshold


def _text_fingerprint(text: str) -> str:
    t = re.sub(r'\s+', ' ', text.lower().strip())
    return t[:150]


def compress_context(results: list[dict]) -> tuple[list[str], list[str]]:
    groups: dict[str, list[dict]] = {}
    for r in results:
        key = f"{r.get('source_book', '')}|{r.get('chapter', '')}"
        groups.setdefault(key, []).append(r)

    merged_texts = []
    used_books = set()

    for key, group in groups.items():
        book = group[0].get("source_book", "")
        if book:
            used_books.add(book)
        group.sort(key=lambda x: x.get("hybrid_score", x.get("score", 0)), reverse=True)

        merged = group[0].get("text", "")
        for r in group[1:]:
            text = r.get("text", "")
            if not text or _significant_overlap(merged, text):
                continue
            merged += "\n\n" + text
        merged_texts.append(merged)

    seen = set()
    final_texts = []
    for text in merged_texts:
        fp = _text_fingerprint(text)
        if fp not in seen:
            seen.add(fp)
            final_texts.append(text)

    return final_texts, sorted(used_books)


def format_references(books: list[str]) -> str:
    seen = set()
    unique = []
    for b in books:
        clean = b.strip().rstrip('.')
        if clean and clean not in seen:
            seen.add(clean)
            unique.append(clean)
    if not unique:
        return ""
    return "\n\n## 📚 References\n" + "\n".join(f"- {b}" for b in unique)


FORMATTING_RULES = (
    "## Formatting Rules\n\n"
    "Never return large paragraphs. Always use:\n"
    "- `# Main heading` at the top\n"
    "- `## Sections` with relevant emoji (use sparingly)\n"
    "- `### Subsections` when needed\n"
    "- Bullet lists and numbered lists\n"
    "- Markdown tables when comparing values\n"
    "- Blockquotes (`>`) for important notes or red flags\n"
    "- **Bold** for diseases, medications, and laboratory tests\n"
    "- Emojis sparingly (only: 🩺📊⚠️✅🚨💬📚) to improve scanning\n\n"
    "Keep answers visually structured. The user should understand the answer within 10 seconds."
)

ANSWER_TEMPLATE_LABS = (
    "## Answer Template (Laboratory Tests)\n\n"
    "Use this structure:\n"
    "- `# Short Answer` — 2-3 sentence concise explanation\n"
    "- `## 🩺 What It Means` — explain simply\n"
    "- `## 📊 Key Findings` — bullet list of relevant values\n"
    "- `## 📋 Interpretation` — markdown table of patterns and meanings\n"
    "- `## ⚠️ Possible Causes` — grouped into Common / Less Common\n"
    "- `## ✅ What You Can Do` — actionable advice\n"
    "- `## 🚨 Seek Medical Care Immediately If` — numbered or bullet list\n"
    "- `## 💬 If You Have Your Results` — ask user to share specific values\n"
    "- `## 📚 References` — sources used"
)

ANSWER_TEMPLATE_SYMPTOMS = (
    "## Answer Template (Symptoms)\n\n"
    "Use this structure:\n"
    "- `# Short Answer` — 2-3 sentence summary\n"
    "- `## 🩺 What It Means` — explain in plain language\n"
    "- `## ⚠️ Possible Causes` — grouped into Common / Less Common\n"
    "- `## ✅ Home Care` — practical self-care advice\n"
    "- `## 🚨 Red Flags` — symptoms requiring urgent medical attention\n"
    "- `## 💬 Questions to Narrow the Diagnosis` — targeted follow-ups\n"
    "- `## 📚 References`"
)

ANSWER_TEMPLATE_DRUGS = (
    "## Answer Template (Medications)\n\n"
    "Use this structure:\n"
    "- `# Short Answer` — 2-3 sentence summary\n"
    "- `## 💊 Uses` — indications\n"
    "- `## 📊 Dosage` — typical dosing\n"
    "- `## ⚠️ Side Effects` — common and serious\n"
    "- `## 🚫 Contraindications` — who should not take it\n"
    "- `## 🔄 Drug Interactions` — significant interactions\n"
    "- `## 📚 References`"
)

ANSWER_TEMPLATE_DISEASES = (
    "## Answer Template (Diseases)\n\n"
    "Use this structure:\n"
    "- `# Short Answer` — 2-3 sentence overview\n"
    "- `## 🩺 Overview` — what it is\n"
    "- `## 📋 Symptoms` — bullet list\n"
    "- `## 🔬 Diagnosis` — how it is diagnosed\n"
    "- `## 💊 Treatment` — standard approaches\n"
    "- `## 📈 Prognosis` — what to expect\n"
    "- `## 🚨 When to Seek Medical Care` — red flags\n"
    "- `## 📚 References`"
)

ANSWER_TEMPLATE_GENERAL = (
    "## Answer Template (General Medical)\n\n"
    "Use this structure:\n"
    "- `# Short Answer` — 2-3 sentence explanation\n"
    "- `## 🩺 What It Means` — explain simply\n"
    "- `## 📊 Key Findings` — bullet list\n"
    "- `## 📋 Interpretation` — table when possible\n"
    "- `## ⚠️ Possible Causes` — grouped Common / Less Common\n"
    "- `## ✅ What You Can Do` — actionable advice\n"
    "- `## 🚨 Seek Medical Care Immediately If` — bullet list\n"
    "- `## 💬 If You Have Your Results` — ask for specific values/details\n"
    "- `## 📚 References`"
)

SYSTEM_PROMPT_CORE = (
    "You are **Medico AI**. You are an evidence-based medical assistant.\n\n"
    "You have access to trusted medical knowledge including Harrison's, Merck Manual, "
    "Oxford Handbook, Davidson, Goodman & Gilman, Current Medical Diagnosis & Treatment, "
    "and other medical references.\n\n"
    "Use these references only to verify your answers.\n"
    "Never mention the retrieval process.\n"
    "Never mention textbooks unless citing them in the references section.\n"
    "Never mention missing definitions. Interpret common patient language naturally.\n\n"
    "Always answer like an experienced physician. Never answer like a textbook.\n"
    "Never dump retrieved passages. Never quote multiple books separately.\n"
    "Summarize everything. If multiple sources agree, merge into one concise explanation.\n\n"
    f"{FORMATTING_RULES}\n\n"
)

SYMPTOM_EXTRA = f"""
{ANSWER_TEMPLATE_SYMPTOMS}

If the question is vague, ask targeted follow-up questions instead of listing dozens of possibilities.
"""

EDUCATIONAL_EXTRA = f"""
{ANSWER_TEMPLATE_DISEASES}

Provide a concise, clear explanation. Synthesize from multiple sources.
Use analogies and plain language where helpful.
"""

TREATMENT_EXTRA = f"""
{ANSWER_TEMPLATE_GENERAL}

Cover standard approaches based on available evidence.
"""

DRUG_EXTRA = f"""
{ANSWER_TEMPLATE_DRUGS}
"""

GENERAL_EXTRA = f"""
{ANSWER_TEMPLATE_GENERAL}
"""


def _get_system_prompt(intent: QueryIntent) -> str:
    base = SYSTEM_PROMPT_CORE
    if intent == QueryIntent.SYMPTOM_TRIAGE:
        return base + SYMPTOM_EXTRA
    if intent == QueryIntent.EDUCATIONAL:
        return base + EDUCATIONAL_EXTRA
    if intent == QueryIntent.TREATMENT:
        return base + TREATMENT_EXTRA
    if intent == QueryIntent.DRUG_INFO:
        return base + DRUG_EXTRA
    return base + GENERAL_EXTRA


def _build_user_prompt(query: str, context_texts: list[str], intent: QueryIntent) -> str:
    context_str = "\n\n".join(context_texts)
    context_str = context_str[:8000]

    return (
        f"Answer the user's question using the structured template provided in the system prompt. "
        f"Use proper GFM markdown. Never return raw paragraphs.\n\n"
        f"User: {query}\n\n"
        f"Relevant context:\n{context_str}\n\n"
        f"Answer:"
    )


class AnswerGenerator:
    def __init__(self, db=None):
        self.db = db

    def _get_ai_provider(self):
        from app.infrastructure.ai_provider_service import AIProviderService
        return AIProviderService(db=self.db)

    def search_only(self, query: str, collection: Optional[str] = None, top_k: int = 5) -> dict:
        import time
        t0 = time.time()
        results = retriever.search(query, collection=collection, top_k=top_k)
        elapsed = round((time.time() - t0) * 1000)

        collection_counts = {}
        for r in results:
            c = r.get("collection", "unknown")
            collection_counts[c] = collection_counts.get(c, 0) + 1

        return {
            "answer": None,
            "mode": "search_only",
            "collection": collection,
            "results": results,
            "metrics": {
                "latency_ms": elapsed,
                "collection_searched": collection or "all",
                "chunks_retrieved": len(results),
                "collections_used": list(collection_counts.keys()),
                "collection_breakdown": collection_counts,
            },
            "sources": [
                {
                    "book": r.get("source_book", ""),
                    "chapter": r.get("chapter", ""),
                    "section": r.get("section", ""),
                    "page": r.get("page_number", ""),
                    "text": r.get("text", ""),
                    "score": round(r.get("rerank_score", r.get("hybrid_score", r.get("score", 0))), 4),
                    "collection": r.get("collection", ""),
                }
                for r in results
            ],
        }

    def search_with_ai(self, query: str, collection: Optional[str] = None, top_k: int = 8) -> dict:
        import time
        t0 = time.time()

        results = retriever.search(query, collection=collection, top_k=top_k + 4, use_reranker=True)
        elapsed = round((time.time() - t0) * 1000)

        intent = classify_query_intent(query)
        provider = self._get_ai_provider()
        answer = None
        mode = "ai_failed"

        # ─── DIRECT RAG: retrieve → compress → prompt → AI (single call) ─────
        # Simple, reliable pipeline. Works with any model, no JSON parsing needed.
        try:
            context_texts, used_books = compress_context(results)
            if context_texts:
                system_prompt = _get_system_prompt(intent)
                user_prompt = _build_user_prompt(query, context_texts, intent)
                logger.info(f"RAG search: {len(context_texts)} chunks, intent={intent.value}, model chain active")
                raw_answer = provider.generate_response(
                    user_prompt, system_instruction=system_prompt, temperature=0.3
                )
                if raw_answer and len(raw_answer) >= 20 and "AI temporarily unavailable" not in raw_answer:
                    answer = raw_answer
                    mode = "ai_generated"
                    logger.info(f"RAG answer generated successfully ({len(answer)} chars)")
                else:
                    logger.warning(f"AI returned empty/short answer: {repr(raw_answer[:100] if raw_answer else '')}")
            else:
                logger.warning("No RAG chunks found for query")
        except Exception as e:
            logger.warning(f"RAG answer generation failed: {e}")
            answer = None
            mode = "ai_failed"

        # ─── REFERENCES & SOURCES ─────────────────────────────────────────────
        references = []
        follow_up_questions = []
        if answer:
            unique_books = set([r.get("source_book") for r in results if r.get("source_book")])
            references = list(unique_books)
            if "## References" not in answer and "## 📚 References" not in answer:
                answer += format_references(references)

        sources = [
            {
                "book": r.get("source_book", ""),
                "chapter": r.get("chapter", ""),
                "section": r.get("section", ""),
                "page": r.get("page_number", ""),
                "text": r.get("text", ""),
                "score": round(r.get("rerank_score", r.get("hybrid_score", r.get("score", 0))), 4),
                "collection": r.get("collection", ""),
            }
            for r in results
        ]

        return {
            "answer": answer,
            "mode": mode,
            "collection": collection,
            "intent": intent.value,
            "references": references,
            "follow_up_questions": follow_up_questions,
            "sources": sources,
            "results": results,
            "metrics": {
                "latency_ms": elapsed,
                "collection_searched": collection or "all",
                "chunks_retrieved": len(results),
                "intent": intent.value,
            },
        }
