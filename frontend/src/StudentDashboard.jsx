import { useEffect, useMemo, useState } from "react";
import "./StudentDashboard.css";

const API_BASE = (
  import.meta.env.VITE_API_BASE ||
  `${window.location.protocol}//${window.location.hostname}:5000/api`
).replace(/\/+$/, "");

async function apiFetch(path, init = {}) {
  const method = String(init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers || {});
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    headers.set("X-Requested-With", "XMLHttpRequest");
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || "Request failed.");
  return data;
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "—";
}

export default function StudentDashboard({ currentUser, onLogout }) {
  const [activePage, setActivePage] = useState("overview");
  const [profile, setProfile] = useState(null);
  const [statistics, setStatistics] = useState(null);
  const [elections, setElections] = useState([]);
  const [history, setHistory] = useState([]);
  const [selectedCandidates, setSelectedCandidates] = useState({});
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [submittingElectionId, setSubmittingElectionId] = useState(null);

  const studentName = profile?.full_name || currentUser?.full_name || "Student";
  const initials = useMemo(
    () => studentName.split(" ").filter(Boolean).slice(0, 2).map((word) => word[0]).join("").toUpperCase(),
    [studentName]
  );
  const menuItems = [
    { id: "overview", icon: "▦", label: "Overview" },
    { id: "elections", icon: "◷", label: "Available Elections" },
    { id: "history", icon: "▤", label: "Voting History" },
    { id: "profile", icon: "♙", label: "My Profile" },
    { id: "security", icon: "⚿", label: "Account Security" },
  ];
  const activeItem = menuItems.find((item) => item.id === activePage);

  async function loadDashboard(signal) {
    setLoading(true);
    setError("");
    try {
      // Each section is independently useful. A temporary history failure
      // must not hide an open election or prevent voting.
      const [dashboardResult, electionsResult, historyResult] = await Promise.allSettled([
        apiFetch("/student/dashboard", { signal }),
        apiFetch("/student/elections", { signal }),
        apiFetch("/student/voting-history", { signal }),
      ]);

      if (signal?.aborted) return;

      const unavailableSections = [];
      if (dashboardResult.status === "fulfilled") {
        setProfile(dashboardResult.value.profile || null);
        setStatistics(dashboardResult.value.statistics || null);
      } else {
        unavailableSections.push("profile and statistics");
      }
      if (electionsResult.status === "fulfilled") {
        setElections(
          Array.isArray(electionsResult.value.elections)
            ? electionsResult.value.elections
            : []
        );
      } else {
        unavailableSections.push("elections");
      }
      if (historyResult.status === "fulfilled") {
        setHistory(
          Array.isArray(historyResult.value.history)
            ? historyResult.value.history
            : []
        );
      } else {
        unavailableSections.push("voting history");
      }

      if (unavailableSections.length) {
        setError(
          `Some information could not be loaded (${unavailableSections.join(
            ", "
          )}). Available sections are still usable.`
        );
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    // Defer the request so the effect itself remains a subscription setup,
    // while cleanup still aborts a request that outlives this dashboard.
    const requestId = window.setTimeout(() => {
      void loadDashboard(controller.signal);
    }, 0);
    return () => {
      window.clearTimeout(requestId);
      controller.abort();
    };
    // loadDashboard is intentionally run once for this authenticated view.
  }, []);

  async function handleVote(election) {
    const candidateId = selectedCandidates[election.id];
    const candidate = election.candidates.find((item) => item.id === Number(candidateId));
    if (!candidate) {
      setError("Choose one approved candidate before submitting your vote.");
      return;
    }
    if (!window.confirm(`Confirm your vote for the selected symbol (${candidate.usn}) in “${election.title}”? This cannot be changed.`)) {
      return;
    }
    setSubmittingElectionId(election.id);
    setError("");
    setMessage("");
    try {
      const result = await apiFetch(`/student/elections/${election.id}/vote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_id: candidate.id }),
      });
      setMessage(result.message || "Your vote has been recorded successfully.");
      await loadDashboard();
      setActivePage("history");
    } catch (requestError) {
      setError(requestError.message || "Your vote could not be recorded.");
    } finally {
      setSubmittingElectionId(null);
    }
  }

  return (
    <div className="student-layout">
      <aside className="student-sidebar">
        <div className="student-brand"><div className="student-brand-logo">U</div><div><strong>UBDTCE</strong><span>SECURE E-VOTING</span></div></div>
        <div className="student-profile-card"><div className="student-avatar">{initials || "S"}</div><div className="student-profile-info"><strong>{studentName}</strong><span>Student Portal</span></div></div>
        <div className="student-nav-label">STUDENT MENU</div>
        <nav className="student-nav">{menuItems.map((item) => <button key={item.id} type="button" className={activePage === item.id ? "student-nav-item active" : "student-nav-item"} onClick={() => setActivePage(item.id)}><span className="student-nav-icon">{item.icon}</span><span>{item.label}</span></button>)}</nav>
        <div className="student-sidebar-bottom"><button type="button" className="student-logout" onClick={onLogout}>↪ Sign out</button></div>
      </aside>
      <main className="student-main">
        <header className="student-topbar"><div><div className="student-breadcrumb">UBDTCE / STUDENT PORTAL</div><h1>{activeItem?.label || "Overview"}</h1></div><div className="student-topbar-right"><span className="student-secure-status"><span /> Secure session</span><div className="student-topbar-avatar">{initials || "S"}</div></div></header>
        <div className="student-content">
          {error && <p className="student-info-card" role="alert">{error}</p>}
          {message && <p className="student-info-card" role="status">{message}</p>}
          {loading ? <section className="student-info-card">Loading your election information…</section> : <>
            {activePage === "overview" && <>
              <section className="student-welcome"><span className="student-eyebrow">STUDENT DASHBOARD</span><h2>Welcome, {studentName}</h2><p>Review only the elections for which you are eligible and participate securely.</p></section>
              <section className="student-stat-grid">
                <article className="student-stat-card"><span>Eligible Elections</span><strong>{statistics?.eligible_elections ?? 0}</strong><small>Elections available to you</small></article>
                <article className="student-stat-card"><span>Active Elections</span><strong>{statistics?.active_elections ?? 0}</strong><small>Currently accepting votes</small></article>
                <article className="student-stat-card"><span>Votes Submitted</span><strong>{statistics?.participated_elections ?? 0}</strong><small>Your participation record</small></article>
              </section>
              <section className="student-info-card"><h2>Election Participation</h2><p>Ballot choices are intentionally never shown in your history.</p><button type="button" onClick={() => setActivePage("elections")}>View Elections →</button></section>
            </>}
            {activePage === "elections" && <section className="student-info-card"><h2>Available Elections</h2>{elections.length === 0 ? <p>No completed or active elections are currently available to you.</p> : elections.map((election) => <article key={election.id} className="student-election-card"><h3>{election.title}</h3>{election.description && <p>{election.description}</p>}<p>{election.election_type}{election.branch ? ` · ${election.branch}` : ""}</p><p><strong>{election.status}</strong> · Opens {formatDate(election.opens_at)} · Closes {formatDate(election.closes_at)}</p>{election.has_participated ? <p>Your participation has been recorded. Your ballot remains secret.</p> : election.status !== "OPEN" ? <p>Voting is not currently open.</p> : election.candidates.length === 0 ? <p>No approved candidates are available yet.</p> : <><fieldset><legend>Select one approved candidate</legend>{election.candidates.map((candidate) => <label key={candidate.id} className="student-candidate-option"><input type="radio" name={`election-${election.id}`} value={candidate.id} checked={Number(selectedCandidates[election.id]) === candidate.id} onChange={() => setSelectedCandidates((previous) => ({ ...previous, [election.id]: candidate.id }))} /><span className="student-candidate-identity"><strong aria-hidden="true">{candidate.symbol?.glyph || "◌"}</strong><span><small>USN: {candidate.usn}</small></span></span></label>)}</fieldset><button type="button" disabled={submittingElectionId === election.id} onClick={() => handleVote(election)}>{submittingElectionId === election.id ? "Submitting…" : "Confirm and cast vote"}</button></>}</article>)}</section>}
            {activePage === "history" && <section className="student-info-card"><h2>Voting History</h2><p>This page proves participation only; it never shows a candidate choice.</p>{history.length === 0 ? <p>No participation records yet.</p> : <ul className="student-history-list">{history.map((item) => <li key={item.election_id}><strong>{item.title}</strong><span>{item.election_type}{item.branch ? ` · ${item.branch}` : ""}</span><span>Participation recorded {formatDate(item.participated_at)}</span></li>)}</ul>}</section>}
            {activePage === "profile" && <section className="student-info-card"><h2>My Profile</h2><div className="student-profile-details"><p><strong>Name:</strong> {profile?.full_name || studentName}</p><p><strong>USN:</strong> {profile?.usn || "—"}</p><p><strong>Email:</strong> {profile?.email || currentUser?.email || "—"}</p><p><strong>Branch:</strong> {profile?.branch_name || "—"}</p><p><strong>Admission year:</strong> {profile?.admission_year || "—"}</p><p><strong>Semester:</strong> {profile?.semester || "—"}</p><p><strong>Account status:</strong> {profile?.is_active ? "Active" : "Inactive"}</p></div></section>}
            {activePage === "security" && <section className="student-info-card"><h2>Account Security</h2><p>Use Forgot Password from the login page to request a short-lived reset link. Never share an activation or reset link, and never share your password.</p></section>}
          </>}
          <footer className="student-footer">UBDTCE Secure E-Voting System<span>Student Portal</span></footer>
        </div>
      </main>
    </div>
  );
}
