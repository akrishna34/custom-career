# Custom Career

> **Your career, structured once. Every opportunity, tailored from verified evidence.**

**Custom Career** is a privacy-first, local-first AI career platform that turns your professional experience into a structured **Career Vault** and uses that knowledge to evaluate job opportunities, identify skill gaps, retrieve relevant evidence, and generate tailored, ATS-friendly resumes.

The core idea is simple:

**Don't rewrite your career for every job. Build your career knowledge base once, then tailor it intelligently for every opportunity.**

---

## 🚀 Why Custom Career?

Traditional resume builders start with a resume.

Custom Career starts with **you**.

Your career contains far more information than can fit into a two-page resume:

* Projects
* Technical contributions
* Architecture decisions
* Technologies
* Skills and proficiency
* Certifications
* Business impact
* Metrics
* Client/domain experience
* Leadership
* Problem-solving examples
* Achievements
* Career goals
* Evidence supporting your claims

Instead of repeatedly reconstructing this information for every application, Custom Career maintains a structured **Career Vault** and retrieves only the most relevant evidence for a specific opportunity.

### The goal

```text
Your Career Knowledge
        ↓
   Career Vault
        ↓
   Job Description
        ↓
Requirement Extraction
        ↓
Evidence Retrieval
        ↓
Match & Gap Analysis
        ↓
Evidence-backed Resume
        ↓
Human Review
        ↓
     Export
```

---

# ✨ Core Principles

### 1. Evidence over hallucination

The system must never invent:

* Skills
* Projects
* Certifications
* Employment history
* Metrics
* Responsibilities
* Achievements

Every important resume claim should be traceable to approved career evidence.

### 2. Your data belongs to you

The MVP is designed to run entirely on your local machine.

Career information, conversations, job descriptions, and generated content stay local rather than being sent to a cloud AI provider.

### 3. AI assists; you remain in control

AI can:

* Ask questions
* Organize information
* Retrieve relevant evidence
* Analyze job requirements
* Explain skill gaps
* Draft resumes

But the user remains the final authority.

A resume is not exported until its claims have been validated and approved.

### 4. Structured career knowledge beats a static resume

A resume is an output.

The **Career Vault is the source of truth.**

---

# 🎯 Planned Capabilities

## Career Vault

Build a structured representation of your professional career.

The vault can contain:

* Career profile
* Employment history
* Projects
* Contributions
* Skills
* Certifications
* Achievements
* Evidence
* Career goals

The architecture is designed so that each user's career information remains isolated and ownership-aware.

---

## 🧠 Guided Career Interview

Instead of forcing users to complete a huge form, Custom Career uses a conversational interview.

Example:

```text
AI: Tell me about the most technically challenging project
    you worked on at your previous company.

User: I designed a Kafka-based observability pipeline...

AI: What was the scale?

User: Around 500 services...

AI: What problem did the existing architecture have?

User: Kafka retention was limited...

AI: What did you change?

User: We introduced an S3-based storage layer...

AI: What was the outcome?

User: We reduced dependency on Kafka retention and improved
    long-term debugging capabilities.
```

The AI proposes structured facts from the conversation.

The user then:

```text
Review → Correct → Approve → Store as Evidence
```

Unapproved conversational information is not treated as verified career data.

---

# 💼 Job Description Intelligence

Paste a job description and Custom Career extracts its requirements.

The system analyzes:

* Required technologies
* Preferred technologies
* Experience requirements
* Domain experience
* Leadership expectations
* Architecture responsibilities
* Certifications
* Seniority
* Other relevant requirements

Each requirement can then be matched against the Career Vault.

---

# 🔎 Evidence-Based Matching

Custom Career uses a hybrid retrieval approach:

1. Structured filtering
2. Keyword search
3. Semantic search
4. Evidence verification

The MVP uses SQLite FTS5 together with local embeddings rather than introducing a dedicated vector database prematurely.

### Example

Job requirement:

> Experience designing distributed event-driven systems using Kafka.

Career Vault:

```text
Project: Centralized Observability Pipeline

Evidence:
- Designed Kafka-based event ingestion
- Deployed Kafka Connect pipelines
- Implemented monitoring for consumer lag
- Designed long-term event storage
- Supported hundreds of services
```

