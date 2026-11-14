
import { useEffect, useState } from "react";
import HODDashboard from "./HODDashboard";
import StudentDashboard from "./StudentDashboard";
import "./App.css";

const API_BASE = (
  import.meta.env.VITE_API_BASE ||
  `${window.location.protocol}//${window.location.hostname}:5000/api`
).replace(/\/+$/, "");

async function apiFetch(input, init = {}) {
  const method = String(init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers || {});

  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    headers.set("X-Requested-With", "XMLHttpRequest");
  }

  return fetch(input, {
    ...init,
    headers,
    credentials: init.credentials || "include",
  });
}

const roles = [
  {
    number: "01",
    title: "Student Portal",
    description:
      "Access eligible elections, review candidates, and cast your vote during an active election.",
    icon: "S",
    target: "student",
  },
  {
    number: "02",
    title: "HOD Portal",
    description:
      "Manage your assigned department, student records, candidates, and branch elections.",
    icon: "H",
    target: "hod",
  },
  {
    number: "03",
    title: "Principal Portal",
    description:
      "Manage college branches, oversee elections, and configure college-wide voting.",
    icon: "P",
    target: "principal",
  },
];

const collegeElectionTypeOptions = [
  { value: "PRESIDENT", label: "College President", candidateRule: "Candidates must be verified winners of completed CR elections." },
  { value: "JOINT_SECRETARY", label: "Joint Secretary", candidateRule: "Candidates must be verified winners of completed CR or FR elections." },
  { value: "CULTURAL", label: "Cultural President", candidateRule: "Candidates are active students in the selected branches and cohort." },
  { value: "SPORTS", label: "Sports President", candidateRule: "Candidates are active students in the selected branches and cohort." },
  { value: "OTHER", label: "Other representative position", candidateRule: "Candidates are active students in the selected branches and cohort." },
];

const ACADEMIC_YEARS = Array.from({ length: 27 }, (_, index) => 2022 + index);

function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [selectedRole, setSelectedRole] = useState(() => {
  const params = new URLSearchParams(window.location.search);
  const role = params.get("role");
  const path = window.location.pathname.replace(/\/+$/, "");

  if (role === "student" || role === "hod" || role === "principal") {
    return role;
  }

  if (
    path === "/student-activate" ||
    path === "/student-reset-password"
  ) {
    return "student";
  }

  return params.has("token") ? "principal" : "student";
});
  const [branches, setBranches] = useState([]);
  const [branchLoading, setBranchLoading] = useState(true);
  const [branchError, setBranchError] = useState("");

  const [statistics, setStatistics] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState("");

  const [refreshKey, setRefreshKey] = useState(0);

  const [loginEmail, setLoginEmail] = useState("");
  const [loginUSN, setLoginUSN] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginMessage, setLoginMessage] = useState("");
  const [currentUser, setCurrentUser] = useState(null);
  const [principalDashboard, setPrincipalDashboard] = useState(null);

  const [newBranchName, setNewBranchName] = useState("");
  const [newBranchCode, setNewBranchCode] = useState("");
  const [branchActionMessage, setBranchActionMessage] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);
  // Principal email management
const [principalEmails, setPrincipalEmails] = useState(null);
const [emailInput, setEmailInput] = useState("");
const [emailOtp, setEmailOtp] = useState("");
const [emailPassword, setEmailPassword] = useState("");
const [confirmEmailPassword, setConfirmEmailPassword] = useState("");
const [passwordForms, setPasswordForms] = useState({});
const [passwordBusyEmail, setPasswordBusyEmail] = useState("");
const [passwordMessages, setPasswordMessages] = useState({});
const [emailMessage, setEmailMessage] = useState("");
const [emailBusy, setEmailBusy] = useState(false);
const [otpSentTo, setOtpSentTo] = useState("");
const [emailOtpExpiresIn, setEmailOtpExpiresIn] = useState(0);
const [emailResendIn, setEmailResendIn] = useState(0);
  const [principalSection, setPrincipalSection] = useState("overview");
  const [dashboardTheme, setDashboardTheme] = useState("light");
  const [electionTitle, setElectionTitle] = useState("");
  const [collegeElectionType, setCollegeElectionType] = useState("PRESIDENT");
  const [collegePositionName, setCollegePositionName] = useState("");
  const [electionDuration, setElectionDuration] = useState("30");
  const [presidentAdmissionYear, setPresidentAdmissionYear] = useState("");
  const [presidentAcademicYear, setPresidentAcademicYear] = useState("");
  const [presidentSemester, setPresidentSemester] = useState("");
  const [selectedElectionBranches, setSelectedElectionBranches] = useState([]);
  const [electionMessage, setElectionMessage] = useState("");
  const [electionMessageType, setElectionMessageType] = useState("");
  const [electionLoading, setElectionLoading] = useState(false);
  const [principalElections, setPrincipalElections] = useState([]);
  const [principalElectionsLoading, setPrincipalElectionsLoading] = useState(false);
  const [selectedPrincipalElectionId, setSelectedPrincipalElectionId] = useState("");
  const [principalCandidates, setPrincipalCandidates] = useState([]);
  const [principalCandidateUsn, setPrincipalCandidateUsn] = useState("");
  const [principalCandidateManifesto, setPrincipalCandidateManifesto] = useState("");
  const [principalCandidateSymbolKey, setPrincipalCandidateSymbolKey] = useState("book");
  const [candidateSymbols, setCandidateSymbols] = useState([]);
  const [eligiblePrincipalCandidates, setEligiblePrincipalCandidates] = useState([]);
  const [principalResult, setPrincipalResult] = useState(null);
  const [branchBusyId, setBranchBusyId] = useState(null);
  const [hodAssignments, setHodAssignments] = useState([]);
  const [hodLoading, setHodLoading] = useState(false);
  const [hodLoadError, setHodLoadError] = useState("");
  const [hodSubmitting, setHodSubmitting] = useState(false);
  const [hodName, setHodName] = useState("");
  const [hodEmail, setHodEmail] = useState("");
  const [hodBranchId, setHodBranchId] = useState("");
  const [hodMessage, setHodMessage] = useState("");
  const [hodMessageType, setHodMessageType] = useState("success");
  const [hodResendBusyId, setHodResendBusyId] = useState(null);
  const [hodDeleteBusyId, setHodDeleteBusyId] = useState(null);

  // Password recovery is a dedicated page, separate from the public website.
  const [authView, setAuthView] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const resetPath = window.location.pathname.replace(/\/+$/, "") === "/reset-password";
    return params.has("token") || resetPath ? "reset" : "login";
  });
  const [recoveryEmail, setRecoveryEmail] = useState("");
  const [recoveryUSN, setRecoveryUSN] = useState("");
  const [recoveryPurpose, setRecoveryPurpose] = useState(() =>
    new URLSearchParams(window.location.search).get("setup") === "1"
      ? "HOD_SETUP"
      : "RESET"
  );
  const [recoveryBranchName, setRecoveryBranchName] = useState("");
  const [recoveryToken, setRecoveryToken] = useState(() =>
    new URLSearchParams(window.location.search).get("token") || ""
  );
  const [recoveryTokenStatus, setRecoveryTokenStatus] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const resetPath = window.location.pathname.replace(/\/+$/, "") === "/reset-password";
    return params.get("token") ? "checking" : resetPath ? "invalid" : "idle";
  });
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [recoveryMessage, setRecoveryMessage] = useState("");
  const [recoveryMessageType, setRecoveryMessageType] = useState("");
  const [recoveryLoading, setRecoveryLoading] = useState(false);
  const currentAuthPath =
  window.location.pathname.replace(/\/+$/, "");

const isStudentActivationPage =
  currentAuthPath === "/student-activate";

const isStudentResetPage =
  currentAuthPath === "/student-reset-password";

const isStandaloneResetPage =
  currentAuthPath === "/reset-password" ||
  isStudentActivationPage ||
  isStudentResetPage ||
  new URLSearchParams(window.location.search).has("token") ||
  (authView === "reset" && Boolean(recoveryToken));
  // Capture the emailed token, remove it from the address bar, and check
  // that it is still unused and within its 15-minute validity period.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token") || recoveryToken;
    const currentPath = window.location.pathname.replace(/\/+$/, "");

    const recoveryPaths = [
  "/reset-password",
  "/student-reset-password",
  "/student-activate",
];

