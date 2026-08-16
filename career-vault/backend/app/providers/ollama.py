from dataclasses import dataclass
import json
from typing import Any

import httpx

from app.config import settings


@dataclass(frozen=True)
class OllamaStatus:
    reachable: bool
    generation_model_available: bool
    embedding_model_available: bool
    installed_models: list[str]


@dataclass(frozen=True)
class InterviewTurn:
    assistant_message: str
    fact_proposals: list[dict[str, Any]]


class OllamaProvider:
    """Local-only adapter for Ollama's HTTP API."""

    async def status(self) -> OllamaStatus:
        try:
            async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=3.0) as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
        except httpx.HTTPError:
            return OllamaStatus(False, False, False, [])

        installed_models = [model["name"] for model in response.json().get("models", [])]
        return OllamaStatus(
            reachable=True,
            generation_model_available=settings.generation_model in installed_models,
            embedding_model_available=settings.embedding_model in installed_models,
            installed_models=installed_models,
        )

    async def next_interview_turn(self, history: list[dict[str, str]], stage_objective: str) -> InterviewTurn:
        """Ask the local model for one focused question and optional fact proposals."""
        system_prompt = """You are Career Vault's careful career-interview guide.
Your task is to build a complete, accurate professional record through a warm, focused conversation.
This user is a consultant with multiple companies, clients, and projects. Capture the full
8-year career inventory, not merely the latest role or impressive work. First create a timeline
of EVERY employer: company name, job title(s), start/end dates, and location if known. Then work
through one employer at a time. For each role, ask the user to list EVERY client/project
engagement, then take one engagement at a time and collect client, project, dates, position,
contribution type, responsibilities, tools, scope, outcomes, and achievements. Before moving to
another employer, explicitly ask whether any other client or project from that employer is
missing. Include support, development, migration, automation, leadership, pre-sales, research,
authorship, and short engagements.

Career-wide assets must be handled in separate focused stages: skills, certifications, recognition,
research/publications, education, and public work. Do not combine categories in one question or
ask the user to write a long response. Do not assume that an absence in the conversation means it does not exist.

The application has placed you in this interview stage. Stay in this stage and do not move to
another one or ask unrelated questions. Current stage objective: """ + stage_objective + """

Ask exactly one useful next question. Do not ask the user to rank work by importance. Prefer
concrete detail: employer, role, dates, clients, projects, responsibilities, tools, outcomes,
scope, or certifications. Do not invent facts or metrics.

From the user's latest message, propose only facts explicitly stated by the user. Each proposal
must be short and useful for a future resume. Return ONLY valid JSON in this exact shape:
{
  \"assistant_message\": \"one friendly next question\",
  \"fact_proposals\": [
    {\"entity_type\": \"employment|client|project|contribution|skill|achievement|certification|publication|research|authorship|award\", \"summary\": \"short fact\", \"data\": {\"key\": \"value\"}}
  ]
}
Use an empty fact_proposals list if no reliable fact can be proposed."""
        messages = [{"role": "system", "content": system_prompt}, *history[-12:]]
        try:
            async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=75.0) as client:
                response = await client.post(
                    "/api/chat",
                    json={"model": settings.generation_model, "messages": messages, "stream": False},
                )
                response.raise_for_status()
            content = response.json()["message"]["content"]
            parsed = json.loads(self._json_object(content))
            assistant_message = str(parsed.get("assistant_message", "")).strip()
            proposals = parsed.get("fact_proposals", [])
            if not assistant_message or not isinstance(proposals, list):
                raise ValueError("The model returned an incomplete interview turn")
            return InterviewTurn(assistant_message, self._safe_proposals(proposals))
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return InterviewTurn(
                "Thanks. Please list every client or project engagement you worked on in that role; we’ll document each one separately.",
                [],
            )

    async def candidate_overview(self, records: list[dict[str, str]]) -> str:
        """Generate a short professional summary from approved records only."""
        evidence = "\n".join(f"- {record['type']}: {record['summary']}" for record in records)
        prompt = "Write one professional Candidate Overview of 50 to 60 words. Use ONLY the verified evidence below. Do not invent employers, dates, years, titles, metrics, or skills. Do not mention that this is an AI summary. Return one plain paragraph only.\n\nVerified evidence:\n" + evidence
        try:
            async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=75.0) as client:
                response = await client.post(
                    "/api/chat",
                    json={"model": settings.generation_model, "messages": [{"role": "system", "content": "You write concise, truthful professional summaries."}, {"role": "user", "content": prompt}], "stream": False},
                )
                response.raise_for_status()
            return response.json()["message"]["content"].strip().replace("\n", " ")
        except (httpx.HTTPError, KeyError, TypeError):
            return "Unable to generate an overview while the local model is unavailable. Please try again."

    async def master_resume(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Turn approved facts into a structured draft; never fabricate missing details."""
        evidence = "\n".join(
            f"- type: {record['type']} | summary: {record['summary']} | details: {json.dumps(record.get('data', {}), ensure_ascii=False)}"
            for record in records
        )
        prompt = """Create a truthful, ATS-friendly MASTER RESUME draft from the approved facts below.
Do not invent employers, roles, dates, years of experience, skills, metrics, credentials, or contact details.
Keep every detail faithful to the evidence. Do not include a section when evidence is missing.
Return ONLY JSON in this exact shape:
{
  "headline": "short role/discipline headline",
  "professional_summary": "2-3 factual sentences",
  "skills": ["skill"],
  "experience": [{"role": "", "company": "", "dates": "", "highlights": ["factual accomplishment or responsibility"]}],
  "certifications": ["verified credential"],
  "education": ["verified education"],
  "additional_highlights": ["publication, award, public work, or other verified item"]
}
For unclear employment data, leave a field empty instead of guessing. Use compact bullet wording.

Approved evidence:\n""" + evidence
        try:
            async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=90.0) as client:
                response = await client.post(
                    "/api/chat",
                    json={"model": settings.generation_model, "messages": [{"role": "system", "content": "You create accurate, evidence-only professional resume drafts."}, {"role": "user", "content": prompt}], "stream": False},
                )
                response.raise_for_status()
            parsed = json.loads(self._json_object(response.json()["message"]["content"]))
            if not isinstance(parsed, dict):
                raise ValueError("Resume was not a JSON object")
            return self._safe_resume(parsed, records)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return self._fallback_resume(records)

    async def job_specific_package(
        self, records: list[dict[str, Any]], job_title: str, job_description: str
    ) -> dict[str, Any]:
        """Tailor a resume + cover letter to one job posting from approved facts only.

        The model may re-select, reorder, re-emphasize, and rephrase existing evidence to
        mirror the job posting's language for ATS keyword matching. It must never invent
        employers, roles, dates, skills, or metrics that are not present in the evidence.
        """
        evidence = "\n".join(
            f"- type: {record['type']} | summary: {record['summary']} | details: {json.dumps(record.get('data', {}), ensure_ascii=False)}"
            for record in records
        )
        prompt = f"""A candidate is applying to this role. Build a tailored, ATS-friendly, ONE-PAGE RESUME
and a tailored COVER LETTER using ONLY the approved evidence below. Do not invent employers, roles,
dates, years of experience, skills, metrics, or credentials that are not present in the evidence.

This resume must read like an industry-standard, single-page resume — not a dump of every fact in the
candidate's Career Vault. You MUST select and condense:
- Include ONLY the 3-4 most relevant experience entries (employer/client engagements) for this specific
  job. Leave out employers, clients, or projects that are not relevant to this posting, even if they
  exist in the evidence.
- For each included experience entry, keep at most 3-4 of the strongest, most relevant bullets. Each
  bullet should be one tight line (roughly 12-20 words), not a full sentence with sub-clauses.
- Include at most 10-12 of the most relevant skills, ordered by relevance to this job.
- professional_summary must be exactly 2 sentences.
- Include at most 3 certifications, 2 education entries, and 3 additional highlights — only the ones most
  relevant to this job. Omit a section entirely if nothing relevant qualifies.
The goal is a resume a hiring manager could scan in under 30 seconds and that prints to a single page.

You may: reorder experience and bullets to put the most relevant items first, rephrase bullets
to mirror the job posting's terminology (only when the underlying fact still matches), choose
which skills/achievements to surface, and write a headline and professional summary aimed at
this role. Naturally weave in exact keywords and phrases from the job posting where the
candidate's real evidence supports them, since this improves ATS keyword matching. Do not
stuff keywords that have no supporting evidence.

Target job title: {job_title}

Job posting / job-specific career description:
{job_description}

Return ONLY JSON in this exact shape:
{{
  "resume": {{
    "headline": "short role/discipline headline tailored to this job",
    "professional_summary": "exactly 2 factual sentences aimed at this job",
    "skills": ["at most 10-12 skills, prioritized by relevance to this job"],
    "experience": [{{"role": "", "company": "", "dates": "", "highlights": ["3-4 tight, factual, job-relevant bullets"]}}],
    "certifications": ["at most 3, most relevant verified credentials"],
    "education": ["at most 2, most relevant verified education entries"],
    "additional_highlights": ["at most 3, most relevant verified items"]
  }},
  "cover_letter": "a complete 250-350 word cover letter body (no address block), professional tone, referencing 2-3 concrete pieces of the candidate's real evidence and connecting them to this specific role",
  "keyword_matches": ["job-posting keyword or phrase that the resume evidence genuinely supports"],
  "gap_analysis": {{
    "match_score": 0,
    "score_reasoning": "one short factual sentence on why this score, based only on the evidence vs. the posting's stated requirements",
    "strengths": ["a requirement from the posting that the evidence clearly satisfies, with a brief reference to which evidence"],
    "gaps": ["a requirement or preferred qualification from the posting that the evidence does NOT show, stated plainly"],
    "suggestions": ["a specific, actionable step the candidate could take to close a gap or strengthen the application — e.g. a certification to pursue, a skill to gain hands-on experience with, a type of achievement to quantify, or a Career Vault fact to add through another interview session"]
  }}
}}
Leave a field empty instead of guessing. Use compact bullet wording in the resume.

For gap_analysis: match_score is an honest 0-100 estimate of this candidate's fit for THIS posting based
strictly on the approved evidence versus the posting's stated must-have and preferred requirements — do
not inflate it. List every requirement in the posting that the evidence does not support as a gap, in
plain language a candidate could act on. Do not soften real gaps and do not invent evidence to close them.

Approved evidence:
""" + evidence
        try:
            async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=120.0) as client:
                response = await client.post(
                    "/api/chat",
                    json={
                        "model": settings.generation_model,
                        "messages": [
                            {"role": "system", "content": "You create accurate, evidence-only, job-tailored resumes, cover letters, and honest fit/gap assessments. You never fabricate facts and you never inflate a fit score to be encouraging."},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                response.raise_for_status()
            parsed = json.loads(self._json_object(response.json()["message"]["content"]))
            if not isinstance(parsed, dict):
                raise ValueError("Job package was not a JSON object")
            return self._safe_job_package(parsed, records)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return self._fallback_job_package(records)

    @staticmethod
    def _json_object(content: str) -> str:
        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found")
        return content[start : end + 1]

    @staticmethod
    def _safe_proposals(proposals: list[Any]) -> list[dict[str, Any]]:
        valid_types = {
            "employment", "client", "project", "contribution", "skill", "achievement",
            "certification", "publication", "research", "authorship", "award",
        }
        safe: list[dict[str, Any]] = []
        for proposal in proposals[:3]:
            if not isinstance(proposal, dict):
                continue
            entity_type = proposal.get("entity_type")
            summary = proposal.get("summary")
            data = proposal.get("data", {})
            if entity_type in valid_types and isinstance(summary, str) and summary.strip() and isinstance(data, dict):
                safe.append({"entity_type": entity_type, "summary": summary.strip()[:600], "data": data})
        return safe

    @staticmethod
    def _safe_resume(resume: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
        def text(value: Any, limit: int = 1000) -> str:
            return str(value).strip()[:limit] if isinstance(value, str) else ""

        def string_list(value: Any, maximum: int = 20) -> list[str]:
            return [text(item, 300) for item in value[:maximum] if text(item, 300)] if isinstance(value, list) else []

        safe_experience: list[dict[str, Any]] = []
        if isinstance(resume.get("experience"), list):
            for entry in resume["experience"][:15]:
                if isinstance(entry, dict):
                    safe_experience.append({
                        "role": text(entry.get("role"), 150), "company": text(entry.get("company"), 150),
                        "dates": text(entry.get("dates"), 80), "highlights": string_list(entry.get("highlights"), 8),
                    })
        result = {
            "headline": text(resume.get("headline"), 160),
            "professional_summary": text(resume.get("professional_summary"), 1000),
            "skills": string_list(resume.get("skills"), 30),
            "experience": safe_experience,
            "certifications": string_list(resume.get("certifications"), 20),
            "education": string_list(resume.get("education"), 12),
            "additional_highlights": string_list(resume.get("additional_highlights"), 20),
        }
        if any(result.values()):
            return result
        return OllamaProvider._fallback_resume(records)

    @staticmethod
    def _safe_job_package(package: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
        def text(value: Any, limit: int = 4000) -> str:
            return str(value).strip()[:limit] if isinstance(value, str) else ""

        def string_list(value: Any, maximum: int = 30, limit: int = 300) -> list[str]:
            return [text(item, limit) for item in value[:maximum] if text(item, limit)] if isinstance(value, list) else []

        resume = package.get("resume")
        safe_resume = OllamaProvider._safe_resume(resume, records) if isinstance(resume, dict) else OllamaProvider._fallback_resume(records)
        safe_resume = OllamaProvider._condense_for_one_page(safe_resume)
        cover_letter = text(package.get("cover_letter"), 4000)
        keyword_matches = string_list(package.get("keyword_matches"), 25, 80)
        gap_analysis = OllamaProvider._safe_gap_analysis(package.get("gap_analysis"))
        if not cover_letter:
            return OllamaProvider._fallback_job_package(records)
        return {"resume": safe_resume, "cover_letter": cover_letter, "keyword_matches": keyword_matches, "gap_analysis": gap_analysis}

    @staticmethod
    def _condense_for_one_page(resume: dict[str, Any]) -> dict[str, Any]:
        """Hard cap on top of the model's own output, so a tailored resume stays a
        realistic single page even if the model does not fully follow the length guidance."""
        experience = []
        for entry in resume.get("experience", [])[:4]:
            experience.append({**entry, "highlights": entry.get("highlights", [])[:4]})
        return {
            **resume,
            "skills": resume.get("skills", [])[:12],
            "experience": experience,
            "certifications": resume.get("certifications", [])[:3],
            "education": resume.get("education", [])[:2],
            "additional_highlights": resume.get("additional_highlights", [])[:3],
        }

    @staticmethod
    def _safe_gap_analysis(gap_analysis: Any) -> dict[str, Any]:
        def text(value: Any, limit: int = 400) -> str:
            return str(value).strip()[:limit] if isinstance(value, str) else ""

        def string_list(value: Any, maximum: int = 15, limit: int = 300) -> list[str]:
            return [text(item, limit) for item in value[:maximum] if text(item, limit)] if isinstance(value, list) else []

        if not isinstance(gap_analysis, dict):
            return {"match_score": None, "score_reasoning": "", "strengths": [], "gaps": [], "suggestions": []}

        raw_score = gap_analysis.get("match_score")
        score: int | None = None
        if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
            score = max(0, min(100, round(raw_score)))

        return {
            "match_score": score,
            "score_reasoning": text(gap_analysis.get("score_reasoning"), 400),
            "strengths": string_list(gap_analysis.get("strengths")),
            "gaps": string_list(gap_analysis.get("gaps")),
            "suggestions": string_list(gap_analysis.get("suggestions")),
        }

    @staticmethod
    def _fallback_job_package(records: list[dict[str, Any]]) -> dict[str, Any]:
        resume = OllamaProvider._condense_for_one_page(OllamaProvider._fallback_resume(records))
        cover_letter = (
            "I was unable to draft a tailored cover letter while the local model is unavailable. "
            "Please try again once Ollama is reachable; your approved Career Vault facts were not changed."
        )
        gap_analysis = {
            "match_score": None,
            "score_reasoning": "Fit could not be assessed while the local model is unavailable.",
            "strengths": [],
            "gaps": [],
            "suggestions": ["Try again once Ollama is reachable to get a fit score and gap analysis for this posting."],
        }
        return {"resume": resume, "cover_letter": cover_letter, "keyword_matches": [], "gap_analysis": gap_analysis}

    @staticmethod
    def _fallback_resume(records: list[dict[str, Any]]) -> dict[str, Any]:
        grouped: dict[str, list[str]] = {}
        for record in records:
            grouped.setdefault(str(record["type"]), []).append(str(record["summary"]))
        experience = [
            {"role": "Professional experience", "company": "", "dates": "", "highlights": values}
            for item_type, values in grouped.items() if item_type in {"employment", "project", "contribution"}
        ]
        return {
            "headline": "Professional Profile",
            "professional_summary": "A master resume draft assembled from approved Career Vault facts. Review and refine it before sharing.",
            "skills": grouped.get("skill", []), "experience": experience,
            "certifications": grouped.get("certification", []), "education": grouped.get("education", []),
            "additional_highlights": sum((values for item_type, values in grouped.items() if item_type in {"achievement", "publication", "research", "authorship", "award"}), []),
        }