Result:

```text
STRONG MATCH
```

The system should be able to show **why** the requirement matched rather than simply returning a similarity score.

---

# 📊 Job Readiness & Gap Analysis

Requirements are classified into four categories:

| Classification   | Meaning                                          |
| ---------------- | ------------------------------------------------ |
| 🟢 Strong Match  | Direct verified evidence exists                  |
| 🟡 Partial Match | Related or transferable experience exists        |
| 🔵 Learnable Gap | Missing today but realistically addressable      |
| 🔴 Critical Gap  | Important requirement with insufficient evidence |

This allows users to answer a more useful question than:

> "Can AI make my resume match this job?"

Instead:

> **"How strong is my actual evidence for this opportunity?"**

---

# 📝 Tailored Resume Generation

Once requirements and evidence are understood, Custom Career generates a job-specific resume draft.

The resume generation process is:

```text
Job Description
      ↓
Requirements
      ↓
Relevant Evidence
      ↓
Evidence Selection
      ↓
Resume Draft
      ↓
Claim Validation
      ↓
User Review
      ↓
Approval
      ↓
DOCX / PDF
```

The system should optimize for:

* ATS compatibility
* Relevance
* Conciseness
* Evidence-backed claims
* Appropriate seniority
* Job-specific terminology
* Strong achievement framing

It should **not** optimize by inventing experience.

---

# 🤖 Bounded Career Agent

Custom Career is designed around a bounded agent rather than an unrestricted autonomous agent.

The agent operates through approved tools such as:

```text
get_job_requirements()
search_career_evidence()
get_evidence_details()
calculate_experience_years()
create_requirement_assessment()
create_gap_plan()
create_resume_draft()
validate_resume_claims()
request_user_approval()
export_approved_resume()
```

The architecture limits the agent to approved operations and records tool calls for auditability.

### Agent flow

```text
User Goal
   ↓
Agent
   ↓
Select Approved Tool
   ↓
Deterministic Tool Execution
   ↓
Read Result
   ↓
Next Step
   ↓
User-facing Result
```

The MVP architecture specifies limits such as a maximum of eight tool calls per run and schema validation for tool inputs/outputs.

---

# 🔐 Privacy & Security

Privacy is a core architectural requirement rather than an optional feature.

The MVP is designed around:

* Local execution
* Local SQLite database
* Local Ollama inference
* User ownership boundaries
* Argon2 password hashing
* Secure sessions
* Audit logging
* Local-only network binding

The browser, FastAPI backend, and Ollama service are intended to remain bound to `127.0.0.1` during the MVP. Ollama's port should never be exposed publicly.

### Important

**Never expose the Ollama endpoint directly to the public internet.**

---

# 🏗️ Architecture

The planned architecture is:

```text
┌─────────────────────────────┐
│       React + TypeScript    │
│          Web UI             │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│          FastAPI            │
│          Backend            │
├─────────────────────────────┤
│ Authentication              │
│ Career Services             │
│ Job Analysis                │
│ Matching                    │
│ Resume Generation           │
│ Career Agent                │
└───────┬───────────┬─────────┘
        │           │
        ▼           ▼
┌────────────┐   ┌────────────────┐
│  SQLite    │   │ Search Index    │
│ Source of  │   │ FTS5 +          │
│ Truth      │   │ Embeddings      │
└────────────┘   └────────────────┘
        │
        ▼
┌─────────────────────────────┐
│       Provider Layer        │
├─────────────────────────────┤
│ Ollama LLM                  │
│ Local Embeddings            │
│ Local File Storage          │
└──────────────┬──────────────┘
               │
               ▼
        ┌─────────────┐
        │   Ollama    │
        │  localhost  │
        ├─────────────┤
        │ Qwen3 4B    │
        │ EmbeddingGemma │
        └─────────────┘
```

The architecture intentionally separates application logic from AI providers so that local models can later be replaced with cloud or self-hosted providers without rewriting the core domain logic.

---

# 🛠️ Technology Stack