const isRecoveryPath = recoveryPaths.includes(currentPath);

  if (token) {
  const targetPath = isRecoveryPath
    ? currentPath
    : "/reset-password";

  window.history.replaceState({}, "", targetPath);
}

    if (!isRecoveryPath && !token) return undefined;
    if (!token) return undefined;

    let controller;
    const requestId = window.setTimeout(() => {
      controller = new AbortController();
      setRecoveryTokenStatus("checking");

      apiFetch(`${API_BASE}/auth/validate-reset-token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
        signal: controller.signal,
      })
        .then(async (response) => {
          const data = await response.json().catch(() => ({}));
          if (controller.signal.aborted) return;
          if (response.ok && data.valid === true) {
            setRecoveryPurpose(data.purpose || "RESET");
            setRecoveryBranchName(data.branch_name || "");
            setRecoveryTokenStatus("valid");
          } else {
            setRecoveryTokenStatus("invalid");
            setRecoveryMessage(
              data.message || "This reset link has already been used or has expired."
            );
          }
        })
        .catch((error) => {
          if (error.name !== "AbortError") {
            setRecoveryTokenStatus("error");
            setRecoveryMessage("We could not verify this reset link. Please try again or request a new link.");
          }
        });
    }, 0);

    return () => {
      window.clearTimeout(requestId);
      controller?.abort();
    };
    // This must run only for the token captured when the email link is opened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    async function loadBranches() {
      try {
        setBranchLoading(true);
        setBranchError("");

        const response = await apiFetch(`${API_BASE}/branches`, {
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error("Department request failed.");
        }

        const data = await response.json();

        if (!Array.isArray(data.branches)) {
          throw new Error("Invalid department data.");
        }

        setBranches(data.branches);
      } catch (error) {
        if (error.name !== "AbortError") {
          setBranchError(
            "Unable to load departments. Check that the Flask backend is running."
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setBranchLoading(false);
        }
      }
    }

    async function loadStatistics() {
      try {
        setStatsLoading(true);
        setStatsError("");

        const response = await apiFetch(`${API_BASE}/statistics`, {
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error("Statistics request failed.");
        }

        const data = await response.json();

        if (
          data.status !== "ok" ||
          !Array.isArray(data.departments)
        ) {
          throw new Error("Invalid statistics data.");
        }

        setStatistics(data);
      } catch (error) {
        if (error.name !== "AbortError") {
          setStatsError(
            "Unable to load student statistics. Please try again."
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setStatsLoading(false);
        }
      }
    }

    loadBranches();
    loadStatistics();

    return () => controller.abort();
  }, [refreshKey]);

  const closeMenu = () => setMenuOpen(false);

  // Login for Principal and HOD.
  const handleLogin = async (event) => {
    event.preventDefault();
    setLoginMessage("");
    setLoginLoading(true);

    try {
     if (selectedRole === "student") {
        const usn = loginUSN.trim().toUpperCase();
    
     if (!/^[0-9]UB[0-9]{2}[A-Z]{2}[0-9]{3}$/.test(usn)) {
    setLoginMessage("Enter a valid 10-character USN, e.g. 4UB23CS406.");
    return;
  }
}

      

      const response = await apiFetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify(
  selectedRole === "student"
    ? {
        usn: loginUSN.trim().toUpperCase(),
        password: loginPassword,
      }
    : {
        email: loginEmail.trim(),
        password: loginPassword,
      }
),
      });

      const data = await response.json();

      if (!response.ok) {
        setLoginMessage(
          data.message || "Login failed. Please try again."
        );
        return;
      }

      const expectedRole =
  selectedRole === "principal"
    ? "PRINCIPAL"
    : selectedRole === "hod"
      ? "HOD"
      : "STUDENT";

      if (data.user?.role !== expectedRole) {
        await apiFetch(`${API_BASE}/auth/logout`, { method: "POST" });
        setLoginMessage(
          `This account is not authorised for the ${
            selectedRole === "principal" ? "Principal" : "HOD"
          } Portal.`
        );
        return;
      }

      // Load the Principal dashboard before entering it.
      if (selectedRole === "principal") {
        const dashboardResponse = await apiFetch(
          `${API_BASE}/principal/dashboard`,
          {
            method: "GET",
            credentials: "include",
          }
        );

        const dashboardData = await dashboardResponse.json();

        if (!dashboardResponse.ok) {
          await apiFetch(`${API_BASE}/auth/logout`, { method: "POST" });
          setLoginMessage(
            dashboardData.message ||
              "Could not load Principal dashboard."
          );
          return;
        }

        setPrincipalDashboard(dashboardData);
      }

      // FIX: Set currentUser for both Principal and HOD.
      setCurrentUser(data.user);

      setLoginMessage(
        `${selectedRole === "principal"
  ? "Principal"
  : selectedRole === "hod"
    ? "HOD"
    : "Student"} login successful.`
      );
    } catch {
      setLoginMessage(
        "Cannot connect to the server. Check that Flask is running."
      );
    } finally {
      setLoginLoading(false);
    }
  };
    const handleLogout = async () => {
    try {
      const response = await apiFetch(`${API_BASE}/auth/logout`, {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error("The server could not end your session. Please try again.");
      }
      setCurrentUser(null);
      setPrincipalDashboard(null);
      setLoginPassword("");
      setLoginMessage("");
      setSelectedRole((role) => (role === "hod" ? "hod" : "principal"));
      setPrincipalSection("overview");
    } catch (error) {
      setLoginMessage(error.message || "Could not log out. Check your connection.");
    }
  };

  // Create a branch using the Principal API.
  const handleCreateBranch = async (event) => {
    event.preventDefault();
    setBranchActionMessage("");

    const name = newBranchName.trim();
    const code = newBranchCode.trim().toUpperCase();

    if (!name || !code) {
      setBranchActionMessage("Please enter both branch name and code.");
      return;
    }

    try {
      const response = await apiFetch(`${API_BASE}/principal/branches`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({ name, code }),
      });

      const data = await response.json();

      if (!response.ok) {
        setBranchActionMessage(
          data.message || "Could not create the branch."
        );
        return;
      }

      setNewBranchName("");
      setNewBranchCode("");
      setBranchActionMessage("Branch created successfully.");

      // Reload the dashboard so PostgreSQL's saved data is displayed.
      const dashboardResponse = await apiFetch(
        `${API_BASE}/principal/dashboard`,
        { credentials: "include" }
      );

      const dashboardData = await dashboardResponse.json();

      if (!dashboardResponse.ok) {
        setBranchActionMessage(
          "Branch saved, but the dashboard could not refresh. Reload the page."
        );
        return;
      }

      setPrincipalDashboard(dashboardData);
      setRefreshKey((key) => key + 1);
    } catch {
      setBranchActionMessage(
        "Cannot connect to the server. Check that Flask is running."
      );
    }
  };

  const refreshPrincipalDashboard = async () => {
    const response = await apiFetch(`${API_BASE}/principal/dashboard`, {
      credentials: "include",
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || "Could not refresh dashboard.");
    setPrincipalDashboard(data);
  };

  const refreshHodAssignments = async () => {
    const response = await apiFetch(`${API_BASE}/principal/hods`, {
      credentials: "include",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.message || "Could not load HOD assignments.");
    }
    setHodAssignments(Array.isArray(data.assignments) ? data.assignments : []);
  };

  const retryHodAssignments = async () => {
    setHodLoading(true);
    setHodLoadError("");
    try {
      await refreshHodAssignments();
    } catch (error) {
      setHodLoadError(error.message || "Could not load HOD assignments.");
    } finally {
      setHodLoading(false);
    }
  };

  const handleAssignHod = async (event) => {
    event.preventDefault();
    setHodMessage("");

    if (!hodBranchId || !hodName.trim() || !hodEmail.trim()) {
      setHodMessage("Select a branch and enter the HOD's full name and email.");
      setHodMessageType("error");
      return;
    }

    setHodSubmitting(true);
    try {
      const response = await apiFetch(`${API_BASE}/principal/hods`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          branch_id: Number(hodBranchId),
          hod_name: hodName.trim(),
          email: hodEmail.trim(),
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.message || "Could not assign this HOD.");
      }

      setHodName("");
      setHodEmail("");
      setHodBranchId("");
      setHodMessage(data.message || "HOD assigned successfully.");
      setHodMessageType("success");
      try {
        await Promise.all([refreshHodAssignments(), refreshPrincipalDashboard()]);
      } catch {
        setHodMessage("The HOD was assigned, but the list could not refresh. Reopen HOD Management to reload it.");
        setHodMessageType("error");
      }
    } catch (error) {
      setHodMessage(error.message || "Could not connect to the HOD management service.");
      setHodMessageType("error");
    } finally {
      setHodSubmitting(false);
    }
  };

  const handleResendHodInvitation = async (accountId) => {
    setHodResendBusyId(accountId);
    setHodMessage("");
    try {
      const response = await apiFetch(
        `${API_BASE}/principal/hods/${accountId}/resend-invitation`,
        { method: "POST", credentials: "include" }
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.message || "Could not resend the HOD setup email.");
      }
      setHodMessage(data.message || "A new setup link was sent.");
      setHodMessageType("success");
      await refreshHodAssignments();
    } catch (error) {
      setHodMessage(error.message || "Could not resend the HOD setup email.");
      setHodMessageType("error");
    } finally {
      setHodResendBusyId(null);
    }
  };
  const handleRemoveHod = async (accountId) => {
  const confirmed = window.confirm(
    "Are you sure you want to remove this HOD?\n\n" +
    "Their department access will be revoked. Historical records will be preserved."
  );

  if (!confirmed) return;

  setHodDeleteBusyId(accountId);
  setHodMessage("");

  try {
    const response = await apiFetch(
      `${API_BASE}/principal/hods/${accountId}`,
      {
        method: "DELETE",
        credentials: "include",
      }
    );

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.message || "Could not remove HOD.");
    }

    setHodMessage(data.message || "HOD removed successfully.");
    setHodMessageType("success");

    await refreshHodAssignments();
    await refreshPrincipalDashboard();

  } catch (error) {
    setHodMessage(error.message || "Could not remove HOD.");
    setHodMessageType("error");

  } finally {
    setHodDeleteBusyId(null);
  }
};
  // Load the Principal's saved email addresses.
const loadPrincipalEmails = async () => {
  try {
    const response = await apiFetch(
      `${API_BASE}/principal/settings/emails`,
      { credentials: "include" }
    );

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(
        data.message || "Could not load email addresses."
      );
    }

    setPrincipalEmails(data);
  } catch (error) {
    setEmailMessage(
      error.message || "Could not connect to the email service."
    );
  }
};

// Send a verification OTP to the requested email.
const handleSendEmailOtp = async (event) => {
  event.preventDefault();

  const email = emailInput.trim().toLowerCase();

  if (!email) {
    setEmailMessage("Please enter an email address.");
    return;
  }

  setEmailBusy(true);
  setEmailMessage("");

  try {
    const response = await apiFetch(
      `${API_BASE}/principal/settings/email/send-otp`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email }),
      }
    );

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      const waitMessage = data.retry_after_seconds
        ? ` Please try again in ${data.retry_after_seconds} seconds.`
        : "";

      throw new Error(
        (data.message || "Could not send the verification code.") +
        waitMessage
      );
    }

    setOtpSentTo(email);
setEmailOtp("");

setEmailOtpExpiresIn(
  Number(data.expires_in_seconds) || 180
);
setEmailResendIn(
  Number(data.resend_after_seconds) || 120
);

setEmailMessage(
  data.message || "Verification code sent. Check your email."
);
  } catch (error) {
    setEmailMessage(
      error.message || "Could not connect to the email service."
    );
  } finally {
    setEmailBusy(false);
  }
};

// Verify the OTP and save the additional email address.
const handleVerifyEmailOtp = async (event) => {
  event.preventDefault();

  if (!otpSentTo) {
    setEmailMessage("Please request a verification code first.");
    return;
  }

  if (!/^\d{6}$/.test(emailOtp.trim())) {
    setEmailMessage("Enter the six-digit verification code.");
    return;
  }

  setEmailBusy(true);
  setEmailMessage("");

  try {
    const response = await apiFetch(
      `${API_BASE}/principal/settings/email/verify-otp`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
       body: JSON.stringify({
  email: otpSentTo,
  otp: emailOtp.trim(),
  password: emailPassword,
  confirm_password: confirmEmailPassword,
}),
      }
    );

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(
        data.message || "Email verification failed."
      );
    }

    setEmailMessage(
      data.message || "Email address verified successfully."
    );

    setEmailInput("");
    setEmailOtp("");
    setOtpSentTo("");
    setEmailPassword("");
    setConfirmEmailPassword("");

    await loadPrincipalEmails();
  } catch (error) {
    setEmailMessage(
      error.message || "Could not connect to the email service."
    );
  } finally {
    setEmailBusy(false);
  }
};

// Remove only the additional verified email.
const handleDeletePrincipalEmail = async (emailId) => {
  const confirmed = window.confirm(
    "Remove this additional email address? Your primary login email will not be changed."
  );

  if (!confirmed) return;

  setEmailBusy(true);
  setEmailMessage("");

  try {
    const response = await apiFetch(
      `${API_BASE}/principal/settings/emails/${emailId}`,
      {
        method: "DELETE",
        credentials: "include",
      }
    );

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(
        data.message || "Could not remove this email address."
      );
    }

    setEmailMessage(
      data.message || "Additional email removed successfully."
    );

    setEmailInput("");
    setEmailOtp("");
    setOtpSentTo("");

    await loadPrincipalEmails();
  } catch (error) {
    setEmailMessage(
      error.message || "Could not connect to the email service."
    );
  } finally {
    setEmailBusy(false);
  }
};
// Delete the primary email and promote the other verified email.
const handleDeletePrimaryEmail = async () => {
  const confirmed = window.confirm(
    "Delete the primary email? The other verified email will become the primary login email and keep its own password."
  );

  if (!confirmed) return;

  setEmailBusy(true);
  setEmailMessage("");

  try {
    const response = await apiFetch(
      `${API_BASE}/principal/settings/emails/primary`,
      {
        method: "DELETE",
        credentials: "include",
      }
    );

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(
        data.message || "Could not delete the primary email."
      );
    }

    setEmailMessage(data.message || "Primary email removed successfully.");
    setEmailInput("");
    setEmailOtp("");
    setEmailPassword("");
    setConfirmEmailPassword("");
    setOtpSentTo("");
    setEmailOtpExpiresIn(0);
    setEmailResendIn(0);

    await loadPrincipalEmails();
  } catch (error) {
    setEmailMessage(
      error.message || "Could not connect to the email service."
    );
  } finally {
    setEmailBusy(false);
  }
};



// Update the form fields for one specific email.
const handlePasswordFieldChange = (email, field, value) => {
  setPasswordForms((current) => ({
    ...current,
    [email]: {
      ...(current[email] || {}),
      [field]: value,
    },
  }));
};

// Change the password for the selected email only.
const handleChangePrincipalEmailPassword = async (event, email) => {
  event.preventDefault();

  const form = passwordForms[email] || {};
  const currentPassword = form.current_password || "";
  const newPasswordValue = form.new_password || "";
  const confirmPasswordValue = form.confirm_password || "";

  const setMessage = (type, message) => {
    setPasswordMessages((current) => ({
      ...current,
      [email]: { type, message },
    }));
  };

  if (!currentPassword || !newPasswordValue || !confirmPasswordValue) {
    setMessage("error", "Please complete all password fields.");
    return;
  }

  if (newPasswordValue.length < 12) {
    setMessage("error", "Use a password with at least 12 characters.");
    return;
  }

  if (newPasswordValue !== confirmPasswordValue) {
    setMessage("error", "The new passwords do not match.");
    return;
  }

  setPasswordBusyEmail(email);
  setMessage("", "");

  try {
    const response = await apiFetch(
      `${API_BASE}/principal/settings/password`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({
          email,
          current_password: currentPassword,
          new_password: newPasswordValue,
          confirm_password: confirmPasswordValue,
        }),
      }
    );

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(
        data.message || "Could not update this email's password."
      );
    }

    setMessage(
      "success",
      data.message || "Password updated successfully."
    );

    // Clear this email's password fields after success.
    setPasswordForms((current) => ({
      ...current,
      [email]: {
        current_password: "",
        new_password: "",
        confirm_password: "",
      },
    }));
  } catch (error) {
    setMessage(
      "error",
      error.message || "Could not connect to the password service."
    );
  } finally {
    setPasswordBusyEmail("");
  }
};
// Load saved email addresses when Principal opens Settings.
useEffect(() => {
  if (
    currentUser?.role !== "PRINCIPAL" ||
    principalSection !== "settings"
  ) {
    return;
  }

  let cancelled = false;

  async function loadEmails() {
    try {
      const response = await apiFetch(
        `${API_BASE}/principal/settings/emails`,
        { credentials: "include" }
      );

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data.message || "Could not load email addresses."
        );
      }

      if (!cancelled) {
        setPrincipalEmails(data);
      }
    } catch (error) {
      if (!cancelled) {
        setEmailMessage(
          error.message || "Could not load email addresses."
        );
      }
    }
  }

  loadEmails();

  return () => {
    cancelled = true;
  };
}, [currentUser, principalSection]);

  useEffect(() => {
    if (currentUser?.role !== "PRINCIPAL" || principalSection !== "elections") {
      return;
    }
    void loadPrincipalElections();
  }, [currentUser, principalSection]);

  useEffect(() => {
    if (currentUser?.role !== "PRINCIPAL") return;
    let cancelled = false;
    async function loadCandidateSymbols() {
      try {
        const response = await apiFetch(`${API_BASE}/candidate-symbols`, { credentials: "include" });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.message || "Could not load approved symbols.");
        if (!cancelled) {
          const symbols = Array.isArray(data.symbols) ? data.symbols : [];
          setCandidateSymbols(symbols);
          if (symbols.length) {
            setPrincipalCandidateSymbolKey((current) => (
              symbols.some((symbol) => symbol.key === current) ? current : symbols[0].key
            ));
          }
        }
      } catch (error) {
        if (!cancelled) {
          setElectionMessage(error.message || "Could not load approved symbols.");
          setElectionMessageType("error");
        }
      }
    }
    void loadCandidateSymbols();
    return () => { cancelled = true; };
  }, [currentUser]);

// Load HOD-to-branch assignments only when the Principal opens HOD Management.
useEffect(() => {
  if (currentUser?.role !== "PRINCIPAL" || principalSection !== "hods") {
    return;
  }

  let cancelled = false;
  async function loadHodAssignments() {
    setHodLoading(true);
    setHodLoadError("");
    setHodMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/principal/hods`, {
        credentials: "include",
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.message || "Could not load HOD assignments.");
      }
      if (!cancelled) {
        setHodAssignments(Array.isArray(data.assignments) ? data.assignments : []);
      }
    } catch (error) {
      if (!cancelled) {
        setHodLoadError(error.message || "Could not load HOD assignments.");
      }
    } finally {
      if (!cancelled) setHodLoading(false);
    }
  }

  loadHodAssignments();
  return () => { cancelled = true; };
}, [currentUser, principalSection]);

