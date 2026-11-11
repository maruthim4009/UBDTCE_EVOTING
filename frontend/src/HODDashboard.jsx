import { useEffect, useMemo, useState } from "react";
import "./HODDashboard.css";

const ROOT_API_BASE = (
  import.meta.env.VITE_API_BASE ||
  `${window.location.protocol}//${window.location.hostname}:5000/api`
).replace(/\/+$/, "");
const API_BASE = `${ROOT_API_BASE}/hod`;

const admissionYears = Array.from({ length: 101 }, (_, index) => 2000 + index);
const defaultAdmissionYear = String(new Date().getFullYear());

const semesters = [1, 2, 3, 4, 5, 6, 7, 8];

async function readResponse(response) {
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      data.message || `Request failed (${response.status}).`
    );
  }

  return data;
}

export default function HODDashboard({ currentUser, onLogout }) {
  const [activePage, setActivePage] = useState("overview");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const [students, setStudents] = useState([]);
  const [studentLoading, setStudentLoading] = useState(false);
  const [studentListError, setStudentListError] = useState("");
  const [studentError, setStudentError] = useState("");
  const [studentMessage, setStudentMessage] = useState("");

  const [studentSearch, setStudentSearch] = useState("");
  const [filterYear, setFilterYear] = useState("");
  const [filterAcademicYear, setFilterAcademicYear] = useState("");
  const [filterSemester, setFilterSemester] = useState("");
  const [selectedStudents, setSelectedStudents] = useState([]);
  const [studentPage, setStudentPage] = useState(1);
  const [studentPagination, setStudentPagination] = useState(null);

  const [studentForm, setStudentForm] = useState({
    name: "",
    usn: "",
    email: "",
    semester: "",
    admission_year: "",
    academic_year: "",
  });

  const [studentSubmitting, setStudentSubmitting] = useState(false);
  const [classes, setClasses] = useState([]);
  
const [classesBranch, setClassesBranch] = useState("");
const [classesLoading, setClassesLoading] = useState(false);
const [classesError, setClassesError] = useState("");
const [classYearFilter, setClassYearFilter] = useState("");
const [classAcademicYearFilter, setClassAcademicYearFilter] = useState("");
const [classSemesterFilter, setClassSemesterFilter] = useState("");
  const [individualAddMessage, setIndividualAddMessage] = useState("");

  const [importYear, setImportYear] = useState(defaultAdmissionYear);
  const [importAcademicYear, setImportAcademicYear] = useState("");
  const [importSemester, setImportSemester] = useState("");
  const [importFile, setImportFile] = useState(null);
  const [importMessage, setImportMessage] = useState("");
  const [importing, setImporting] = useState(false);
  const [importPreview, setImportPreview] = useState(null);
  const [elections, setElections] = useState([]);
  const [electionsLoading, setElectionsLoading] = useState(false);
  const [electionError, setElectionError] = useState("");
  const [electionMessage, setElectionMessage] = useState("");
  const [electionForm, setElectionForm] = useState({
    title: "", description: "", election_type: "CR", admission_year: "", academic_year: "", semester: "", duration_minutes: "30",
  });
  const [selectedElectionId, setSelectedElectionId] = useState("");
  const [candidates, setCandidates] = useState([]);
  const [candidateUsn, setCandidateUsn] = useState("");
  const [candidateManifesto, setCandidateManifesto] = useState("");
  const [candidateSymbols, setCandidateSymbols] = useState([]);
  const [candidateSymbolKey, setCandidateSymbolKey] = useState("book");
  const [result, setResult] = useState(null);

  const menuItems = [
    { id: "overview", icon: "▦", label: "Overview" },
    { id: "students", icon: "♙", label: "Student Management" },
    { id: "classes", icon: "▤", label: "Classes & Semesters" },
    { id: "elections", icon: "◷", label: "CR / FR Elections" },
    { id: "candidates", icon: "♧", label: "Candidates" },
    { id: "results", icon: "▥", label: "Election Results" },
  ];

  const activeItem = menuItems.find(
    (item) => item.id === activePage
  );
  const filteredClasses = classes.filter((classItem) => {
  const yearMatches =
    !classYearFilter ||
    String(classItem.admission_year) === classYearFilter;
  const academicYearMatches =
    !classAcademicYearFilter ||
    String(classItem.academic_year || "") === classAcademicYearFilter;

  const semesterMatches =
    !classSemesterFilter ||
    String(classItem.semester) === classSemesterFilter;

  return yearMatches && academicYearMatches && semesterMatches;
});
  const fullName = currentUser?.full_name || "Department Head";

  const initials = fullName
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

  const visibleStudents = useMemo(() => {
    return students.filter((student) => {
      const yearMatches =
        !filterYear ||
        String(student.admission_year || "") === String(filterYear);
      const academicYearMatches =
        !filterAcademicYear ||
        String(student.academic_year || "") === String(filterAcademicYear);

      const semesterMatches =
        !filterSemester ||
        String(student.semester) === String(filterSemester);

      const search = studentSearch.trim().toLowerCase();

      const searchMatches =
        !search ||
        String(student.name || "").toLowerCase().includes(search) ||
        String(student.usn || "").toLowerCase().includes(search) ||
        String(student.email || "").toLowerCase().includes(search);

      return yearMatches && academicYearMatches && semesterMatches && searchMatches;
    });
  }, [students, filterYear, filterAcademicYear, filterSemester, studentSearch]);

  const allVisibleSelected =
    visibleStudents.length > 0 &&
    visibleStudents.every((student) =>
      selectedStudents.includes(student.id)
    );

  const selectedUnactivatedStudentIds = selectedStudents.filter((studentId) => {
    const student = students.find((item) => item.id === studentId);
    return student?.is_active && !student?.is_activated;
  });

  useEffect(() => {
    let cancelled = false;
    async function loadCandidateSymbols() {
      try {
        const data = await readResponse(await fetch(`${ROOT_API_BASE}/candidate-symbols`, {
          credentials: "include",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        }));
        if (!cancelled) {
          const symbols = Array.isArray(data.symbols) ? data.symbols : [];
          setCandidateSymbols(symbols);
          if (symbols.length) {
            setCandidateSymbolKey((current) => (
              symbols.some((symbol) => symbol.key === current)
                ? current
                : symbols[0].key
            ));
          }
        }
      } catch (error) {
        if (!cancelled) setElectionError(error.message || "Could not load approved symbols.");
      }
    }
    void loadCandidateSymbols();
    return () => { cancelled = true; };
  }, []);

  async function loadStudents() {
  setStudentLoading(true);
  setStudentListError("");

  try {
    const params = new URLSearchParams();

    params.set("page", String(studentPage));
    params.set("per_page", "25");

    if (studentSearch.trim()) {
      params.set("search", studentSearch.trim());
    }

    if (filterSemester) {
      params.set("semester", filterSemester);
    }

    if (filterYear) {
      params.set("admission_year", filterYear);
    }
    if (filterAcademicYear) {
      params.set("academic_year", filterAcademicYear);
    }

    const response = await fetch(
      `${API_BASE}/students?${params.toString()}`,
      {
        method: "GET",
        credentials: "include",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
      }
    );

    const data = await readResponse(response);

    setStudents(data.students || []);
    setStudentPagination(data.pagination || null);
    setSelectedStudents([]);
  } catch (error) {
    setStudentListError(
      error.message === "Failed to fetch"
        ? "Cannot connect to Flask. Check that the backend is running."
        : error.message
    );
  } finally {
    setStudentLoading(false);
  }
}

  useEffect(() => {
    if (activePage === "students") {
      // Fetching starts an asynchronous state update; it is not a synchronous effect update.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadStudents();
    }
    // loadStudents intentionally uses the listed query values.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePage, studentSearch, filterSemester, filterYear, filterAcademicYear, studentPage]);

  async function loadClasses() {
  setClassesLoading(true);
  setClassesError("");

  try {
    const response = await fetch(`${API_BASE}/classes`, {
      method: "GET",
      credentials: "include",
      headers: {
        "X-Requested-With": "XMLHttpRequest"
      }
    });

    const data = await readResponse(response);

    setClasses(data.classes || []);
    setClassesBranch(data.branch || "");
  } catch (error) {
    setClassesError(
      error.message === "Failed to fetch"
        ? "Cannot connect to Flask. Check that the backend is running."
        : error.message
    );
  } finally {
    setClassesLoading(false);
  }
} 

  async function loadHodElections() {
    setElectionsLoading(true);
    setElectionError("");
    try {
      const data = await readResponse(await fetch(`${API_BASE}/elections`, {
        credentials: "include",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      }));
      const nextElections = Array.isArray(data.elections) ? data.elections : [];
      setElections(nextElections);
      if (!selectedElectionId && nextElections.length) setSelectedElectionId(String(nextElections[0].id));
    } catch (error) {
      setElectionError(error.message || "Could not load elections.");
    } finally {
      setElectionsLoading(false);
    }
  }

  async function loadCandidates(electionId) {
    if (!electionId) {
      setCandidates([]);
      return;
    }
    setElectionError("");
    try {
      const data = await readResponse(await fetch(`${API_BASE}/elections/${electionId}/candidates`, {
        credentials: "include",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      }));
      setCandidates(Array.isArray(data.candidates) ? data.candidates : []);
    } catch (error) {
      setElectionError(error.message || "Could not load candidates.");
    }
  }

  async function handleCreateElection(event) {
    event.preventDefault();
    setElectionError("");
    setElectionMessage("");
    try {
      const data = await readResponse(await fetch(`${API_BASE}/elections`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify({
          ...electionForm,
          admission_year: Number(electionForm.admission_year),
          academic_year: Number(electionForm.academic_year),
          semester: Number(electionForm.semester),
          duration_minutes: Number(electionForm.duration_minutes),
        }),
      }));
      setElectionMessage(data.message || "Election created as a draft.");
      setElectionForm({ title: "", description: "", election_type: "CR", admission_year: "", academic_year: "", semester: "", duration_minutes: "30" });
      await loadHodElections();
    } catch (error) {
      setElectionError(error.message || "Could not create the election.");
    }
  }

  async function handleCandidateSubmit(event) {
    event.preventDefault();
    if (!selectedElectionId) {
      setElectionError("Select an election first.");
      return;
    }
    setElectionError("");
    try {
      const data = await readResponse(await fetch(`${API_BASE}/elections/${selectedElectionId}/candidates`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify({
          usn: candidateUsn,
          manifesto: candidateManifesto,
          symbol_key: candidateSymbolKey,
        }),
      }));
      setElectionMessage(data.message || "Candidate registered.");
      setCandidateUsn("");
      setCandidateManifesto("");
      setCandidateSymbolKey(candidateSymbols[0]?.key || "book");
      await loadCandidates(selectedElectionId);
    } catch (error) {
      setElectionError(error.message || "Could not register candidate.");
    }
  }

  async function reviewCandidate(candidateId, action) {
    if (!selectedElectionId) return;
    setElectionError("");
    try {
      const data = await readResponse(await fetch(`${API_BASE}/elections/${selectedElectionId}/candidates/${candidateId}/${action}`, {
        method: "POST",
        credentials: "include",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      }));
      setElectionMessage(data.message || "Candidate review saved.");
      await loadCandidates(selectedElectionId);
      await loadHodElections();
    } catch (error) {
      setElectionError(error.message || "Could not review candidate.");
    }
  }

  async function changeElectionStatus(electionId, action) {
    setElectionError("");
    try {
      const data = await readResponse(await fetch(`${API_BASE}/elections/${electionId}/${action}`, {
        method: "POST",
        credentials: "include",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      }));
      setElectionMessage(data.message || "Election updated.");
      await loadHodElections();
    } catch (error) {
      setElectionError(error.message || "Could not update election status.");
    }
  }

  async function loadResult(electionId) {
    setElectionError("");
    try {
      const data = await readResponse(await fetch(`${API_BASE}/elections/${electionId}/results`, {
        credentials: "include",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      }));
      setResult(data.result || null);
    } catch (error) {
      setResult(null);
      setElectionError(error.message || "Could not load results.");
    }
  }

  function changePage(page) {
  setActivePage(page);
  setSidebarOpen(false);
  setStudentMessage("");
  setStudentError("");

  if (page === "classes") {
    loadClasses();
  }
  if (page === "elections" || page === "candidates" || page === "results") {
    loadHodElections();
  }
}

  function updateStudentForm(event) {
    const { name, value } = event.target;

    setStudentForm((previous) => ({
      ...previous,
      [name]: value,
    }));
  }

  async function handleAddStudent(event) {
    event.preventDefault();

    setStudentError("");
    setIndividualAddMessage("");
    setStudentSubmitting(true);

    try {
      const response = await fetch(`${API_BASE}/students`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify(studentForm),
      });

      const data = await readResponse(response);

     setIndividualAddMessage(
  data.message || "Student registered successfully."
);

window.setTimeout(() => {
  setIndividualAddMessage("");
}, 10000);

      setStudentForm({
        name: "",
        usn: "",
        email: "",
        semester: "",
        admission_year: "",
        academic_year: "",
      });

      await loadStudents();
    } catch (error) {
      setStudentError(
        error.message === "Failed to fetch"
          ? "Cannot connect to Flask. Check that the backend is running."
          : error.message
      );
    } finally {
      setStudentSubmitting(false);
    }
  }

  function toggleStudentSelection(studentId) {
    setSelectedStudents((previous) =>
      previous.includes(studentId)
        ? previous.filter((id) => id !== studentId)
        : [...previous, studentId]
    );
  }

  function toggleAllVisible() {
    if (allVisibleSelected) {
      setSelectedStudents((previous) =>
        previous.filter(
          (id) =>
            !visibleStudents.some((student) => student.id === id)
        )
      );
    } else {
      setSelectedStudents((previous) => [
        ...new Set([
          ...previous,
          ...visibleStudents.map((student) => student.id),
        ]),
      ]);
    }
  }

  async function handleImport() {
  if (importing) return;

  if (!importYear || !importAcademicYear || !importSemester || !importFile) {
    setImportMessage(
      "Select an admission year, academic year, semester and Excel/CSV file."
    );
    return;
  }

  const formData = new FormData();
  formData.append("file", importFile);
  formData.append("admission_year", importYear);
  formData.append("academic_year", importAcademicYear);
  formData.append("semester", importSemester);

  setImporting(true);
  setImportMessage("Uploading file for validation...");
  setImportPreview(null);

  try {
    const response = await fetch(
      `${API_BASE}/students/bulk-upload/preview`,
      {
        method: "POST",
        credentials: "include",
        headers: {
          "X-Requested-With": "XMLHttpRequest"
        },
        body: formData
      }
    );

    if (response.status === 429) {
      throw new Error(
        "Too many requests. Please wait one minute before trying again."
      );
    }

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.message || "File validation failed.");
    }

    setImportPreview(data);
  setImportMessage("");
  } catch (error) {
    setImportMessage(error.message || "Unable to validate the file.");
  } finally {
    setImporting(false);
  }
}


