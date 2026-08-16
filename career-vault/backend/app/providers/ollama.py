from dataclasses import dataclass
import html
import json
import re
from typing import Any, Dict, List

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

    # ============================================================
    # OLLAMA STATUS
    # ============================================================

    async def status(self) -> OllamaStatus:
        try:
            async with httpx.AsyncClient(
                base_url=settings.ollama_base_url,
                timeout=3.0,
            ) as client:
                response = await client.get("/api/tags")
                response.raise_for_status()

            payload = response.json()

        except (httpx.HTTPError, ValueError, TypeError):
            return OllamaStatus(
                reachable=False,
                generation_model_available=False,
                embedding_model_available=False,
                installed_models=[],
            )

        models = payload.get("models", [])

        if not isinstance(models, list):
            models = []

        installed_models = [
            str(model.get("name"))
            for model in models
            if isinstance(model, dict) and model.get("name")
        ]

        return OllamaStatus(
            reachable=True,
            generation_model_available=(
                settings.generation_model in installed_models
            ),
            embedding_model_available=(
                settings.embedding_model in installed_models
            ),
            installed_models=installed_models,
        )

    # ============================================================
    # INTERVIEW
    # ============================================================

    async def next_interview_turn(
        self,
        history: list[dict[str, str]],
        stage_objective: str,
    ) -> InterviewTurn:
        """Ask the local model for one focused question and optional fact proposals."""

        system_prompt = """
You are Career Vault's careful career-interview guide.

Your task is to build a complete, accurate professional record through a warm,
focused conversation.

This user is a consultant with multiple companies, clients, and projects.
Capture the full career inventory, not merely the latest role or impressive work.

First create a timeline of EVERY employer:
- company name
- job title(s)
- start/end dates
- location if known

Then work through one employer at a time.

For each role:
- ask the user to list EVERY client/project engagement
- take one engagement at a time
- collect client
- project
- dates
- position
- contribution type
- responsibilities
- tools
- scope
- outcomes
- achievements

Before moving to another employer, explicitly ask whether any other client
or project from that employer is missing.

Include:
- support
- development
- migration
- automation
- leadership
- pre-sales
- research
- authorship
- short engagements

Career-wide assets must be handled in separate focused stages:
- skills
- certifications
- recognition
- research/publications
- education
- public work

Do not combine categories in one question.
Do not ask the user to write a long response.
Do not assume that an absence in the conversation means it does not exist.

The application has placed you in this interview stage.

Stay in this stage and do not move to another stage.

Current stage objective:
""" + stage_objective + """

Ask exactly ONE useful next question.

Do not ask the user to rank work by importance.

Prefer concrete detail:
- employer
- role
- dates
- clients
- projects
- responsibilities
- tools
- outcomes
- scope
- certifications
- education

Do not invent facts or metrics.

From the user's latest message, propose ONLY facts explicitly stated
by the user.

Each proposal must be short and useful for a future resume.

Return ONLY valid JSON in this exact shape:

{
  "assistant_message": "one friendly next question",
  "fact_proposals": [
    {
      "entity_type": "employment|client|project|contribution|skill|achievement|certification|publication|research|authorship|award|education",
      "summary": "short fact",
      "data": {
        "key": "value"
      }
    }
  ]
}

Use an empty fact_proposals list if no reliable fact can be proposed.
"""

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            *history[-12:],
        ]

        try:
            async with httpx.AsyncClient(
                base_url=settings.ollama_base_url,
                timeout=75.0,
            ) as client:

                response = await client.post(
                    "/api/chat",
                    json={
                        "model": settings.generation_model,
                        "messages": messages,
                        "stream": False,
                    },
                )

                response.raise_for_status()

            payload = response.json()

            content = payload["message"]["content"]

            parsed = json.loads(
                self._json_object(content)
            )

            assistant_message = str(
                parsed.get("assistant_message", "")
            ).strip()

            proposals = parsed.get(
                "fact_proposals",
                [],
            )

            if not assistant_message:
                raise ValueError(
                    "The model returned no assistant message"
                )

            if not isinstance(proposals, list):
                raise ValueError(
                    "The model returned invalid fact proposals"
                )

            return InterviewTurn(
                assistant_message=assistant_message,
                fact_proposals=self._safe_proposals(proposals),
            )

        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return InterviewTurn(
                (
                    "Thanks. Please list every client or project engagement "
                    "you worked on in that role; we'll document each one separately."
                ),
                [],
            )

    # ============================================================
    # CANDIDATE OVERVIEW
    # ============================================================

    async def candidate_overview(
        self,
        records: list[dict[str, str]],
    ) -> str:
        """Generate a short professional summary from approved records only."""

        evidence = "\n".join(
            f"- {record.get('type', '')}: {record.get('summary', '')}"
            for record in records
        )

        prompt = (
            "Write one professional Candidate Overview of 50 to 60 words. "
            "Use ONLY the verified evidence below. "
            "Do not invent employers, dates, years, titles, metrics, or skills. "
            "Do not mention that this is an AI summary. "
            "Return one plain paragraph only.\n\n"
            "Verified evidence:\n"
            + evidence
        )

        try:
            async with httpx.AsyncClient(
                base_url=settings.ollama_base_url,
                timeout=75.0,
            ) as client:

                response = await client.post(
                    "/api/chat",
                    json={
                        "model": settings.generation_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You write concise, truthful "
                                    "professional summaries."
                                ),
                            },
                            {
                                "role": "user",
                                "content": prompt,
                            },
                        ],
                        "stream": False,
                    },
                )

                response.raise_for_status()

            return (
                response.json()["message"]["content"]
                .strip()
                .replace("\n", " ")
            )

        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
        ):
            return (
                "Unable to generate an overview while the local model "
                "is unavailable. Please try again."
            )

    # ============================================================
    # MASTER RESUME
    # ============================================================

    async def master_resume(
        self,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Turn approved facts into a structured resume draft."""

        evidence = "\n".join(
            (
                f"- type: {record.get('type', '')} | "
                f"summary: {record.get('summary', '')} | "
                f"details: "
                f"{json.dumps(record.get('data', {}), ensure_ascii=False)}"
            )
            for record in records
        )

        prompt = """
Create a truthful, ATS-friendly ONE-PAGE MASTER RESUME draft from the approved facts below.

The output will be rendered into a compact A4 single-page, two-column resume:
- LEFT COLUMN: contact, programming, expertise, education, publications/highlights, certifications
- RIGHT COLUMN: summary, skill summary, experience
- Prioritize readability and evidence over completeness.
- Keep the professional summary to EXACTLY 2 concise factual sentences.
- Keep skill_summary to at most 2 concise items.
- Keep each employer to at most 3 concise, high-value bullets.
- Keep at most 5 employer entries, while preserving chronological career coverage.
- Keep certifications to at most 4 and education to at most 2 entries.
- Keep additional_highlights to at most 2 concise items.
- Do not repeat information between summary, skills, and experience.
- Bullets should be compact: ideally 15-25 words each.

Do not invent:
- employers
- roles
- dates
- years of experience
- skills
- metrics
- credentials
- education
- contact details

Keep every detail faithful to the evidence.

IMPORTANT EXPERIENCE RULE:

Each employer/company must appear ONCE under experience.

If multiple approved facts belong to the same company, merge them into
one company entry.

Group projects, clients and contributions related to that company inside
that company's highlights.

Do NOT create a separate employment entry for every project.

Return ONLY JSON in this exact shape:

{
  "headline": "Lead Data Engineer",
  "professional_summary": "2-3 factual sentences summarizing the evidence.",
  "core_skills": {
    "Programming": [],
    "Expertise": []
  },
  "skill_summary": [],
  "experience": [
    {
      "role": "Job Title",
      "company": "Company Name",
      "location": "Location",
      "dates": "Dates",
      "highlights": [
        "Factual project/responsibility/achievement"
      ]
    }
  ],
  "certifications": [],
  "education": [
    {
      "degree": "",
      "institution": "",
      "location": "",
      "year": ""
    }
  ],
  "additional_highlights": []
}

For unclear data, leave the field empty instead of guessing.

Approved evidence:
""" + evidence

        try:
            async with httpx.AsyncClient(
                base_url=settings.ollama_base_url,
                timeout=90.0,
            ) as client:

                response = await client.post(
                    "/api/chat",
                    json={
                        "model": settings.generation_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You create accurate, "
                                    "evidence-only professional resumes."
                                ),
                            },
                            {
                                "role": "user",
                                "content": prompt,
                            },
                        ],
                        "stream": False,
                    },
                )

                response.raise_for_status()

            parsed = json.loads(
                self._json_object(
                    response.json()["message"]["content"]
                )
            )

            if not isinstance(parsed, dict):
                raise ValueError(
                    "Resume was not a JSON object"
                )

            safe_resume = self._safe_resume(
                parsed,
                records,
            )

            # Master resumes must use the same one-page content budget
            # as tailored resumes so both outputs render consistently.
            return self._condense_for_one_page(
                safe_resume
            )

        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return self._fallback_resume(records)

    # ============================================================
    # JOB-SPECIFIC PACKAGE
    # ============================================================

    async def job_specific_package(
        self,
        records: list[dict[str, Any]],
        job_title: str,
        job_description: str,
    ) -> dict[str, Any]:
        """Tailor a resume and cover letter using approved facts only."""

        evidence = "\n".join(
            (
                f"- type: {record.get('type', '')} | "
                f"summary: {record.get('summary', '')} | "
                f"details: "
                f"{json.dumps(record.get('data', {}), ensure_ascii=False)}"
            )
            for record in records
        )

        prompt = f"""
A candidate is applying to this role.

Build a tailored, ATS-friendly ONE-PAGE RESUME and COVER LETTER using
ONLY the approved evidence below.

The resume will be rendered into the same compact A4 two-column layout as
the master resume:
- LEFT COLUMN: contact, programming, expertise, education, publications/highlights, certifications
- RIGHT COLUMN: summary, skill summary, experience
- Keep the professional summary to EXACTLY 2 concise factual sentences.
- Keep skill_summary to at most 2 concise items.
- Keep each employer to at most 3 concise, job-relevant bullets.
- Keep at most 5 employer entries.
- Keep certifications to at most 4 and education to at most 2 entries.
- Keep additional_highlights to at most 2 concise items.
- Never sacrifice factual accuracy merely to match keywords.

Do not invent:
- employers
- roles
- dates
- years of experience
- skills
- metrics
- credentials
- education

Target job title:
{job_title}

Job posting:
{job_description}

IMPORTANT EXPERIENCE RULE:

Each employer must appear ONCE.

Merge projects and contributions under the appropriate employer.

Return ONLY JSON:

{{
  "resume": {{
    "headline": "",
    "professional_summary": "exactly 2 factual sentences",
    "core_skills": {{
      "Programming": [],
      "Expertise": []
    }},
    "skill_summary": [],
    "experience": [
      {{
        "role": "",
        "company": "",
        "location": "",
        "dates": "",
        "highlights": [
          "3-4 factual job-relevant bullets"
        ]
      }}
    ],
    "certifications": [],
    "education": [
      {{
        "degree": "",
        "institution": "",
        "location": "",
        "year": ""
      }}
    ],
    "additional_highlights": []
  }},
  "cover_letter": "250-350 word cover letter body",
  "keyword_matches": [],
  "gap_analysis": {{
    "match_score": 0,
    "score_reasoning": "",
    "strengths": [],
    "gaps": [],
    "suggestions": []
  }}
}}

Approved evidence:

{evidence}
"""

        try:
            async with httpx.AsyncClient(
                base_url=settings.ollama_base_url,
                timeout=120.0,
            ) as client:

                response = await client.post(
                    "/api/chat",
                    json={
                        "model": settings.generation_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You create accurate, evidence-only, "
                                    "job-tailored resumes, cover letters, "
                                    "and honest fit assessments."
                                ),
                            },
                            {
                                "role": "user",
                                "content": prompt,
                            },
                        ],
                        "stream": False,
                    },
                )

                response.raise_for_status()

            parsed = json.loads(
                self._json_object(
                    response.json()["message"]["content"]
                )
            )

            if not isinstance(parsed, dict):
                raise ValueError(
                    "Job package was not a JSON object"
                )

            return self._safe_job_package(
                parsed,
                records,
            )

        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return self._fallback_job_package(records)

    # ============================================================
    # RESUME HTML RENDERER
    # ============================================================

    @staticmethod
    def render_resume_html(
        resume: dict[str, Any],
        candidate_info: dict[str, str] = None,
    ) -> str:
        """
        Render a compact, evidence-only A4 one-page resume matching the reference layout.

        IMPORTANT:
        This function contains NO hardcoded career facts.

        All:
        - experience
        - projects
        - education
        - certifications
        - publications
        - skills
        - summary

        come from `resume`.
        """

        # Both master and tailored resumes pass through the same
        # deterministic one-page content budget at render time.
        resume = OllamaProvider._condense_for_one_page(
            resume
        )

        info = candidate_info or {}

        name = info.get(
            "full_name",
            "KRISHNA AGRAWAL",
        )

        address = info.get(
            "address",
            "",
        )

        phone = info.get(
            "phone",
            "",
        )

        email = info.get(
            "email",
            "",
        )

        # --------------------------------------------------------
        # Helpers
        # --------------------------------------------------------

        def esc(value: Any) -> str:
            if value is None:
                return ""

            return html.escape(
                str(value),
                quote=True,
            )

        def clean_list(value: Any) -> list[str]:
            if not isinstance(value, list):
                return []

            result = []

            for item in value:
                if isinstance(item, str):
                    item = item.strip()

                    if item:
                        result.append(item)

            return result

        def unique(items: list[str]) -> list[str]:
            result = []
            seen = set()

            for item in items:
                key = re.sub(
                    r"\W+",
                    "",
                    item.lower(),
                )

                if key not in seen:
                    seen.add(key)
                    result.append(item)

            return result

        # --------------------------------------------------------
        # Skills
        # --------------------------------------------------------

        programming: list[str] = []
        expertise: list[str] = []

        core_skills = resume.get(
            "core_skills",
            {},
        )

        if isinstance(core_skills, dict):

            for category, items in core_skills.items():

                if not isinstance(items, list):
                    continue

                values = clean_list(items)

                category_name = str(
                    category
                ).lower()

                if any(
                    keyword in category_name
                    for keyword in (
                        "programming",
                        "language",
                        "languages",
                        "program",
                    )
                ):
                    programming.extend(values)

                else:
                    expertise.extend(values)

        # --------------------------------------------------------
        # Flat skills fallback
        # --------------------------------------------------------

        flat_skills = clean_list(
            resume.get("skills")
        )

        if not programming and not expertise:
            expertise.extend(flat_skills)

        programming = unique(programming)
        expertise = unique(expertise)

        # --------------------------------------------------------
        # Education
        # --------------------------------------------------------

        education = resume.get(
            "education",
            [],
        )

        if not isinstance(education, list):
            education = []

        education_html = ""

        for item in education:

            if not isinstance(item, dict):
                continue

            degree = esc(
                item.get("degree", "")
            )

            institution = esc(
                item.get("institution", "")
            )

            location = esc(
                item.get("location", "")
            )

            year = esc(
                item.get("year", "")
            )

            if not any(
                (
                    degree,
                    institution,
                    location,
                    year,
                )
            ):
                continue

            education_html += f"""
            <div class="education-item">

                {
                    f'<div class="education-degree"><strong>{degree}</strong></div>'
                    if degree
                    else ""
                }

                {
                    f'<div>{year}</div>'
                    if year
                    else ""
                }

                {
                    f'<div>{institution}</div>'
                    if institution
                    else ""
                }

                {
                    f'<div>{location}</div>'
                    if location
                    else ""
                }

            </div>
            """

        # --------------------------------------------------------
        # Certifications
        # --------------------------------------------------------

        certifications = unique(
            clean_list(
                resume.get(
                    "certifications",
                    [],
                )
            )
        )

        certifications_html = ""

        for cert in certifications:

            certifications_html += f"""
            <p class="certificate-item">
                <strong>{esc(cert)}</strong>
            </p>
            """

        # --------------------------------------------------------
        # Publications / research / awards
        # --------------------------------------------------------

        additional_highlights = unique(
            clean_list(
                resume.get(
                    "additional_highlights",
                    [],
                )
            )
        )

        highlights_html = ""

        for item in additional_highlights:

            highlights_html += f"""
            <p class="additional-item">
                {esc(item)}
            </p>
            """

        # --------------------------------------------------------
        # Summary
        # --------------------------------------------------------

        summary = resume.get(
            "professional_summary",
            "",
        )

        if isinstance(summary, list):

            summary_items = clean_list(
                summary
            )

        elif isinstance(summary, str):

            summary_items = (
                [summary.strip()]
                if summary.strip()
                else []
            )

        else:

            summary_items = []

        summary_html = ""

        for item in summary_items:

            summary_html += f"""
            <li>{esc(item)}</li>
            """

        # --------------------------------------------------------
        # Skill Summary
        # --------------------------------------------------------

        skill_summary = resume.get(
            "skill_summary",
            [],
        )

        skill_summary = clean_list(
            skill_summary
        )

        if not skill_summary:

            if programming:
                skill_summary.append(
                    "Programming and scripting: "
                    + ", ".join(programming)
                    + "."
                )

            if expertise:
                skill_summary.append(
                    "Data, cloud, infrastructure, "
                    "and platform technologies: "
                    + ", ".join(expertise)
                    + "."
                )

        skill_summary_html = ""

        for item in skill_summary:

            skill_summary_html += f"""
            <li>{esc(item)}</li>
            """

        # --------------------------------------------------------
        # Programming sidebar
        # --------------------------------------------------------

        programming_html = ""

        for item in programming:

            programming_html += f"""
            <li>● {esc(item)}</li>
            """

        # --------------------------------------------------------
        # Expertise sidebar
        # --------------------------------------------------------

        expertise_html = ""

        for item in expertise:

            expertise_html += f"""
            <li>● {esc(item)}</li>
            """

        # --------------------------------------------------------
        # Experience
        # --------------------------------------------------------

        experience = resume.get(
            "experience",
            [],
        )

        if not isinstance(experience, list):
            experience = []

        experience_html = ""

        for exp in experience:

            if not isinstance(exp, dict):
                continue

            role = esc(
                exp.get("role", "")
            )

            company = esc(
                exp.get("company", "")
            )

            dates = esc(
                exp.get("dates", "")
            )

            location = esc(
                exp.get("location", "")
            )

            title_line = role

            if dates:

                if title_line:
                    title_line += (
                        f" - {dates}"
                    )
                else:
                    title_line = dates

            sub_line = company

            if location:

                if sub_line:
                    sub_line += (
                        f", {location}"
                    )
                else:
                    sub_line = location

            highlights = clean_list(
                exp.get("highlights", [])
            )

            bullets_html = ""

            for highlight in highlights:

                bullets_html += f"""
                <li>{esc(highlight)}</li>
                """

            experience_html += f"""
            <div class="experience-item">

                <div class="experience-title">
                    {title_line}
                </div>

                <div class="experience-company">
                    {sub_line}
                </div>

                {
                    f'''
                    <ul>
                        {bullets_html}
                    </ul>
                    '''
                    if bullets_html
                    else ""
                }

            </div>
            """

        # --------------------------------------------------------
        # Address HTML
        # --------------------------------------------------------

        address_html = esc(
            address
        ).replace(
            "\n",
            "<br>",
        )

        # --------------------------------------------------------
        # Final HTML
        # --------------------------------------------------------

        return f"""<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>{esc(name)} - Resume</title>

<style>

* {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    font-family:
        'Segoe UI',
        Tahoma,
        Geneva,
        Verdana,
        sans-serif;
}}

