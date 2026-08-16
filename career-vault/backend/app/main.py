from contextlib import asynccontextmanager
from hashlib import sha256
import secrets

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import data_directory, settings
from app.db import (
    AccessSession,
    CareerInterviewMessage,
    CareerInterviewSession,
    CareerRecord,
    FactProposal,
    ResumeDraft,
    SessionLocal,
    User,
    initialize_database,
)
from app.interview import STAGES, next_stage, stage_for
from app.providers.ollama import OllamaProvider
from app.resume_document import render_master_resume

password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


class SystemStatusResponse(BaseModel):
    app_name: str
    local_only: bool
    database: str
    ollama_reachable: bool
    generation_model_available: bool
    embedding_model_available: bool
    installed_models: list[str]


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=200)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class AuthResponse(BaseModel):
    token: str
    username: str
    display_name: str


class InterviewMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class ProposalDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")


def serialize_resume(draft: ResumeDraft) -> dict:
    return {"id": draft.id, "type": draft.resume_type, "content": draft.content, "created_at": draft.created_at.isoformat()}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def issue_token(user: User, db: Session) -> AuthResponse:
    token = secrets.token_urlsafe(32)
    db.add(AccessSession(user_id=user.id, token_hash=token_digest(token)))
    db.commit()
    return AuthResponse(token=token, username=user.username, display_name=user.display_name)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in is required")
    session = db.scalar(select(AccessSession).where(AccessSession.token_hash == token_digest(credentials.credentials)))
    user = db.get(User, session.user_id) if session else None
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return user


def serialize_session(session: CareerInterviewSession, db: Session) -> dict:
    messages = db.scalars(
        select(CareerInterviewMessage)
        .where(CareerInterviewMessage.session_id == session.id)
        .order_by(CareerInterviewMessage.created_at)
    ).all()
    proposals = db.scalars(
        select(FactProposal).where(FactProposal.session_id == session.id).order_by(FactProposal.created_at)
    ).all()
    current_stage = stage_for(session.current_topic)
    return {
        "id": session.id,
        "status": session.status,
        "stage": current_stage.key,
        "stage_label": current_stage.label,
        "stages": [{"key": item.key, "label": item.label} for item in STAGES],
        "messages": [{"id": item.id, "role": item.role, "content": item.content} for item in messages],
        "proposals": [
            {"id": item.id, "entity_type": item.entity_type, "summary": item.summary, "data": item.proposed_data, "status": item.status}
            for item in proposals
        ],
    }


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/system/status", response_model=SystemStatusResponse)
async def system_status() -> SystemStatusResponse:
    ollama = await OllamaProvider().status()
    return SystemStatusResponse(
        app_name=settings.app_name,
        local_only=True,
        database="SQLite",
        ollama_reachable=ollama.reachable,
        generation_model_available=ollama.generation_model_available,
        embedding_model_available=ollama.embedding_model_available,
        installed_models=ollama.installed_models,
    )


@app.post("/api/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    username = payload.username.lower()
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username is already in use")
    user = User(username=username, display_name=payload.display_name.strip(), password_hash=password_hash.hash(payload.password))
    db.add(user)
    db.flush()
    return issue_token(user, db)


@app.post("/api/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.scalar(select(User).where(User.username == payload.username.lower()))
    if not user or not password_hash.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    return issue_token(user, db)


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)) -> dict[str, str]:
    return {"id": user.id, "username": user.username, "display_name": user.display_name}