async function handleConfirmImport() {
  if (!importPreview || importPreview.valid_rows?.length === 0) {
    setImportMessage("There are no valid students to import.");
    return;
  }

  const validStudents = importPreview.valid_rows.map((student) => ({
    row: student.row,
    name: student.name,
    usn: student.usn,
    email: student.email
  }));

  const confirmed = window.confirm(
    `Import ${validStudents.length} valid student(s) into ${importPreview.branch}, Academic Year ${importAcademicYear}, Semester ${importSemester}, Admission Year ${importYear}?`
  );

  if (!confirmed) return;

  setImporting(true);
  setImportMessage("Registering students...");

  try {
    const response = await fetch(
      `${API_BASE}/students/bulk-upload/import`,
      {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest"
        },
        body: JSON.stringify({
          students: validStudents,
          admission_year: Number(importYear),
          academic_year: Number(importAcademicYear),
          semester: Number(importSemester),
        })
      }
    );

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.message || "Student import failed.");
    }

    setSelectedStudents([]);
    setImportPreview(null);
    setImportFile(null);
    setImportMessage(
      `Registration summary — submitted: ${data.submitted_count}; ` +
      `registered: ${data.registered_students}; conflicts: ${data.rejected_count}; ` +
      `invitations queued: ${data.activation_emails_queued}.`
    );
    await loadStudents();