body {{
    background: #ffffff;
    color: #111111;
    line-height: 1.25;
    padding: 0;
}}

.resume-container {{
    width: 210mm;
    min-height: 297mm;
    margin: 0 auto;
    padding: 10mm 11mm 9mm 11mm;
    background: #ffffff;

    display: grid;
    grid-template-columns: 36% 64%;
    column-gap: 0;

    overflow: hidden;
}}

.sidebar {{
    background: #ffffff;
    color: #111111;
    padding: 0 10mm 0 0;
    border-right: 1px solid #d9d9d9;
}}

.main-content {{
    padding: 0 0 0 9mm;
}}

.sidebar h1 {{
    font-size: 18px;
    line-height: 1.05;
    letter-spacing: 0.3px;
    text-transform: uppercase;
    margin-bottom: 9px;
    color: #111111;
}}

.sidebar h2,
.main-content h2 {{
    font-size: 10.5px;
    line-height: 1.1;
    text-transform: none;
    color: #111111;
    border-bottom: 1px solid #222222;
    padding-bottom: 2px;
    margin-top: 8px;
    margin-bottom: 5px;
    letter-spacing: 0;
    font-weight: 700;
}}

.sidebar p,
.sidebar li {{
    font-size: 8.4px;
    line-height: 1.22;
    color: #222222;
    margin-bottom: 3px;
    word-wrap: break-word;
    list-style: none;
}}

