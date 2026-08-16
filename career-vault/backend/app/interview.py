from dataclasses import dataclass


@dataclass(frozen=True)
class InterviewStage:
    key: str
    label: str
    objective: str
    opening_question: str


STAGES = [
    InterviewStage(
        "timeline",
        "Career timeline",
        "Create a complete list of every employer, job title, and approximate start/end date. Do not discuss projects yet.",
        "Please list every company you have worked for, in any order. For each one, include company name, job title(s), and approximate start and end dates.",
    ),
    InterviewStage(
        "responsibilities",
        "Role responsibilities",
        "For every role in the timeline, capture the complete recurring responsibilities, scope, domain, team, and position. Do not rank responsibilities.",
        "Now let’s document role responsibilities. Start with one company and role: what were all of your regular responsibilities, domain, team scope, and position?",
    ),
    InterviewStage(
        "projects",
        "Clients & projects",
        "For each employer, capture every client and every project/engagement, including short support work. For each: timeline, role, contribution, tools/skills, work performed, and outcomes.",
        "For your first company, please list every client and project engagement you worked on. We will then document each engagement one at a time.",
    ),
    InterviewStage(
        "professional_assets",
        "Skills & platforms",
        "Capture technical skills, cloud platforms, tools, languages, frameworks, operating systems, and domain expertise only. Ask about one skill group at a time.",
        "Let’s capture your skills first. Which cloud platforms, technologies, programming languages, tools, or domains have you worked with?",
    ),
    InterviewStage(
        "certifications",
        "Certifications",
        "Capture certifications only: name, issuing organization, issue/expiry date, credential ID, and relevant skills. Ask about one certification at a time.",
        "Now let’s capture certifications only. Please share one certification: its name, issuing organization, and approximate date.",
    ),
    InterviewStage(
        "achievements",
        "Achievements & recognition",
        "Capture awards, leadership, mentoring, promotions, talks, patents, and professional recognition only. Ask about one item at a time.",
        "Now let’s capture achievements and recognition. Please share one award, promotion, leadership contribution, mentoring activity, talk, or patent.",
    ),
    InterviewStage(
        "research_publications",
        "Research & publications",
        "Capture research, academic/professional publications, authored articles, papers, and books only. Ask about one item at a time.",
        "Now let’s capture research and publications. Please share one research project, article, paper, book, or other authored work.",
    ),
    InterviewStage(
        "education",
        "Education",
        "Capture education, degrees, institutions, dates, courses, thesis, and academic achievements.",
        "Please share your academic details: degrees, institutions, dates, relevant courses, thesis, or academic achievements.",
    ),
    InterviewStage(
        "public_presence",
        "Public work",
        "Capture GitHub repositories, portfolio projects, open-source work, blogs, and public professional profiles only. Ask about one link or project at a time.",
        "Finally, let’s capture public work. Please share one GitHub repository, portfolio project, open-source contribution, blog, or professional link.",
    ),
    InterviewStage(
        "review",
        "Completeness review",
        "Check for missing employers, clients, projects, contributions, skills, credentials, education, or public work. Ask only focused missing-data questions.",
        "We are reviewing your Career Vault for completeness. Is there any employer, client, project, achievement, credential, education item, or public work we have missed?",
    ),
]


def stage_for(key: str) -> InterviewStage:
    return next((stage for stage in STAGES if stage.key == key), STAGES[0])


def next_stage(key: str) -> InterviewStage | None:
    for index, stage in enumerate(STAGES):
        if stage.key == key and index + 1 < len(STAGES):
            return STAGES[index + 1]
    return None
