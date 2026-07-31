"""
Seed drug interaction data from curated clinical knowledge.
Populates the DrugInteraction table with well-known drug-drug interactions.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.database import SessionLocal
from app.services.drug_service import DrugService

INTERACTIONS = [
    # Anticoagulants + NSAIDs → bleeding
    {
        "drug_a": "warfarin",
        "drug_b": "aspirin",
        "severity": "major",
        "mechanism": "Additive inhibition of platelet aggregation and anticoagulation. Aspirin irreversibly inhibits COX-1, reducing thromboxane A2 production and impairing platelet function.",
        "clinical_effect": "Significantly increased risk of major bleeding events including gastrointestinal hemorrhage and intracranial bleeding.",
        "management": "Avoid concurrent use if possible. If unavoidable, monitor INR frequently and watch for signs of bleeding. Consider alternative analgesia such as acetaminophen.",
        "references": "Clinical Pharmacology [Database]. Warfarin-Aspirin Interaction. Elsevier Gold Standard.",
        "source": "curated",
    },
    {
        "drug_a": "warfarin",
        "drug_b": "ibuprofen",
        "severity": "major",
        "mechanism": "Additive anticoagulant effect. NSAIDs inhibit platelet cyclooxygenase and can displace warfarin from albumin binding sites.",
        "clinical_effect": "Increased INR and elevated risk of gastrointestinal bleeding. Ibuprofen may also cause gastric mucosal damage independently.",
        "management": "Prefer acetaminophen for pain management. If NSAID required, use lowest effective dose for shortest duration. Monitor INR within 3-5 days of starting NSAID.",
        "references": "FDA Drug Safety Communication: NSAIDs and Warfarin Interaction.",
        "source": "curated",
    },
    {
        "drug_a": "warfarin",
        "drug_b": "naproxen",
        "severity": "major",
        "mechanism": "Additive anticoagulant effect with platelet inhibition. Naproxen has a long half-life leading to sustained antiplatelet effect.",
        "clinical_effect": "Elevated INR and increased risk of bleeding, particularly GI bleeding.",
        "management": "Avoid combination. Use alternative analgesia (acetaminophen, opioids). If unavoidable, monitor INR closely and reduce warfarin dose as needed.",
        "references": "UpToDate: Warfarin Drug Interactions. Lexicomp.",
        "source": "curated",
    },
    {
        "drug_a": "warfarin",
        "drug_b": "diclofenac",
        "severity": "major",
        "mechanism": "Additive anticoagulant effect via platelet COX inhibition and potential protein binding displacement.",
        "clinical_effect": "Increased risk of bleeding events. Diclofenac may also cause fluid retention masking bleeding signs.",
        "management": "Monitor INR frequently. Consider PPI co-therapy for GI protection. Limit NSAID duration.",
        "references": "Drug Interaction Facts: Warfarin-NSAID Interactions.",
        "source": "curated",
    },
    # ACE Inhibitor + K-sparing diuretic → hyperkalemia
    {
        "drug_a": "lisinopril",
        "drug_b": "spironolactone",
        "severity": "moderate",
        "mechanism": "Additive hyperkalemic effect. ACE inhibitors reduce aldosterone-mediated potassium excretion, while spironolactone blocks aldosterone receptors directly in the collecting duct.",
        "clinical_effect": "Elevated serum potassium levels, potentially life-threatening hyperkalemia (K+ > 5.5 mEq/L), especially in patients with renal impairment or diabetes.",
        "management": "Monitor serum potassium and renal function at baseline, 1 week after initiation, and periodically thereafter. Consider potassium restriction. Avoid in patients with CrCl <30 mL/min.",
        "references": "ACC/AHA Heart Failure Guidelines. NICE Guideline NG106.",
        "source": "curated",
    },
    {
        "drug_a": "lisinopril",
        "drug_b": "losartan",
        "severity": "moderate",
        "mechanism": "Dual blockade of the renin-angiotensin-aldosterone system (RAAS). ACE inhibitor + ARB provides additive suppression of angiotensin II.",
        "clinical_effect": "Increased risk of hyperkalemia, hypotension, and acute kidney injury without additional cardiovascular benefit in most patients.",
        "management": "Not recommended for routine combination therapy. If used (e.g., heart failure with reduced EF), monitor BP, renal function, and potassium closely.",
        "references": "ONTARGET Trial. ACC/AHA Hypertension Guidelines 2017.",
        "source": "curated",
    },
    # Statins + Macrolides → myopathy
    {
        "drug_a": "atorvastatin",
        "drug_b": "clarithromycin",
        "severity": "moderate",
        "mechanism": "CYP3A4 inhibition. Clarithromycin is a potent CYP3A4 inhibitor, reducing metabolism of atorvastatin leading to significantly increased statin plasma concentrations.",
        "clinical_effect": "Increased risk of statin-related adverse effects including myopathy, rhabdomyolysis, and hepatotoxicity.",
        "management": "Consider temporary statin discontinuation during clarithromycin course. Alternatively, use azithromycin (no CYP3A4 interaction) or consider pravastatin/rosuvastatin (less CYP3A4 metabolism).",
        "references": "FDA Adverse Event Reporting System. FDA Drug Safety Communication 2012.",
        "source": "curated",
    },
    {
        "drug_a": "simvastatin",
        "drug_b": "clarithromycin",
        "severity": "major",
        "mechanism": "CYP3A4 inhibition. Clarithromycin is a potent CYP3A4 inhibitor significantly reducing simvastatin metabolism.",
        "clinical_effect": "Dramatically increased simvastatin levels (up to 10x) leading to high risk of rhabdomyolysis.",
        "management": "CONTRAINDICATED. Do not use simvastatin with clarithromycin. Switch to a non-interacting statin or antibiotic.",
        "references": "FDA label update for simvastatin 2011. EMA restrictions on simvastatin.",
        "source": "curated",
    },
    # SSRIs + MAOIs → serotonin syndrome
    {
        "drug_a": "sertraline",
        "drug_b": "phenelzine",
        "severity": "major",
        "mechanism": "Additive serotonergic effect. MAOIs inhibit metabolism of serotonin, while SSRIs block serotonin reuptake, leading to excessive serotonin in the synaptic cleft.",
        "clinical_effect": "Serotonin syndrome: confusion, agitation, hyperthermia, diaphoresis, hyperreflexia, clonus, tremor, tachycardia, potentially fatal.",
        "management": "ABSOLUTE CONTRAINDICATION. Requires 14-day washout period between MAOI discontinuation and SSRI initiation (5 weeks for fluoxetine due to long half-life).",
        "references": "American Psychiatric Association Practice Guidelines. FDA labeling.",
        "source": "curated",
    },
    {
        "drug_a": "fluoxetine",
        "drug_b": "phenelzine",
        "severity": "major",
        "mechanism": "Additive serotonergic effect. Fluoxetine and its active metabolite norfluoxetine have a long half-life (4-16 days) prolonging the interaction risk window.",
        "clinical_effect": "Severe serotonin syndrome. Risk persists for 5+ weeks after fluoxetine discontinuation.",
        "management": "ABSOLUTE CONTRAINDICATION. Allow minimum 5-week washout after fluoxetine before starting MAOI.",
        "references": "FDA Prescribing Information. Clinical Pharmacology Review.",
        "source": "curated",
    },
    # SSRI + SNRI → serotonin syndrome risk (milder)
    {
        "drug_a": "sertraline",
        "drug_b": "duloxetine",
        "severity": "minor",
        "mechanism": "Additive serotonergic effects. Both drugs increase serotonin availability through different mechanisms (SSRI blocks reuptake, SNRI blocks reuptake of both serotonin and norepinephrine).",
        "clinical_effect": "Mild serotonin excess: anxiety, restlessness, GI upset, insomnia. Rarely progresses to serotonin syndrome but risk increases at higher doses.",
        "management": "Use with caution. Start at low doses and titrate slowly. Monitor for signs of serotonin excess. Consider monotherapy if possible.",
        "references": "Lexicomp Drug Interactions. MicroMedex.",
        "source": "curated",
    },
    {
        "drug_a": "fluoxetine",
        "drug_b": "duloxetine",
        "severity": "minor",
        "mechanism": "Additive serotonergic effects. Both are potent serotonin reuptake inhibitors.",
        "clinical_effect": "Mild serotonin excess symptoms including GI distress, agitation, insomnia. Serotonin syndrome risk is low but present.",
        "management": "Use lowest effective doses. Monitor for serotonin syndrome symptoms. Consider monotherapy or augmentation with non-serotonergic agents.",
        "references": "Clinical Pharmacology Drug Interaction Monograph.",
        "source": "curated",
    },
    # Clopidogrel + Omeprazole → reduced efficacy
    {
        "drug_a": "clopidogrel",
        "drug_b": "omeprazole",
        "severity": "moderate",
        "mechanism": "CYP2C19 inhibition. Omeprazole inhibits CYP2C19, reducing conversion of clopidogrel prodrug to its active metabolite. Pantoprazole has less CYP2C19 inhibition.",
        "clinical_effect": "Reduced antiplatelet activity of clopidogrel, potentially increasing risk of cardiovascular events including stent thrombosis.",
        "management": "Prefer pantoprazole over omeprazole for patients on clopidogrel. If omeprazole must be used, separate dosing by at least 12 hours (though this may not fully mitigate the interaction).",
        "references": "FDA Drug Safety Communication 2009. COGENT Trial. ACC/AHA Guidelines.",
        "source": "curated",
    },
    # Methotrexate + NSAIDs → toxicity
    {
        "drug_a": "methotrexate",
        "drug_b": "ibuprofen",
        "severity": "major",
        "mechanism": "Reduced renal clearance of methotrexate. NSAIDs inhibit renal prostaglandin synthesis, reducing renal blood flow and tubular secretion of methotrexate.",
        "clinical_effect": "Elevated methotrexate levels leading to increased risk of bone marrow suppression, hepatotoxicity, and renal toxicity.",
        "management": "Avoid NSAIDs during high-dose methotrexate therapy. For low-dose MTX, use with extreme caution. Monitor MTX levels, renal function, and CBC closely.",
        "references": "American College of Rheumatology Guidelines. FDA label warnings.",
        "source": "curated",
    },
    # Digoxin + Amiodarone → toxicity
    {
        "drug_a": "digoxin",
        "drug_b": "amiodarone",
        "severity": "moderate",
        "mechanism": "P-glycoprotein inhibition. Amiodarone inhibits P-gp-mediated renal and biliary digoxin clearance, reducing digoxin distribution volume.",
        "clinical_effect": "Increased serum digoxin levels (50-100% increase), leading to risk of digoxin toxicity (nausea, vomiting, arrhythmias, visual disturbances).",
        "management": "Reduce digoxin dose by 30-50% when starting amiodarone. Monitor digoxin levels and renal function. Watch for ECG changes.",
        "references": "Circulation: Drug-Drug Interactions in Cardiovascular Medicine. FDA labeling.",
        "source": "curated",
    },
    # Lithium + NSAIDs → increased lithium levels
    {
        "drug_a": "lithium",
        "drug_b": "ibuprofen",
        "severity": "moderate",
        "mechanism": "Reduced renal lithium clearance. NSAIDs inhibit renal prostaglandin synthesis, reducing GFR and increasing lithium reabsorption in the proximal tubule.",
        "clinical_effect": "Increased serum lithium levels (30-50% increase), increasing risk of lithium toxicity (tremor, ataxia, confusion, renal impairment).",
        "management": "Monitor lithium levels 5-7 days after starting NSAID. Reduce lithium dose as needed. Prefer acetaminophen for analgesia in lithium patients.",
        "references": "International Bipolar Association Guidelines. Lexicomp Drug Interactions.",
        "source": "curated",
    },
    # Quinolones + NSAIDs → CNS toxicity
    {
        "drug_a": "ciprofloxacin",
        "drug_b": "ibuprofen",
        "severity": "minor",
        "mechanism": "GABA-A receptor antagonism. Both fluoroquinolones and NSAIDs can antagonize GABA-A receptors, lowering seizure threshold.",
        "clinical_effect": "Increased risk of CNS stimulation (dizziness, confusion, agitation) and potentially seizures, especially in elderly or patients with history of seizures.",
        "management": "Use with caution in patients with seizure history. Monitor for CNS symptoms. Consider alternative antibiotic or analgesic.",
        "references": "FDA label warnings for fluoroquinolones. Clinical Neuropharmacology 2010.",
        "source": "curated",
    },
    # Theophylline + Ciprofloxacin → increased theophylline
    {
        "drug_a": "theophylline",
        "drug_b": "ciprofloxacin",
        "severity": "moderate",
        "mechanism": "CYP1A2 inhibition. Ciprofloxacin is a potent CYP1A2 inhibitor, significantly reducing theophylline metabolism.",
        "clinical_effect": "Increased theophylline levels (up to 2-3x), leading to nausea, vomiting, tachycardia, and seizures at toxic levels.",
        "management": "Reduce theophylline dose by 30-50% when starting ciprofloxacin. Monitor theophylline levels and adjust accordingly. Consider alternative antibiotic.",
        "references": "Chest Journal: Theophylline-Fluoroquinolone Interactions. FDA labeling.",
        "source": "curated",
    },
    # Metformin + contrast → lactic acidosis
    {
        "drug_a": "metformin",
        "drug_b": "furosemide",
        "severity": "minor",
        "mechanism": "Potential renal function interaction. Both drugs rely on renal function for clearance. Furosemide-induced volume depletion can reduce GFR and impair metformin elimination.",
        "clinical_effect": "Slightly increased risk of metformin accumulation and lactic acidosis in patients with renal impairment.",
        "management": "Monitor renal function. Ensure adequate hydration. Temporarily hold metformin in acute illness with risk of renal impairment.",
        "references": "FDA metformin label. KDIGO Guidelines.",
        "source": "curated",
    },
    # Warfarin + Acetaminophen
    {
        "drug_a": "warfarin",
        "drug_b": "acetaminophen",
        "severity": "minor",
        "mechanism": "Weak inhibition of warfarin metabolism via CYP1A2 and CYP3A4 pathways. Acetaminophen may also interfere with vitamin K-dependent clotting factor synthesis at high doses.",
        "clinical_effect": "Slight INR increase with regular high-dose acetaminophen (>2g/day for >1 week). Clinically significant bleeding is rare but possible.",
        "management": "Use lowest effective dose of acetaminophen. Monitor INR more frequently with regular high-dose use. No interaction with intermittent use.",
        "references": "Clinical Pharmacology Review. Pharmacotherapy 2015.",
        "source": "curated",
    },
]


def seed():
    db = SessionLocal()
    try:
        service = DrugService(db)
        count = 0
        errors = 0
        for interaction in INTERACTIONS:
            try:
                service.store_interaction(interaction)
                print(f"  ✓ {interaction['drug_a']} + {interaction['drug_b']} ({interaction['severity']})")
                count += 1
            except Exception as e:
                print(f"  ✗ {interaction['drug_a']} + {interaction['drug_b']}: {e}")
                errors += 1
        print(f"\n{'='*50}")
        print(f"Seeded {count} interactions, {errors} errors")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