.sidebar ul {{
    padding-left: 0;
    margin-bottom: 5px;
}}

.main-content p,
.main-content li {{
    font-size: 8.8px;
    line-height: 1.22;
    color: #222222;
    margin-bottom: 3px;
}}

.main-content ul {{
    padding-left: 13px;
    margin-bottom: 5px;
}}

.experience-item {{
    margin-bottom: 7px;
    break-inside: avoid;
    page-break-inside: avoid;
}}

.experience-title {{
    font-weight: 700;
    font-size: 9.4px;
    line-height: 1.15;
    color: #111111;
}}

.experience-company {{
    font-size: 8.8px;
    line-height: 1.15;
    color: #333333;
    font-weight: 600;
    margin-bottom: 2px;
}}

.experience-item ul {{
    padding-left: 13px;
    margin-bottom: 0;
}}

.experience-item li {{
    margin-bottom: 2px;
}}

.education-item {{
    margin-bottom: 6px;
    font-size: 8.4px;
    line-height: 1.2;
    color: #222222;
    break-inside: avoid;
    page-break-inside: avoid;
}}

.education-degree {{
    color: #111111;
}}

.additional-item {{
    margin-bottom: 5px;
    line-height: 1.2;
}}

.certificate-item {{
    margin-bottom: 5px;
    line-height: 1.2;
}}

