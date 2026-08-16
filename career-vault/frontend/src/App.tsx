import { useEffect, useState, type FormEvent } from "react";

type SystemStatus = {
  app_name: string;
  local_only: boolean;
  database: string;
  ollama_reachable: boolean;
  generation_model_available: boolean;
  embedding_model_available: boolean;
  installed_models: string[];
};
type Auth = { token: string; username: string; display_name: string };
type ChatMessage = { id: string; role: "user" | "assistant"; content: string };
type Proposal = { id: string; entity_type: string; summary: string; status: "pending" | "approved" | "rejected" };
type Stage = { key: string; label: string };
type Interview = { id: string; status: string; stage: string; stage_label: string; stages: Stage[]; messages: ChatMessage[]; proposals: Proposal[] };
type CareerRecord = { id: string; type: string; summary: string; data: Record<string, unknown> };
type MasterResume = {
  id: string;
  type: string;
  created_at: string;
  evidence_count: number;
  content: {
    headline: string;
    professional_summary: string;
    skills: string[];
    experience: { role: string; company: string; dates: string; highlights: string[] }[];
    certifications: string[];
    education: string[];
    additional_highlights: string[];
  };
};

function Status({ ready, label }: { ready: boolean; label: string }) {
  return <li className={ready ? "ready" : "waiting"}>{ready ? "●" : "○"} {label}</li>;
}

