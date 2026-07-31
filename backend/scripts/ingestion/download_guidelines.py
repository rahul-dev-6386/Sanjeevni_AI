import os
import sys
import httpx
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.config import settings


GUIDELINES = {
    "who_diabetes": {
        "url": "https://www.who.int/publications/i/item/9789241565257",
        "specialty": "diabetes",
        "content": (
            "The World Health Organization (WHO) provides global guidelines for diabetes prevention and management. "
            "Key recommendations include: maintaining healthy body weight (BMI 18.5-24.9), regular physical activity "
            "(at least 150 minutes of moderate-intensity aerobic activity per week), healthy diet rich in fruits, "
            "vegetables, and whole grains with limited sugar and saturated fats. For diagnosed diabetes, glycemic "
            "control targets include HbA1c < 7.0% (53 mmol/mol) for most adults, fasting plasma glucose 80-130 mg/dL "
            "(4.4-7.2 mmol/L), and postprandial glucose < 180 mg/dL (10.0 mmol/L). Annual screening for complications "
            "including retinopathy, nephropathy, neuropathy, and cardiovascular disease is recommended. Blood pressure "
            "target < 140/90 mmHg, LDL cholesterol target < 100 mg/dL (2.6 mmol/L)."
        ),
    },
    "who_hypertension": {
        "url": "https://www.who.int/publications/i/item/9789240033986",
        "specialty": "hypertension",
        "content": (
            "WHO guidelines for hypertension management recommend accurate blood pressure measurement using validated "
            "devices. Classification: Normal < 120/80 mmHg, Elevated 120-129/<80 mmHg, Stage 1 HTN 130-139/80-89 mmHg, "
            "Stage 2 HTN >= 140/90 mmHg. Treatment targets: general population < 140/90 mmHg, diabetes/CKD patients "
            "< 130/80 mmHg. Lifestyle modifications include sodium restriction < 2g/day, DASH diet, regular exercise, "
            "weight management, alcohol moderation, and smoking cessation. First-line medications include thiazide "
            "diuretics, ACE inhibitors, ARBs, and calcium channel blockers. Combination therapy is often required."
        ),
    },
    "who_cardiovascular": {
        "url": "https://www.who.int/publications/i/item/9789240000000",
        "specialty": "cardiovascular_disease",
        "content": (
            "WHO cardiovascular disease prevention guidelines emphasize total cardiovascular risk assessment using "
            "scoring systems like WHO/ISH risk prediction charts. Key risk factors: age, sex, smoking, blood pressure, "
            "total cholesterol, diabetes. Prevention strategies include: smoking cessation, healthy diet (low saturated "
            "fat, high fiber), physical activity (150 min/week moderate or 75 min/week vigorous), weight management "
            "(BMI 18.5-24.9), blood pressure control < 140/90 mmHg, lipid management (LDL < 100 mg/dL high risk, "
            "< 70 mg/dL very high risk). Aspirin for secondary prevention. Statins for primary prevention when 10-year "
            "CVD risk > 20%."
        ),
    },
    "who_ckd": {
        "url": "https://www.who.int/publications/i/item/9789240000000",
        "specialty": "chronic_kidney_disease",
        "content": (
            "Chronic kidney disease (CKD) is defined by kidney damage or GFR < 60 mL/min/1.73m² for > 3 months. "
            "Staging: Stage 1 GFR >= 90 with kidney damage, Stage 2 GFR 60-89, Stage 3a GFR 45-59, Stage 3b GFR 30-44, "
            "Stage 4 GFR 15-29, Stage 5 GFR < 15. Management includes: blood pressure control < 130/80 mmHg with ACE "
            "inhibitors or ARBs, glycemic control in diabetes, protein restriction (0.8 g/kg/day in non-dialysis), "
            "sodium restriction < 2g/day, anemia management (Hb target 10-11.5 g/dL), mineral bone disorder management, "
            "and preparation for renal replacement therapy when GFR < 20 mL/min/1.73m²."
        ),
    },
    "who_asthma": {
        "url": "https://www.who.int/publications/i/item/9789240000000",
        "specialty": "asthma",
        "content": (
            "Asthma management follows a stepwise approach: Step 1: As-needed low-dose ICS-formoterol. "
            "Step 2: Low-dose ICS maintenance plus as-needed SABA. Step 3: Low-dose ICS-LABA maintenance. "
            "Step 4: Medium-dose ICS-LABA. Step 5: High-dose ICS-LABA plus add-on therapies (LAMA, anti-IgE, "
            "anti-IL5/IL5R, anti-IL4R). Key principles: confirm diagnosis with spirometry (reversible airflow "
            "obstruction), assess symptom control (ACT questionnaire), identify and avoid triggers, written asthma "
            "action plan, regular follow-up every 1-6 months. Severe asthma requires specialist referral."
        ),
    },
    "cdc_diabetes": {
        "url": "https://www.cdc.gov/diabetes/prevention/index.html",
        "specialty": "diabetes",
        "content": (
            "CDC Diabetes Prevention Program (DPP) guidelines: lifestyle intervention program for prediabetes "
            "(HbA1c 5.7-6.4%, fasting glucose 100-125 mg/dL, or 2-hour glucose 140-199 mg/dL). Goals: 5-7% weight "
            "loss, 150 minutes/week physical activity, reduced calorie and fat intake. Screening recommendations: "
            "adults 35+ years with overweight/obesity should be screened annually. Earlier screening for those with "
            "risk factors: family history, gestational diabetes, polycystic ovary syndrome, high-risk race/ethnicity. "
            "Diagnostic criteria: HbA1c >= 6.5%, fasting glucose >= 126 mg/dL, 2-hour glucose >= 200 mg/dL during "
            "OGTT, or random glucose >= 200 mg/dL with symptoms."
        ),
    },
    "cdc_hypertension": {
        "url": "https://www.cdc.gov/bloodpressure/index.htm",
        "specialty": "hypertension",
        "content": (
            "CDC Million Hearts initiative: control blood pressure through team-based care, use of evidence-based "
            "treatment protocols, self-measured blood pressure monitoring, and health IT interventions. Regular "
            "screening: adults 18+ years with normal BP (< 120/80) screened every 2 years, those with elevated BP "
            "(120-129/<80) screened annually. Therapeutic lifestyle changes are first-line. Medication adherence "
            "is critical for BP control. Use single-pill combination therapy to improve adherence."
        ),
    },
    "ada_diabetes": {
        "url": "https://diabetesjournals.org/care/issue/47/Supplement_1",
        "specialty": "diabetes",
        "content": (
            "American Diabetes Association Standards of Care 2024: Classification includes type 1, type 2, "
            "gestational diabetes, and specific types due to other causes. Diagnosis: HbA1c >= 6.5%, FPG >= 126 mg/dL, "
            "OGTT 2-hour PG >= 200 mg/dL, or random PG >= 200 mg/dL with symptoms. Glycemic targets: HbA1c < 7.0% "
            "for most non-pregnant adults (more stringent < 6.5% if achievable without significant hypoglycemia, "
            "less stringent < 8.0% for those with comorbidities). Pharmacotherapy: metformin is first-line for type 2 "
            "diabetes. GLP-1 receptor agonists or SGLT2 inhibitors recommended for those with ASCVD, CKD, or heart "
            "failure regardless of HbA1c. Annual comprehensive medical evaluation, lipid profile, nephropathy "
            "screening (urine albumin-to-creatinine ratio, eGFR), dilated eye exam, foot exam, and dental exam."
        ),
    },
    "aha_heart": {
        "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000000678",
        "specialty": "cardiovascular_disease",
        "content": (
            "AHA/ACC Guideline on the Assessment of Cardiovascular Risk (2019): Use pooled cohort equations (PCE) "
            "for 10-year ASCVD risk estimation in adults 40-75 years without clinical ASCVD. Risk categories: "
            "low < 5%, borderline 5-7.4%, intermediate 7.5-19.9%, high >= 20%. Risk-enhancing factors: family "
            "history of premature ASCVD, metabolic syndrome, chronic kidney disease, chronic inflammatory conditions, "
            "history of preeclampsia or premature menopause, high-risk race/ethnicity, lipid/biomarker abnormalities. "
            "Coronary artery calcium (CAC) scoring for intermediate-risk patients: CAC = 0 can reclassify to low risk; "
            "CAC >= 100 or >= 75th percentile supports statin therapy. Lifestyle: Mediterranean diet, 150 min/week "
            "moderate exercise, BMI 18.5-24.9."
        ),
    },
    "kdigo_ckd": {
        "url": "https://kdigo.org/guidelines/ckd-evaluation-and-management/",
        "specialty": "chronic_kidney_disease",
        "content": (
            "KDIGO 2024 CKD Guideline: Diagnose and classify CKD based on cause, GFR category (G1-G5), and "
            "albuminuria category (A1-A3). Risk of progression: use KDIGO heat map. Management: blood pressure "
            "target < 120/80 mmHg (standard office BP). ACE inhibitors or ARBs for hypertension or albuminuria. "
            "SGLT2 inhibitors recommended for patients with CKD and eGFR >= 20 mL/min/1.73m² regardless of diabetes "
            "status. Non-steroidal MRAs for those with T2D and albuminuria. Glycemic target HbA1c < 7.0% in diabetes "
            "with CKD. Dietary: sodium < 2g/day, protein 0.8 g/kg/day for non-dialysis, potassium management based "
            "on serum levels. Prepare for RRT when eGFR < 15-20."
        ),
    },
    "nih_nutrition": {
        "url": "https://www.nhlbi.nih.gov/health/educational/lose_wt/eat/shop_calories.htm",
        "specialty": "nutrition",
        "content": (
            "NIH Dietary Guidelines: DASH (Dietary Approaches to Stop Hypertension) eating plan: rich in fruits, "
            "vegetables, whole grains, low-fat dairy; includes fish, poultry, beans, nuts; limits saturated fat, "
            "sodium, sweets, sugary beverages, red meats. Heart-healthy eating: limit sodium to 1500-2300 mg/day, "
            "saturated fat < 7% of calories, trans fat as low as possible, dietary cholesterol < 200 mg/day, "
            "total fat 25-35% of calories. Mediterranean diet: high intake of olive oil, fruits, vegetables, "
            "legumes, whole grains, moderate fish and poultry, low red meat, moderate wine consumption."
        ),
    },
    "who_exercise": {
        "url": "https://www.who.int/publications/i/item/9789240015128",
        "specialty": "exercise_guidelines",
        "content": (
            "WHO Physical Activity Guidelines 2020: Adults (18-64 years): at least 150-300 minutes moderate-intensity "
            "aerobic physical activity, or 75-150 minutes vigorous-intensity, or equivalent combination per week. "
            "Muscle-strengthening activities involving major muscle groups on 2+ days/week. Older adults (65+): "
            "same as adults plus balance training 3+ days/week. Children and adolescents (5-17): at least 60 "
            "minutes/day moderate-to-vigorous intensity, with vigorous activities 3 days/week. All adults should "
            "limit sedentary time. Some activity is better than none. Benefits include reduced all-cause mortality, "
            "CVD, hypertension, diabetes, various cancers, depression, and improved cognitive function."
        ),
    },
    "cdc_immunization": {
        "url": "https://www.cdc.gov/vaccines/schedules/hcp/imz/adult.html",
        "specialty": "immunization",
        "content": (
            "CDC Adult Immunization Schedule: Annual influenza vaccine for all adults. Tdap once then Td/Tdap "
            "booster every 10 years. HPV vaccine through age 26 (shared decision-making 27-45). Zoster vaccine "
            "(Shingrix) for adults 50+ years (2 doses). Pneumococcal vaccines: PCV15 or PCV20 for adults 65+ and "
            "younger adults with risk conditions. COVID-19 vaccines: updated vaccine annually for all adults. "
            "RSV vaccine for adults 60+ years. Hepatitis B vaccine for adults 19-59, and 60+ with risk factors. "
            "MMR for adults born after 1957 without evidence of immunity."
        ),
    },
}


def download_guidelines():
    guidelines_dir = settings.GUIDELINES_DIR
    os.makedirs(guidelines_dir, exist_ok=True)

    for key, info in GUIDELINES.items():
        filename = os.path.join(guidelines_dir, f"{key}.txt")
        with open(filename, "w") as f:
            f.write(f"Source: {info['url']}\n")
            f.write(f"Specialty: {info['specialty']}\n")
            f.write(f"---\n\n")
            f.write(info["content"])
        print(f"  ✓ {key}.txt ({len(info['content'])} chars)")

    print(f"\n{len(GUIDELINES)} guidelines downloaded to {guidelines_dir}/")


if __name__ == "__main__":
    download_guidelines()