| Layer            | MVP Technology             |
| ---------------- | -------------------------- |
| Frontend         | React + TypeScript + Vite  |
| Backend          | Python 3.12 + FastAPI      |
| Database         | SQLite                     |
| ORM              | SQLAlchemy                 |
| Migrations       | Alembic                    |
| Search           | SQLite FTS5                |
| Semantic Search  | Local embeddings           |
| LLM Runtime      | Ollama                     |
| Generation Model | Qwen3 4B                   |
| Embedding Model  | EmbeddingGemma             |
| Authentication   | Local accounts + Argon2    |
| Background Jobs  | SQLite-backed worker       |
| Resume Export    | DOCX + PDF                 |
| Future Database  | PostgreSQL + pgvector      |
| Future AI        | Cloud/self-hosted provider |

These technology choices are documented in the current MVP architecture.

---

# 💻 Local Development

## Prerequisites

The current bootstrap script is designed specifically for:

* macOS
* Apple Silicon (`arm64`)
* At least 12 GB free disk space
* Internet access for initial dependency/model downloads

The setup script checks these requirements before proceeding.

---

## Quick Setup

Clone the repository:

```bash
git clone https://github.com/akrishna34/custom-career.git
cd custom-career
```

Run the local MVP bootstrap:

```bash
bash bootstrap-local-mvp.sh
```

When prompted, type:

```text
INSTALL
```

The bootstrap process installs/configures:

* Apple Command Line Tools
* Homebrew
* Git
* Python 3.12
* Node.js
* Ollama
* Qwen3 4B
* EmbeddingGemma

and verifies that Ollama is responding locally.

---

## Verify Ollama

```bash
ollama list
```

Check the local API:

```bash
curl http://127.0.0.1:11434/api/tags
```

The expected models are:

```text
qwen3:4b
embeddinggemma:300m-qat-q4_0
```

The bootstrap script also performs an embedding health check before declaring the local AI infrastructure ready.

---

# 📁 Planned Repository Structure

```text
custom-career/
│
├── frontend/
│   └── React + TypeScript application
│
├── backend/
│   └── app/
│       ├── api/
│       ├── core/
│       ├── db/
│       ├── domains/
│       ├── agent/
│       ├── providers/
│       ├── interview/
│       ├── documents/
│       └── workers/
│
├── data/
│   └── Local application data
│
├── docs/
│
├── bootstrap-local-mvp.sh
├── LOCAL_SETUP.md
├── career-vault-mvp-architecture.md
└── README.md
```

The `data/` directory is intended to remain outside version control because it can contain private career information and the local database.

---

# 🗺️ Development Roadmap

## Milestone 0 — Local Foundation

* [ ] Local development environment
* [ ] React application
* [ ] FastAPI backend
* [ ] SQLite database
* [ ] Alembic migrations
* [ ] Configuration management
* [ ] Ollama provider
* [ ] Embedding provider
* [ ] Health endpoint

**Success criteria:** UI and API run locally and the backend successfully communicates with Ollama.

---

## Milestone 1 — Career Vault

* [ ] Local authentication
* [ ] Career profile
* [ ] Employment history
* [ ] Projects
* [ ] Contributions
* [ ] Skills
* [ ] Certifications
* [ ] Evidence model
* [ ] Guided Career Interview
* [ ] AI fact proposals
* [ ] User approval workflow
* [ ] Ownership/security tests

**Success criteria:** a user can build and maintain a detailed Career Vault through guided conversation.

---

## Milestone 2 — Job Intelligence

* [ ] Job description storage
* [ ] Requirement extraction
* [ ] Requirement categorization
* [ ] FTS5 search
* [ ] Semantic retrieval
* [ ] Evidence matching
* [ ] Deterministic scoring
* [ ] Gap analysis
* [ ] Job readiness report

**Success criteria:** a pasted job description produces an evidence-linked assessment.

---

## Milestone 3 — Resume Intelligence

* [ ] Evidence selection
* [ ] Resume generation
* [ ] Resume claim model
* [ ] Claim validation
* [ ] Resume editing
* [ ] User approval
* [ ] DOCX export
* [ ] PDF export

**Success criteria:** an approved resume contains only traceable, evidence-backed claims.

---

## Milestone 4 — Career Agent

* [ ] Agent orchestration
* [ ] Tool registry
* [ ] Tool schemas
* [ ] Run state
* [ ] Audit log
* [ ] Tool-call limits
* [ ] Human approval checkpoints
* [ ] End-to-end assessment → resume workflow