export default function App() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [auth, setAuth] = useState<Auth | null>(() => {
    const saved = localStorage.getItem("career-vault-auth");
    return saved ? JSON.parse(saved) as Auth : null;
  });
  const [mode, setMode] = useState<"login" | "register">("register");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [interview, setInterview] = useState<Interview | null>(null);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [records, setRecords] = useState<CareerRecord[]>([]);
  const [overview, setOverview] = useState<string | null>(null);
  const [generatingOverview, setGeneratingOverview] = useState(false);
  const [masterResume, setMasterResume] = useState<MasterResume | null>(null);
  const [generatingMasterResume, setGeneratingMasterResume] = useState(false);

  useEffect(() => {
    fetch("/api/system/status")
      .then((response) => response.ok ? response.json() as Promise<SystemStatus> : Promise.reject(new Error("Backend is not available")))
      .then(setStatus)
      .catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    if (!auth) return;
    fetch("/api/career-records", { headers: { Authorization: `Bearer ${auth.token}` } })
      .then((response) => response.ok ? response.json() as Promise<CareerRecord[]> : [])
      .then(setRecords)
      .catch(() => setRecords([]));
  }, [auth]);

  function authenticatedFetch(path: string, options: RequestInit = {}) {
    return fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${auth?.token ?? ""}`, ...options.headers }
    });
  }

  async function submitAuth(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const body = mode === "register" ? { username, display_name: displayName, password } : { username, password };
    const response = await fetch(`/api/auth/${mode}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!response.ok) {
      const result = await response.json() as { detail?: string };
      setError(result.detail ?? "Could not sign in");
      return;
    }
    const nextAuth = await response.json() as Auth;
    localStorage.setItem("career-vault-auth", JSON.stringify(nextAuth));
    setAuth(nextAuth);
    setPassword("");
  }

  function signOut() {
    localStorage.removeItem("career-vault-auth");
    setAuth(null);
    setInterview(null);
    setRecords([]);
  }

  async function startInterview() {
    const response = await authenticatedFetch("/api/interviews", { method: "POST" });
    if (!response.ok) return setError("Could not start your interview");
    setInterview(await response.json() as Interview);
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    if (!interview || !message.trim() || sending) return;
    setSending(true);
    try {
      const response = await authenticatedFetch(`/api/interviews/${interview.id}/messages`, { method: "POST", body: JSON.stringify({ content: message.trim() }) });
      if (!response.ok) throw new Error("Unable to send message");
      setInterview(await response.json() as Interview);
      setMessage("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to send message");
    } finally {
      setSending(false);
    }
  }

  async function advanceStage() {
    if (!interview) return;
    const response = await authenticatedFetch(`/api/interviews/${interview.id}/advance`, { method: "POST" });
    if (response.ok) setInterview(await response.json() as Interview);
  }

  async function decideProposal(proposalId: string, decision: "approved" | "rejected") {
    const response = await authenticatedFetch(`/api/fact-proposals/${proposalId}`, { method: "POST", body: JSON.stringify({ decision }) });
    if (!response.ok || !interview) return;
    const updated = await response.json() as { id: string; status: Proposal["status"] };
    setInterview({ ...interview, proposals: interview.proposals.map((item) => item.id === updated.id ? { ...item, status: updated.status } : item) });
    if (decision === "approved") {
      const recordsResponse = await authenticatedFetch("/api/career-records");
      if (recordsResponse.ok) setRecords(await recordsResponse.json() as CareerRecord[]);
    }
  }

  async function generateOverview() {
    setGeneratingOverview(true);
    setError(null);
    try {
      const response = await authenticatedFetch("/api/candidate-overview", { method: "POST" });
      const result = await response.json() as { overview?: string; detail?: string };
      if (!response.ok) throw new Error(result.detail ?? "Could not generate overview");
      setOverview(result.overview ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not generate overview");
    } finally {
      setGeneratingOverview(false);
    }
  }

  async function generateMasterResume() {
    setGeneratingMasterResume(true);
    setError(null);
    try {
      const response = await authenticatedFetch("/api/master-resume", { method: "POST" });
      const result = await response.json() as MasterResume & { detail?: string };
      if (!response.ok) throw new Error(result.detail ?? "Could not create master resume");
      setMasterResume(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create master resume");
    } finally {
      setGeneratingMasterResume(false);
    }
  }

  async function downloadMasterResume() {
    if (!masterResume) return;
    setError(null);
    try {
      const response = await authenticatedFetch(`/api/resumes/${masterResume.id}/download/docx`);
      if (!response.ok) {
        const result = await response.json() as { detail?: string };
        throw new Error(result.detail ?? "Could not download master resume");
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "career-vault-master-resume.docx";
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not download master resume");
    }
  }

  return <main>
    <header><p className="eyebrow">LOCAL-FIRST CAREER INTELLIGENCE</p>{auth && <button className="secondary signout" onClick={signOut}>Sign out</button>}</header>
    <section className="hero">
      <h1>Your complete career story, kept private.</h1>
      <p className="intro">Career Vault follows a structured interview: career timeline, responsibilities, clients and projects, credentials, education, and public work. It never skips ahead or asks you to rank your experience.</p>
    </section>

    {error && <p className="error">{error}</p>}
    {!auth ? <section className="panel auth-panel">
      <p className="eyebrow">LOCAL ACCOUNT</p><h2>{mode === "register" ? "Create your private vault" : "Sign in"}</h2>
      <form onSubmit={submitAuth} className="composer">
        {mode === "register" && <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Your name" required />}
        <input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Username" minLength={3} required />
        <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" placeholder="Password (10+ characters)" minLength={10} required />
        <button>{mode === "register" ? "Create account" : "Sign in"}</button>
      </form>
      <button className="link-button" onClick={() => setMode(mode === "register" ? "login" : "register")}>{mode === "register" ? "Already have an account? Sign in" : "Need an account? Create one"}</button>
    </section> : <>
      <section className="welcome"><p>Signed in as <strong>{auth.display_name}</strong>.</p><button onClick={startInterview}>{interview ? "Resume Career Interview" : "Start Career Interview"}</button></section>
      {interview && <section className="interview panel">
        <div><p className="eyebrow">STRUCTURED CAREER INTERVIEW</p><h2>{interview.stage_label}</h2></div>
        <ol className="stages">{interview.stages.map((stage) => <li key={stage.key} className={stage.key === interview.stage ? "current" : ""}>{stage.label}</li>)}</ol>
        <div className="messages">{interview.messages.map((item) => <article key={item.id} className={`message ${item.role}`}><span>{item.role === "assistant" ? "Career guide" : "You"}</span><p>{item.content}</p></article>)}</div>
        {interview.status === "active" && <><form onSubmit={sendMessage} className="composer"><textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Answer in as much detail as you want." rows={3} /><button disabled={sending || !message.trim()}>{sending ? "Thinking locally…" : "Send"}</button></form><button className="secondary advance" onClick={advanceStage}>Complete this section → Next section</button></>}
        {interview.proposals.length > 0 && <div className="proposals"><p className="eyebrow">FACTS TO CONFIRM</p>{interview.proposals.map((proposal) => <article key={proposal.id} className="proposal"><p><strong>{proposal.entity_type}</strong> · {proposal.summary}</p>{proposal.status === "pending" ? <div><button onClick={() => decideProposal(proposal.id, "approved")}>Approve</button><button className="secondary" onClick={() => decideProposal(proposal.id, "rejected")}>Reject</button></div> : <small>{proposal.status}</small>}</article>)}</div>}
      </section>}
      {records.length > 0 && <section className="panel records"><p className="eyebrow">CONFIRMED CAREER VAULT</p><h2>Approved facts</h2>{records.map((record) => <p key={record.id}><strong>{record.type}</strong> · {record.summary}</p>)}<div className="overview-action"><button onClick={generateOverview} disabled={generatingOverview}>{generatingOverview ? "Writing overview locally…" : "Generate Candidate Overview"}</button><button onClick={generateMasterResume} disabled={generatingMasterResume}>{generatingMasterResume ? "Building master resume locally…" : "Create Master Resume"}</button></div>{overview && <article className="overview"><p className="eyebrow">CANDIDATE OVERVIEW · APPROX. 50–60 WORDS</p><p>{overview}</p><small>Generated from approved Career Vault records only.</small></article>}{masterResume && <article className="master-resume"><div className="resume-heading"><div><p className="eyebrow">MASTER RESUME · {masterResume.evidence_count} APPROVED FACTS</p><h3>{masterResume.content.headline || "Professional Profile"}</h3></div><button onClick={downloadMasterResume}>Download DOCX</button></div><p className="resume-summary">{masterResume.content.professional_summary}</p>{masterResume.content.skills.length > 0 && <><h4>Core skills</h4><p className="skill-list">{masterResume.content.skills.join(" · ")}</p></>}{masterResume.content.experience.length > 0 && <><h4>Experience</h4>{masterResume.content.experience.map((entry, index) => <div className="experience" key={`${entry.role}-${index}`}><strong>{entry.role || "Professional experience"}{entry.company ? ` | ${entry.company}` : ""}</strong>{entry.dates && <small>{entry.dates}</small>}{entry.highlights.map((highlight, highlightIndex) => <p key={highlightIndex}>• {highlight}</p>)}</div>)}</>}{masterResume.content.certifications.length > 0 && <><h4>Certifications</h4><p>{masterResume.content.certifications.join(" · ")}</p></>}{masterResume.content.education.length > 0 && <><h4>Education</h4><p>{masterResume.content.education.join(" · ")}</p></>}{masterResume.content.additional_highlights.length > 0 && <><h4>Additional highlights</h4><p>{masterResume.content.additional_highlights.join(" · ")}</p></>}<small>Draft generated locally from approved facts only. Review it before sharing.</small></article>}</section>}
    </>}

    <section className="panel system"><p className="eyebrow">LOCAL SYSTEM STATUS</p>{status && <ul><Status ready label="SQLite local database" /><Status ready={status.ollama_reachable} label="Ollama available at localhost" /><Status ready={status.generation_model_available} label="Qwen3 4B generation model" /><Status ready={status.embedding_model_available} label="EmbeddingGemma matching model" /></ul>}</section>
  </main>;
}