@page {{
    size: A4;
    margin: 0;
}}

@media print {{
    html,
    body {{
        width: 210mm;
        height: 297mm;
        margin: 0;
        padding: 0;
        background: #ffffff;
    }}

    .resume-container {{
        width: 210mm;
        height: 297mm;
        min-height: 297mm;
        margin: 0;
        padding: 10mm 11mm 9mm 11mm;
        box-shadow: none;
        border-radius: 0;
        overflow: hidden;
    }}

    .sidebar,
    .main-content,
    .experience-item,
    .education-item {{
        break-inside: avoid;
        page-break-inside: avoid;
    }}
}}

@media screen {{
    body {{
        padding: 16px;
        background: #f3f4f6;
    }}

    .resume-container {{
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
    }}
}}</style>

</head>

<body>

<div class="resume-container">

    <!-- ==================================================
         LEFT SIDEBAR
         ================================================== -->

    <div class="sidebar">

        <h1>
            {esc(name)}
        </h1>


        <!-- CONTACT -->

        <h2>
            Contact:
        </h2>

        {
            f'''
            <p>
                <strong>Address:</strong><br>
                {address_html}
            </p>
            '''
            if address
            else ""
        }

        {
            f'''
            <p style="margin-top: 6px;">
                <strong>Phone:</strong><br>
                {esc(phone)}
            </p>
            '''
            if phone
            else ""
        }

        {
            f'''
            <p style="margin-top: 6px;">
                <strong>Email:</strong><br>
                {esc(email)}
            </p>
            '''
            if email
            else ""
        }


        <!-- PROGRAMMING -->

        {
            f'''
            <h2>
                Programming:
            </h2>

            <ul>
                {programming_html}
            </ul>
            '''
            if programming_html
            else ""
        }


        <!-- EXPERTISE -->

        {
            f'''
            <h2>
                Expertise:
            </h2>

            <ul>
                {expertise_html}
            </ul>
            '''
            if expertise_html
            else ""
        }


        <!-- EDUCATION -->

        {
            f'''
            <h2>
                Education:
            </h2>

            {education_html}
            '''
            if education_html
            else ""
        }


        <!-- PUBLICATIONS / HIGHLIGHTS -->

        {
            f'''
            <h2>
                Publication / Highlights:
            </h2>

            {highlights_html}
            '''
            if highlights_html
            else ""
        }


        <!-- CERTIFICATIONS -->

        {
            f'''
            <h2>
                Certificate:
            </h2>

            {certifications_html}
            '''
            if certifications_html
            else ""
        }

    </div>


    <!-- ==================================================
         MAIN CONTENT
         ================================================== -->

    <div class="main-content">


        <!-- SUMMARY -->

        {
            f'''
            <h2>
                Summary:
            </h2>

            <ul>
                {summary_html}
            </ul>
            '''
            if summary_html
            else ""
        }


        <!-- SKILL SUMMARY -->

        {
            f'''
            <h2>
                Skill Summary:
            </h2>

            <ul>
                {skill_summary_html}
            </ul>
            '''
            if skill_summary_html
            else ""
        }


        <!-- EXPERIENCE -->

        {
            f'''
            <h2>
                Experience:
            </h2>

            {experience_html}
            '''
            if experience_html
            else ""
        }

    </div>