// Count down the OTP expiry and resend waiting period.
useEffect(() => {
  if (emailOtpExpiresIn <= 0 && emailResendIn <= 0) {
    return;
  }

  const timer = window.setInterval(() => {
    setEmailOtpExpiresIn((seconds) => Math.max(0, seconds - 1));
    setEmailResendIn((seconds) => Math.max(0, seconds - 1));
  }, 1000);

  return () => window.clearInterval(timer);
}, [emailOtpExpiresIn, emailResendIn]);
  const handleToggleBranch = async (branch) => {
    setBranchActionMessage("");
    setBranchBusyId(branch.id);
    try {
      const response = await apiFetch(`${API_BASE}/principal/branches/${branch.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ is_active: !branch.is_active }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || "Could not update branch status.");
      await refreshPrincipalDashboard();
      setBranchActionMessage(`${branch.name} is now ${branch.is_active ? "inactive" : "active"}.`);
    } catch (error) {
      setBranchActionMessage(error instanceof TypeError ? "Could not reach the branch API. Check that Flask is running and that its routes match the Principal dashboard." : (error.message || "Cannot connect to the server."));
    } finally {
      setBranchBusyId(null);
    }
  };

  const handleDeleteBranch = async (branch) => {
    if (!window.confirm(`Delete the ${branch.name} branch? This action may be blocked if records depend on it.`)) return;
    setBranchActionMessage("");
    setBranchBusyId(branch.id);
    try {
      const response = await apiFetch(`${API_BASE}/principal/branches/${branch.id}`, {
        method: "DELETE",
        credentials: "include",
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || "Delete is not available in the current backend.");
      await refreshPrincipalDashboard();
      setBranchActionMessage(`${branch.name} was deleted.`);
    } catch (error) {
      setBranchActionMessage(error instanceof TypeError ? "Could not reach the branch API. Check that Flask is running and that its routes match the Principal dashboard." : (error.message || "Cannot connect to the server."));
    } finally {
      setBranchBusyId(null);
    }
  };

  const handleCreateElection = async (event) => {
    event.preventDefault();
    setElectionMessage("");
    setElectionMessageType("");
    if (!electionTitle.trim()) {
      setElectionMessage("Enter a title for this election.");
      setElectionMessageType("error");
      return;
    }
    if (!selectedElectionBranches.length) {
      setElectionMessage("Select at least one participating branch.");
      setElectionMessageType("error");
      return;
    }
    if (collegeElectionType === "OTHER" && !collegePositionName.trim()) {
      setElectionMessage("Enter the representative position name.");
      setElectionMessageType("error");
      return;
    }
    const cohortValues = [
      presidentAdmissionYear,
      presidentAcademicYear,
      presidentSemester,
    ];
    if (cohortValues.some(Boolean) && !cohortValues.every(Boolean)) {
      setElectionMessage("Select admission year, academic year and semester together, or leave the voter cohort unrestricted.");
      setElectionMessageType("error");
      return;
    }
    setElectionLoading(true);
    try {
      const requestBody = {
        title: electionTitle.trim(),
        election_type: collegeElectionType,
        branch_ids: selectedElectionBranches,
        duration_minutes: Number(electionDuration),
      };
      if (collegeElectionType === "OTHER") {
        requestBody.position_name = collegePositionName.trim();
      }
      if (cohortValues.every(Boolean)) {
        requestBody.admission_year = Number(presidentAdmissionYear);
        requestBody.academic_year = Number(presidentAcademicYear);
        requestBody.semester = Number(presidentSemester);
      }
      const response = await apiFetch(`${API_BASE}/principal/elections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(requestBody),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || "Election creation is not available in the current backend yet.");
      setElectionMessage(data.message || "Election created successfully.");
      setElectionMessageType("success");
      setElectionTitle("");
      setCollegeElectionType("PRESIDENT");
      setCollegePositionName("");
      setPresidentAdmissionYear("");
      setPresidentAcademicYear("");
      setPresidentSemester("");
      setSelectedElectionBranches([]);
      await Promise.all([refreshPrincipalDashboard(), loadPrincipalElections()]);
    } catch (error) {
      setElectionMessage(error instanceof TypeError ? "Could not reach the election API. Check that Flask is running and that its routes match the Principal dashboard." : (error.message || "Cannot connect to the server."));
      setElectionMessageType("error");
    } finally {
      setElectionLoading(false);
    }
  };

  async function loadPrincipalElections() {
    setPrincipalElectionsLoading(true);
    try {
      const response = await apiFetch(`${API_BASE}/principal/elections`, {
        credentials: "include",
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.message || "Could not load college-wide elections.");
      }
      setPrincipalElections(Array.isArray(data.elections) ? data.elections : []);
    } catch (error) {
      setElectionMessage(error.message || "Could not load college-wide elections.");
      setElectionMessageType("error");
    } finally {
      setPrincipalElectionsLoading(false);
    }
  }

  async function loadPrincipalCandidates(electionId) {
    setSelectedPrincipalElectionId(String(electionId));
    setPrincipalResult(null);
    try {
      const [response, eligibleResponse] = await Promise.all([
        apiFetch(`${API_BASE}/principal/elections/${electionId}/candidates`, { credentials: "include" }),
        apiFetch(`${API_BASE}/principal/elections/${electionId}/eligible-candidates`, { credentials: "include" }),
      ]);
      const [data, eligibleData] = await Promise.all([
        response.json().catch(() => ({})),
        eligibleResponse.json().catch(() => ({})),
      ]);
      if (!response.ok) throw new Error(data.message || "Could not load candidates.");
      if (!eligibleResponse.ok) throw new Error(eligibleData.message || "Could not load eligible candidates.");
      setPrincipalCandidates(Array.isArray(data.candidates) ? data.candidates : []);
      setEligiblePrincipalCandidates(Array.isArray(eligibleData.candidates) ? eligibleData.candidates : []);
    } catch (error) {
      setPrincipalCandidates([]);
      setEligiblePrincipalCandidates([]);
      setElectionMessage(error.message || "Could not load candidates.");
      setElectionMessageType("error");
    }
  }

  const handlePrincipalCandidateSubmit = async (event) => {
    event.preventDefault();
    if (!selectedPrincipalElectionId) {
      setElectionMessage("Choose a draft election before registering a candidate.");
      setElectionMessageType("error");
      return;
    }
    try {
      const response = await apiFetch(
        `${API_BASE}/principal/elections/${selectedPrincipalElectionId}/candidates`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            usn: principalCandidateUsn.trim().toUpperCase(),
            manifesto: principalCandidateManifesto,
            symbol_key: principalCandidateSymbolKey,
          }),
        }
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || "Could not register the candidate.");
      setPrincipalCandidateUsn("");
      setPrincipalCandidateManifesto("");
      setPrincipalCandidateSymbolKey(candidateSymbols[0]?.key || "book");
      setElectionMessage(data.message || "Candidate registered successfully.");
      setElectionMessageType("success");
      await Promise.all([
        loadPrincipalCandidates(selectedPrincipalElectionId),
        loadPrincipalElections(),
      ]);
    } catch (error) {
      setElectionMessage(error.message || "Could not register the candidate.");
      setElectionMessageType("error");
    }
  };

  const reviewPrincipalCandidate = async (candidateId, action) => {
    try {
      const response = await apiFetch(
        `${API_BASE}/principal/elections/${selectedPrincipalElectionId}/candidates/${candidateId}/${action}`,
        { method: "POST", credentials: "include" }
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || "Could not review the candidate.");
      setElectionMessage(data.message || "Candidate review saved.");
      setElectionMessageType("success");
      await Promise.all([
        loadPrincipalCandidates(selectedPrincipalElectionId),
        loadPrincipalElections(),
      ]);
    } catch (error) {
      setElectionMessage(error.message || "Could not review the candidate.");
      setElectionMessageType("error");
    }
  };

  const changePrincipalElectionStatus = async (electionId, action) => {
    try {
      const response = await apiFetch(
        `${API_BASE}/principal/elections/${electionId}/${action}`,
        { method: "POST", credentials: "include" }
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || "Could not update the election.");
      setElectionMessage(data.message || "Election updated successfully.");
      setElectionMessageType("success");
      await loadPrincipalElections();
      if (String(electionId) === selectedPrincipalElectionId) {
        await loadPrincipalCandidates(electionId);
      }
    } catch (error) {
      setElectionMessage(error.message || "Could not update the election.");
      setElectionMessageType("error");
    }
  };

  const loadPrincipalResult = async (electionId) => {
    try {
      const response = await apiFetch(
        `${API_BASE}/principal/elections/${electionId}/results`,
        { credentials: "include" }
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || "Could not load results.");
      setPrincipalResult(data.result || null);
      setSelectedPrincipalElectionId(String(electionId));
    } catch (error) {
      setPrincipalResult(null);
      setElectionMessage(error.message || "Could not load results.");
      setElectionMessageType("error");
    }
  };

  // Open the Forgot Password form.
  const openForgotPassword = () => {
  if (selectedRole === "student") {
    setRecoveryUSN(loginUSN.trim().toUpperCase());
  } else {
    setRecoveryEmail(loginEmail.trim());
  }

  setRecoveryMessage("");
  setRecoveryMessageType("");
  setAuthView("forgot");
};

  // Leave the standalone recovery screen and open the normal website login.
  const returnToLogin = () => {
    setAuthView("login");
    setRecoveryMessage("");
    setRecoveryMessageType("");
    setRecoveryTokenStatus("idle");
    setNewPassword("");
    setConfirmPassword("");
    setRecoveryToken("");
    window.history.replaceState({}, "", "/#portal-access");

    window.requestAnimationFrame(() => {
      document.getElementById("portal-access")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
      if (selectedRole !== "student") {
        document.getElementById("portal-login-form")?.focus({
          preventScroll: true,
        });
      }
    });
  };

  // Request a password-reset email.
  const handleForgotPassword = async (event) => {
    event.preventDefault();
    setRecoveryMessage("");
    setRecoveryMessageType("");
    setRecoveryLoading(true);
    setRecoveryMessage("Processing your request…");
    setRecoveryMessageType("success");

    try {
      const response = await apiFetch(
        `${API_BASE}/auth/forgot-password`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(
  selectedRole === "student"
    ? {
        usn: recoveryUSN.trim().toUpperCase(),
      }
    : {
        email: recoveryEmail.trim(),
      }
),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        setRecoveryMessage(
          data.message ||
            "Unable to process your request. Please try again."
        );
        setRecoveryMessageType("error");
        return;
      }

      setRecoveryMessage(
        data.message ||
          "If an eligible account exists, password-reset instructions will be sent to its registered email address."
      );
      setRecoveryMessageType("success");
    } catch {
      setRecoveryMessage(
        "Cannot connect to the server. Please check that Flask is running."
      );
      setRecoveryMessageType("error");
    } finally {
      setRecoveryLoading(false);
    }
  };

  // Save a new password using the emailed, time-limited token.
  const handleResetPassword = async (event) => {
    event.preventDefault();
    setRecoveryMessage("");
    setRecoveryMessageType("");

    // Read the live input elements at submit time. This also handles browser
    // password-manager autofill, which may not update React state reliably.
    const formData = new FormData(event.currentTarget);
    const submittedPassword = String(formData.get("new_password") || "");
    const submittedConfirmation = String(
      formData.get("confirm_password") || ""
    );
    setNewPassword(submittedPassword);
    setConfirmPassword(submittedConfirmation);

    if (!recoveryToken || recoveryTokenStatus !== "valid") {
      setRecoveryMessage(
        "This reset link is unavailable. Request a new password-reset email."
      );
      setRecoveryMessageType("error");
      setRecoveryTokenStatus("invalid");
      return;
    }

    if (submittedPassword.length < 12) {
      setRecoveryMessage(
        "Your new password must contain at least 12 characters."
      );
      setRecoveryMessageType("error");
      return;
    }

    if (submittedPassword !== submittedConfirmation) {
      setRecoveryMessage(
        "The entries are different. Check both fields for typing differences or extra spaces."
      );
      setRecoveryMessageType("error");
      return;
    }

    setRecoveryLoading(true);

    try {
      const response = await apiFetch(
        `${API_BASE}/auth/reset-password`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            token: recoveryToken,
            password: submittedPassword,
            confirm_password: submittedConfirmation,
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        setRecoveryMessage(
          data.message ||
            "Password reset failed. The link may have expired."
        );
        setRecoveryMessageType("error");
        if (/invalid|expired|already been used/i.test(data.message || "")) {
          setRecoveryTokenStatus("invalid");
        }
        return;
      }

      setRecoveryMessage(
        data.message ||
          "Your password has been changed successfully. You can now sign in."
      );
      setRecoveryMessageType("success");
      setRecoveryTokenStatus("used");
      setNewPassword("");
      setConfirmPassword("");
      setRecoveryToken("");
    } catch {
      setRecoveryMessage(
        "Cannot connect to the server. Please try again."
      );
      setRecoveryMessageType("error");
    } finally {
      setRecoveryLoading(false);
    }
  };


  // Activate a student account using the emailed invitation link.