window.setTimeout(() => {
  setImportMessage("");
}, 5000);
  } catch (error) {
    setImportMessage(error.message || "Unable to import students.");
  } finally {
    setImporting(false);
  }
}

 async function handleSingleStatusChange(student, nextStatus) {
  const action = nextStatus ? "activate" : "deactivate";

  const confirmed = window.confirm(
    `Are you sure you want to ${action} ${student.name} (${student.usn})?`
  );

  if (!confirmed) return;

  setStudentMessage("");
  setStudentListError("");

  try {
    const response = await fetch(
      `${API_BASE}/students/${student.id}/status`,
      {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest"
        },
        body: JSON.stringify({ is_active: nextStatus })
      }
    );

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.message || "Unable to update student status.");
    }

    setStudents((previous) =>
      previous.map((item) =>
        item.id === student.id
          ? { ...item, is_active: data.is_active }
          : item
      )
    );

   setStudentMessage(data.message);

window.setTimeout(() => {
  setStudentMessage("");
}, 10000);


  } catch (error) {
    setStudentListError(error.message);
  }
}

  async function handleBulkStatusChange(nextStatus) {
  if (selectedStudents.length === 0) {
    setStudentMessage("Select students first.");
    return;
  }

  const action = nextStatus ? "activate" : "deactivate";

  const confirmed = window.confirm(
    `${action} ${selectedStudents.length} selected student(s)?`
  );

  if (!confirmed) return;

  setStudentMessage("");
  setStudentListError("");

  try {
    const response = await fetch(
      `${API_BASE}/students/bulk-status`,
      {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest"
        },
        body: JSON.stringify({
          student_ids: selectedStudents,
          is_active: nextStatus
        })
      }
    );

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.message || "Unable to update selected students.");
    }

    setStudents((previous) =>
      previous.map((student) =>
        selectedStudents.includes(student.id)
          ? { ...student, is_active: data.is_active }
          : student
      )
    );

    setSelectedStudents([]);
    setStudentMessage(data.message);
  } catch (error) {
    setStudentListError(error.message);
  }
}

  async function handleEditElection(election) {
    const title = window.prompt("Election title", election.title);
    if (title === null) return;
    const description = window.prompt("Election description", election.description || "");
    if (description === null) return;
    const durationValue = window.prompt("Duration in minutes", String(election.duration_minutes));
    if (durationValue === null) return;
    const durationMinutes = Number(durationValue);
    if (!title.trim() || !Number.isInteger(durationMinutes)) {
      setElectionError("Enter a valid title and duration.");
      return;
    }
    try {
      const data = await readResponse(await fetch(`${API_BASE}/elections/${election.id}`, {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
          title: title.trim(),
          description: description.trim(),
          duration_minutes: durationMinutes,
        }),
      }));
      setElectionMessage(data.message || "Election updated successfully.");
      await loadHodElections();
    } catch (error) {
      setElectionError(error.message || "Could not update the election.");
    }
  }

  async function handleResendActivation(studentIds) {
    if (!studentIds.length) return;
    try {
      const endpoint = studentIds.length === 1
        ? `${API_BASE}/students/${studentIds[0]}/resend-activation`
        : `${API_BASE}/students/bulk-resend-activation`;
      const response = await fetch(endpoint, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: studentIds.length === 1 ? undefined : JSON.stringify({ student_ids: studentIds }),
      });
      const data = await readResponse(response);
      setStudentMessage(data.message || "Activation invitation(s) queued.");
      setSelectedStudents([]);
      await loadStudents();
    } catch (error) {
      setStudentListError(error.message || "Could not queue activation invitations.");
    }
  }

  function changeStudentPage(nextPage) {
    const totalPages = studentPagination?.total_pages || 1;
    if (nextPage >= 1 && nextPage <= totalPages) {
      setStudentPage(nextPage);
    }
  }

  return (
    <div className="hod-layout">
      {sidebarOpen && (
        <button
          type="button"
          className="hod-sidebar-overlay"
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* SIDEBAR */}
      <aside className={`hod-sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="hod-brand">
          <div className="hod-brand-logo">U</div>

          <div className="hod-brand-text">
            <strong>UBDTCE</strong>
            <span>SECURE E-VOTING</span>
          </div>
        </div>

        <div className="hod-profile-card">
          <div className="hod-avatar">{initials || "H"}</div>

          <div className="hod-profile-info">
            <strong>{fullName}</strong>
            <span>Department Head</span>
          </div>
        </div>

        <div className="hod-nav-label">MAIN MENU</div>

        <nav className="hod-nav">
          {menuItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={
                activePage === item.id
                  ? "hod-nav-item active"
                  : "hod-nav-item"
              }
              onClick={() => changePage(item.id)}
            >
              <span className="hod-nav-icon">{item.icon}</span>
              <span>{item.label}</span>

              {activePage === item.id && (
                <span className="hod-nav-indicator" />
              )}
            </button>
          ))}
        </nav>

        <div className="hod-sidebar-bottom">
          <button
            type="button"
            className="hod-logout"
            onClick={onLogout}
          >
            <span>↪</span>
            Sign out
          </button>
        </div>
      </aside>

      {/* MAIN CONTENT */}
      <main className="hod-main">
        {/* TOP BAR */}
        <header className="hod-topbar">
          <div className="hod-topbar-left">
            <button
              type="button"
              className="hod-menu-toggle"
              onClick={() => setSidebarOpen((open) => !open)}
              aria-label="Toggle navigation"
            >
              ☰
            </button>

            <div>
              <div className="hod-breadcrumb">
                UBDTCE <span>/</span> HOD PORTAL
              </div>

              <h1>{activeItem?.label || "Overview"}</h1>
            </div>
          </div>

          <div className="hod-topbar-right">
            <div className="hod-secure-status">
              <span />
              Secure session
            </div>

            <div className="hod-topbar-avatar">
              {initials || "H"}
            </div>
          </div>
        </header>

        <div className="hod-page-content">
          {/* OVERVIEW */}
          {activePage === "overview" && (
            <>
              <section className="hod-welcome">
                <div className="hod-welcome-content">
                  <span className="hod-eyebrow">
                    HOD DASHBOARD
                  </span>

                  <h2>Welcome back, {fullName}</h2>

                  <p>
                    Manage students, classes and department elections
                    from your dashboard.
                  </p>
                </div>

                <div className="hod-welcome-art">
                  <div className="hod-art-circle">U</div>
                </div>
              </section>

              <section className="hod-section-heading">
                <div>
                  <h2>Overview</h2>
                  <p>Your department at a glance.</p>
                </div>
              </section>

              <section className="hod-stat-grid">
                <article className="hod-stat-card">
                  <div className="hod-stat-top">
                    <span>Total Students</span>
                    <span className="hod-stat-icon blue">♙</span>
                  </div>
                  <strong>—</strong>
                  <p>Registered students</p>
                </article>

                <article className="hod-stat-card">
                  <div className="hod-stat-top">
                    <span>Active Classes</span>
                    <span className="hod-stat-icon purple">▤</span>
                  </div>
                  <strong>—</strong>
                  <p>Academic groups</p>
                </article>

                <article className="hod-stat-card">
                  <div className="hod-stat-top">
                    <span>Active Elections</span>
                    <span className="hod-stat-icon orange">◷</span>
                  </div>
                  <strong>—</strong>
                  <p>Currently running</p>
                </article>

                <article className="hod-stat-card">
                  <div className="hod-stat-top">
                    <span>Completed Elections</span>
                    <span className="hod-stat-icon green">✓</span>
                  </div>
                  <strong>—</strong>
                  <p>Election history</p>
                </article>
              </section>

              <section className="hod-section-heading hod-quick-heading">
                <div>
                  <h2>Quick Access</h2>
                  <p>Choose a module to get started.</p>
                </div>
              </section>

              <section className="hod-quick-grid">
                <button
                  type="button"
                  className="hod-quick-card"
                  onClick={() => changePage("students")}
                >
                  <span className="hod-quick-icon blue">♙</span>
                  <strong>Manage Students</strong>
                  <p>Add, update and view student records.</p>
                  <span className="hod-quick-link">Open module →</span>
                </button>

                <button
                  type="button"
                  className="hod-quick-card"
                  onClick={() => changePage("classes")}
                >
                  <span className="hod-quick-icon purple">▤</span>
                  <strong>Manage Classes</strong>
                  <p>Manage academic years and semesters.</p>
                  <span className="hod-quick-link">Open module →</span>
                </button>

                <button
                  type="button"
                  className="hod-quick-card"
                  onClick={() => changePage("elections")}
                >
                  <span className="hod-quick-icon orange">◷</span>
                  <strong>Manage Elections</strong>
                  <p>Create and manage CR / FR elections.</p>
                  <span className="hod-quick-link">Open module →</span>
                </button>
              </section>
            </>
          )}

          {/* STUDENT MANAGEMENT */}
          {activePage === "students" && (
            <section className="hod-students-module">

              {/* No second Student Management heading here.
                  The top bar already displays that heading. */}

              {/* 01 - BULK UPLOAD */}
              <section className="hod-student-panel">
                <div className="hod-panel-heading">
                  <div className="hod-panel-number">01</div>

                  <div>
                    <h3>Bulk Upload</h3>
                    <p>
                      Select the admission year, academic year and semester, then
                      choose your Excel or CSV file.
                    </p>
                  </div>
                </div>

                <div className="hod-import-controls">
                  <label>
                    Admission Year

                    <select
                      value={importYear}
                      onChange={(event) =>
                        setImportYear(event.target.value)
                      }
                    >
                      {admissionYears.map((year) => (
                        <option key={year} value={year}>
                          {year}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Academic Year

                    <select
                      value={importAcademicYear}
                      onChange={(event) => setImportAcademicYear(event.target.value)}
                      required
                    >
                      <option value="">Select academic year</option>
                      {admissionYears.map((year) => (
                        <option key={year} value={year}>{year}</option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Semester

                    <select
                      value={importSemester}
                      onChange={(event) =>
                        setImportSemester(event.target.value)
                      }
                    >
                      <option value="">Select semester</option>

                      {semesters.map((semester) => (
                        <option key={semester} value={semester}>
                          Semester {semester}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <label className="hod-file-label">
  Excel / CSV File

  <input
    key={importFile?.name || "no-file"}
    type="file"
    accept=".csv,.xlsx"
    onChange={(event) => {
      setImportFile(event.target.files?.[0] || null);
      setImportPreview(null);
      setImportMessage("");
    }}
  />
</label>

                {importFile && (
                  <p className="hod-import-selected">
                    Selected file: {importFile.name}
                  </p>
                )}

                {importMessage && (
                  <p className="hod-student-notice" role="status">
                    {importMessage}
                  </p>
                )}
                {importPreview && (
  <div className="hod-import-preview">
   <div className="hod-import-preview-header">
  <h4>Validation Preview</h4>

  <button
    type="button"
    className="hod-import-cancel-button"
    onClick={() => {
      setImportPreview(null);
      setImportFile(null);
      setImportMessage("");
    }}
  >
    Cancel
  </button>
</div>

    <p>
      Branch: {importPreview.branch} |
      Admission Year: {importPreview.admission_year} |
      Academic Year: {importPreview.academic_year} |
      Semester: {importPreview.semester}
    </p>

    <p>
      Valid: {importPreview.valid_count} |
      Invalid: {importPreview.invalid_count}
    </p>

    {importPreview.valid_rows?.length > 0 && (
      <>
        <h4>Valid Students</h4>
        <table>
  <thead>
    <tr>
      <th>Name</th>
      <th>USN</th>
      <th>Email</th>
      <th>Semester</th>
      <th>Admission Year</th>
      <th>Academic Year</th>
    </tr>
  </thead>

  <tbody>
    {importPreview.valid_rows.map((student) => (
      <tr key={student.row}>
        <td>{student.name}</td>
        <td>{student.usn}</td>
        <td>{student.email}</td>
        <td>{importPreview.semester}</td>
        <td>{importPreview.admission_year}</td>
        <td>{importPreview.academic_year}</td>
      </tr>
    ))}
  </tbody>
</table>
      </>
    )}

    {importPreview.invalid_rows?.length > 0 && (
      <>
        <h4>Invalid Students</h4>
        <table>
  <thead>
    <tr>
      <th>Row</th>
      <th>Name</th>
      <th>USN</th>
      <th>Email</th>
      <th>Semester</th>
      <th>Admission Year</th>
      <th>Academic Year</th>
      <th>Validation Errors</th>
    </tr>
  </thead>

  <tbody>
    {importPreview.invalid_rows.map((student) => (
      <tr key={student.row}>
        <td>{student.row}</td>
        <td>{student.name}</td>
        <td>{student.usn}</td>
        <td>{student.email}</td>
        <td>{importPreview.semester}</td>
        <td>{importPreview.admission_year}</td>
        <td>{importPreview.academic_year}</td>
        <td>{student.errors.join(", ")}</td>
      </tr>
    ))}
  </tbody>
</table>
      </>
    )}
  </div>
)}

                {importPreview ? (
  <button
    type="button"
    className="hod-primary-button"
    disabled={importing || importPreview.valid_count === 0}
    onClick={handleConfirmImport}
  >
    {importing
      ? "Importing..."
      : importPreview.valid_count > 0
        ? `Confirm & Import ${importPreview.valid_count} Students`
        : "No Valid Students to Import"}
  </button>
) : (
  <button
    type="button"
    className="hod-primary-button"
    disabled={!importFile || !importAcademicYear || !importSemester || importing}
    onClick={handleImport}
  >
    {importing ? "Validating..." : "Preview & Validate"}
  </button>
)}
                <p className="hod-import-note">
                  Review the validated student records before confirming the import.
                  Only valid records will be registered.
                </p>
              </section>

              {/* 02 - INDIVIDUAL ADD */}
              <section className="hod-student-panel">
                <div className="hod-panel-heading">
                  <div className="hod-panel-number">02</div>

                  <div>
                    <h3>Individual Add</h3>
                    <p>
                      Register one student manually. The branch is
                      determined by your HOD account.
                    </p>
                  </div>
                </div>

                <form
                  className="hod-student-form"
                  onSubmit={handleAddStudent}
                >
                  <div className="hod-student-form-grid">
                    <label>
                      Student Full Name

                      <input
                        type="text"
                        name="name"
                        placeholder="Enter student name"
                        value={studentForm.name}
                        onChange={updateStudentForm}
                        required
                      />
                    </label>

                    <label>
                      USN

                      <input
                        type="text"
                        name="usn"
                        placeholder="Enter USN"
                        value={studentForm.usn}
                        onChange={updateStudentForm}
                        maxLength={10}
                        style={{ textTransform: "uppercase" }}
                        pattern="[0-9][Uu][Bb][0-9]{2}[A-Za-z]{2}[0-9]{3}"
                        required
                      />
                    </label>

                    <label>
                      Email Address

                      <input
                        type="email"
                        name="email"
                        placeholder="Enter student email"
                        value={studentForm.email}
                        onChange={updateStudentForm}
                        required
                      />
                    </label>

                    <label>
                      Admission Year

                      <select
                        name="admission_year"
                        value={studentForm.admission_year}
                        onChange={updateStudentForm}
                        required
                      >
                       <option value="">Select admission year</option>

                        {admissionYears.map((year) => (
                          <option key={year} value={year}>
                            {year}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Semester

                      <select
                        name="semester"
                        value={studentForm.semester}
                        onChange={updateStudentForm}
                        required
                      >
                      <option value="">Select semester</option>

                        {semesters.map((semester) => (
                          <option key={semester} value={semester}>
                            Semester {semester}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Academic Year

                      <select
                        name="academic_year"
                        value={studentForm.academic_year}
                        onChange={updateStudentForm}
                        required
                      >
                        <option value="">Select academic year</option>
                        {admissionYears.map((year) => (
                          <option key={year} value={year}>{year}</option>
                        ))}
                      </select>
                    </label>
                  </div>

                  {studentError && (
                    <p className="hod-student-error" role="alert">
                      {studentError}
                    </p>
                  )}

                  
                  <button
                    type="submit"
                    className="hod-primary-button"
                    disabled={studentSubmitting}
                  >
                    {studentSubmitting ? "Registering..." : "Add Student"}
                  </button>
                </form>
                {individualAddMessage && (
  <p className="hod-student-notice" role="status">
    {individualAddMessage}
  </p>
)}
              </section>

              {/* 03 - REGISTERED STUDENTS */}
              <section className="hod-student-panel">
                <div className="hod-panel-heading">
                  <div className="hod-panel-number">03</div>

                  <div>
                    <h3>Registered Student Management</h3>
                    <p>
                      Filter students by admission year, academic year, semester
                      or USN. Select records to manage them.
                    </p>
                  </div>
                </div>

                <div className="hod-student-filters">
                  <label>
                    Admission Year

                    <select
                      value={filterYear}
                      onChange={(event) => {
                        setFilterYear(event.target.value);
                        setStudentPage(1);
                      }}
                    >
                      <option value="">All Admission Years</option>

                      {admissionYears.map((year) => (
                        <option key={year} value={year}>
                          {year}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Academic Year

                    <select
                      value={filterAcademicYear}
                      onChange={(event) => {
                        setFilterAcademicYear(event.target.value);
                        setStudentPage(1);
                      }}
                    >
                      <option value="">All Academic Years</option>
                      {admissionYears.map((year) => (
                        <option key={year} value={year}>{year}</option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Semester

                    <select
                      value={filterSemester}
                      onChange={(event) => {
                        setFilterSemester(event.target.value);
                        setStudentPage(1);
                      }}
                    >
                      <option value="">All Semesters</option>

                      {semesters.map((semester) => (
                        <option key={semester} value={semester}>
                          Semester {semester}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="hod-search-field">
                    Search USN / Name / Email

                    <input
                      type="search"
                      placeholder="Enter USN, name or email"
                      value={studentSearch}
                      onChange={(event) => {
                        setStudentSearch(event.target.value);
                        setStudentPage(1);
                      }}
                    />
                  </label>
                </div>

                <div className="hod-student-toolbar">
                  <span>
                    {visibleStudents.length} matching student(s)
                  </span>

                 
                </div>

                {selectedStudents.length > 0 && (
                  <div className="hod-bulk-toolbar">
                    <span>
                      {selectedStudents.length} student(s) selected
                    </span>

                    <div>
                      <button
                        type="button"
                        className="hod-activate-button"
                        onClick={() => handleBulkStatusChange(true)}
                      >
                        Activate selected
                      </button>

                      <button
                        type="button"
                        className="hod-deactivate-button"
                        onClick={() => handleBulkStatusChange(false)}
                      >
                        Deactivate selected
                      </button>

                      {selectedUnactivatedStudentIds.length > 0 && <button
                        type="button"
                        className="hod-primary-button"
                        onClick={() => handleResendActivation(selectedUnactivatedStudentIds)}
                      >
                        Queue pending invitations
                      </button>}
                    </div>
                  </div>
                )}

                {studentListError && (
                  <p className="hod-student-error" role="alert">
                    {studentListError}
                  </p>
                )}

                {studentLoading ? (
                  <div className="hod-student-empty">
                    Loading registered students...
                  </div>
                ) : visibleStudents.length === 0 ? (
                  <div className="hod-student-empty">
                    No students match the selected filters.
                  </div>
                ) : (
                  <div className="hod-student-table-wrapper">
                    <table className="hod-student-table">
                      <thead>
                        <tr>
                          <th>
                            <input
                              type="checkbox"
                              aria-label="Select all visible students"
                              checked={allVisibleSelected}
                              onChange={toggleAllVisible}
                            />
                          </th>

                          <th>Name</th>
                          <th>USN</th>
                          <th>Email</th>
                          <th>Semester</th>
                          <th>Admission Year</th>
                          <th>Academic Year</th>
                          <th>Status</th>
                          <th>Action</th>
                        </tr>
                      </thead>

                      <tbody>
                        {visibleStudents.map((student) => (
                          <tr key={student.id}>
                            <td>
                              <input
                                type="checkbox"
                                aria-label={`Select ${student.name}`}
                                checked={selectedStudents.includes(
                                  student.id
                                )}
                                onChange={() =>
                                  toggleStudentSelection(student.id)
                                }
                              />
                            </td>

                            <td>{student.name}</td>
                            <td>{student.usn}</td>
                            <td>{student.email}</td>
                            <td>{student.semester}</td>
                            <td>{student.admission_year || "—"}</td>
                            <td>{student.academic_year || "—"}</td>

                            <td>
                              <span
                                className={
                                  student.is_active
                                    ? "hod-status-active"
                                    : "hod-status-inactive"
                                }
                              >
                                {student.is_active ? "Active" : "Inactive"}
                              </span>
                              <br />
                              <small>{student.is_activated ? "Activated" : student.activation_email_status === "FAILED" ? "Invitation failed — retry available" : student.activation_email_failure_kind === "TEMPORARY" ? "Invitation retry scheduled" : `Activation: ${student.activation_email_status || "pending"}`}</small>
                            </td>

                            <td>
                              <button
                                type="button"
                                className={
                                  student.is_active
                                    ? "hod-deactivate-button"
                                    : "hod-activate-button"
                                }
                                onClick={() =>
                                  handleSingleStatusChange(
                                    student,
                                    !student.is_active
                                  )
                                }
                              >
                                {student.is_active
                                  ? "Deactivate"
                                  : "Activate"}
                              </button>

                              {student.is_active && !student.is_activated && (
                                <button
                                  type="button"
                                  onClick={() => handleResendActivation([student.id])}
                                >
                                  {student.activation_email_status === "FAILED"
                                    ? "Retry invitation"
                                    : "Resend invitation"}
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {studentPagination && studentPagination.total_pages > 1 && (
                  <div className="hod-student-toolbar" aria-label="Student pagination">
                    <button
                      type="button"
                      onClick={() => changeStudentPage(studentPage - 1)}
                      disabled={studentPage <= 1}
                    >
                      Previous
                    </button>
                    <span>
                      Page {studentPagination.page} of {studentPagination.total_pages}
                    </span>
                    <button
                      type="button"
                      onClick={() => changeStudentPage(studentPage + 1)}
                      disabled={studentPage >= studentPagination.total_pages}
                    >
                      Next
                    </button>
                  </div>
                )}

                {studentMessage && (
                  <p className="hod-student-notice" role="status">
                    {studentMessage}
                  </p>
                )}
              </section>
            </section>
          )}

          {/* CLASSES & SEMESTERS */}
{activePage === "classes" && (
  <section className="hod-classes-module">

    <div className="hod-classes-toolbar">
  <p>
    Select admission year, academic year and semester to view the corresponding class.
  </p>

  <div className="hod-class-filters">
    <label>
      Admission Year

      <select
        value={classYearFilter}
        onChange={(event) =>
          setClassYearFilter(event.target.value)
        }
      >
        <option value="">Select admission year</option>

        {admissionYears.map((year) => (
          <option key={year} value={year}>
            {year}
          </option>
        ))}
      </select>
    </label>

    <label>
      Academic Year

      <select
        value={classAcademicYearFilter}
        onChange={(event) =>
          setClassAcademicYearFilter(event.target.value)
        }
      >
        <option value="">Select academic year</option>

        {admissionYears.map((year) => (
          <option key={year} value={year}>
            {year}
          </option>
        ))}
      </select>
    </label>

    <label>
      Semester

      <select
        value={classSemesterFilter}
        onChange={(event) =>
          setClassSemesterFilter(event.target.value)
        }
      >
        <option value="">Select semester</option>

        {semesters.map((semester) => (
          <option key={semester} value={semester}>
            Semester {semester}
          </option>
        ))}
      </select>
    </label>
  </div>
</div>


    {classesError && (
      <p className="hod-student-error" role="alert">
        {classesError}
      </p>
    )}

    {classesLoading ? (
      <div className="hod-student-empty">
        Loading classes from database...
      </div>
   ) : !classYearFilter || !classAcademicYearFilter || !classSemesterFilter ? (
  <div className="hod-student-empty">
    Select an admission year, academic year and semester to view classes.
  </div>
) : filteredClasses.length === 0 ? (
      <div className="hod-student-empty">
        No classes found. Register students to see classes here.
      </div>
    ) : (
      <>
        <p className="hod-classes-branch">
          Department: <strong>{classesBranch}</strong>
        </p>

        <div className="hod-classes-grid">
          {filteredClasses.map((classItem) => (
            
            <article
  className="hod-class-card"
  key={`${classItem.admission_year}-${classItem.academic_year}-${classItem.semester}`}
  role="button"
  tabIndex={0}
  onClick={() => {
    setFilterYear(String(classItem.admission_year));
    setFilterAcademicYear(String(classItem.academic_year));
    setFilterSemester(String(classItem.semester));
    setActivePage("students");
    setSidebarOpen(false);
  }}
  onKeyDown={(event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      event.currentTarget.click();
    }
  }}
>
              <div className="hod-class-card-header">
                <div>
                  <span>ADMISSION YEAR</span>
                  <h3>{classItem.admission_year || "Not specified"}</h3>
                </div>

                <span className="hod-class-semester">
                  Semester {classItem.semester}
                </span>
              </div>

              <div className="hod-class-total">
                <strong>{classItem.total_students}</strong>
                <span>Total Students</span>
              </div>

              <div className="hod-class-stats">
                <div>
                  <strong>{classItem.active_students}</strong>
                  <span>Active</span>
                </div>

                <div>
                  <strong>{classItem.inactive_students}</strong>
                  <span>Inactive</span>
                </div>

                <div>
                  <strong>{classItem.cr_count}</strong>
                  <span>CR</span>
                </div>

                <div>
                  <strong>{classItem.fr_count}</strong>
                  <span>FR</span>
                </div>
              </div>
            </article>
          ))}
        </div>
      </>
    )}
  </section>
)}

{/* OTHER MODULES */}
{electionError && <p className="hod-student-error" role="alert">{electionError}</p>}
{electionMessage && <p className="hod-student-notice" role="status">{electionMessage}</p>}

{activePage === "elections" && (
  <section className="hod-election-module">
    <header className="hod-election-hero">
      <div><span>DEPARTMENT ELECTIONS</span><h2>CR &amp; FR election control</h2><p>Create a class-specific draft, review candidates, then open a secure timed ballot.</p></div>
      <div aria-hidden="true">▣</div>
    </header>
    <div className="hod-election-workspace">
      <aside className="hod-election-create-panel">
        <div className="hod-candidate-panel-heading"><span>01</span><div><h3>Create a draft</h3><p>Academic eligibility is snapshotted at creation.</p></div></div>
        <form className="hod-election-form" onSubmit={handleCreateElection}>
          <label>Election title<input value={electionForm.title} onChange={(event) => setElectionForm((previous) => ({ ...previous, title: event.target.value }))} maxLength="200" placeholder="e.g. CSE CR Election" required /></label>
          <label>Description <small>Optional</small><textarea value={electionForm.description} onChange={(event) => setElectionForm((previous) => ({ ...previous, description: event.target.value }))} maxLength="5000" rows="3" placeholder="Brief election context" /></label>
          <div className="hod-election-form-grid">
            <label>Representative type<select value={electionForm.election_type} onChange={(event) => setElectionForm((previous) => ({ ...previous, election_type: event.target.value }))}><option value="CR">Class Representative</option><option value="FR">Faculty Representative</option></select></label>
            <label>Admission year<select value={electionForm.admission_year} onChange={(event) => setElectionForm((previous) => ({ ...previous, admission_year: event.target.value }))} required><option value="">Select year</option>{admissionYears.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
            <label>Academic year<select value={electionForm.academic_year} onChange={(event) => setElectionForm((previous) => ({ ...previous, academic_year: event.target.value }))} required><option value="">Select year</option>{admissionYears.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
            <label>Semester<select value={electionForm.semester} onChange={(event) => setElectionForm((previous) => ({ ...previous, semester: event.target.value }))} required><option value="">Select semester</option>{semesters.map((semester) => <option key={semester} value={semester}>Semester {semester}</option>)}</select></label>
            <label>Voting minutes<input type="number" min="1" max="10080" value={electionForm.duration_minutes} onChange={(event) => setElectionForm((previous) => ({ ...previous, duration_minutes: event.target.value }))} required /></label>
          </div>
          <button type="submit">Create draft <span aria-hidden="true">→</span></button>
        </form>
      </aside>
      <section className="hod-election-list-panel">
        <div className="hod-candidate-list-heading"><div><span className="hod-candidate-eyebrow">02 · ELECTION DIRECTORY</span><h3>Department elections</h3><p>Each card shows the live workflow state and approved candidate readiness.</p></div><strong className="hod-election-total">{elections.length} election{elections.length === 1 ? "" : "s"}</strong></div>
        {electionsLoading ? <div className="hod-election-empty"><span>◌</span><h4>Loading elections</h4><p>Retrieving your department election directory.</p></div> : elections.length === 0 ? <div className="hod-election-empty"><span>▣</span><h4>No elections created</h4><p>Create a class-specific draft from the panel on the left.</p></div> : <div className="hod-election-card-grid">{elections.map((election) => <article className="hod-election-card" key={election.id}>
          <div className="hod-election-card-top"><span className="hod-election-type">{election.election_type}</span><span className={`hod-election-status ${election.status.toLowerCase()}`}>{election.status}</span></div>
          <h4>{election.title}</h4>
          <p className="hod-election-cohort">{election.admission_year} · Semester {election.semester}</p>
          <p className="hod-election-description">{election.description || "No additional description provided."}</p>
          <div className="hod-election-metrics"><div><strong>{election.eligible_voters}</strong><span>eligible voters</span></div><div><strong>{election.approved_candidates}</strong><span>approved candidates</span></div><div><strong>{election.duration_minutes}</strong><span>minutes</span></div></div>
          <div className="hod-election-actions">{election.status === "DRAFT" && <><button type="button" className="edit" onClick={() => handleEditElection(election)}>Edit</button><button type="button" className="start" onClick={() => changeElectionStatus(election.id, "start")}>Start voting</button></>}{election.status === "OPEN" && <button type="button" className="close" onClick={() => changeElectionStatus(election.id, "close")}>Close voting</button>}{election.status === "CLOSED" && <button type="button" className="results" onClick={() => { setActivePage("results"); loadResult(election.id); }}>View results</button>}</div>
        </article>)}</div>}
      </section>
    </div>
  </section>
)}

{activePage === "candidates" && (
  <section className="hod-candidate-module">
    <header className="hod-candidate-hero">
      <div>
        <span className="hod-candidate-eyebrow">ELECTION CONTROL</span>
        <h2>Candidate management</h2>
        <p>Register, assign a unique election symbol, and review each candidate before voting opens.</p>
      </div>
      <div className="hod-candidate-hero-mark" aria-hidden="true">★</div>
    </header>

    <div className="hod-candidate-workspace">
      <aside className="hod-candidate-form-panel">
        <div className="hod-candidate-panel-heading">
          <span>01</span>
          <div><h3>Register a candidate</h3><p>Select a draft election first.</p></div>
        </div>

        <label className="hod-candidate-label">
          Election
          <select value={selectedElectionId} onChange={(event) => { setSelectedElectionId(event.target.value); loadCandidates(event.target.value); }}>
            <option value="">Select a draft election</option>
            {elections.filter((election) => ["DRAFT", "SCHEDULED"].includes(election.status)).map((election) => <option key={election.id} value={election.id}>{election.title} · Semester {election.semester}</option>)}
          </select>
        </label>

        <form className="hod-candidate-form" onSubmit={handleCandidateSubmit}>
          <label className="hod-candidate-label">
            Student USN
            <input value={candidateUsn} onChange={(event) => setCandidateUsn(event.target.value.toUpperCase())} placeholder="4UB23CS026" maxLength="10" required />
          </label>

          <fieldset className="hod-symbol-picker" disabled={!selectedElectionId || !candidateSymbols.length}>
            <legend>Election symbol <small>Unique within this election</small></legend>
            <div className="hod-symbol-grid">
              {candidateSymbols.map((symbol) => <button key={symbol.key} type="button" className={candidateSymbolKey === symbol.key ? "selected" : ""} onClick={() => setCandidateSymbolKey(symbol.key)} aria-pressed={candidateSymbolKey === symbol.key} title={symbol.label}><span>{symbol.glyph}</span><small>{symbol.label}</small></button>)}
            </div>
            {!candidateSymbols.length && <p>Loading approved symbols…</p>}
          </fieldset>

          <label className="hod-candidate-label">
            Manifesto <span>Optional</span>
            <textarea value={candidateManifesto} onChange={(event) => setCandidateManifesto(event.target.value)} maxLength="5000" rows="4" placeholder="Brief candidate statement" />
          </label>
          <button className="hod-candidate-submit" type="submit" disabled={!selectedElectionId || !candidateSymbols.length}>Register candidate <span aria-hidden="true">→</span></button>
        </form>
      </aside>

      <section className="hod-candidate-list-panel" aria-live="polite">
        <div className="hod-candidate-list-heading">
          <div>
            <span className="hod-candidate-eyebrow">02 · REVIEW QUEUE</span>
            <h3>{selectedElectionId ? "Registered candidates" : "Choose an election"}</h3>
            <p>{selectedElectionId ? "Approve only eligible students. Symbols cannot change once voting opens." : "Candidate records appear here after an election is selected."}</p>
          </div>
          {selectedElectionId && <div className="hod-candidate-counts"><span>{candidates.length} total</span><strong>{candidates.filter((candidate) => candidate.review_status === "APPROVED").length} approved</strong></div>}
        </div>

        {!selectedElectionId ? <div className="hod-candidate-empty"><span aria-hidden="true">⌁</span><h4>No election selected</h4><p>Select a draft election to view its candidate queue.</p></div> : candidates.length === 0 ? <div className="hod-candidate-empty"><span aria-hidden="true">♧</span><h4>No candidates yet</h4><p>Register the first eligible candidate using the panel on the left.</p></div> : <div className="hod-candidate-card-grid">{candidates.map((candidate) => {
          const reviewStatus = candidate.review_status || (candidate.is_approved ? "APPROVED" : "PENDING");
          return <article className="hod-candidate-card" key={candidate.id}>
            <div className="hod-candidate-card-top">
              <div className="hod-candidate-symbol" title={candidate.symbol?.label || "Symbol pending"}>{candidate.symbol?.glyph || "◌"}</div>
              <span className={`hod-candidate-status ${reviewStatus.toLowerCase()}`}>{reviewStatus}</span>
            </div>
            <h4>{candidate.name}</h4>
            <p className="hod-candidate-usn">USN · {candidate.usn}</p>
            <p className="hod-candidate-symbol-label">{candidate.symbol?.label || "Symbol pending"}</p>
            <p className="hod-candidate-manifesto">{candidate.manifesto || "No manifesto submitted."}</p>
            {reviewStatus === "PENDING" || !candidate.is_approved ? <div className="hod-candidate-actions"><button type="button" className="approve" onClick={() => reviewCandidate(candidate.id, "approve")}>Approve</button><button type="button" className="reject" onClick={() => reviewCandidate(candidate.id, "reject")}>Reject</button></div> : <div className="hod-candidate-reviewed">Reviewed and locked for this draft</div>}
          </article>;
        })}</div>}
      </section>
    </div>
  </section>
)}

{activePage === "results" && (
  <section className="hod-module-card">
    <h2>Election Results</h2>
    {elections.filter((election) => election.status === "CLOSED").length === 0 ? <p>Results become available only after an election is closed.</p> : <p>{elections.filter((election) => election.status === "CLOSED").map((election) => <button key={election.id} type="button" onClick={() => loadResult(election.id)}>{election.title}</button>)}</p>}
    {result && <div className="hod-student-table-wrapper"><h3>{result.election.title}</h3><p>Turnout: {result.participation_count} of {result.eligible_voters} ({result.turnout_percentage}%). {result.is_tie ? "Tie result." : result.winners.length ? `Winner: ${result.winners[0].name}.` : "No winner."}</p><table className="hod-student-table"><thead><tr><th>Symbol</th><th>Candidate</th><th>Votes</th></tr></thead><tbody>{result.candidates.map((candidate) => <tr key={candidate.id}><td>{candidate.symbol?.glyph || "◌"} {candidate.symbol?.label || "Pending"}</td><td>{candidate.name} ({candidate.usn})</td><td>{candidate.vote_count}</td></tr>)}</tbody></table></div>}
  </section>
)}
          <footer className="hod-footer">
            <span>UBDTCE Secure E-Voting System</span>
            <span>HOD Portal</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
