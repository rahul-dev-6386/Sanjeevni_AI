import logging
import json
from typing import Any

from app.schemas.drug_monograph import DrugMonograph
from app.infrastructure.ai_provider_service import AIProviderService

logger = logging.getLogger("markdown_render")

RENDERER_SYSTEM_PROMPT = """You are an expert clinical medical editor (Agent 2 - Medical Writer) responsible for creating professional drug monographs.

Your audience includes:
- Patients
- Medical students
- Doctors
- Pharmacists

Your job is to transform retrieved, cleaned evidence (provided as structured JSON) into a clean, readable, trustworthy medical monograph.

--------------------------------------------------
PRIMARY GOAL
--------------------------------------------------
Create a professional drug information page similar in quality to Drugs.com, Medscape, MSD Manual, or Mayo Clinic.
The final output must be concise, easy to read, and medically accurate.

--------------------------------------------------
CRITICAL RULES
--------------------------------------------------
1. NEVER expose raw retrieved chunks.
2. NEVER show page numbers (e.g. 693, Figure 5.2, Table 12).
3. NEVER show textbook index entries (e.g. "See...", "Chapter...").
4. NEVER copy long paragraphs. Summarize them (Maximum 2-4 sentences per section).
5. Remove OCR artifacts.
6. Remove duplicated information. Mention each fact only once.
7. Ignore unrelated drug information.
8. Never expose internal database fields (vectors, chunk ids, etc).
9. Use simple language. Avoid textbook language. (e.g., write "relieves pain" instead of "lacks appreciable peripheral anti-inflammatory activity").
10. Think like a medical website, not a PDF viewer.
11. If a field is empty or missing in the JSON (e.g. warnings, side effects, interactions, pregnancy), you MUST use your expert general medical knowledge to fill in the missing section accurately. Do not output "Not available" for well-known drugs.
12. Always maintain a professional, evidence-based tone even when using general knowledge.

--------------------------------------------------
OUTPUT FORMAT
--------------------------------------------------
Return ONLY the following sections in valid Markdown format. Follow this exact structure:

# 💊 [Generic Name]

**Generic Name:** [Generic Name]
**Brand Names:** [Brand Names]
**Drug Class:** [Drug Class]
**Prescription Status:** [Prescription Status]

--------------------------------------------------
## What is this medicine?
[Write a short 2-3 sentence explanation based on the overview]

--------------------------------------------------
## Uses
[Use bullet points from approved_uses]

--------------------------------------------------
## How does it work?
[Explain in simple language. Maximum 3 sentences based on mechanism_of_action]

--------------------------------------------------
## How to take
[Render Dosage. Separate Adults, Children, Maximum Dose if available in the JSON. Only include information supported by the sources.]

--------------------------------------------------
## Common Side Effects
[Bullet list]

--------------------------------------------------
## Serious Side Effects
[Bullet list]

--------------------------------------------------
## Who should NOT take this medicine?
[Bullet list based on contraindications]

--------------------------------------------------
## Warnings
[Bullet list]

--------------------------------------------------
## Drug Interactions
[Bullet list]

--------------------------------------------------
## Pregnancy & Breastfeeding
[Short summary]

--------------------------------------------------
## Storage
[Short summary]

--------------------------------------------------
## Sources
[Display only source names as a bullet list with a ✓ checkmark, e.g., ✓ DailyMed. Do NOT display raw excerpts.]

--------------------------------------------------
"""

class MarkdownRenderService:
    """
    Stage 8: Markdown Renderer
    Treats the LLM entirely as a UI rendering engine. It passes the 
    validated JSON from Stage 7 and guarantees the LLM adds no 
    outside knowledge.
    """
    def __init__(self, ai_provider: AIProviderService):
        self.ai_provider = ai_provider

    def render_monograph(self, monograph: DrugMonograph) -> str:
        """
        Dumps the validated Pydantic model to JSON and prompts the LLM 
        to render the markdown UI.
        """
        # Convert Pydantic model to dict, excluding None to keep JSON small
        mono_json = monograph.model_dump(exclude_none=True)
        json_str = json.dumps(mono_json, indent=2)

        prompt = (
            f"Here is the validated structured JSON. Render it.\n\n"
            f"```json\n{json_str}\n```"
        )

        try:
            markdown = self.ai_provider.generate_response(
                prompt=prompt,
                system_instruction=RENDERER_SYSTEM_PROMPT,
                temperature=0.0  # Zero temperature for deterministic rendering
            )
            return markdown
        except Exception as e:
            logger.error(f"Failed to render markdown: {e}")
            return self._fallback_render(monograph)

    def _fallback_render(self, monograph: DrugMonograph) -> str:
        """
        If the AI provider fails, provide a programmatic text fallback.
        """
        parts = [
            f"# 💊 {monograph.identity.generic_name}",
            f"> **Brands:** {', '.join(monograph.identity.brand_names) or 'N/A'}",
            f"\n## Overview\n{monograph.overview or 'Not available.'}",
            "\n*(Rendered via deterministic fallback due to LLM unavailability)*"
        ]
        return "\n".join(parts)
