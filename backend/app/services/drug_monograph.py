from typing import Any

from app.services.drug_text_cleaner import (
    clean_indications,
    parse_dosage,
    clean_formulations,
    clean_storage,
    clean_contraindications,
    clean_side_effects,
    clean_warnings,
    clean_pregnancy,
    extract_admin_notes,
    make_summary,
    NOT_AVAILABLE,
)


def _s(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val).strip()


def build_drug_monograph(drug: dict[str, Any]) -> str:
    parts: list[str] = []

    name = drug.get("generic_name", "Unknown Drug")
    brand_names = drug.get("brand_names") or []
    if isinstance(brand_names, str):
        brand_names = [brand_names] if brand_names else []
    legacy_brand = drug.get("brand_name", "")
    if legacy_brand and legacy_brand not in brand_names:
        brand_names.insert(0, legacy_brand)

    drug_class = drug.get("drug_class", "")
    pharmacologic_class = drug.get("pharmacologic_class", "")
    therapeutic_class = drug.get("therapeutic_class", "")
    display_class = drug_class or pharmacologic_class or therapeutic_class or ""

    parts.append(f"# 💊 {name}\n")
    parts.append(f"> **Generic Name:** {name}")
    if brand_names:
        parts.append(f"> **Brand Names:** {', '.join(brand_names[:5])}")
    if display_class:
        parts.append(f"> **Drug Class:** {display_class}")
    if drug.get("therapeutic_class"):
        parts.append(f"> **Therapeutic Class:** {drug['therapeutic_class']}")
    if drug.get("atc_code"):
        parts.append(f"> **ATC Classification:** {drug['atc_code']}")
    rx_status = drug.get("prescription_status", "Rx" if drug.get("prescription_required") else "")
    if not rx_status:
        for field in ("prescription_required", "is_prescription", "rx_only"):
            v = drug.get(field)
            if v is True:
                rx_status = "Rx"
                break
            if v is False:
                rx_status = "OTC"
                break
    if not rx_status:
        rx_status = "Rx / OTC"
    parts.append(f"> **Prescription Status:** {rx_status}")
    parts.append("> **Evidence Sources:** DailyMed • OpenFDA • RxNorm")
    parts.append("")
    parts.append("---\n")

    # Pre-clean fields
    indications = clean_indications(drug.get("indications", ""))
    moa = _s(drug.get("mechanism_of_action"))
    dose_info = parse_dosage(drug.get("adult_dose", ""))
    formulations = clean_formulations(drug.get("dose_forms"))
    contra_items = clean_contraindications(drug.get("contraindications", ""))
    common_se = clean_side_effects(drug.get("common_side_effects", ""))
    serious_se = clean_side_effects(drug.get("serious_side_effects", ""))
    warnings = clean_warnings(_s(drug.get("warnings")), _s(drug.get("boxed_warning")))
    storage_items = clean_storage(drug.get("storage_instructions", ""))
    admin_notes = extract_admin_notes(_s(drug.get("administration")))
    preg = clean_pregnancy(_s(drug.get("pregnancy")))
    lact = clean_pregnancy(_s(drug.get("breastfeeding")))
    max_dose = dose_info.get("max_daily", "")

    # --- Quick Summary ---
    parts.append("## Quick Summary\n")
    parts.append(make_summary(name, indications, moa, max_dose))
    parts.append("")

    # --- Quick Facts ---
    qf_route = _s(drug.get("route_of_administration")) or _s(drug.get("administration"))
    qf_forms = ", ".join(f[0] for f in formulations) if formulations else ""
    qf_hl = _s(drug.get("half_life"))
    qf_pb = _s(drug.get("protein_binding"))
    qf_ba = _s(drug.get("bioavailability"))
    qf_met = _s(drug.get("metabolism"))
    qf_elim = _s(drug.get("elimination"))

    quick_facts = [
        ("Generic Name", name),
        ("Brand Names", ", ".join(brand_names[:5]) if brand_names else NOT_AVAILABLE),
        ("Drug Class", display_class or NOT_AVAILABLE),
        ("Therapeutic Class", therapeutic_class or NOT_AVAILABLE),
        ("Mechanism", (moa.split(".")[0] if moa else NOT_AVAILABLE)),
        ("Route", qf_route or NOT_AVAILABLE),
        ("Available Forms", qf_forms or NOT_AVAILABLE),
        ("Half-life", qf_hl or NOT_AVAILABLE),
        ("Protein Binding", qf_pb or NOT_AVAILABLE),
        ("Bioavailability", qf_ba or NOT_AVAILABLE),
        ("Metabolism", qf_met or NOT_AVAILABLE),
        ("Elimination", qf_elim or NOT_AVAILABLE),
        ("Prescription Status", rx_status),
    ]

    parts.append("## Quick Facts\n")
    parts.append("| Property | Value |")
    parts.append("|----------|-------|")
    for prop, val in quick_facts:
        parts.append(f"| {prop} | {val} |")
    parts.append("")

    # --- Approved Indications ---
    if indications:
        parts.append("## Approved Indications\n")
        for item in indications:
            parts.append(f"- {item}")
        parts.append("")
    else:
        parts.append(f"## Approved Indications\n{NOT_AVAILABLE}\n")

    # --- Mechanism of Action ---
    if moa:
        parts.append("## Mechanism of Action\n")
        parts.append(moa)
        parts.append("")
    else:
        parts.append(f"## Mechanism of Action\n{NOT_AVAILABLE}\n")

    # --- Dosage ---
    dose_lines: list[str] = []
    if dose_info.get("adult_dose"):
        dose_lines.append("### Adults\n")
        dose_lines.append("| Recommendation | Dose |")
        dose_lines.append("|---------------|------|")
        dose_lines.append(f"| Standard dose | {dose_info['adult_dose']} |")
        if dose_info.get("max_daily"):
            dose_lines.append(f"| Maximum daily | {dose_info['max_daily']} |")
        if dose_info.get("max_duration"):
            dose_lines.append(f"| Duration | {dose_info['max_duration']} |")
    else:
        adult_dose_raw = _s(drug.get("adult_dose"))
        if adult_dose_raw:
            dose_lines.append(f"### Adults\n- {adult_dose_raw}")
    if dose_info.get("pediatric"):
        dose_lines.append(f"### Children\n- {dose_info['pediatric']}")
    elif _s(drug.get("pediatric_dose")):
        dose_lines.append(f"### Children\n- {_s(drug.get('pediatric_dose'))}")
    if _s(drug.get("geriatric_dose")):
        dose_lines.append(f"### Geriatric\n- {_s(drug.get('geriatric_dose'))}")
    if _s(drug.get("renal_dose_adjustment")):
        dose_lines.append(f"### Renal Impairment\n- {_s(drug.get('renal_dose_adjustment'))}")
    if _s(drug.get("hepatic_dose_adjustment")):
        dose_lines.append(f"### Hepatic Impairment\n- {_s(drug.get('hepatic_dose_adjustment'))}")
    if _s(drug.get("maximum_dose")) and not dose_info.get("max_daily"):
        dose_lines.append(f"- **Maximum dose:** {_s(drug.get('maximum_dose'))}")

    if dose_lines:
        parts.append("## Dosage\n")
        parts.append("\n".join(dose_lines))
        parts.append("")

    # --- Available Formulations ---
    if formulations:
        parts.append("## Available Formulations\n")
        parts.append("| Formulation | Strengths |")
        parts.append("|-------------|-----------|")
        for form, strength in formulations:
            parts.append(f"| {form} | {strength} |")
        parts.append("")

    # --- Administration ---
    if admin_notes or _s(drug.get("patient_instructions")):
        parts.append("## Administration\n")
        if admin_notes:
            for note in admin_notes:
                parts.append(f"- {note}")
        if _s(drug.get("missed_dose_instructions")):
            parts.append(f"- **Missed dose:** {_s(drug.get('missed_dose_instructions'))}")
        parts.append("")

    # --- Contraindications ---
    if contra_items:
        parts.append("## Contraindications\n")
        for item in contra_items:
            parts.append(f"- {item}")
        parts.append("")

    # --- Warnings & Precautions ---
    if warnings:
        parts.append("## Warnings & Precautions\n")
        for w in warnings:
            parts.append(w)
        parts.append("")

    # --- Side Effects ---
    if common_se or serious_se:
        parts.append("## Side Effects\n")
        if common_se:
            parts.append("### Common\n")
            for item in common_se:
                parts.append(f"- {item}")
            parts.append("")
        if serious_se:
            parts.append("### Serious\n")
            for item in serious_se:
                parts.append(f"- {item}")
            parts.append("")

    # --- Drug Interactions ---
    di = drug.get("drug_interactions")
    food = drug.get("food_interactions")
    alcohol = drug.get("alcohol_interactions")
    if di or food or alcohol:
        parts.append("## Drug Interactions\n")
        parts.append("| Drug / Substance | Clinical Effect |")
        parts.append("|------------------|-----------------|")
        if di:
            if ";" in str(di) or "\n" in str(di):
                for item in di.replace(";", "\n").split("\n"):
                    item = item.strip()
                    if ":" in item:
                        d, e = item.split(":", 1)
                        parts.append(f"| {d.strip()} | {e.strip()} |")
                    elif item:
                        parts.append(f"| {item} | See prescribing information |")
            else:
                parts.append(f"| See labeling | {di} |")
        if food:
            parts.append(f"| Food | {food} |")
        if alcohol:
            parts.append(f"| Alcohol | {alcohol} |")
        parts.append("")

    # --- Monitoring ---
    monitoring_parts: list[str] = []
    if _s(drug.get("monitoring")):
        monitoring_parts.append(_s(drug.get("monitoring")))
    if _s(drug.get("required_monitoring")):
        monitoring_parts.append(_s(drug.get("required_monitoring")))
    if _s(drug.get("laboratory_tests")):
        monitoring_parts.append(_s(drug.get("laboratory_tests")))
    if monitoring_parts:
        parts.append("## Monitoring\n")
        for m in monitoring_parts:
            parts.append(f"- {m}")
        parts.append("")

    # --- Pregnancy & Lactation ---
    if preg or lact:
        parts.append("## Pregnancy & Lactation\n")
    if preg:
        parts.append(f"### Pregnancy\n{preg}\n")
    if lact:
        parts.append(f"### Lactation\n{lact}\n")
    if not preg and not lact:
        if _s(drug.get("pregnancy")) or _s(drug.get("breastfeeding")):
            parts.append("## Pregnancy & Lactation\n")
            if _s(drug.get("pregnancy")):
                parts.append(f"### Pregnancy\n{_s(drug.get('pregnancy'))}\n")
            if _s(drug.get("breastfeeding")):
                parts.append(f"### Lactation\n{_s(drug.get('breastfeeding'))}\n")

    # --- Overdose ---
    tox_parts: list[str] = []
    if _s(drug.get("toxicity")):
        tox_parts.append(f"- **Toxicity:** {_s(drug.get('toxicity'))}")
    if _s(drug.get("antidote")):
        tox_parts.append(f"- **Antidote:** {_s(drug.get('antidote'))}")
    if _s(drug.get("poisoning_management")):
        tox_parts.append(f"- **Management:** {_s(drug.get('poisoning_management'))}")
    if tox_parts:
        parts.append("## Overdose\n")
        parts.append("\n".join(tox_parts))
        parts.append("")

    # --- Storage ---
    if storage_items:
        parts.append("## Storage\n")
        for item in storage_items:
            parts.append(f"- {item}")
        parts.append("")

    # --- Patient Counselling ---
    counselling: list[str] = []
    if _s(drug.get("patient_instructions")):
        counselling.append(_s(drug.get("patient_instructions")))
    if _s(drug.get("missed_dose_instructions")):
        counselling.append(f"- **Missed dose:** {_s(drug.get('missed_dose_instructions'))}")
    if _s(drug.get("overdose_instructions")):
        counselling.append(f"- **Overdose:** {_s(drug.get('overdose_instructions'))}")
    if counselling:
        parts.append("## Patient Counselling\n")
        parts.append("\n".join(counselling))
        parts.append("")

    # --- Clinical Pearls ---
    pearls: list[str] = []
    if _s(drug.get("clinical_pearls")):
        pearls.append(_s(drug.get("clinical_pearls")))
    if _s(drug.get("high_yield_points")):
        pearls.append(_s(drug.get("high_yield_points")))
    if pearls:
        parts.append("## Clinical Pearls\n")
        for p in pearls:
            parts.append(f"- {p}")
        parts.append("")

    # --- References ---
    refs = ["DailyMed", "OpenFDA", "RxNorm"]
    if _s(drug.get("references")):
        refs.append(_s(drug.get("references")))
    parts.append("## References\n")
    for r in refs:
        parts.append(f"- {r}")
    parts.append("")

    # --- Evidence Quality ---
    parts.append("## Evidence Quality\n")
    parts.append("| Source | Status |")
    parts.append("|--------|--------|")
    parts.append("| PostgreSQL Database | ✅ Used |")
    parts.append("| DailyMed | ✅ Used |")
    parts.append("| OpenFDA | ✅ Used |")
    parts.append("| Medical Textbooks | ⚪ Not retrieved |")
    parts.append("| AI Summary | ⚪ Not generated |")
    parts.append("")

    # --- Disclaimer ---
    parts.append("## Disclaimer\n")
    parts.append(
        "> This information is intended for educational purposes only. "
        "It should not replace professional medical advice, diagnosis, or treatment. "
        "Always consult a qualified healthcare professional before starting, stopping, "
        "or changing any medication.\n"
    )

    return "\n".join(parts)


def build_drug_not_found_markdown(drug_name: str, similar_drugs: list[str] = None) -> str:
    parts = []
    parts.append("# Drug Not Found\n")
    parts.append("> **Search Term:** " + drug_name + "\n")
    parts.append("---\n")
    parts.append("## Search Result\n")
    parts.append("No verified information was found for this medicine in the indexed medical references.\n")
    parts.append("Possible reasons:\n")
    parts.append("- Brand name not indexed")
    parts.append("- Regional brand")
    parts.append("- Spelling variation")
    parts.append("- Newly marketed medicine\n")

    if similar_drugs:
        parts.append("## Did You Mean?\n")
        for d in similar_drugs[:5]:
            parts.append(f"- {d}")
        parts.append("")

    parts.append("## Recommended Search\n")
    parts.append("Please search using:\n")
    parts.append("- Generic name")
    parts.append("- International Nonproprietary Name (INN)")
    parts.append("- Alternative brand name\n")

    parts.append("## Sources Checked\n")
    parts.append("- PostgreSQL Drug Database")
    parts.append("- DailyMed")
    parts.append("- OpenFDA")
    parts.append("- RxNorm")
    parts.append("- Medical Textbooks\n")

    return "\n".join(parts)
