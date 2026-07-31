import re
import logging

logger = logging.getLogger("medical_library")

MEDICAL_SYNONYMS: dict[str, str] = {
    # Abbreviations → full forms
    "htn": "hypertension high blood pressure",
    "dm": "diabetes mellitus diabetes",
    "ckd": "chronic kidney disease renal failure",
    "mi": "myocardial infarction heart attack",
    "cva": "cerebrovascular accident stroke",
    "uti": "urinary tract infection",
    "copd": "chronic obstructive pulmonary disease",
    "cbc": "complete blood count",
    "bp": "blood pressure",
    "hr": "heart rate",
    "bmi": "body mass index",
    "ecg": "electrocardiogram ekg",
    "mri": "magnetic resonance imaging",
    "ct": "computed tomography cat scan",
    "usg": "ultrasound ultrasonography",
    "hb": "hemoglobin",
    "wbc": "white blood cell leukocyte",
    "rbc": "red blood cell erythrocyte",
    "hdl": "high density lipoprotein",
    "ldl": "low density lipoprotein",
    "t2dm": "type 2 diabetes mellitus",
    "nsaid": "nonsteroidal anti-inflammatory drug",
    "acei": "ace inhibitor angiotensin converting enzyme inhibitor",
    "arb": "angiotensin receptor blocker",
    "ccb": "calcium channel blocker",
    "ppi": "proton pump inhibitor",
    "ssri": "selective serotonin reuptake inhibitor",
    "snri": "serotonin norepinephrine reuptake inhibitor",
    "cvd": "cardiovascular disease",
    "chf": "congestive heart failure heart failure",
    "cad": "coronary artery disease",
    "pvd": "peripheral vascular disease",
    "dvt": "deep vein thrombosis",
    "pe": "pulmonary embolism",
    "gerd": "gastroesophageal reflux disease",
    "ibs": "irritable bowel syndrome",
    "ibd": "inflammatory bowel disease",
    "ra": "rheumatoid arthritis",
    "oa": "osteoarthritis",
    "bph": "benign prostatic hyperplasia",
    "osa": "obstructive sleep apnea",
    "nafld": "non alcoholic fatty liver disease",
    "tb": "tuberculosis",
    "hiv": "human immunodeficiency virus",
    "aids": "acquired immunodeficiency syndrome",
    "sob": "shortness of breath dyspnea",
    "doe": "dyspnea on exertion",
    "pnd": "paroxysmal nocturnal dyspnea",
    "jvd": "jugular venous distension",
    "npo": "nothing by mouth nil per os",
    "prn": "as needed pro re nata",
    "bid": "twice daily",
    "tid": "three times daily",
    "qid": "four times daily",
    "qhs": "at bedtime",
    "qam": "every morning",
    "po": "by mouth orally",
    "iv": "intravenous",
    "im": "intramuscular",
    "sc": "subcutaneous",
    "perrla": "pupils equal round reactive to light accommodation",

    # Synonyms → related terms
    "myocardial infarction": "heart attack mi",
    "cerebrovascular accident": "stroke cva",
    "urinary tract infection": "uti",
    "hyperlipidemia": "high cholesterol",
    "hypoglycemia": "low blood sugar",
    "hyperglycemia": "high blood sugar",
    "edema": "swelling fluid retention",
    "dyspnea": "shortness of breath breathing difficulty",
    "nausea": "feeling sick",
    "emesis": "vomiting throwing up",
    "pyrexia": "fever temperature",
    "cephalalgia": "headache",
    "pruritus": "itching",
    "erythema": "redness",
    "cyanosis": "bluish discoloration",
    "jaundice": "icterus yellowing",
    "hemoptysis": "coughing blood",
    "hematemesis": "vomiting blood",
    "hematuria": "blood in urine",
    "melena": "blood in stool black tarry stool",
    "syncope": "fainting passing out",
    "vertigo": "dizziness spinning sensation",
    "paresthesia": "tingling numbness",
    "myalgia": "muscle pain",
    "arthralgia": "joint pain",
    "neuralgia": "nerve pain",
    "anuria": "no urine output",
    "oliguria": "decreased urine output",
    "polyuria": "excessive urination",
    "dysuria": "painful urination",
    "nocturia": "nighttime urination",
    "polyphagia": "excessive hunger",
    "polydipsia": "excessive thirst",
    "anorexia": "loss of appetite",
    "dysphagia": "difficulty swallowing",
    "odynophagia": "painful swallowing",
    "hematoma": "bruise blood collection",
    "petechiae": "small red dots",
    "ecchymosis": "bruising",
    "hypertension": "high blood pressure htn",
    "diabetes": "diabetes mellitus dm",
    "kidney failure": "renal failure ckd chronic kidney disease",
    "heart attack": "myocardial infarction mi",
    "stroke": "cerebrovascular accident cva",
    "high cholesterol": "hyperlipidemia",
    "weight loss": "unintentional weight loss",
    "difficulty breathing": "dyspnea shortness of breath",
    "chest pain": "angina",
    "palpitations": "heart racing irregular heartbeat",
    "coughing blood": "hemoptysis",
    "vomiting blood": "hematemesis",
    "blood in urine": "hematuria",
    "blood in stool": "melena hematochezia",
    "black stool": "melena",
    "fainting": "syncope passing out",
    "dizziness": "vertigo lightheadedness",
    "tingling": "paresthesia numbness",
    "muscle pain": "myalgia",
    "joint pain": "arthralgia",
    "nerve pain": "neuralgia neuropathic pain",
    "difficulty swallowing": "dysphagia",
    "loss of appetite": "anorexia",
    "excessive thirst": "polydipsia",
    "excessive urination": "polyuria",
    "painful urination": "dysuria",
    "fever": "pyrexia temperature",
    "itching": "pruritus",
    "redness": "erythema",
    "bruising": "ecchymosis hematoma",
    "yellow skin": "jaundice icterus",
    "swelling": "edema fluid retention",
    "shortness of breath": "dyspnea sob",

    # Hematology / Oncology
    "blood cancer": "leukemia lymphoma myeloma hematological malignancy",
    "leukemia": "blood cancer hematological malignancy acute leukemia chronic leukemia",
    "lymphoma": "hodgkin lymphoma non-hodgkin lymphoma blood cancer",
    "myeloma": "multiple myeloma plasma cell malignancy",
    "anemia": "low hemoglobin low haemoglobin low hb iron deficiency",
    "low hemoglobin": "anemia low hb iron deficiency",
    "low haemoglobin": "anemia low hb iron deficiency",
    "thrombocytopenia": "low platelets bleeding tendency",
    "pancytopenia": "aplastic anemia bone marrow failure",
    "neutropenia": "low white blood cells immunocompromised",
    "polycythemia": "high red blood cells high hemoglobin",
    "cml": "chronic myeloid leukemia chronic myelogenous leukemia",
    "aml": "acute myeloid leukemia",
    "all": "acute lymphoblastic leukemia",
    "cll": "chronic lymphocytic leukemia",
    "dl bcl": "diffuse large b cell lymphoma",
    "nhl": "non-hodgkin lymphoma",
    "hl": "hodgkin lymphoma",
    "mm": "multiple myeloma",
    "itp": "immune thrombocytopenic purpura low platelets",
    "dic": "disseminated intravascular coagulation",
    "von willebrand": "bleeding disorder coagulation",
    "hemophilia": "bleeding disorder clotting factor deficiency",
    "haemophilia": "bleeding disorder clotting factor deficiency",
    "sickle cell": "sickle cell anemia sickle cell disease hemolysis",
    "thalassemia": "haemoglobinopathy microcytic anemia",
    "bone marrow failure": "aplastic anemia pancytopenia",
}


