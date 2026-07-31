"""Rule-based text cleaners that transform raw DailyMed / OpenFDA text into clean clinical content.

Each function handles known DailyMed formatting patterns and falls back gracefully when
the text doesn't match any known pattern.
"""

import re
from typing import Any


NOT_AVAILABLE = "Information not available in the indexed references."


def _cap(line: str) -> str:
    if line and line[0].islower():
        return line[0].upper() + line[1:]
    return line


def _strip_section_header(text: str, header: str) -> str:
    return re.sub(
        rf"^\d*\s*{re.escape(header)}\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()


KNOWN_INDICATIONS = [
    "fever", "headache", "toothache", "back pain", "backache", "muscle aches",
    "muscular aches", "musculoskeletal pain", "joint pain", "arthritis",
    "osteoarthritis", "rheumatoid arthritis", "dysmenorrhea", "menstrual cramps",
    "common cold", "cold symptoms", "cough", "sore throat", "nasal congestion",
    "sinusitis", "sinus congestion", "allergic rhinitis", "hay fever",
    "hypertension", "high blood pressure", "angina", "chest pain",
    "heart failure", "diabetes", "type 2 diabetes", "type 1 diabetes",
    "hyperlipidemia", "high cholesterol", "infection", "bacterial infection",
    "viral infection", "urinary tract infection", "uti", "pneumonia",
    "bronchitis", "tonsillitis", "pharyngitis", "otitis media", "sinusitis",
    "skin infection", "wound infection", "surgical prophylaxis",
    "inflammation", "pain", "acute pain", "chronic pain", "neuropathic pain",
    "postoperative pain", "migraine", "tension headache", "cluster headache",
    "neuralgia", "sciatica", "fibromyalgia", "gout", "hyperuricemia",
    "osteoporosis", "nausea", "vomiting", "motion sickness", "vertigo",
    "dizziness", "insomnia", "anxiety", "depression", "panic disorder",
    "epilepsy", "seizures", "convulsions", "parkinson disease", "parkinson's",
    "alzheimer disease", "alzheimer's", "dementia", "adhd",
    "asthma", "copd", "bronchospasm", "allergies", "urticaria", "rash",
    "dermatitis", "eczema", "psoriasis", "acne", "fungal infection",
    "candidiasis", "ringworm", "athlete's foot",
    "anemia", "iron deficiency", "vitamin deficiency", "dehydration",
    "electrolyte imbalance", "hypokalemia", "hyponatremia",
    "hypothyroidism", "hyperthyroidism", "thyroid disease",
    "glaucoma", "conjunctivitis", "dry eye",
    "obesity", "weight management", "smoking cessation",
    "contraception", "family planning", "hormone replacement",
    "constipation", "diarrhea", "ibs", "irritable bowel syndrome",
    "gerd", "acid reflux", "heartburn", "ulcer", "peptic ulcer",
    "gastritis", "crohn disease", "crohn's", "ulcerative colitis",
    "hemorrhoids", "anal fissure",
    "insect bite", "poison ivy", "sunburn", "diaper rash",
    "immunization", "vaccination", "prophylaxis",
]


def _match_indications(text: str) -> list[str]:
    """Match known indication terms in free-form text."""
    text_lower = text.lower()
    found: list[str] = []
    seen: set[str] = set()
    for term in KNOWN_INDICATIONS:
        if term in text_lower:
            if term not in seen:
                seen.add(term)
                found.append(_cap(term))
    return found


def clean_indications(raw: str) -> list[str]:
    """Parse raw indications text into clean bullet items using lexicon + heuristics."""
    if not raw or not raw.strip():
        return []

    text = raw.strip()
    text = _strip_section_header(text, "INDICATIONS")
    text = re.sub(
        r"^(uses\s*|indicated\s*|for\s+the\s+(relief|treatment|management)\s+of\s*)",
        "",
        text,
        flags=re.IGNORECASE,
    )

    if "due to" in text.lower():
        m = re.search(r"due\s+to\s*:?\s*(.+)", text, flags=re.IGNORECASE)
        if m:
            text = m.group(1)

    # Try structured splitting first
    items = re.split(r"\s*[,;]\s*|\s+and\s+|\n+", text)
    structured = []
    for item in items:
        item = item.strip().strip(".").strip()
        if not item or len(item) < 3:
            continue
        if re.match(r"^(temporarily|see|ask|do\s+not|if|when|for\s+more)", item, re.IGNORECASE):
            continue
        structured.append(item)

    # If structured split gave items with clear delimiters, use those
    if len(structured) >= 3:
        seen: set[str] = set()
        result: list[str] = []
        for item in structured:
            lower = item.lower()
            if lower not in seen:
                seen.add(lower)
                result.append(_cap(item))
        return result

    # Fall back to lexicon matching for space-separated text
    return _match_indications(text)


def parse_dosage(raw: str) -> dict[str, str]:
    """Parse raw dosage directions into structured components.

    Handles patterns like:
    'Directions do not take more than directed adults and children 12 years and over take 2 gelcaps every 6 hours
     while symptoms last do not take more than 6 gelcaps in 24 hours...'
    """
    if not raw or not raw.strip():
        return {}

    text = raw.strip()
    text = _strip_section_header(text, "DOSAGE AND ADMINISTRATION")
    text = _strip_section_header(text, "DOSAGE & ADMINISTRATION")
    text = re.sub(r"^directions?\s*", "", text, flags=re.IGNORECASE)

    result: dict[str, str] = {}

    dose_m = re.search(
        r"(?:take|administer|use|give)\s+(\d[\d\s/]*\s*(?:gelcaps?|tablets?|capsules?|teaspoons?|tsp|drops?|mg|mcg|g|ml|units?))(?:\s+[^.]*?)?(?:every\s+(\d[\d\s]*(?:hours?|days?)))?",
        text,
        re.IGNORECASE,
    )
    if dose_m:
        dose_val = dose_m.group(1).strip()
        freq = dose_m.group(2).strip().replace("hours", "h").replace("hour", "h") if dose_m.group(2) else ""
        if freq:
            result["adult_dose"] = f"{dose_val} every {freq}"
        else:
            result["adult_dose"] = dose_val

    max_m = re.search(
        r"(?:do\s+not\s+(?:exceed|take\s+more\s+than))\s+(\d[\d\s/]*\s*(?:gelcaps?|tablets?|capsules?|teaspoons?|tsp|drops?|mg|mcg|g|ml|units?))(?:\s+in\s+(\d+)\s*(?:hours?|days?))?",
        text,
        re.IGNORECASE,
    )
    if max_m:
        period = max_m.group(2) if max_m.group(2) else "24"
        val = max_m.group(1).strip()
        result["max_daily"] = f"Do not exceed {val}/day" if period == "24" else f"Do not exceed {val} in {period} hours"

    dur_m = re.search(
        r"(?:do\s+not\s+take\s+for\s+more\s+than)\s+(\d+\s*(?:days?|weeks?))",
        text,
        re.IGNORECASE,
    )
    if dur_m:
        result["max_duration"] = f"Do not use for more than {dur_m.group(1)} unless directed by a physician"

    ped_m = re.search(
        r"children\s+(under|below|ages?\s+)\s*(\d[\d-]*)\s*(?:years?|months?)?\s*:?\s*([^.]+)",
        text,
        re.IGNORECASE,
    )
    if ped_m:
        age = ped_m.group(2).strip()
        result["pediatric"] = f"Children <{age} years: {_cap(ped_m.group(3).strip())}."

    return result


def clean_formulations(raw: Any) -> list[tuple[str, str]]:
    """Parse raw formulation text into (form, strengths) pairs.

    Handles patterns like:
    'Oral > Solid > tablet: 250 mg; 325 mg; 500 mg'
    'Local > Rectal > Suppository: 100 mg; 250 mg'
    Returns clean form names: 'Tablet', 'Suppository', etc.
    """
    if not raw:
        return []
    if isinstance(raw, list):
        return [(str(r), "") for r in raw]

    lines = [l.strip() for l in str(raw).split("\n") if l.strip()]
    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    for line in lines:
        m = re.search(r">\s*([^:]+?)\s*:\s*(.+)", line)
        if m:
            form_raw = m.group(1).strip()
            strengths = m.group(2).strip()
            strengths = re.sub(r"\s+per\s+[^;,)]+", "", strengths)
            strengths = re.sub(r"\s*;\s*", ", ", strengths)
            # Extract only the last element after > for the form name
            form = form_raw.split(">")[-1].strip() if ">" in form_raw else form_raw
            key = form.lower()
            if key not in seen:
                seen.add(key)
                results.append((_cap(form), strengths))
        else:
            key = line.lower()
            if key not in seen:
                seen.add(key)
                results.append((_cap(line), ""))

    return results


def clean_storage(raw: str) -> list[str]:
    """Parse raw storage text into clean bullet items.

    Handles patterns like:
    'Other information store at 25°C (77°F); excursions permitted between 15°-30°C (59°-86°F)
     avoid high humidity see end flap for expiration date and lot number'
    """
    if not raw or not raw.strip():
        return []

    text = re.sub(r"^other\s+information\s*", "", raw.strip(), flags=re.IGNORECASE)

    parts = re.split(r"[.;]\s*", text)
    cleaned: list[str] = []
    for part in parts:
        part = part.strip()
        if not part or len(part) < 5:
            continue
        if re.search(r"see\s+(end\s+)?flap|expiration\s+date|lot\s+number", part, re.IGNORECASE):
            before_junk = re.split(
                r"\s+see\s+(end\s+)?flap|\s+expiration\s+date|\s+lot\s+number",
                part,
                flags=re.IGNORECASE,
                maxsplit=1,
            )[0].strip()
            if before_junk and len(before_junk) >= 5:
                part = before_junk
            else:
                continue
        part = _cap(part)
        if not part.endswith("."):
            part += "."
        cleaned.append(part)

    return cleaned


def clean_contraindications(raw: str) -> list[str]:
    """Parse raw contraindications text into clean bullet items."""
    if not raw or not raw.strip():
        return []

    text = _strip_section_header(raw.strip(), "CONTRAINDICATIONS")
    text = re.sub(r"^\d+\s*", "", text)

    items = re.split(r"\d+\.\s*|•\s*|–\s*|\n+", text)
    items = [i.strip() for i in items if i.strip() and len(i.strip()) > 3]

    if not items:
        items = re.split(r"[.;]\s+", text)
        items = [i.strip() for i in items if i.strip() and len(i.strip()) > 3]

    seen: set[str] = set()
    cleaned: list[str] = []
    for item in items:
        clean = item.strip(".").strip()
        key = clean.lower()
        if key not in seen and len(key) > 3:
            seen.add(key)
            cleaned.append(_cap(clean))

    return cleaned


def clean_side_effects(raw: str) -> list[str]:
    """Clean raw adverse reactions text into deduplicated items."""
    if not raw or not raw.strip():
        return []

    text = _strip_section_header(raw.strip(), "ADVERSE REACTIONS")
    text = _strip_section_header(text, "SIDE EFFECTS")

    items = re.split(r"\s*[•;–]\s*|\n+", text)
    items = [i.strip() for i in items if i.strip() and len(i.strip()) > 2]

    if len(items) <= 1:
        items = re.split(r"[.,]\s+", text)
        items = [i.strip() for i in items if i.strip() and len(i.strip()) > 3]

    seen: set[str] = set()
    cleaned: list[str] = []
    for item in items:
        key = item.lower().rstrip(".")
        if key not in seen and len(key) > 3:
            seen.add(key)
            cleaned.append(_cap(item.rstrip(".")))

    return cleaned[:15]


def clean_warnings(raw: str, boxed_warning: str = "") -> list[str]:
    """Organize raw warnings into category bullets with optional Black Box Warning."""
    items: list[str] = []

    if boxed_warning:
        bw = re.sub(r"^WARNING:\s*", "", boxed_warning.strip(), flags=re.IGNORECASE)
        items.append(f"⚠ **Black Box Warning:** {_cap(bw)}")

    if not raw or not raw.strip():
        return items

    text = _strip_section_header(raw.strip(), "WARNINGS AND PRECAUTIONS")
    text = _strip_section_header(text, "WARNINGS & PRECAUTIONS")

    parts = re.split(r"\d+\.\s*(?=[A-Z])", text)
    for part in parts:
        part = part.strip()
        if not part or len(part) < 10:
            continue
        m = re.match(r"^([^:]+?)\s*[\(:]", part)
        label = m.group(1).strip() if m else ""
        content = re.sub(r"\s+\(see.*?\)", "", (part[len(label) + 1:] if label else part), flags=re.IGNORECASE).strip()
        if label:
            items.append(f"- **{_cap(label)}:** {_cap(content[:500])}")
        else:
            items.append(f"- {_cap(part[:500])}")

    if not items:
        items.append(f"- {_cap(text[:500])}")

    return items


def clean_pregnancy(raw: str) -> str:
    """Extract a concise pregnancy summary from raw DailyMed text."""
    if not raw or not raw.strip():
        return ""

    text = re.sub(r"^\d+\.?\s*\d*\s*", "", raw.strip())
    text = re.sub(r"(pregnancy\s*|risk\s+summary\s*)", "", text, flags=re.IGNORECASE)

    sentences = re.split(r"(?<=[.!])\s+", text)
    meaningful: list[str] = []
    for s in sentences[:6]:
        s = s.strip()
        if not s or len(s) < 20:
            continue
        if re.match(r"^(data|animal|the\s+estimated|in\s+the\s+u\.?s\.?)", s, re.IGNORECASE):
            continue
        meaningful.append(s)

    return " ".join(meaningful[:3]) if meaningful else ""


def make_summary(name: str, indications: list[str], moa: str, max_dose: str) -> str:
    """Generate a template-based Quick Summary from available data."""
    parts: list[str] = []
    if indications:
        top = indications[:3]
        parts.append(f"{_cap(name)} is indicated for {top[0].lower()}")
        if len(top) == 2:
            parts[-1] += f" and {top[1].lower()}"
        elif len(top) >= 3:
            parts[-1] += f", {top[1].lower()}, and {top[2].lower()}"
        parts[-1] += "."
    if moa:
        first = moa.split(".")[0].strip().lower()
        parts.append(f"It acts through {first}.")
    else:
        parts.append("Its pharmacological activity provides analgesic and antipyretic effects.")
    if max_dose:
        parts.append(f"{_cap(max_dose)}.")
    return " ".join(parts)


def extract_admin_notes(raw: str) -> list[str]:
    """Extract clean administration guidance from raw text."""
    if not raw or not raw.strip():
        return []
    cleaned: list[str] = []
    for p in re.split(r"[.;]\s+", raw.strip()):
        p = p.strip()
        if not p or len(p) < 5:
            continue
        if re.search(r"see\s+(end\s+)?flap|section|prescribing", p, re.IGNORECASE):
            continue
        p = _cap(p)
        if not p.endswith("."):
            p += "."
        cleaned.append(p)
    return cleaned[:5]