const handleStudentActivation = async (event) => {
  event.preventDefault();

  setRecoveryMessage("");
  setRecoveryMessageType("");

  const formData = new FormData(event.currentTarget);

  const submittedPassword = String(
    formData.get("new_password") || ""
  );

  const submittedConfirmation = String(
    formData.get("confirm_password") || ""
  );

  if (!recoveryToken || recoveryTokenStatus !== "valid") {
    setRecoveryMessage("Your activation link is invalid or expired.");
    setRecoveryMessageType("error");
    return;
  }

  if (submittedPassword.length < 12 ||
      submittedPassword.length > 128) {
    setRecoveryMessage(
      "Password must contain between 12 and 128 characters."
    );
    setRecoveryMessageType("error");
    return;
  }

  if (submittedPassword !== submittedConfirmation) {
    setRecoveryMessage("The passwords do not match.");
    setRecoveryMessageType("error");
    return;
  }

  setRecoveryLoading(true);

  try {
    const response = await apiFetch(
      `${API_BASE}/student/activation/complete`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          token: recoveryToken,
          password: submittedPassword,
          confirm_password: submittedConfirmation,
        }),
      }
    );

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(
        data.message || "Student account activation failed."
      );
    }

    setRecoveryMessage(
      data.message || "Your student account is now activated."
    );

    setRecoveryMessageType("success");
    setRecoveryTokenStatus("used");
    setRecoveryToken("");
    setNewPassword("");
    setConfirmPassword("");

  } catch (error) {
    setRecoveryMessage(
      error.message || "Unable to activate your account."
    );
    setRecoveryMessageType("error");
  } finally {
    setRecoveryLoading(false);
  }
};

  const openPortal = (role) => {
    setSelectedRole(role);
    setLoginMessage("");
    setLoginPassword("");
    setAuthView("login");
    setRecoveryMessage("");
    closeMenu();

    requestAnimationFrame(() => {
      document.getElementById("portal-access")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });

      if (role !== "student") {
        document.getElementById("portal-login-form")?.focus({
          preventScroll: true,
        });
      }
    });
  };

  const retryConnection = () => {
    setRefreshKey((value) => value + 1);
  };

  const numberFormat = (value) =>
    Number(value ?? 0).toLocaleString("en-IN");

  const displayedDepartments =
    statistics?.departments ??
    branches.map((branch) => ({
      ...branch,
      student_count: null,
    }));

  const maxStudents = Math.max(
    1,
    ...displayedDepartments.map((department) =>
      Number(department.student_count ?? 0)
    )
  );

  
  if (isStandaloneResetPage) {
    return (
      <main className="password-reset-screen">
        <section
          className="password-recovery password-reset-card"
          aria-labelledby="password-reset-title"
        >
          <div className="password-reset-brand">UBDTCE · SECURE E-VOTING</div>
          
{/* ==========================================
    UBDTCE STUDENT ACCOUNT ACTIVATION
========================================== */}

{recoveryTokenStatus === "valid" &&
  recoveryPurpose === "STUDENT_ACTIVATION" &&
  recoveryMessageType !== "success" && (

    <div className="password-reset-state student-activation-form">

      <span className="eyebrow eyebrow-dark">
        <span className="eyebrow-line" />
        STUDENT ACCOUNT ACTIVATION
      </span>

      <h2 id="password-reset-title">
        Welcome to UBDTCE!
      </h2>

      <p>
        Your department has successfully registered your student
        account. Create your password below to activate your
        UBDTCE Secure E-Voting account.
      </p>

      <div className="student-activation-notice">
        <strong>Account security</strong>
        <p>
          Create a password containing at least 12 characters.
          Keep your password private and never share it.
        </p>
      </div>

      <form
        className="login-form"
        onSubmit={handleStudentActivation}
      >

        <label htmlFor="student-new-password">
          Create Password
        </label>

        <input
          id="student-new-password"
          name="new_password"
          type="password"
          autoComplete="new-password"
          placeholder="Enter your new password"
          minLength={12}
          maxLength={128}
          value={newPassword}
          onChange={(event) =>
            setNewPassword(event.target.value)
          }
          required
        />

        <label htmlFor="student-confirm-password">
          Confirm Password
        </label>

        <input
          id="student-confirm-password"
          name="confirm_password"
          type="password"
          autoComplete="new-password"
          placeholder="Re-enter your password"
          minLength={12}
          maxLength={128}
          value={confirmPassword}
          onChange={(event) =>
            setConfirmPassword(event.target.value)
          }
          required
        />

        {confirmPassword && (
          <p
            className={
              newPassword === confirmPassword
                ? "recovery-success"
                : "recovery-error"
            }
            role="status"
            aria-live="polite"
          >
            {newPassword === confirmPassword
              ? "✓ Passwords match"
              : "Passwords do not match"}
          </p>
        )}

        {recoveryMessage && (
          <p className="recovery-error" role="alert">
            {recoveryMessage}
          </p>
        )}

        <button
          className="button button-gold login-submit"
          type="submit"
          disabled={recoveryLoading}
        >
          {recoveryLoading
            ? "Activating Your Account..."
            : "Activate My Account"}
          <span>→</span>
        </button>

      </form>

      <p className="student-activation-footer">
        Secure access to your college election portal.
        <br />
        UBDTCE Secure E-Voting System
      </p>

    </div>
)}


          {recoveryTokenStatus === "checking" && (
            <div className="password-reset-state" role="status" aria-live="polite">
              <h2 id="password-reset-title">Checking reset link</h2>
              <p>Please wait while we verify that this link is valid and has not been used.</p>
            </div>
          )}

          {(recoveryTokenStatus === "invalid" || recoveryTokenStatus === "error") && (
            <div className="password-reset-state">
              <h2 id="password-reset-title">Reset link unavailable</h2>
              <p>
                {recoveryMessage ||
                  "This password-reset link has already been used or has expired. Request a new link to continue."}
              </p>
              <button
                className="button button-gold login-submit"
                type="button"
                onClick={returnToLogin}
              >
                Go to Login <span>→</span>
              </button>
            </div>
          )}

          {recoveryTokenStatus === "used" && recoveryMessageType === "success" && (
            <div className="password-reset-state">
              <h2 id="password-reset-title">
                {recoveryPurpose === "HOD_SETUP"
  ? "HOD password created"
  : recoveryPurpose === "STUDENT_ACTIVATION"
    ? "Student account activated!"
    : "Password updated"}
              </h2>
              <p>
                {recoveryPurpose === "HOD_SETUP"
  ? "Your HOD account is ready. This setup link can no longer be used."
  : recoveryPurpose === "STUDENT_ACTIVATION"
    ? "Congratulations! Your UBDTCE student account is now active. You can return to the Student Portal."
    : "Your password has been changed successfully. This reset link can no longer be used."}
    </p>
              <p className="recovery-success" role="status" aria-live="polite">
                {recoveryMessage}
              </p>
              <button
                className="button button-gold login-submit"
                type="button"
                onClick={returnToLogin}
              >
                Go to Login <span>→</span>
              </button>
            </div>
          )}

          {recoveryTokenStatus === "valid" &&
            recoveryPurpose !== "STUDENT_ACTIVATION" &&
                 recoveryMessageType !== "success" && ( 

            <div className="password-reset-state">
              <span className="eyebrow eyebrow-dark">
                <span className="eyebrow-line" />
                {recoveryPurpose === "HOD_SETUP" ? "HOD ACCOUNT ACTIVATION" : "SECURE ACCOUNT RECOVERY"}{recoveryPurpose === "HOD_SETUP"
  ? "HOD ACCOUNT ACTIVATION"
  : selectedRole === "student"
    ? "STUDENT PASSWORD RECOVERY"
    : "SECURE ACCOUNT RECOVERY"}
              </span>
              <h2 id="password-reset-title">
  {recoveryPurpose === "HOD_SETUP"
    ? "Create your HOD password"
    : selectedRole === "student"
      ? "Reset your student password"
      : "Set a new password"}
</h2>
              <p>
                {recoveryPurpose === "HOD_SETUP"
  ? `Create a password for your assigned department${recoveryBranchName ? ` (${recoveryBranchName})` : ""}. Use at least 12 characters.`
  : selectedRole === "student"
    ? "Create a new password for your UBDTCE student account. Use at least 12 characters."
    : "Enter your new password twice. It must contain at least 12 characters."}
              </p>

              <form className="login-form" onSubmit={handleResetPassword}>
                <label htmlFor="new-password">New password</label>
                <input
                  id="new-password"
                  name="new_password"
                  type="password"
                  autoComplete="new-password"
                  placeholder="Enter your new password"
                  minLength={12}
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  required
                />

                <label htmlFor="confirm-password">Confirm new password</label>
                <input
                  id="confirm-password"
                  name="confirm_password"
                  type="password"
                  autoComplete="new-password"
                  placeholder="Enter the password again"
                  minLength={12}
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  required
                />

                {confirmPassword && (
                  <p
                    className={newPassword === confirmPassword ? "recovery-success" : "recovery-error"}
                    role="status"
                    aria-live="polite"
                  >
                    {newPassword === confirmPassword
                      ? "Passwords match."
                      : "Passwords do not match yet."}
                  </p>
                )}

                {recoveryMessage && (
                  <p className="recovery-error" role="alert">
                    {recoveryMessage}
                  </p>
                )}

                <button
                  className="button button-gold login-submit"
                  type="submit"
                  disabled={recoveryLoading}
                >
                  {recoveryLoading ? "Updating password…" : "Set Password"}
                  <span>→</span>
                </button>
              </form>
            </div>
          )}
        </section>
      </main>
    );
  }

  if (currentUser?.role === "PRINCIPAL" && principalDashboard) {
    const dashboardBranches = principalDashboard.branches || [];
    // If the HOD-assignment API is unavailable, keep active registered
    // branches selectable from the already-loaded Principal dashboard.
    // The backend still enforces the one-HOD-per-branch rule on submission.
    const activeUnassignedHodBranches = hodLoadError
      ? dashboardBranches
          .filter((branch) => branch.is_active)
          .map((branch) => ({
            branch_id: branch.id,
            branch_name: branch.name,
            branch_code: branch.code,
            branch_active: branch.is_active,
            assigned: false,
          }))
      : hodAssignments.filter((item) => item.branch_active && !item.assigned);
    const activeElectionBranches = dashboardBranches.filter((branch) => branch.is_active);
    const summary = principalDashboard.summary || {};
    const activeBranchCount = dashboardBranches.filter(
  (branch) => branch.is_active
).length;

const registeredBranchCount = dashboardBranches.length;

    const navItems = [
      { id: "overview", label: "Overview", icon: "▦" },
      { id: "branches", label: "Manage Branches", icon: "⌂" },
      { id: "hods", label: "HOD Management", icon: "♙" },
      { id: "elections", label: "Conduct Elections", icon: "◷" },
      { id: "settings", label: "Settings & Security", icon: "⚙" },
    ];

    const activePage =
      navItems.find((item) => item.id === principalSection)?.label ||
      "Overview";
    const pageDescriptions = {
      overview: "A clear summary of college branches, students and elections.",
      branches: "Register and maintain the college departments.",
      hods: "Register department heads and manage branch access.",
      elections: "Set up a college-wide election and choose eligible departments.",
      settings: "Manage your dashboard preferences and account security.",
    };

    return (
     <div
  className={`principal-app-shell ${
    dashboardTheme === "dark" ? "theme-dark" : ""
  }`}
>
        <aside className="principal-sidebar">
          <div className="principal-brand">
            <span className="principal-brand-mark">U</span>
            <span>
              <strong>UBDTCE</strong>
              <small>SECURE E-VOTING</small>
            </span>
          </div>

          <p className="principal-sidebar-caption">ADMINISTRATION</p>

          <nav className="principal-side-nav">
            {navItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className={principalSection === item.id ? "active" : ""}
                onClick={() => {
                  setPrincipalSection(item.id);
                  window.scrollTo({ top: 0, left: 0, behavior: "auto" });
                }}
              >
                <span className="principal-nav-icon">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </nav>

          <div className="principal-sidebar-bottom">
            <div className="principal-secure-note">
              <span>✓</span>
              <div>
                <strong>Secure workspace</strong>
                <small>Principal access</small>
              </div>
            </div>

            <button
              type="button"
              className="principal-logout"
              onClick={handleLogout}
            >
              ← Return to Home
            </button>
          </div>
        </aside>

        <main className="principal-workspace">
          <header className="principal-topbar">
            <div className="principal-breadcrumb">
              UBDTCE / Administration / <strong>{activePage}</strong>
            </div>

            <div className="principal-profile">
              <span className="principal-online-dot" />
              <div>
                <strong>Principal</strong>
                <small>College administrator</small>
              </div>
              <span className="principal-avatar">P</span>
            </div>
          </header>

          <div className="principal-content-grid">
            <section className="principal-main-column">
              {principalSection !== "settings" && (
                <div className="principal-page-heading">
                  <div>
                    <h1>{activePage}</h1>
                    <p>{pageDescriptions[principalSection] || "Manage college administration."}</p>
                  </div>
                </div>
              )}
              {principalSection === "overview" && (
                <>
                  <section className="principal-welcome-panel">
                    <div>
                      <span className="principal-welcome-label">
                        PRINCIPAL CONTROL CENTRE
                      </span>
                      <h2>Good day, Principal.</h2>
                      <p>Your college election administration at a glance.</p>
                    </div>
                    <div className="principal-welcome-emblem">U</div>
                  </section>

                  
<div className="principal-stat-grid">
  <article>
    <small>Total Departments</small>
    <strong>{numberFormat(registeredBranchCount)}</strong>
    <em>Registered college branches</em>
  </article>

  <article>
    <small>Active Branches</small>
    <strong>{numberFormat(activeBranchCount)}</strong>
    <em>Currently enabled branches</em>
  </article>

  <article>
    <small>Total Students</small>
    <strong>{numberFormat(summary.total_students)}</strong>
    <em>Registered learners</em>
  </article>

  <article>
    <small>Active HODs</small>
    <strong>{numberFormat(summary.active_hods)}</strong>
    <em>Branch administrators</em>
  </article>
</div>

                  <section className="principal-panel">
                    <div className="principal-panel-heading">
                      <div>
                        <h2>College branches</h2>
                        <p>Branch status and assigned administrators</p>
                      </div>
                      <button
                        type="button"
                        className="principal-text-button"
                        onClick={() => {
                          setPrincipalSection("branches");
                          window.scrollTo({ top: 0, left: 0, behavior: "auto" });
                        }}
                      >
                        Manage branches →
                      </button>
                    </div>

                    <div className="principal-branch-table">
                      <div className="principal-table-head">
                        <span>BRANCH</span>
                        <span>STUDENTS</span>
                        <span>HOD</span>
                        <span>STATUS</span>
                      
                      </div>

                      {dashboardBranches.slice(0, 5).map((branch) => (
                        <div className="principal-table-row" key={branch.id}>
                          <div className="principal-branch-name">
                            <span className="principal-branch-symbol">
                              {String(branch.code || branch.name || "B")
                                .slice(0, 2)
                                .toUpperCase()}
                            </span>
                            <div>
                              <strong>{branch.name}</strong>
                              <small>{branch.code}</small>
                            </div>
                          </div>

                          <span>{numberFormat(branch.student_count)}</span>
                          <span>
                            {branch.hod_count ? "Assigned" : "Not assigned"}
                          </span>
                          <span>
                            <i
                              className={`principal-status-dot ${
                                branch.is_active ? "is-active" : "is-inactive"
                              }`}
                            />
                            {branch.is_active ? "Active" : "Inactive"}
                          </span>

                        

                        </div>
                      ))}
                    </div>
                  </section>

                  <section className="principal-panel principal-election-shortcut">
                    <div>
                      <h2>Ready to conduct an election?</h2>
                      <p>Choose branches and configure voting duration.</p>
                    </div>
                    <button
                      type="button"
                      className="principal-primary-button"
                      onClick={() => {
                        setPrincipalSection("elections");
                        window.scrollTo({ top: 0, left: 0, behavior: "auto" });
                      }}
                    >
                      Set up election →
                    </button>
                  </section>
                </>
              )}

              {principalSection === "branches" && (
                <>
                  <section className="principal-panel">
                    <div className="principal-panel-heading">
                      <div>
                        <h2>Add a college branch</h2>
                        <p>
                          Register a department here. This form appears only on
                          Manage Branches.
                        </p>
                      </div>
                    </div>

                    <form
                      className="principal-add-branch-form"
                      onSubmit={handleCreateBranch}
                    >
                      <label htmlFor="principalBranchName">Branch name</label>
                      <input
                        id="principalBranchName"
                        value={newBranchName}
                        onChange={(event) =>
                          setNewBranchName(event.target.value)
                        }
                        placeholder="e.g. Computer Science and Engineering"
                        maxLength={120}
                        required
                      />

                      <label htmlFor="principalBranchCode">Branch code</label>
                      <input
                        id="principalBranchCode"
                        value={newBranchCode}
                        onChange={(event) =>
                          setNewBranchCode(event.target.value)
                        }
                        placeholder="e.g. CSE"
                        maxLength={20}
                        required
                      />

                      <button
                        type="submit"
                        className="principal-primary-button"
                      >
                        + Add Branch
                      </button>
                    </form>

                    {branchActionMessage && (
                      <p className="principal-feedback" role="status">
                        {branchActionMessage}
                      </p>
                    )}
                  </section>

                  <section className="principal-panel">
                    <div className="principal-panel-heading">
                      <div>
                        <h2>Manage college branches</h2>
                        <p>
                          Enable, disable, or delete a branch.
                        </p>
                      </div>
                      <span className="principal-count-pill">
                        {dashboardBranches.length} registered
                      </span>
                    </div>

                    <div className="principal-branch-table">
                      <div className="principal-table-head">
                        <span>BRANCH</span>
                        <span>STUDENTS</span>
                        <span>HOD</span>
                        <span>STATUS</span>
                        <span>ACTIONS</span>
                      </div>

                      {dashboardBranches.map((branch) => (
                        <div className="principal-table-row" key={branch.id}>
                          <div className="principal-branch-name">
                            <span className="principal-branch-symbol">
                              {String(branch.code || branch.name || "B")
                                .slice(0, 2)
                                .toUpperCase()}
                            </span>
                            <div>
                              <strong>{branch.name}</strong>
                              <small>{branch.code}</small>
                            </div>
                          </div>

                          <span>{numberFormat(branch.student_count)}</span>
                          <span>
                            {branch.hod_count ? "Assigned" : "Not assigned"}
                          </span>
                          <span>
                            <i
                              className={`principal-status-dot ${
                                branch.is_active ? "is-active" : "is-inactive"
                              }`}
                            />
                            {branch.is_active ? "Active" : "Inactive"}
                          </span>

                          <span className="principal-row-actions">
                            <button
                              type="button"
                              disabled={branchBusyId === branch.id}
                              onClick={() => handleToggleBranch(branch)}
                            >
                              {branchBusyId === branch.id
                                ? "Saving…"
                                : branch.is_active
                                ? "Disable"
                                : "Enable"}
                            </button>
                            <button
                              type="button"
                              className="danger"
                              disabled={branchBusyId === branch.id}
                              onClick={() => handleDeleteBranch(branch)}
                            >
                              Delete
                            </button>
                          </span>
                        </div>
                      ))}
                    </div>
                  </section>
                </>
              )}

              {principalSection === "hods" && (
                <div className="principal-hod-page">
                  <section className="principal-panel principal-hod-register-panel">
                    <div className="principal-hod-panel-heading">
                      <div>
                        <span className="principal-section-kicker">DEPARTMENT ACCESS</span>
                        <h2>Register a Head of Department</h2>
                        <p>Choose a registered branch and enter the HOD's official details. The HOD creates their own password from the invitation email.</p>
                      </div>
                    </div>

                    <form className="principal-hod-form" onSubmit={handleAssignHod}>
                      <div className="principal-hod-fields">
                        <div className="principal-hod-field">
                          <label htmlFor="principalHodBranch">Department / branch</label>
                          <select
                            id="principalHodBranch"
                            value={hodBranchId}
                            onChange={(event) => setHodBranchId(event.target.value)}
                            required
                            disabled={hodLoading || hodSubmitting || activeUnassignedHodBranches.length === 0}
                          >
                            <option value="">{activeUnassignedHodBranches.length ? "Select a department" : "No unassigned branch available"}</option>
                            {activeUnassignedHodBranches.map((item) => (
                              <option key={item.branch_id} value={item.branch_id}>
                                {item.branch_name} ({item.branch_code})
                              </option>
                            ))}
                          </select>
                        </div>

                        <div className="principal-hod-field">
                          <label htmlFor="principalHodName">HOD full name</label>
                          <input
                            id="principalHodName"
                            type="text"
                            value={hodName}
                            onChange={(event) => setHodName(event.target.value)}
                            placeholder="Enter full name"
                            maxLength={150}
                            autoComplete="name"
                            required
                            disabled={hodSubmitting || activeUnassignedHodBranches.length === 0}
                          />
                        </div>

                        <div className="principal-hod-field">
                          <label htmlFor="principalHodEmail">Official email address</label>
                          <input
                            id="principalHodEmail"
                            type="email"
                            value={hodEmail}
                            onChange={(event) => setHodEmail(event.target.value)}
                            placeholder="hod@college.edu"
                            maxLength={254}
                            autoComplete="email"
                            required
                            disabled={hodSubmitting || activeUnassignedHodBranches.length === 0}
                          />
                        </div>
                      </div>

                      <div className="principal-hod-form-footer">
                        <p>
                          {hodLoading
                            ? "Loading department availability…"
                            : hodLoadError
                            ? "Assignment status could not be refreshed. The server will verify availability when you submit."
                            : activeUnassignedHodBranches.length
                            ? `${activeUnassignedHodBranches.length} active department${activeUnassignedHodBranches.length === 1 ? "" : "s"} available.`
                            : hodAssignments.length
                            ? "All active departments already have an assigned HOD."
                            : "Add an active department in Manage Branches first."}
                        </p>
                        <button
                          type="submit"
                          className="principal-primary-button"
                          disabled={hodSubmitting || hodLoading || activeUnassignedHodBranches.length === 0}
                        >
                          {hodSubmitting ? "Sending invitation…" : "Assign HOD & Send Invitation"}
                          <span aria-hidden="true">→</span>
                        </button>
                      </div>

                      {hodMessage && (
                        <p className={`principal-feedback ${hodMessageType === "error" ? "is-error" : "is-success"}`} role="status" aria-live="polite">
                          {hodMessage}
                        </p>
                      )}
                    </form>
                  </section>

                  <section className="principal-panel principal-hod-directory-panel">
                    <div className="principal-hod-directory-heading">
                      <div>
                        <span className="principal-section-kicker">CURRENT RECORDS</span>
                        <h2>Department HOD assignments</h2>
                      </div>
                      
                    </div>

                    {hodLoading ? (
                      <div className="principal-hod-state">Loading department records…</div>
                    ) : hodLoadError ? (
                      <div className="principal-hod-load-error" role="alert">
                        <span>{hodLoadError}</span>
                        <button type="button" onClick={retryHodAssignments}>Retry</button>
                      </div>
                    ) : hodAssignments.length ? (
                      <div className="principal-hod-table-wrap">
                        <div className="principal-hod-table-head" aria-hidden="true">
                          <span>Department</span>
                          <span>Head of department</span>
                          <span>Account setup</span>
                          <span>Action</span>
                        </div>
                        <div className="principal-hod-assignment-list">
                          {hodAssignments.map((item) => (
                            <article className="principal-hod-assignment-row" key={item.branch_id}>
                              <div className="principal-hod-branch">
                                <span className="principal-branch-symbol">
                                  {String(item.branch_code || "BR").slice(0, 2).toUpperCase()}
                                </span>
                                <div>
                                  <strong>{item.branch_name}</strong>
                                  <small>{item.branch_code}</small>
                                </div>
                              </div>
                              <div className="principal-hod-person">
                                {item.assigned ? (
                                  <>
                                    <strong>{item.hod_name || "HOD name not set"}</strong>
                                    <small>{item.hod_email}</small>
                                  </>
                                ) : (
                                  <span className="principal-hod-unassigned">No HOD assigned</span>
                                )}
                              </div>
                              <div className="principal-hod-status">
                                {item.assigned ? (
                                  item.password_set ? (
                                    <span className="principal-hod-status-ready">Setup complete</span>
                                  ) : (
                                    <span className="principal-hod-status-pending">Invitation pending</span>
                                  )
                                ) : (
                                  <span className="principal-hod-unassigned">Unassigned</span>
                                )}
                              </div>
                              <div className="principal-hod-actions">
  {item.assigned && (
    <>
      {!item.password_set && (
        <button
          type="button"
          disabled={hodResendBusyId === item.hod_account_id}
          onClick={() =>
            handleResendHodInvitation(item.hod_account_id)
          }
        >
          {hodResendBusyId === item.hod_account_id
            ? "Sending…"
            : "Resend invitation"}
        </button>
      )}

      <button
        type="button"
        className="principal-hod-remove-button"
        disabled={
          hodDeleteBusyId === item.hod_account_id ||
          hodResendBusyId === item.hod_account_id
        }
        onClick={() =>
          handleRemoveHod(item.hod_account_id)
        }
      >
        {hodDeleteBusyId === item.hod_account_id
          ? "Removing…"
          : "Remove HOD"}
      </button>
    </>
  )}
</div>
                            </article>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="principal-hod-empty-state">
                        <span className="principal-hod-empty-mark" aria-hidden="true">H</span>
                        <div>
                          <h3>No departments to display</h3>
                          <p>Create a department in Manage Branches. It will appear here and can then be assigned to an HOD.</p>
                          <button type="button" className="principal-secondary-button" onClick={() => {
                            setPrincipalSection("branches");
                            window.scrollTo({ top: 0, left: 0, behavior: "auto" });
                          }}>
                            Go to Manage Branches <span aria-hidden="true">→</span>
                          </button>
                        </div>
                      </div>
                    )}
                  </section>
                </div>
              )}

              {principalSection === "elections" && (
                <div className="principal-election-page">
                  <section className="principal-panel principal-election-panel">
                    <div className="principal-election-panel-heading">
                      <span className="principal-section-kicker">COLLEGE-WIDE ELECTION</span>
                      <h2>Election details</h2>
                      <p>Set the election title, choose participating departments and define the voting duration.</p>
                    </div>

                    <form className="principal-election-form" onSubmit={handleCreateElection}>
                      <div className="principal-election-fields">
                        <div className="principal-election-field principal-election-title-field">
                          <label htmlFor="principalElectionTitle">Election title</label>
                          <input
                            id="principalElectionTitle"
                            value={electionTitle}
                            onChange={(event) => setElectionTitle(event.target.value)}
                            placeholder="e.g. President Elections 2026"
                            maxLength={160}
                            required
                          />
                        </div>
                        <div className="principal-election-field">
                          <label htmlFor="collegeElectionType">Representative position</label>
                          <select
                            id="collegeElectionType"
                            value={collegeElectionType}
                            onChange={(event) => setCollegeElectionType(event.target.value)}
                          >
                            {collegeElectionTypeOptions.map((option) => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </select>
                        </div>
                        {collegeElectionType === "OTHER" && (
                          <div className="principal-election-field">
                            <label htmlFor="collegePositionName">Position name</label>
                            <input
                              id="collegePositionName"
                              value={collegePositionName}
                              onChange={(event) => setCollegePositionName(event.target.value)}
                              maxLength={120}
                              placeholder="e.g. Student Welfare Secretary"
                              required
                            />
                          </div>
                        )}
                        <div className="principal-election-field principal-election-duration-field">
                          <label htmlFor="principalElectionDuration">Voting duration</label>
                          <select
                            id="principalElectionDuration"
                            value={electionDuration}
                            onChange={(event) => setElectionDuration(event.target.value)}
                          >
                            <option value="15">15 minutes</option>
                            <option value="30">30 minutes</option>
                            <option value="60">60 minutes</option>
                            <option value="120">2 hours</option>
                            <option value="360">6 hours</option>
                            <option value="1440">24 hours</option>
                          </select>
                        </div>
                        <div className="principal-election-field">
                          <label htmlFor="presidentAdmissionYear">Admission year (optional)</label>
                          <select
                            id="presidentAdmissionYear"
                            value={presidentAdmissionYear}
                            onChange={(event) => setPresidentAdmissionYear(event.target.value)}
                          >
                            <option value="">All student cohorts</option>
                            {ACADEMIC_YEARS.map((year) => (
                              <option key={year} value={year}>{year}</option>
                            ))}
                          </select>
                        </div>
                        <div className="principal-election-field">
                          <label htmlFor="presidentAcademicYear">Academic year (optional)</label>
                          <select
                            id="presidentAcademicYear"
                            value={presidentAcademicYear}
                            onChange={(event) => setPresidentAcademicYear(event.target.value)}
                          >
                            <option value="">All academic years</option>
                            {ACADEMIC_YEARS.map((year) => (
                              <option key={year} value={year}>{year}</option>
                            ))}
                          </select>
                        </div>
                        <div className="principal-election-field">
                          <label htmlFor="presidentSemester">Semester (optional)</label>
                          <select
                            id="presidentSemester"
                            value={presidentSemester}
                            onChange={(event) => setPresidentSemester(event.target.value)}
                          >
                            <option value="">All semesters</option>
                            {[1, 2, 3, 4, 5, 6, 7, 8].map((semester) => <option key={semester} value={semester}>Semester {semester}</option>)}
                          </select>
                        </div>
                      </div>

                      <div className="principal-election-departments">
                        <div className="principal-election-departments-heading">
                          <div>
                            <h3>Participating departments</h3>
                            <p>Select the branches whose active students can participate.</p>
                          </div>
                          {activeElectionBranches.length > 0 && (
                            <div className="principal-election-selection-actions">
                              <span>{selectedElectionBranches.length} selected</span>
                              <button
                                type="button"
                                onClick={() => setSelectedElectionBranches(activeElectionBranches.map((branch) => branch.id))}
                              >
                                Select all
                              </button>
                              <button type="button" onClick={() => setSelectedElectionBranches([])}>
                                Clear
                              </button>
                            </div>
                          )}
                        </div>

                        {activeElectionBranches.length ? (
                          <div className="principal-branch-picker">
                            {activeElectionBranches.map((branch) => (
                              <label
                                key={branch.id}
                                className={selectedElectionBranches.includes(branch.id) ? "selected" : ""}
                              >
                                <input
                                  type="checkbox"
                                  checked={selectedElectionBranches.includes(branch.id)}
                                  onChange={(event) => setSelectedElectionBranches((current) =>
                                    event.target.checked
                                      ? [...current, branch.id]
                                      : current.filter((id) => id !== branch.id)
                                  )}
                                />
                                <span className="principal-election-branch-code">{String(branch.code || branch.name || "BR").slice(0, 2).toUpperCase()}</span>
                                <span className="principal-election-branch-name">
                                  <strong>{branch.name}</strong>
                                  <small>{branch.code}</small>
                                </span>
                                <span className="principal-election-check" aria-hidden="true">✓</span>
                              </label>
                            ))}
                          </div>
                        ) : (
                          <div className="principal-election-empty-state">
                            <p>No active departments are available. Add or enable departments before creating a college election.</p>
                            <button type="button" className="principal-secondary-button" onClick={() => {
                              setPrincipalSection("branches");
                              window.scrollTo({ top: 0, left: 0, behavior: "auto" });
                            }}>
                              Go to Manage Branches <span aria-hidden="true">→</span>
                            </button>
                          </div>
                        )}
                      </div>

                      {electionMessage && (
                        <p className={`principal-feedback ${electionMessageType === "error" ? "is-error" : "is-success"}`} role="status" aria-live="polite">
                          {electionMessage}
                        </p>
                      )}

                      <div className="principal-election-form-footer">
                        <p>Voting duration: <strong>{Number(electionDuration) < 60 ? `${electionDuration} minutes` : Number(electionDuration) === 1440 ? "24 hours" : Number(electionDuration) % 60 === 0 ? `${Number(electionDuration) / 60} hours` : `${electionDuration} minutes`}</strong>. Voters are restricted to active students in the selected branches{presidentAdmissionYear && presidentAcademicYear && presidentSemester ? ` in admission year ${presidentAdmissionYear}, academic year ${presidentAcademicYear}, semester ${presidentSemester}` : ""}. {collegeElectionTypeOptions.find((option) => option.value === collegeElectionType)?.candidateRule}</p>
                        <button
                          type="submit"
                          className="principal-primary-button"
                          disabled={electionLoading || !activeElectionBranches.length || !selectedElectionBranches.length}
                        >
                          {electionLoading ? "Creating election…" : "Create election"}
                          <span aria-hidden="true">→</span>
                        </button>
                      </div>
                    </form>
                  </section>

                  <section className="principal-panel principal-election-management-panel">
                    <div className="principal-election-panel-heading">
                      <div>
                        <span className="principal-section-kicker">ELECTION OVERSIGHT</span>
                        <h2>College-wide elections</h2>
                        <p>Register and review eligible candidates before opening voting. Results appear only after closure.</p>
                      </div>
                    </div>

                    {principalElectionsLoading ? (
                      <p>Loading college-wide elections…</p>
                    ) : principalElections.length === 0 ? (
                      <p>No college-wide elections have been created yet.</p>
                    ) : (
                      <div className="principal-election-existing-list">
                        {principalElections.map((election) => (
                          <article className="principal-election-existing-card" key={election.id}>
                            <div>
                              <h3>{election.position_label || election.title}</h3>
                              {election.position_label && election.position_label !== election.title && <p>{election.title}</p>}
                              {election.description && <p>{election.description}</p>}
                              <p>
                                <strong>{election.status}</strong>
                                {" · "}{election.eligible_voters} eligible voter(s)
                                {" · "}{election.approved_candidate_count} approved candidate(s)
                              </p>
                            </div>
                            <div className="principal-row-actions">
                              <button type="button" onClick={() => loadPrincipalCandidates(election.id)}>
                                Candidates
                              </button>
                              {election.status === "DRAFT" && (
                                <button
                                  type="button"
                                  className="principal-primary-button"
                                  onClick={() => changePrincipalElectionStatus(election.id, "start")}
                                >
                                  Start voting
                                </button>
                              )}
                              {election.status === "OPEN" && (
                                <button
                                  type="button"
                                  className="danger"
                                  onClick={() => changePrincipalElectionStatus(election.id, "close")}
                                >
                                  Close voting
                                </button>
                              )}
                              {election.status === "CLOSED" && (
                                <button type="button" onClick={() => loadPrincipalResult(election.id)}>
                                  View results
                                </button>
                              )}
                            </div>
                          </article>
                        ))}
                      </div>
                    )}

                    {selectedPrincipalElectionId && (() => {
                      const selectedElection = principalElections.find(
                        (item) => String(item.id) === selectedPrincipalElectionId
                      );
                      return (
                        <div className="principal-election-candidate-workspace">
                          <h3>
                            Candidates{selectedElection ? ` — ${selectedElection.title}` : ""}
                          </h3>
                          {selectedElection?.status === "DRAFT" && (
                            <>
                            {selectedElection.candidate_eligibility === "CR_WINNER" && (
                              <section className="principal-cr-shortlist" aria-labelledby="principal-cr-shortlist-title">
                                <div>
                                  <h4 id="principal-cr-shortlist-title">Elected CRs in selected branches</h4>
                                  <p>Select an elected CR to fill the candidate field. Their closed CR-election symbol is shown for identification; choose a unique symbol for this President election below.</p>
                                </div>
                                {eligiblePrincipalCandidates.length === 0 ? (
                                  <p className="principal-election-eligibility-note">No elected CR matches this election’s selected branches and cohort yet.</p>
                                ) : (
                                  <div className="principal-cr-shortlist-grid">
                                    {eligiblePrincipalCandidates.map((candidate) => (
                                      <button
                                        key={`${candidate.branch}-${candidate.usn}`}
                                        type="button"
                                        className={principalCandidateUsn === candidate.usn ? "selected" : ""}
                                        onClick={() => setPrincipalCandidateUsn(candidate.usn)}
                                      >
                                        <strong>{candidate.name}</strong>
                                        <span>{candidate.usn} · {candidate.branch}</span>
                                        <small>
                                          {candidate.representative_symbol?.glyph || "◌"}
                                          {" "}{candidate.representative_symbol?.label || "CR symbol not recorded"}
                                        </small>
                                      </button>
                                    ))}
                                  </div>
                                )}
                              </section>
                            )}
                            <form className="principal-election-form" onSubmit={handlePrincipalCandidateSubmit}>
                              <div className="principal-election-fields">
                                <div className="principal-election-field">
                                  <label htmlFor="principalCandidateUsn">Eligible candidate USN</label>
                                  <input
                                    id="principalCandidateUsn"
                                    value={principalCandidateUsn}
                                    onChange={(event) => setPrincipalCandidateUsn(event.target.value.toUpperCase())}
                                    maxLength={10}
                                    pattern="[0-9][Uu][Bb][0-9]{2}[A-Za-z]{2}[0-9]{3}"
                                    placeholder="4UB23CS026"
                                    list="principalEligibleCandidateUsns"
                                    required
                                  />
                                  <datalist id="principalEligibleCandidateUsns">
                                    {eligiblePrincipalCandidates.map((candidate) => <option key={`${candidate.branch}-${candidate.usn}`} value={candidate.usn}>{candidate.name} · {candidate.branch}</option>)}
                                  </datalist>
                                </div>
                                <div className="principal-election-field">
                                  <label htmlFor="principalCandidateSymbol">Election symbol</label>
                                  <select
                                    id="principalCandidateSymbol"
                                    value={principalCandidateSymbolKey}
                                    onChange={(event) => setPrincipalCandidateSymbolKey(event.target.value)}
                                    required
                                  >
                                    {candidateSymbols.map((symbol) => <option key={symbol.key} value={symbol.key}>{symbol.glyph} {symbol.label}</option>)}
                                  </select>
                                </div>
                                <div className="principal-election-field">
                                  <label htmlFor="principalCandidateManifesto">Manifesto (optional)</label>
                                  <input
                                    id="principalCandidateManifesto"
                                    value={principalCandidateManifesto}
                                    onChange={(event) => setPrincipalCandidateManifesto(event.target.value)}
                                    maxLength={5000}
                                  />
                                </div>
                              </div>
                              <p className="principal-election-eligibility-note">{selectedElection?.candidate_eligibility_label || "Only students eligible under this election's policy are available."} {eligiblePrincipalCandidates.length} eligible candidate(s) found.</p>
                              <button type="submit" className="principal-primary-button" disabled={!candidateSymbols.length}>Register candidate</button>
                            </form>
                            </>
                          )}

                          {principalCandidates.length === 0 ? (
                            <p>No candidates are registered for this election.</p>
                          ) : (
                            <div className="principal-election-candidate-list">
                              {principalCandidates.map((candidate) => (
                                <article className="principal-election-candidate-card" key={candidate.id}>
                                  <div>
                                    <strong>{candidate.name}</strong>
                                    <p>{candidate.symbol?.glyph || "◌"} {candidate.symbol?.label || "Symbol pending"} · {candidate.usn} · {candidate.branch} · {candidate.review_status}</p>
                                    {candidate.manifesto && <p>{candidate.manifesto}</p>}
                                  </div>
                                  {selectedElection?.status === "DRAFT" && (
                                    <div className="principal-row-actions">
                                      <button type="button" onClick={() => reviewPrincipalCandidate(candidate.id, "approve")}>Approve</button>
                                      <button type="button" className="danger" onClick={() => reviewPrincipalCandidate(candidate.id, "reject")}>Reject</button>
                                    </div>
                                  )}
                                </article>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })()}

                    {principalResult && (
                      <div className="principal-election-result" role="status">
                        <h3>Published result — {principalResult.election?.title}</h3>
                        <p>
                          Turnout: {principalResult.turnout_percentage}%
                          {" · "}{principalResult.participation_count} participation record(s)
                          {" · "}{principalResult.eligible_voters} eligible voter(s)
                        </p>
                        {principalResult.is_tie ? <p>Result: tie.</p> : <p>Result: winner identified.</p>}
                        <ul>
                          {(principalResult.candidates || []).map((candidate) => (
                            <li key={candidate.id}>{candidate.symbol?.glyph || "◌"} {candidate.name} ({candidate.usn}): {candidate.vote_count} vote(s)</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </section>
                </div>
              )}

             
{principalSection === "settings" && (
  <section className="principal-settings-page">
    <div className="principal-settings-header">
      <div>
        <span className="principal-settings-eyebrow">
          ACCOUNT PREFERENCES
        </span>
        <h2>Settings &amp; Security</h2>
        <p>
          Manage your dashboard appearance, email addresses and account
          protection.
        </p>
      </div>

      <div className="principal-settings-header-icon">
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M12 3 19 6V11.5C19 16 16.1 19.3 12 21
              7.9 19.3 5 16 5 11.5V6L12 3Z"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinejoin="round"
          />
          <path
            d="m9 12 2 2 4-4"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </div>

    <div className="principal-settings-security-banner">
      <span className="principal-settings-banner-icon">
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect
            x="5"
            y="10"
            width="14"
            height="11"
            rx="2"
            stroke="currentColor"
            strokeWidth="1.7"
          />
          <path
            d="M8 10V7a4 4 0 0 1 8 0v3"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
          />
          <path
            d="M12 14v3"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
          />
        </svg>
      </span>
      <div>
        <strong>Principal account security</strong>
        <p>
          Keep your account details up to date and use verified email
          addresses to protect access.
        </p>
      </div>
      <span className="principal-settings-session-badge">
        <i />
        Session active
      </span>
    </div>

    <div className="principal-settings-section-heading">
      <div>
        <h3>Appearance</h3>
        <p>Customize the appearance of your administration dashboard.</p>
      </div>
    </div>

    <div className="principal-settings-card">
      <div className="principal-settings-card-icon appearance-icon">
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle
            cx="12"
            cy="12"
            r="4"
            stroke="currentColor"
            strokeWidth="1.7"
          />
          <path
            d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42
              m11.3 11.3 1.42 1.42M2 12h2m16 0h2
              M4.93 19.07l1.42-1.42m11.3-11.3
              1.42-1.42"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
          />
        </svg>
      </div>

      <div className="principal-settings-card-content">
        <strong>Dashboard theme</strong>
        <p>Choose a comfortable display for your workspace.</p>
      </div>

      <div className="principal-theme-options" aria-label="Dashboard theme">
  <button
    type="button"
    className={`principal-theme-option ${
      dashboardTheme === "light" ? "is-selected" : ""
    }`}
    onClick={() => setDashboardTheme("light")}
    aria-pressed={dashboardTheme === "light"}
  >
    <span className="principal-theme-preview light-preview" />
    Light
  </button>

  <button
    type="button"
    className={`principal-theme-option ${
      dashboardTheme === "dark" ? "is-selected" : ""
    }`}
    onClick={() => setDashboardTheme("dark")}
    aria-pressed={dashboardTheme === "dark"}
  >
    <span className="principal-theme-preview dark-preview" />
    Dark
  </button>
</div>
    </div>

    <div className="principal-settings-section-heading">
      <div>
        <h3>Email management</h3>
        <p>Manage your verified contact addresses.</p>
      </div>
      <span className="principal-settings-limit">Maximum 2 emails</span>
    </div>
<div className="principal-settings-card principal-settings-email-card">
  <div className="principal-settings-card-icon email-icon">
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect
        x="3"
        y="5"
        width="18"
        height="14"
        rx="2"
        stroke="currentColor"
        strokeWidth="1.7"
      />
      <path
        d="m4 7 8 6 8-6"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  </div>

  <div className="principal-settings-card-content">
    <strong>Email addresses</strong>
    <p>
      Manage your primary address and verify an additional address
      for your Principal account.
    </p>

    <div className="principal-settings-email-policy">
      <span><i /> OTP valid for 3 minutes</span>
      <span><i /> Resend available after 2 minutes</span>
    </div>

    {principalEmails && (
      <div className="principal-email-saved-list">
        <div className="principal-email-saved-item">
  <span className="principal-email-label">
    Primary email
  </span>

  <strong>{principalEmails.primary_email}</strong>

  <div className="principal-email-row-actions">
    <span className="principal-email-verified">
      ✓ Account email
    </span>

    {(principalEmails.additional_emails || []).length > 0 && (
      <button
        type="button"
        className="principal-email-delete-button"
        disabled={emailBusy}
        onClick={handleDeletePrimaryEmail}
      >
        {emailBusy ? "Removing…" : "Delete"}
      </button>
    )}
  </div>
</div>

        {(principalEmails.additional_emails || []).map((item) => (
          <div
            className="principal-email-saved-item"
            key={item.id}
          >
            <span className="principal-email-label">
              Additional email
            </span>
            <strong>{item.email}</strong>
            <div className="principal-email-row-actions">
  <span className="principal-email-verified">
    ✓ Verified
  </span>

  <button
    type="button"
    className="principal-email-delete-button"
    disabled={emailBusy}
    onClick={() => handleDeletePrincipalEmail(item.id)}
  >
    {emailBusy ? "Removing…" : "Remove"}
  </button>
</div>
          </div>
        ))}
      </div>
    )}

    {!principalEmails && (
      <p className="principal-email-hint">
        Your saved email addresses will appear here when loaded.
      </p>
    )}

    {!(principalEmails?.additional_emails?.length > 0) && (
      <>
        <form
          className="principal-settings-email-form"
          onSubmit={handleSendEmailOtp}
        >
          <label htmlFor="principal-additional-email">
            Additional email address
          </label>

          <input
            id="principal-additional-email"
            type="email"
            autoComplete="email"
            placeholder="Enter the email address"
            value={emailInput}
            onChange={(event) => setEmailInput(event.target.value)}
            maxLength={254}
            disabled={emailBusy || Boolean(otpSentTo)}
            required
          />

          <button
            type="submit"
            className="principal-primary-button"
            disabled={emailBusy}
          >
            {emailBusy
              ? "Processing…"
              : otpSentTo
                ? "Resend verification code"
                : "Send verification code"}
          </button>
        </form>

        {otpSentTo && (
          <form
            className="principal-settings-email-form"
            onSubmit={handleVerifyEmailOtp}
          >
            <p>
              A verification code was requested for{" "}
              <strong>{otpSentTo}</strong>. Check your inbox.
            </p>
            
            <div className="principal-otp-countdowns" aria-live="polite">
  <p>
    <span className="principal-otp-timer-label">
      OTP expires in
    </span>
    {emailOtpExpiresIn > 0 ? (
      <strong>
        {Math.floor(emailOtpExpiresIn / 60)}:
        {String(emailOtpExpiresIn % 60).padStart(2, "0")}
      </strong>
    ) : (
      <strong className="principal-otp-expired">
        Expired — request a new code
      </strong>
    )}
  </p>

  <p>
    <span className="principal-otp-timer-label">
      Resend available in
    </span>
    {emailResendIn > 0 ? (
      <strong>
        {Math.floor(emailResendIn / 60)}:
        {String(emailResendIn % 60).padStart(2, "0")}
      </strong>
    ) : (
      <strong className="principal-otp-ready">
        Resend available now
      </strong>
    )}
  </p>
</div>

            <label htmlFor="principal-email-otp">
              Six-digit verification code
            </label>

            <input
              id="principal-email-otp"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="000000"
              value={emailOtp}
              onChange={(event) =>
                setEmailOtp(
                  event.target.value.replace(/\D/g, "").slice(0, 6)
                )
              }
              maxLength={6}
              pattern="[0-9]{6}"
              required
            />
            <label htmlFor="principal-email-password">
  Password for this email
</label>
<input
  id="principal-email-password"
  type="password"
  autoComplete="new-password"
  placeholder="Create a password (minimum 12 characters)"
  value={emailPassword}
  onChange={(event) => setEmailPassword(event.target.value)}
  minLength={12}
  required
/>

<label htmlFor="principal-confirm-email-password">
  Confirm password
</label>
<input
  id="principal-confirm-email-password"
  type="password"
  autoComplete="new-password"
  placeholder="Re-enter the new password"
  value={confirmEmailPassword}
  onChange={(event) => setConfirmEmailPassword(event.target.value)}
  minLength={12}
  required
/>

            <button
              type="submit"
              className="principal-primary-button"
              disabled={emailBusy}
            >
              {emailBusy
                ? "Verifying…"
                : "Verify email address"}
            </button>
          </form>
        )}
      </>
    )}

    {emailMessage && (
      <p
        className="principal-feedback"
        role="status"
        aria-live="polite"
      >
        {emailMessage}
      </p>
    )}
  </div>
</div>
    <div className="principal-settings-section-heading">
      <div>
        <h3>Password &amp; account protection</h3>
        <p>Keep your account access secure.</p>
      </div>
    </div>

    <div className="principal-password-management">
  {principalEmails ? (
    [
      {
        email: principalEmails.primary_email,
        label: "Primary email",
      },
      ...(principalEmails.additional_emails || []).map((item) => ({
        email: item.email,
        label: "Additional email",
      })),
    ].map((accountEmail, index) => {
      const form = passwordForms[accountEmail.email] || {};
      const message = passwordMessages[accountEmail.email];

      return (
        <section
          className="principal-settings-card principal-password-card"
          key={accountEmail.email}
        >
          <div className="principal-settings-card-icon password-icon">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <rect
                x="4"
                y="10"
                width="16"
                height="11"
                rx="2"
                stroke="currentColor"
                strokeWidth="1.7"
              />
              <path
                d="M8 10V7a4 4 0 1 1 8 0v3"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
              />
            </svg>
          </div>

          <div className="principal-settings-card-content">
            <strong>
              Change password — {accountEmail.label}
            </strong>

            <p>{accountEmail.email}</p>

            <p>
              Change the password for this email only. The other
              email's password will remain unchanged.
            </p>

            <form
              className="principal-settings-email-form principal-password-form"
              onSubmit={(event) =>
                handleChangePrincipalEmailPassword(
                  event,
                  accountEmail.email
                )
              }
            >
              <label htmlFor={`current-password-${index}`}>
                Current password
              </label>

              <input
                id={`current-password-${index}`}
                type="password"
                autoComplete="current-password"
                value={form.current_password || ""}
                onChange={(event) =>
                  handlePasswordFieldChange(
                    accountEmail.email,
                    "current_password",
                    event.target.value
                  )
                }
                required
              />

              <label htmlFor={`new-password-${index}`}>
                New password
              </label>

              <input
                id={`new-password-${index}`}
                type="password"
                autoComplete="new-password"
                minLength={12}
                placeholder="At least 12 characters"
                value={form.new_password || ""}
                onChange={(event) =>
                  handlePasswordFieldChange(
                    accountEmail.email,
                    "new_password",
                    event.target.value
                  )
                }
                required
              />

              <label htmlFor={`confirm-password-${index}`}>
                Confirm new password
              </label>

              <input
                id={`confirm-password-${index}`}
                type="password"
                autoComplete="new-password"
                minLength={12}
                value={form.confirm_password || ""}
                onChange={(event) =>
                  handlePasswordFieldChange(
                    accountEmail.email,
                    "confirm_password",
                    event.target.value
                  )
                }
                required
              />

              {message?.message && (
                <p
                  className="principal-feedback"
                  role="status"
                  aria-live="polite"
                >
                  {message.message}
                </p>
              )}

              <button
                type="submit"
                className="principal-primary-button"
                disabled={Boolean(passwordBusyEmail)}
              >
                {passwordBusyEmail === accountEmail.email
                  ? "Updating password…"
                  : "Update this email's password"}
              </button>
            </form>
          </div>
        </section>
      );
    })
  ) : (
    <p className="principal-email-hint">
      Loading your verified email addresses…
    </p>
  )}
</div>

    <p className="principal-settings-footer">
      UBDTCE Secure E-Voting System
      <span> • </span>
      Account preferences
    </p>
  </section>
)}

            </section>
          </div>
        </main>
      </div>
    );
  }
 if (currentUser?.role === "HOD") {
  return (
    <HODDashboard
      currentUser={currentUser}
      onLogout={handleLogout}
    />
  );
}

if (currentUser?.role === "STUDENT") {
  return (
    <StudentDashboard
      currentUser={currentUser}
      onLogout={handleLogout}
    />
  );
}

return (
    <div className="website">
      <header className="site-header">
        <a className="brand" href="#home" onClick={closeMenu}>
          <span className="brand-mark">U</span>
          <span className="brand-copy">
            <strong>UBDTCE</strong>
            <small>SECURE E-VOTING SYSTEM</small>
          </span>
        </a>

        <button
          className="menu-toggle"
          type="button"
          aria-label="Toggle navigation"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(!menuOpen)}
        >
          {menuOpen ? "✕" : "☰"}
        </button>

        <nav className={`main-nav ${menuOpen ? "nav-open" : ""}`}>
          <a href="#home" onClick={closeMenu}>
            Home
          </a>
          <a href="#college-strength" onClick={closeMenu}>
            College Strength
          </a>
          <a href="#elections" onClick={closeMenu}>
            Elections
          </a>
          <a href="#branches" onClick={closeMenu}>
            Departments
          </a>
          <button
            className="nav-login"
            type="button"
            onClick={() => openPortal("student")}
          >
            Portal Login <span aria-hidden="true">↗</span>
          </button>
        </nav>
      </header>

      <main>
        <section className="hero" id="home">
          <div className="hero-image-layer" aria-hidden="true" />
          <div className="hero-shade" aria-hidden="true" />

          <div className="hero-content">
            <div className="eyebrow">
              <span className="eyebrow-line" />
              UNIVERSITY B.D.T. COLLEGE OF ENGINEERING
            </div>

            <h1>
              Your Campus.
              <br />
              Your <span>Voice.</span>
              <br />
              Your Future.
            </h1>

            <p className="hero-description">
              A centralised digital election portal designed to make college
              elections more accessible, organised, and transparent.
            </p>

            <div className="hero-actions">
              <button
                className="button button-gold"
                type="button"
                onClick={() => openPortal("student")}
              >
                Access Voting Portal <span>→</span>
              </button>

              <a
                className="button button-outline"
                href="#college-strength"
              >
                Explore College <span>↓</span>
              </a>
            </div>

            <div className="hero-footnote">
              <span className="status-dot" />
              COLLEGE ELECTIONS · DIGITAL ACCESS
            </div>
          </div>

          <div className="hero-side-note">
            <span>DAVANAGERE</span>
            <span className="side-note-divider" />
            <span>KARNATAKA, INDIA</span>
          </div>

          <a className="scroll-cue" href="#college-strength">
            <span className="scroll-cue-icon">↓</span>
            <span>SCROLL TO EXPLORE</span>
          </a>
        </section>

        <section
          className="strength-section section-pad"
          id="college-strength"
        >
          <div className="section-heading">
            <div>
              <div className="eyebrow eyebrow-dark">
                <span className="eyebrow-line" />
                COLLEGE AT A GLANCE
              </div>
              <h2>
                One campus.
                <br />
                <span>Every voice counts.</span>
              </h2>
            </div>

            <p className="section-intro">
              College statistics and department registration counts are
              retrieved from PostgreSQL through the Flask API.
            </p>
          </div>

          <div className="strength-summary">
            <article className="summary-card summary-primary">
              <span className="summary-label">
                REGISTERED STUDENTS
              </span>
              <strong className="summary-number">
                {statsLoading
                  ? "…"
                  : statsError
                    ? "—"
                    : numberFormat(statistics?.total_students)}
              </strong>
              <span className="summary-caption">
                {statsError
                  ? "Statistics unavailable"
                  : "Total registered student records"}
              </span>
              <span className="summary-watermark" aria-hidden="true">
                01
              </span>
            </article>

            <article className="summary-card">
              <span className="summary-label">
                DEPARTMENTS / PROGRAMS
              </span>
              <strong className="summary-number">
                {branchLoading
                  ? "…"
                  : branchError
                    ? "—"
                    : branches.length}
              </strong>
              <span className="summary-caption">
                Loaded from PostgreSQL
              </span>
            </article>

            <article className="summary-card">
              <span className="summary-label">ACTIVE ELECTIONS</span>
              <strong className="summary-number">
                {statsLoading
                  ? "…"
                  : statsError
                    ? "—"
                    : numberFormat(statistics?.active_elections)}
              </strong>
              <span className="summary-caption">
                Elections currently accepting votes
              </span>
            </article>
          </div>

          <div className="strength-summary">
            <article className="summary-card">
              <span className="summary-label">
                CLASS REPRESENTATIVES
              </span>
              <strong className="summary-number">
                {statsLoading
                  ? "…"
                  : statsError
                    ? "—"
                    : numberFormat(statistics?.total_crs)}
              </strong>
              <span className="summary-caption">
                Registered CR records
              </span>
            </article>

            <article className="summary-card">
              <span className="summary-label">
                FACULTY REPRESENTATIVES
              </span>
              <strong className="summary-number">
                {statsLoading
                  ? "…"
                  : statsError
                    ? "—"
                    : numberFormat(statistics?.total_frs)}
              </strong>
              <span className="summary-caption">
                Registered FR records
              </span>
            </article>
          </div>

          <div className="chart-panel">
            <div className="chart-header">
              <div>
                <span className="chart-kicker">
                  REGISTRATION OVERVIEW
                </span>
                <h3>Student strength by department</h3>
              </div>

              <span className="chart-badge">
                <span className="status-dot" />
                {statsLoading || branchLoading
                  ? "Loading statistics"
                  : statsError || branchError
                    ? "Connection issue"
                    : "Live database data"}
              </span>
            </div>

            <p className="chart-description">
              Student totals are retrieved from the database for each
              active department. Bars scale relative to the department
              with the highest student count.
            </p>

            {(statsLoading || branchLoading) && (
              <p role="status">Loading college statistics…</p>
            )}

            {(statsError || branchError) && (
              <div role="alert">
                <p>{statsError || branchError}</p>
                <button
                  className="portal-action"
                  type="button"
                  onClick={retryConnection}
                >
                  Retry connection →
                </button>
              </div>
            )}

            {!statsLoading &&
              !branchLoading &&
              !statsError &&
              !branchError && (
                <div className="branch-chart">
                  {displayedDepartments.map((department) => {
                    const count = Number(
                      department.student_count ?? 0
                    );

                    const width =
                      count > 0
                        ? Math.max(2, (count / maxStudents) * 100)
                        : 0;

                    return (
                      <div
                        className="chart-row"
                        key={department.id}
                      >
                        <div className="chart-label">
                          <strong>{department.code}</strong>
                          <span>{department.name}</span>
                        </div>

                        <div
                          className="chart-track"
                          role="img"
                          aria-label={`${department.name}: ${numberFormat(count)} students`}
                        >
                          <div
                            className="chart-bar"
                            style={{ width: `${width}%` }}
                          />
                        </div>

                        <strong className="chart-value">
                          {numberFormat(count)}
                        </strong>
                      </div>
                    );
                  })}
                </div>
              )}

            <div className="chart-footer">
              <span>
                <span className="legend-dot" />
                Registered students
              </span>
              <span>
                {statsError
                  ? "Counts unavailable"
                  : "Counts from PostgreSQL"}
              </span>
            </div>
          </div>
        </section>

        <section
          className="branches-section section-pad"
          id="branches"
        >
          <div className="section-heading">
            <div>
              <div className="eyebrow eyebrow-dark">
                <span className="eyebrow-line" />
                ACADEMIC STRUCTURE
              </div>
              <h2>
                Our departments.
                <br />
                <span>One connected campus.</span>
              </h2>
            </div>

            <p className="section-intro">
              Active department records are loaded directly from the
              college database.
            </p>
          </div>

          {branchLoading && (
            <p role="status">Loading departments…</p>
          )}

          {branchError && (
            <p role="alert">{branchError}</p>
          )}

          {!branchLoading && !branchError && (
            <div className="branch-grid">
              {branches.map((branch, index) => (
                <article className="branch-card" key={branch.id}>
                  <span className="branch-index">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div className="branch-symbol">
                    {branch.code.slice(0, 1)}
                  </div>
                  <h3>{branch.code}</h3>
                  <p>{branch.name}</p>
                  <span
                    className="branch-card-arrow"
                    aria-hidden="true"
                  >
                    ↗
                  </span>
                </article>
              ))}
            </div>
          )}
        </section>

        <section
          className="elections-section section-pad"
          id="elections"
        >
          <div className="elections-copy">
            <div className="eyebrow">
              <span className="eyebrow-line" />
              THE DIGITAL ELECTION PROCESS
            </div>
            <h2>
              Better participation.
              <br />
              <span>Clearer processes.</span>
            </h2>
            <p>
              A structured election workflow connects student eligibility,
              candidate management, voting windows, and election oversight
              in one college portal.
            </p>
          </div>

          <div className="process-list">
            <article className="process-step">
              <span>01</span>
              <div>
                <h3>Eligibility first</h3>
                <p>
                  Voting access is based on configured student and
                  election eligibility.
                </p>
              </div>
            </article>

            <article className="process-step">
              <span>02</span>
              <div>
                <h3>Authorised administration</h3>
                <p>
                  HODs manage their assigned departments; the Principal
                  oversees college-wide elections.
                </p>
              </div>
            </article>

            <article className="process-step">
              <span>03</span>
              <div>
                <h3>Time-bound voting</h3>
                <p>
                  Configured opening and closing times determine when
                  voting is available.
                </p>
              </div>
            </article>
          </div>
        </section>

        <section
          className="portal-section section-pad"
          id="portal-access"
        >
          <div className="section-heading">
            <div>
              <div className="eyebrow eyebrow-dark">
                <span className="eyebrow-line" />
                ROLE-BASED ACCESS
              </div>
              <h2>
                Welcome to your
                <br />
                <span>election portal.</span>
              </h2>
            </div>

            <p className="section-intro">
              Select a role to open its portal. Administrator login is
              connected to the Flask API.
            </p>
          </div>

          <div className="portal-grid">
            {roles.map((role) => (
              <article
                className={`portal-card portal-card-clickable ${
                  selectedRole === role.target
                    ? "portal-selected"
                    : ""
                }`}
                key={role.target}
                role="button"
                tabIndex={0}
                aria-pressed={selectedRole === role.target}
                onClick={() => openPortal(role.target)}
                onKeyDown={(event) => {
                  if (
                    event.target === event.currentTarget &&
                    (event.key === "Enter" || event.key === " ")
                  ) {
                    event.preventDefault();
                    openPortal(role.target);
                  }
                }}
              >
                <div className="portal-card-top">
                  <span className="portal-icon">{role.icon}</span>
                  <span className="portal-number">{role.number}</span>
                </div>

                <h3>{role.title}</h3>
                <p>{role.description}</p>

                <button
                  className="portal-action"
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    openPortal(role.target);
                  }}
                >
                  Select portal <span>→</span>
                </button>
              </article>
            ))}
          </div>

            {authView === "login" && (
            <div
              className="portal-login-panel"
              id="portal-login-form"
              tabIndex={-1}
            >
              <div className="portal-login-heading">
                <span className="eyebrow eyebrow-dark">
                  <span className="eyebrow-line" />
                  SECURE ADMINISTRATOR ACCESS
                </span>

                <h3>
  {selectedRole === "principal"
    ? "Principal Login"
    : selectedRole === "hod"
      ? "HOD Login"
      : "Student Login"}
</h3>

               <p>
  {selectedRole === "student"
  ? "Enter your University Seat Number (USN) and password."
  : "Enter your registered administrator email and password."}
</p>
              </div>

              <form className="login-form" onSubmit={handleLogin}>
                
{selectedRole === "student" ? (
  <>
    <label htmlFor="login-usn">University Seat Number (USN)</label>
    <input
      id="login-usn"
      type="text"
      placeholder="Enter your 10-character USN"
      maxLength={10}
      autoComplete="username"
      value={loginUSN}
      onChange={(event) =>
        setLoginUSN(event.target.value.toUpperCase().slice(0, 10))
      }
      required
    />
  </>
) : (
  <>
    <label htmlFor="login-email">Email address</label>
    <input
      id="login-email"
      type="email"
      autoComplete="username"
      placeholder="Enter your registered email"
      value={loginEmail}
      onChange={(event) => setLoginEmail(event.target.value)}
      required
    />
  </>
)}

                <label htmlFor="login-password">Password</label>
                <input
                  id="login-password"
                  type="password"
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  value={loginPassword}
                  onChange={(event) =>
                    setLoginPassword(event.target.value)
                  }
                  required
                />

                <button
                  type="button"
                  className="recovery-back"
                  onClick={openForgotPassword}
                >
                  Forgot password?
                </button>

                {loginMessage && (
                  <p
                    className="login-message"
                    role="status"
                    aria-live="polite"
                  >
                    {loginMessage}
                  </p>
                )}

                <button
                  className="button button-gold login-submit"
                  type="submit"
                  disabled={loginLoading}
                >
                  {loginLoading ? "Signing in…" : "Sign in securely"}
                  <span>→</span>
                </button>
              </form>
            </div>
          )}

          {authView === "forgot" && (
            <div
              className="password-recovery"
              id="portal-login-form"
              tabIndex={-1}
            >
              <span className="eyebrow eyebrow-dark">
                <span className="eyebrow-line" />
                ACCOUNT RECOVERY
              </span>

              <h2>Forgot your password?</h2>

              <p>
  {selectedRole === "student"
    ? "Enter your registered USN. We'll send password reset instructions to your registered email address."
    : "Enter your registered administrator email address. If your account is eligible, we'll send you instructions to reset your password."}
</p>

              <form
                className="login-form"
                onSubmit={handleForgotPassword}
              >
                {selectedRole === "student" ? (
  <>
    <label htmlFor="recovery-usn">
      University Seat Number (USN)
    </label>

    <input
      id="recovery-usn"
      type="text"
      placeholder="Enter your registered USN"
      autoComplete="off"
      maxLength={10}
      value={recoveryUSN}
      onChange={(event) =>
        setRecoveryUSN(
          event.target.value.toUpperCase().trim()
        )
      }
      required
    />
  </>
) : (
  <>
    <label htmlFor="recovery-email">
      Registered email address
    </label>

    <input
      id="recovery-email"
      type="email"
      autoComplete="email"
      placeholder="Enter your registered email"
      value={recoveryEmail}
      onChange={(event) =>
        setRecoveryEmail(event.target.value)
      }
      required
    />
  </>
)}

                {recoveryMessage && (
                  <p
                    className={
                      recoveryMessageType === "success"
                        ? "recovery-success"
                        : "recovery-error"
                    }
                    role="status"
                    aria-live="polite"
                  >
                    {recoveryMessage}
                  </p>
                )}

                <button
                  className="button button-gold login-submit"
                  type="submit"
                  disabled={recoveryLoading}
                >
                  {recoveryLoading
                    ? "Sending request…"
                    : "Send reset instructions"}
                  <span>→</span>
                </button>
              </form>

              <button
                className="recovery-back"
                type="button"
                onClick={returnToLogin}
              >
                ← Back to login
              </button>
            </div>
          )}

          {authView === "reset" && (
            <div
              className="password-recovery"
              id="portal-login-form"
              tabIndex={-1}
            >
              <span className="eyebrow eyebrow-dark">
                <span className="eyebrow-line" />
                SECURE ACCOUNT RECOVERY
              </span>

              <h2>Set a new password</h2>

              <p>
                Choose a strong password with at least 12 characters.
                You'll need to sign in again using your new password.
              </p>

              <form
                className="login-form"
                onSubmit={handleResetPassword}
              >
                <label htmlFor="new-password">New password</label>

                <input
                  id="new-password"
                  name="new_password"
                  type="password"
                  autoComplete="new-password"
                  placeholder="Enter your new password"
                  minLength={12}
                  value={newPassword}
                  onChange={(event) =>
                    setNewPassword(event.target.value)
                  }
                  required
                />

                <label htmlFor="confirm-password">
                  Confirm new password
                </label>

                <input
                  id="confirm-password"
                  name="confirm_password"
                  type="password"
                  autoComplete="new-password"
                  placeholder="Enter the password again"
                  minLength={12}
                  value={confirmPassword}
                  onChange={(event) =>
                    setConfirmPassword(event.target.value)
                  }
                  required
                />

                {confirmPassword && (
                  <p
                    className={
                      newPassword === confirmPassword
                        ? "recovery-success"
                        : "recovery-error"
                    }
                    role="status"
                    aria-live="polite"
                  >
                    {newPassword === confirmPassword
                      ? "Passwords match."
                      : "Passwords do not match yet."}
                  </p>
                )}

                {recoveryMessage && (
                  <p
                    className={
                      recoveryMessageType === "success"
                        ? "recovery-success"
                        : "recovery-error"
                    }
                    role="status"
                    aria-live="polite"
                  >
                    {recoveryMessage}
                  </p>
                )}

                {recoveryMessageType !== "success" && (
                  <button
                    className="button button-gold login-submit"
                    type="submit"
                    disabled={recoveryLoading}
                  >
                    {recoveryLoading
                      ? "Updating password…"
                      : "Reset password"}
                    <span>→</span>
                  </button>
                )}
              </form>

              <button
                className="recovery-back"
                type="button"
                onClick={returnToLogin}
              >
                ← Back to login
              </button>
            </div>
          )}

          {selectedRole === "student" && (
            <div className="portal-notice">
              <span className="notice-icon">i</span>
              <p>
                <strong>Student Portal:</strong> Student OTP login is not
                available yet. Select Principal or HOD to access the
                administrator login form.
              </p>
            </div>
          )}

          <div className="portal-notice">
            <span className="notice-icon">i</span>
            <p>
              <strong>Portal status:</strong> Department and student
              statistics are loaded from PostgreSQL. Student OTP
              verification, voting, and election management require their
              respective backend workflows.
            </p>
          </div>
        </section>

        <section className="closing-banner">
          <div>
            <span className="eyebrow">
              <span className="eyebrow-line" />
              UBDTCE SECURE E-VOTING
            </span>
            <h2>Every vote begins with trust.</h2>
          </div>

          <a className="button button-gold" href="#home">
            Back to top <span>↑</span>
          </a>
        </section>
      </main>

      <footer className="site-footer">
        <a className="footer-brand" href="#home">
          UBDTCE <span>·</span> E-VOTING
        </a>

        <p>
          University B.D.T. College of Engineering · Davanagere
        </p>

        <a href="#home">Back to home ↑</a>
      </footer>
    </div>
  );
}


export default App;