def expand_query(query: str) -> str:
    query_lower = query.lower().strip()
    if not query_lower:
        return query

    expanded_terms = []
    tokens = query_lower.split()
    used = set()
    i = 0

    while i < len(tokens):
        matched = False
        for n in range(min(4, len(tokens) - i), 0, -1):
            phrase = " ".join(tokens[i : i + n])
            if phrase in MEDICAL_SYNONYMS and phrase not in used:
                expanded_terms.append(tokens[i : i + n])
                used.add(phrase)
                extra = MEDICAL_SYNONYMS[phrase]
                if extra not in used:
                    expanded_terms.append(extra.split())
                    used.add(extra)
                i += n
                matched = True
                break

        if not matched:
            token = tokens[i]
            if token not in used:
                expanded_terms.append([token])
                if token in MEDICAL_SYNONYMS:
                    extra = MEDICAL_SYNONYMS[token]
                    if extra not in used:
                        expanded_terms.append(extra.split())
                        used.add(extra)
                used.add(token)
            i += 1

    flat = []
    seen_tokens: set[str] = set()
    for group in expanded_terms:
        for t in group:
            if t not in seen_tokens:
                flat.append(t)
                seen_tokens.add(t)

    result = " ".join(flat)
    if result != query_lower:
        logger.debug(f"Query expanded: '{query}' -> '{result}'")
    return result