**Success criteria:** the agent can complete the workflow without unrestricted access to user data or unsupported career claims.

---

# 🚫 Intentionally Out of Scope for the MVP

The initial version deliberately avoids unnecessary complexity.

Not included initially:

* Public hosting
* External user registration
* Job-board scraping
* Automatic job applications
* Mobile application
* Payments
* Subscriptions
* Enterprise SSO
* Multiple autonomous agents
* Kubernetes
* Docker
* Dedicated vector database
* Cloud infrastructure
* Resume upload/parsing

These can be considered after the local MVP proves the core workflow.

---

# 🌐 Future Architecture

The local-first architecture is designed to evolve into a cloud deployment without rewriting the core product.

Potential future replacements:

```text
MVP                         Future
────────────────────────────────────────────
SQLite                  →   PostgreSQL
SQLite FTS5             →   PostgreSQL FTS
Local embeddings        →   pgvector
Ollama                  →   Cloud/self-hosted LLM
Local storage           →   Object/blob storage
SQLite worker           →   Redis/managed queue
Local authentication    →   OIDC/Auth provider
localhost               →   Cloud deployment
```

The provider abstraction is intentionally designed as the migration boundary.

---

# 🧩 API Direction

The planned API includes endpoints for:

```text
Authentication
POST /auth/login
POST /auth/logout
GET  /me

Career
GET   /career/profile
PATCH /career/employments/{id}
PATCH /career/projects/{id}

Career Interview
POST /career-interviews
POST /career-interviews/{id}/messages
GET  /career-interviews/{id}

Fact Approval
POST /fact-proposals/{id}/approve
POST /fact-proposals/{id}/reject

Jobs
POST /jobs
GET  /jobs/{id}
POST /jobs/{id}/analyze
GET  /jobs/{id}/assessment

Agent
POST /agent/runs
GET  /agent/runs/{id}

Resume
POST /resumes
GET  /resumes/{id}
POST /resumes/{id}/validate
POST /resumes/{id}/approve
POST /resumes/{id}/export
```

These endpoints correspond to the current architecture blueprint and are subject to change during implementation.

---

# 🔒 Security Rules

The following rules are fundamental to the project:

1. Never expose Ollama publicly.
2. Never trust a `user_id` supplied by the browser.
3. Always derive ownership from the authenticated session.
4. Never store passwords using custom cryptography.
5. Use Argon2 for password hashing.
6. Keep private career data out of Git.
7. Never generate unsupported career claims.
8. Require user approval before resume export.
9. Record important actions in the audit log.
10. Keep AI-generated facts unverified until explicitly approved.

These rules are part of the MVP architecture rather than optional enhancements.

---

# 🧪 Product Philosophy

Custom Career is not intended to be another generic:

> "Paste your resume → paste JD → get AI resume."

Instead, it is designed as a **personal career intelligence system**.

The long-term model is:

```text
                    ┌──────────────────────┐
                    │    Career Vault      │
                    │                      │
                    │ Projects             │
                    │ Skills               │
                    │ Experience           │
                    │ Achievements         │
                    │ Evidence             │
                    │ Certifications       │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
        Job Analysis      Resume Builder   Career Planning
              │                │                │
              ▼                ▼                ▼
        Gap Analysis       Tailoring       Skill Roadmap
              │                │                │
              └────────────────┼────────────────┘
                               ▼
                       Better Decisions
```

The resume is only one application of the underlying career knowledge.

---

# ⚠️ Current Status

**Status: Early MVP / Architecture & Local Infrastructure**

The repository currently contains the local-first architecture, setup documentation, bootstrap infrastructure, and implementation patches. The full React/FastAPI application is the next implementation phase.

The current architecture explicitly recommends starting with **Milestone 0** before implementing the agent or resume templates.

---

# 🤝 Contributing

This project is currently primarily being developed as a personal career intelligence platform.

As the architecture stabilizes, contribution guidelines and development documentation will be added.

---

# 📜 License

License information will be added as the project moves toward a broader release.

---

# ⭐ Vision

> **Build a permanent, private, evidence-backed representation of your professional career — and let AI adapt that knowledge to whatever opportunity comes next.**

Your career should not live inside a resume.

**The resume should be generated from your career.**