</div>

</body>

</html>
"""

    # ============================================================
    # JSON EXTRACTION
    # ============================================================

    @staticmethod
    def _json_object(content: str) -> str:
        """
        Extract a JSON object from model output.

        Supports:
        - plain JSON
        - ```json ... ```
        - JSON surrounded by explanatory text
        """

        if not isinstance(content, str):
            raise ValueError(
                "Model response was not text"
            )

        match = re.search(
            r"```(?:json)?\s*(\{.*\})\s*```",
            content,
            re.DOTALL,
        )

        if match:
            return match.group(1)

        start = content.find("{")
        end = content.rfind("}")

        if (
            start == -1
            or end == -1
            or end <= start
        ):
            raise ValueError(
                "No JSON object found"
            )

        return content[
            start:end + 1
        ]

    # ============================================================
    # SAFE INTERVIEW PROPOSALS
    # ============================================================

    @staticmethod
    def _safe_proposals(
        proposals: list[Any],
    ) -> list[dict[str, Any]]:

        valid_types = {
            "employment",
            "client",
            "project",
            "contribution",
            "skill",
            "achievement",
            "certification",
            "publication",
            "research",
            "authorship",
            "award",
            "education",
        }

        safe = []

        for proposal in proposals[:5]:

            if not isinstance(
                proposal,
                dict,
            ):
                continue

            entity_type = proposal.get(
                "entity_type"
            )

            summary = proposal.get(
                "summary"
            )

            data = proposal.get(
                "data",
                {},
            )

            if (
                entity_type in valid_types
                and isinstance(summary, str)
                and summary.strip()
                and isinstance(data, dict)
            ):
                safe.append(
                    {
                        "entity_type": entity_type,
                        "summary": summary.strip()[:600],
                        "data": data,
                    }
                )

        return safe

    # ============================================================
    # SAFE RESUME
    # ============================================================

    @staticmethod
    def _safe_resume(
        resume: dict[str, Any],
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:

        def text(
            value: Any,
            limit: int = 1000,
        ) -> str:

            if not isinstance(
                value,
                str,
            ):
                return ""

            return value.strip()[:limit]

        def string_list(
            value: Any,
            maximum: int = 30,
            limit: int = 500,
        ) -> list[str]:

            if not isinstance(
                value,
                list,
            ):
                return []

            result = []

            for item in value[:maximum]:

                if not isinstance(
                    item,
                    str,
                ):
                    continue

                item = item.strip()[:limit]

                if item:
                    result.append(item)

            return result

        # --------------------------------------------------------
        # Skills
        # --------------------------------------------------------

        core_skills: Dict[
            str,
            List[str],
        ] = {}

        raw_core_skills = resume.get(
            "core_skills"
        )

        if isinstance(
            raw_core_skills,
            dict,
        ):

            for category, items in raw_core_skills.items():

                category_name = text(
                    category,
                    80,
                )

                if not category_name:
                    continue

                if isinstance(
                    items,
                    list,
                ):

                    values = string_list(
                        items,
                        30,
                        300,
                    )

                    if values:
                        core_skills[
                            category_name
                        ] = values

        if not core_skills:

            flat_skills = string_list(
                resume.get("skills"),
                50,
                300,
            )

            if flat_skills:
                core_skills[
                    "Expertise"
                ] = flat_skills

        # --------------------------------------------------------
        # Experience
        # --------------------------------------------------------

        safe_experience = []

        raw_experience = resume.get(
            "experience"
        )

        if isinstance(
            raw_experience,
            list,
        ):

            for entry in raw_experience[:20]:

                if not isinstance(
                    entry,
                    dict,
                ):
                    continue

                highlights = string_list(
                    entry.get(
                        "highlights"
                    ),
                    15,
                    700,
                )

                safe_experience.append(
                    {
                        "role": text(
                            entry.get("role"),
                            150,
                        ),
                        "company": text(
                            entry.get("company"),
                            150,
                        ),
                        "location": text(
                            entry.get("location"),
                            120,
                        ),
                        "dates": text(
                            entry.get("dates"),
                            100,
                        ),
                        "highlights": highlights,
                    }
                )

        # --------------------------------------------------------
        # Education
        # --------------------------------------------------------

        safe_education = []

        raw_education = resume.get(
            "education",
            [],
        )

        if isinstance(
            raw_education,
            list,
        ):

            for item in raw_education[:10]:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                safe_education.append(
                    {
                        "degree": text(
                            item.get("degree"),
                            200,
                        ),
                        "institution": text(
                            item.get("institution"),
                            200,
                        ),
                        "location": text(
                            item.get("location"),
                            120,
                        ),
                        "year": text(
                            item.get("year"),
                            20,
                        ),
                    }
                )

        # --------------------------------------------------------
        # Final result
        # --------------------------------------------------------

        result = {
            "headline": (
                text(
                    resume.get("headline"),
                    160,
                )
                or "Lead Data Engineer"
            ),
            "professional_summary": text(
                resume.get(
                    "professional_summary"
                ),
                1500,
            ),
            "core_skills": core_skills,
            "skills": string_list(
                resume.get("skills"),
                50,
                300,
            ),
            "skill_summary": string_list(
                resume.get(
                    "skill_summary"
                ),
                15,
                500,
            ),
            "experience": safe_experience,
            "certifications": string_list(
                resume.get(
                    "certifications"
                ),
                20,
                300,
            ),
            "education": safe_education,
            "additional_highlights": string_list(
                resume.get(
                    "additional_highlights"
                ),
                20,
                1000,
            ),
        }

        # If Ollama returned a valid resume with experience,
        # use it.
        if safe_experience:
            return result

        # Otherwise use deterministic fallback.
        return OllamaProvider._fallback_resume(
            records
        )

    # ============================================================
    # SAFE JOB PACKAGE
    # ============================================================

    @staticmethod
    def _safe_job_package(
        package: dict[str, Any],
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:

        def text(
            value: Any,
            limit: int = 4000,
        ) -> str:

            if not isinstance(
                value,
                str,
            ):
                return ""

            return value.strip()[:limit]

        def string_list(
            value: Any,
            maximum: int = 30,
            limit: int = 300,
        ) -> list[str]:

            if not isinstance(
                value,
                list,
            ):
                return []

            return [
                text(item, limit)
                for item in value[:maximum]
                if text(item, limit)
            ]

        raw_resume = package.get(
            "resume"
        )

        if isinstance(
            raw_resume,
            dict,
        ):

            safe_resume = (
                OllamaProvider._safe_resume(
                    raw_resume,
                    records,
                )
            )

        else:

            safe_resume = (
                OllamaProvider._fallback_resume(
                    records
                )
            )

        safe_resume = (
            OllamaProvider._condense_for_one_page(
                safe_resume
            )
        )

        cover_letter = text(
            package.get(
                "cover_letter"
            ),
            5000,
        )

        keyword_matches = string_list(
            package.get(
                "keyword_matches"
            ),
            25,
            100,
        )

        gap_analysis = (
            OllamaProvider._safe_gap_analysis(
                package.get(
                    "gap_analysis"
                )
            )
        )

        if not cover_letter:
            return (
                OllamaProvider._fallback_job_package(
                    records
                )
            )

        return {
            "resume": safe_resume,
            "cover_letter": cover_letter,
            "keyword_matches": keyword_matches,
            "gap_analysis": gap_analysis,
        }

    # ============================================================
    # ONE PAGE RESUME
    # ============================================================

    @staticmethod
    def _condense_for_one_page(
        resume: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Normalize any resume (master or tailored) to the content budget
        required by the single-page A4 reference layout.

        This is intentionally deterministic. It does not invent or rewrite
        career facts; it only limits the amount of content rendered.
        """

        def as_list(value: Any) -> list[Any]:
            return value if isinstance(value, list) else []

        # ------------------------------------------------------------
        # EXPERIENCE
        # ------------------------------------------------------------
        experience = []

        for index, entry in enumerate(
            as_list(resume.get("experience"))
        ):
            if not isinstance(entry, dict):
                continue

            # Give the newest three roles slightly more room.
            bullet_limit = 3 if index < 3 else 2

            highlights = [
                item.strip()
                for item in as_list(entry.get("highlights"))
                if isinstance(item, str) and item.strip()
            ]

            experience.append(
                {
                    **entry,
                    "highlights": highlights[:bullet_limit],
                }
            )

            if len(experience) >= 5:
                break

        # ------------------------------------------------------------
        # SKILLS
        # ------------------------------------------------------------
        core_skills = resume.get("core_skills")
        if not isinstance(core_skills, dict):
            core_skills = {}

        compact_core_skills: dict[str, list[str]] = {}

        for category, items in core_skills.items():
            if not isinstance(items, list):
                continue

            values = []
            seen = set()

            for item in items:
                if not isinstance(item, str):
                    continue

                item = item.strip()
                if not item:
                    continue

                key = re.sub(r"\W+", "", item.lower())
                if key in seen:
                    continue

                seen.add(key)
                values.append(item)

            if not values:
                continue

            category_name = str(category).strip()
            category_lower = category_name.lower()

            if any(
                keyword in category_lower
                for keyword in (
                    "programming",
                    "language",
                    "languages",
                    "program",
                )
            ):
                compact_core_skills[category_name] = values[:7]
            else:
                compact_core_skills[category_name] = values[:10]

        # ------------------------------------------------------------
        # SUMMARY / SKILL SUMMARY
        # ------------------------------------------------------------
        summary = resume.get("professional_summary", "")

        if isinstance(summary, list):
            summary = " ".join(
                item.strip()
                for item in summary
                if isinstance(item, str) and item.strip()
            )

        summary = summary.strip() if isinstance(summary, str) else ""

        skill_summary = [
            item.strip()
            for item in as_list(resume.get("skill_summary"))
            if isinstance(item, str) and item.strip()
        ][:2]

        return {
            **resume,
            "professional_summary": summary,
            "core_skills": compact_core_skills,
            "skill_summary": skill_summary,
            "experience": experience,
            "certifications": [
                item
                for item in as_list(resume.get("certifications"))
                if isinstance(item, str) and item.strip()
            ][:4],
            "education": [
                item
                for item in as_list(resume.get("education"))
                if isinstance(item, dict)
            ][:2],
            "additional_highlights": [
                item
                for item in as_list(resume.get("additional_highlights"))
                if isinstance(item, str) and item.strip()
            ][:2],
        }

    # ============================================================
    # SAFE GAP ANALYSIS
    # ============================================================

    @staticmethod
    def _safe_gap_analysis(
        gap_analysis: Any,
    ) -> dict[str, Any]:

        def text(
            value: Any,
            limit: int = 400,
        ) -> str:

            if not isinstance(
                value,
                str,
            ):
                return ""

            return value.strip()[:limit]

        def string_list(
            value: Any,
            maximum: int = 15,
            limit: int = 300,
        ) -> list[str]:

            if not isinstance(
                value,
                list,
            ):
                return []

            return [
                text(item, limit)
                for item in value[:maximum]
                if text(item, limit)
            ]

        if not isinstance(
            gap_analysis,
            dict,
        ):
            return {
                "match_score": None,
                "score_reasoning": "",
                "strengths": [],
                "gaps": [],
                "suggestions": [],
            }

        raw_score = gap_analysis.get(
            "match_score"
        )

        score = None

        if (
            isinstance(
                raw_score,
                (int, float),
            )
            and not isinstance(
                raw_score,
                bool,
            )
        ):
            score = max(
                0,
                min(
                    100,
                    round(raw_score),
                ),
            )

        return {
            "match_score": score,
            "score_reasoning": text(
                gap_analysis.get(
                    "score_reasoning"
                ),
                400,
            ),
            "strengths": string_list(
                gap_analysis.get(
                    "strengths"
                )
            ),
            "gaps": string_list(
                gap_analysis.get(
                    "gaps"
                )
            ),
            "suggestions": string_list(
                gap_analysis.get(
                    "suggestions"
                )
            ),
        }

    # ============================================================
    # FALLBACK JOB PACKAGE
    # ============================================================

    @staticmethod
    def _fallback_job_package(
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:

        resume = (
            OllamaProvider._condense_for_one_page(
                OllamaProvider._fallback_resume(
                    records
                )
            )
        )

        cover_letter = (
            "I was unable to draft a tailored cover letter "
            "while the local model is unavailable. Please try "
            "again once Ollama is reachable; your approved "
            "Career Vault facts were not changed."
        )

        gap_analysis = {
            "match_score": None,
            "score_reasoning": (
                "Fit could not be assessed while "
                "the local model is unavailable."
            ),
            "strengths": [],
            "gaps": [],
            "suggestions": [
                (
                    "Try again once Ollama is reachable "
                    "to get a fit score and gap analysis "
                    "for this posting."
                )
            ],
        }

        return {
            "resume": resume,
            "cover_letter": cover_letter,
            "keyword_matches": [],
            "gap_analysis": gap_analysis,
        }

    # ============================================================
    # FALLBACK RESUME
    # ============================================================

    @staticmethod
    def _fallback_resume(
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Build a deterministic resume from approved facts only.

        IMPORTANT:
        This function deliberately does NOT contain:
        - old resume projects
        - old education
        - old certifications
        - old publications
        - old skills
        - invented years of experience

        It only uses `records`.
        """

        def clean(
            value: Any,
        ) -> str:

            if value is None:
                return ""

            return str(value).strip()

        def unique(
            items: list[str],
        ) -> list[str]:

            result = []
            seen = set()

            for item in items:

                item = clean(item)

                if not item:
                    continue

                key = re.sub(
                    r"\W+",
                    "",
                    item.lower(),
                )

                if key in seen:
                    continue

                seen.add(key)
                result.append(item)

            return result

        def normalize_company(
            company: str,
        ) -> str:

            company = clean(company)

            if not company:
                return ""

            normalized = re.sub(
                r"\s+",
                " ",
                company.lower(),
            ).strip()

            aliases = {
                "pythian": "Pythian Technology",
                "pythian technology": "Pythian Technology",

                "cuelogic": (
                    "Cuelogic Technology | LTI Company"
                ),
                "cuelogic technology": (
                    "Cuelogic Technology | LTI Company"
                ),
                "cuelogic technologies": (
                    "Cuelogic Technology | LTI Company"
                ),

                "cognizant": (
                    "Cognizant Technology Solutions"
                ),
                "cognizant technology solutions": (
                    "Cognizant Technology Solutions"
                ),
            }

            return aliases.get(
                normalized,
                company,
            )

        companies: dict[
            str,
            dict[str, Any],
        ] = {}

        skills: list[str] = []
        certifications: list[str] = []
        additional_highlights: list[str] = []
        education: list[dict[str, str]] = []

        # ========================================================
        # PROCESS APPROVED RECORDS
        # ========================================================

        for record in records:

            if not isinstance(
                record,
                dict,
            ):
                continue

            rec_type = clean(
                record.get("type")
            ).lower()

            summary = clean(
                record.get("summary")
            )

            data = record.get(
                "data",
                {},
            )

            if not isinstance(
                data,
                dict,
            ):
                data = {}

            # ----------------------------------------------------
            # SKILL
            # ----------------------------------------------------

            if rec_type == "skill":

                if summary:
                    skills.append(summary)

                continue

            # ----------------------------------------------------
            # CERTIFICATION
            # ----------------------------------------------------

            if rec_type == "certification":

                if summary:
                    certifications.append(
                        summary
                    )

                continue

            # ----------------------------------------------------
            # EDUCATION
            # ----------------------------------------------------

            if rec_type == "education":

                education.append(
                    {
                        "degree": clean(
                            data.get(
                                "degree"
                            )
                            or summary
                        ),
                        "institution": clean(
                            data.get(
                                "institution"
                            )
                        ),
                        "location": clean(
                            data.get(
                                "location"
                            )
                        ),
                        "year": clean(
                            data.get(
                                "year"
                            )
                        ),
                    }
                )

                continue

            # ----------------------------------------------------
            # PUBLICATION / RESEARCH / AWARD
            # ----------------------------------------------------

            if rec_type in {
                "achievement",
                "publication",
                "research",
                "authorship",
                "award",
            }:

                if summary:
                    additional_highlights.append(
                        summary
                    )

                continue

            # ----------------------------------------------------
            # EXPERIENCE
            # ----------------------------------------------------

            if rec_type not in {
                "employment",
                "client",
                "project",
                "contribution",
            }:
                continue

            company = clean(
                data.get("company")
                or data.get("employer")
                or data.get("organization")
            )

            # ----------------------------------------------------
            # Try to identify employer from summary.
            # This is only used when the structured record
            # does not contain company information.
            # ----------------------------------------------------

            if not company:

                known_companies = [
                    "Pythian Technology",
                    "Pythian",
                    "Cuelogic Technology",
                    "Cuelogic Technologies",
                    "Cuelogic",
                    "Cognizant Technology Solutions",
                    "Cognizant",
                ]

                for known_company in known_companies:

                    if (
                        known_company.lower()
                        in summary.lower()
                    ):
                        company = known_company
                        break

            company = normalize_company(
                company
            )

            if not company:
                company = "Professional Experience"

            company_key = re.sub(
                r"\W+",
                "",
                company.lower(),
            )

            # ----------------------------------------------------
            # Create employer only once.
            # ----------------------------------------------------

            if company_key not in companies:

                companies[company_key] = {
                    "role": "",
                    "company": company,
                    "location": "",
                    "dates": "",
                    "highlights": [],
                }

            entry = companies[
                company_key
            ]

            # ----------------------------------------------------
            # Extract structured employment details.
            # ----------------------------------------------------

            role = clean(
                data.get("role")
                or data.get("job_title")
                or data.get("title")
            )

            dates = clean(
                data.get("dates")
                or data.get("date_range")
                or data.get("period")
            )

            location = clean(
                data.get("location")
            )

            if role:

                # Prefer an explicit employment role.
                # Don't overwrite it with project records.
                if not entry["role"]:
                    entry["role"] = role

            if dates:

                if not entry["dates"]:
                    entry["dates"] = dates

            if location:

                if not entry["location"]:
                    entry["location"] = location

            # ----------------------------------------------------
            # Employment record
            # ----------------------------------------------------

            if rec_type == "employment":

                if summary:

                    # Only add summary if it doesn't duplicate
                    # role/company information.
                    summary_key = re.sub(
                        r"\W+",
                        "",
                        summary.lower(),
                    )

                    existing_keys = {
                        re.sub(
                            r"\W+",
                            "",
                            str(h).lower(),
                        )
                        for h in entry[
                            "highlights"
                        ]
                    }

                    if (
                        summary_key
                        not in existing_keys
                    ):

                        # If summary is essentially only
                        # "Lead Data Engineer at Pythian",
                        # don't put that as a bullet.
                        is_job_identity = (
                            company.lower()
                            in summary.lower()
                            and (
                                " at "
                                in summary.lower()
                                or " | "
                                in summary
                                or " - "
                                in summary
                            )
                        )

                        if not is_job_identity:
                            entry[
                                "highlights"
                            ].append(summary)

            # ----------------------------------------------------
            # Project / client / contribution
            # ----------------------------------------------------

            else:

                if summary:

                    summary_key = re.sub(
                        r"\W+",
                        "",
                        summary.lower(),
                    )

                    existing_keys = {
                        re.sub(
                            r"\W+",
                            "",
                            str(h).lower(),
                        )
                        for h in entry[
                            "highlights"
                        ]
                    }

                    if (
                        summary_key
                        not in existing_keys
                    ):
                        entry[
                            "highlights"
                        ].append(summary)

                # ------------------------------------------------
                # If no summary exists, build a useful factual
                # highlight from structured data.
                # ------------------------------------------------

                if not summary:

                    structured_parts = []

                    for key in (
                        "client",
                        "project",
                        "responsibilities",
                        "contribution",
                        "tools",
                        "scope",
                        "outcome",
                        "achievement",
                    ):

                        value = data.get(key)

                        if isinstance(
                            value,
                            list,
                        ):

                            values = [
                                clean(v)
                                for v in value
                                if clean(v)
                            ]

                            value = (
                                ", ".join(values)
                                if values
                                else ""
                            )

                        value = clean(
                            value
                        )

                        if value:
                            structured_parts.append(
                                (
                                    f"{key.replace('_', ' ').title()}: "
                                    f"{value}"
                                )
                            )

                    if structured_parts:

                        entry[
                            "highlights"
                        ].append(
                            "; ".join(
                                structured_parts
                            )
                        )

        # ========================================================
        # CLEAN EXPERIENCE
        # ========================================================

        experience = []

        for entry in companies.values():

            cleaned_highlights = unique(
                entry.get(
                    "highlights",
                    [],
                )
            )

            entry["highlights"] = (
                cleaned_highlights
            )

            experience.append(
                entry
            )

        # ========================================================
        # CLEAN EVERYTHING
        # ========================================================

        skills = unique(
            skills
        )

        certifications = unique(
            certifications
        )

        additional_highlights = unique(
            additional_highlights
        )

        # ========================================================
        # EDUCATION DEDUPLICATION
        # ========================================================

        clean_education = []

        education_seen = set()

        for item in education:

            degree = clean(
                item.get("degree")
            )

            institution = clean(
                item.get("institution")
            )

            location = clean(
                item.get("location")
            )

            year = clean(
                item.get("year")
            )

            key = (
                degree.lower(),
                institution.lower(),
                year.lower(),
            )

            if key in education_seen:
                continue

            education_seen.add(key)

            clean_education.append(
                {
                    "degree": degree,
                    "institution": institution,
                    "location": location,
                    "year": year,
                }
            )

        # ========================================================
        # PROFESSIONAL SUMMARY
        # ========================================================

        summary_parts = []

        company_names = [
            entry.get("company")
            for entry in experience
            if entry.get("company")
        ]

        if company_names:

            summary_parts.append(
                "Data engineering professional "
                "with experience across "
                + ", ".join(
                    unique(company_names)
                )
                + "."
            )

        if skills:

            summary_parts.append(
                "Experienced with "
                + ", ".join(
                    skills[:8]
                )
                + "."
            )

        if not summary_parts:

            professional_summary = (
                "Data engineering professional "
                "with experience in data platforms "
                "and engineering."
            )

        else:

            professional_summary = (
                " ".join(
                    summary_parts
                )
            )

        # ========================================================
        # CORE SKILLS
        # ========================================================

        programming_keywords = {
            "python",
            "java",
            "sql",
            "javascript",
            "typescript",
            "scala",
            "perl",
            "shell",
            "bash",
            "nosql",
        }

        programming = []

        expertise = []

        for skill in skills:

            lower_skill = skill.lower()

            if any(
                keyword in lower_skill
                for keyword in programming_keywords
            ):

                programming.append(
                    skill
                )

            else:

                expertise.append(
                    skill
                )

        # ========================================================
        # FINAL FALLBACK RESUME
        # ========================================================

        return {
            "headline": (
                "Lead Data Engineer"
            ),

            "professional_summary": (
                professional_summary
            ),

            "core_skills": {
                "Programming": unique(
                    programming
                ),
                "Expertise": unique(
                    expertise
                ),
            },

            "skills": skills,

            "skill_summary": [],

            "experience": experience,

            "certifications": certifications,

            "education": clean_education,

            "additional_highlights": (
                additional_highlights
            ),
        }