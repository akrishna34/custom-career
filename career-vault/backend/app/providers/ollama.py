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