@app.post("/api/interviews")
def start_interview(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    active = db.scalar(
        select(CareerInterviewSession).where(CareerInterviewSession.user_id == user.id, CareerInterviewSession.status == "active")
    )
    if active:
        return serialize_session(active, db)

    first_stage = STAGES[0]
    session = CareerInterviewSession(user_id=user.id, current_topic=first_stage.key)
    db.add(session)
    db.flush()
    db.add(CareerInterviewMessage(session_id=session.id, role="assistant", content=first_stage.opening_question))
    db.commit()
    db.refresh(session)
    return serialize_session(session, db)


@app.get("/api/interviews/{session_id}")
def get_interview(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    session = db.get(CareerInterviewSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return serialize_session(session, db)


@app.post("/api/interviews/{session_id}/messages")
async def send_interview_message(
    session_id: str,
    payload: InterviewMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = db.get(CareerInterviewSession, session_id)
    if not session or session.user_id != user.id or session.status != "active":
        raise HTTPException(status_code=404, detail="Active interview session not found")

    user_message = CareerInterviewMessage(session_id=session.id, role="user", content=payload.content.strip())
    db.add(user_message)
    db.flush()
    history = [
        {"role": message.role, "content": message.content}
        for message in db.scalars(
            select(CareerInterviewMessage)
            .where(CareerInterviewMessage.session_id == session.id)
            .order_by(CareerInterviewMessage.created_at)
        ).all()
    ]
    current_stage = stage_for(session.current_topic)
    turn = await OllamaProvider().next_interview_turn(history, current_stage.objective)
    db.add(CareerInterviewMessage(session_id=session.id, role="assistant", content=turn.assistant_message))
    for proposal in turn.fact_proposals:
        db.add(
            FactProposal(
                session_id=session.id,
                source_message_id=user_message.id,
                entity_type=proposal["entity_type"],
                summary=proposal["summary"],
                proposed_data=proposal["data"],
            )
        )
    db.commit()
    return serialize_session(session, db)


@app.post("/api/interviews/{session_id}/advance")
def advance_interview(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    session = db.get(CareerInterviewSession, session_id)
    if not session or session.user_id != user.id or session.status != "active":
        raise HTTPException(status_code=404, detail="Active interview session not found")
    upcoming = next_stage(session.current_topic)
    if not upcoming:
        session.status = "complete"
        db.commit()
        return serialize_session(session, db)
    session.current_topic = upcoming.key
    db.add(CareerInterviewMessage(session_id=session.id, role="assistant", content=upcoming.opening_question))
    db.commit()
    return serialize_session(session, db)


@app.post("/api/fact-proposals/{proposal_id}")
def decide_fact_proposal(
    proposal_id: str,
    payload: ProposalDecisionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    proposal = db.get(FactProposal, proposal_id)
    interview = db.get(CareerInterviewSession, proposal.session_id) if proposal else None
    if not proposal or not interview or interview.user_id != user.id:
        raise HTTPException(status_code=404, detail="Fact proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Fact proposal was already decided")
    proposal.status = payload.decision
    if payload.decision == "approved":
        db.add(
            CareerRecord(
                user_id=user.id,
                source_proposal_id=proposal.id,
                record_type=proposal.entity_type,
                summary=proposal.summary,
                data=proposal.proposed_data,
            )
        )
    db.commit()
    return {"id": proposal.id, "status": proposal.status}


@app.get("/api/career-records")
def career_records(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    records = db.scalars(
        select(CareerRecord).where(CareerRecord.user_id == user.id).order_by(CareerRecord.created_at.desc())
    ).all()
    return [{"id": item.id, "type": item.record_type, "summary": item.summary, "data": item.data} for item in records]


@app.post("/api/candidate-overview")
async def candidate_overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    records = db.scalars(select(CareerRecord).where(CareerRecord.user_id == user.id).order_by(CareerRecord.created_at)).all()
    if not records:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Approve some Career Vault facts before generating an overview")
    overview = await OllamaProvider().candidate_overview([{"type": item.record_type, "summary": item.summary} for item in records])
    return {"overview": overview, "word_count": len(overview.split()), "evidence_count": len(records)}


@app.post("/api/master-resume")
async def generate_master_resume(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    records = db.scalars(select(CareerRecord).where(CareerRecord.user_id == user.id).order_by(CareerRecord.created_at)).all()
    if not records:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Approve some Career Vault facts before creating a master resume")
    content = await OllamaProvider().master_resume(
        [{"type": item.record_type, "summary": item.summary, "data": item.data} for item in records]
    )
    draft = ResumeDraft(user_id=user.id, resume_type="master", content=content)
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return serialize_resume(draft) | {"evidence_count": len(records)}


@app.get("/api/resumes/{resume_id}/download/docx")
def download_master_resume_docx(resume_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> FileResponse:
    draft = db.get(ResumeDraft, resume_id)
    if not draft or draft.user_id != user.id or draft.resume_type != "master":
        raise HTTPException(status_code=404, detail="Master resume not found")
    export_directory = data_directory / "exports"
    export_path = export_directory / user.id / f"career-vault-master-resume-{draft.id}.docx"
    render_master_resume(export_path, user.display_name, draft.content)
    filename = f"{user.display_name.strip().replace(' ', '-').lower() or 'career-vault'}-master-resume.docx"
    return FileResponse(export_path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=filename)
