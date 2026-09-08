/**
 * app.js — Continuity Guardian (Studio Edition)
 */

// Dynamic API base URL: defaults to localhost:8000 when served from frontend dev server on port 3000,
// and relative "" in production/Vercel or when served directly from the FastAPI origin.
const API_BASE_URL = (window.location.hostname === "localhost" && window.location.port === "3000")
  ? "http://localhost:8000"
  : "";

// ─── DOM References ────────────────────────────────────────────────────────
const form               = document.getElementById("check-form");
const episodeInput       = document.getElementById("episode-id");
const scriptInput        = document.getElementById("script-text");
const submitBtn          = document.getElementById("submit-btn");
const btnLabel           = submitBtn.querySelector(".btn-label");
const btnSpinner         = submitBtn.querySelector(".btn-spinner");

const episodeError       = document.getElementById("episode-id-error");
const scriptError        = document.getElementById("script-text-error");
const formError          = document.getElementById("form-error");
const charCountDisplay   = document.getElementById("char-count");

const resultsSection     = document.getElementById("results-section");
const summaryCard        = document.getElementById("summary-card");
const summaryEpisode     = document.getElementById("summary-episode-badge");
const summaryTime        = document.getElementById("summary-timestamp");
const summaryText        = document.getElementById("summary-text");
const summaryStatusTag   = document.getElementById("summary-status-tag");
const issueList          = document.getElementById("issue-list");
const allClear           = document.getElementById("all-clear");

// Filter Tabs
const filterAllBtn       = document.getElementById("filter-all");
const filterInternalBtn  = document.getElementById("filter-internal");
const filterRealWorldBtn = document.getElementById("filter-realworld");
const badgeAllCount      = document.getElementById("badge-all-count");
const badgeInternalCount = document.getElementById("badge-internal-count");
const badgeRealWorldCount= document.getElementById("badge-realworld-count");

// Script Doctor
const rewritePanel       = document.getElementById("rewrite-panel");
const btnRunRewrite      = document.getElementById("btn-run-rewrite");
const rewriteBtnLabel    = btnRunRewrite ? btnRunRewrite.querySelector(".rewrite-btn-label") : null;
const rewriteBtnSpinner  = btnRunRewrite ? btnRunRewrite.querySelector(".rewrite-spinner") : null;
const rewriteOutput      = document.getElementById("rewrite-output");
const rewriteSummaryText = document.getElementById("rewrite-summary-text");
const rewrittenContent   = document.getElementById("rewritten-script-content");
const btnCopyRewrite     = document.getElementById("btn-copy-rewrite");
const btnExportReport    = document.getElementById("btn-export-report");

// Navigation View Tabs
const tabBtnStudio       = document.getElementById("tab-btn-studio");
const tabBtnApiDocs      = document.getElementById("tab-btn-apidocs");
const viewStudio         = document.getElementById("view-studio");
const viewApiDocs        = document.getElementById("view-apidocs");

// Show Bible Modal
const btnOpenBible       = document.getElementById("btn-open-bible");
const showBibleModal     = document.getElementById("show-bible-modal");
const btnCloseModal      = document.getElementById("btn-close-modal");
const btnModalCloseAction= document.getElementById("btn-modal-close-action");
const modalBody          = document.getElementById("modal-body");
const canonStatusCount   = document.getElementById("canon-status-count");

// Dynamic API links
const apiDocsNavLinks    = document.querySelectorAll(".nav-link--api");
apiDocsNavLinks.forEach(link => {
  link.href = `${API_BASE_URL}/docs`;
});
const apiBaseDisplay = document.getElementById("api-base-display");
if (apiBaseDisplay) apiBaseDisplay.textContent = API_BASE_URL;

// ─── State ─────────────────────────────────────────────────────────────────
let currentScript = "";
let currentReport = null;
let currentFilter = "all";

// ─── Preloaded Demo Scripts ────────────────────────────────────────────────
const SAMPLE_SCRIPTS = {
  hero: {
    episode_id: "s01e04",
    text: `INT. MAYA'S APARTMENT - NIGHT

MAYA pours two glasses of scotch as DETECTIVE CARTER enters, taking off his wet coat.

CARTER
Did you speak to him?

MAYA
I did. My brother Daniel called me from Chicago this morning. He says he is alive and doing well.

CARTER
I thought we closed that chapter. Speaking of which, Dr. Vance was typing furiously on his laptop with both hands when I raided Apex Corp today.

MAYA
Vance is slippery. Reminds me of when Alexander Fleming invented penicillin back in 1985. Science always leaves a trail.

CARTER
Let's head down to the river. If we need to, I'll dive in and swim across to retrieve the briefcase.`
  },
  medical: {
    episode_id: "s01e04",
    text: `INT. HOSPITAL EMERGENCY ROOM - DAY

DOCTOR
She's running a dangerously high fever from the infection.

ALEX
Give Maya a strong dose of penicillin right away, Doctor. It's the only antibiotic that will knock this out before our morning meeting in Portland.

DOCTOR
Understood, administering penicillin IV immediately.`
  },
  clean: {
    episode_id: "s01e04",
    text: `INT. DETECTIVE AGENCY - DAY

MAYA sits at her desk in Portland, examining a faded photograph of Daniel from 2020.

ALEX enters, taking a puff from his asthma inhaler before setting a dossier on the desk.

ALEX
Apex Corporation just transferred their research funds back to their Seattle headquarters.

MAYA
Carter's staking out the perimeter by the docks. He won't go near the water, but he has eyes on the front gate.

ALEX
World War II ended in 1945, but this secret war is just getting started.`
  }
};

// ─── Initialization ────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
  // Load hero sample by default
  loadSample("hero");
  fetchCanonStatus();
});

function updateCharCount() {
  const len = scriptInput.value.length;
  charCountDisplay.textContent = `${len.toLocaleString()} character${len === 1 ? "" : "s"}`;
}
scriptInput.addEventListener("input", updateCharCount);

// Demo chip click listeners
document.querySelectorAll(".btn-demo-chip").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".btn-demo-chip").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    loadSample(btn.dataset.sample);
  });
});

function loadSample(key) {
  const sample = SAMPLE_SCRIPTS[key];
  if (sample) {
    episodeInput.value = sample.episode_id;
    scriptInput.value = sample.text;
    updateCharCount();
    clearFieldError(episodeInput, episodeError);
    clearFieldError(scriptInput, scriptError);
    clearFormError();
  }
}

// ─── View Toggling (Studio vs API Reference Hub) ───────────────────────────
if (tabBtnStudio && tabBtnApiDocs) {
  tabBtnStudio.addEventListener("click", () => switchView("studio"));
  tabBtnApiDocs.addEventListener("click", () => switchView("apidocs"));
}

function switchView(viewName) {
  if (viewName === "studio") {
    tabBtnStudio.classList.add("active");
    tabBtnApiDocs.classList.remove("active");
    viewStudio.classList.add("active");
    viewStudio.hidden = false;
    viewApiDocs.classList.remove("active");
    viewApiDocs.hidden = true;
  } else {
    tabBtnApiDocs.classList.add("active");
    tabBtnStudio.classList.remove("active");
    viewApiDocs.classList.add("active");
    viewApiDocs.hidden = false;
    viewStudio.classList.remove("active");
    viewStudio.hidden = true;
    viewApiDocs.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

// ─── Live Firestore Status Fetcher ─────────────────────────────────────────
async function fetchCanonStatus() {
  try {
    const res = await fetch(`${API_BASE_URL}/episodes`);
    if (res.ok) {
      const data = await res.json();
      if (canonStatusCount) {
        canonStatusCount.textContent = `${data.length} Episode${data.length === 1 ? "" : "s"}`;
      }
    }
  } catch (_) {
    if (canonStatusCount) canonStatusCount.textContent = "Offline (Local Canon)";
  }
}

// ─── Form Submission ───────────────────────────────────────────────────────
form.addEventListener("submit", handleSubmit);

episodeInput.addEventListener("input", () => clearFieldError(episodeInput, episodeError));
scriptInput.addEventListener("input",  () => clearFieldError(scriptInput,  scriptError));

async function handleSubmit(e) {
  e.preventDefault();

  if (!validateForm()) return;

  const episodeId  = episodeInput.value.trim();
  const scriptText = scriptInput.value.trim();
  currentScript    = scriptText;

  setLoading(true);
  clearFormError();
  hideResults();

  try {
    const report = await checkEpisode(episodeId, scriptText);
    currentReport = report;
    renderReport(report);
  } catch (err) {
    showFormError(err.message || "An unexpected error occurred connecting to the agent engine.");
  } finally {
    setLoading(false);
  }
}

function validateForm() {
  let valid = true;
  if (!episodeInput.value.trim()) {
    showFieldError(episodeInput, episodeError, "Please enter a target episode ID (e.g. s01e04).");
    valid = false;
  } else {
    clearFieldError(episodeInput, episodeError);
  }

  const script = scriptInput.value.trim();
  if (!script) {
    showFieldError(scriptInput, scriptError, "Please paste or type your script text.");
    valid = false;
  } else if (script.length < 20) {
    showFieldError(
      scriptInput,
      scriptError,
      `Script is too short (${script.length} chars). Please provide at least 20 characters.`
    );
    valid = false;
  } else {
    clearFieldError(scriptInput, scriptError);
  }
  return valid;
}

function showFieldError(input, errorEl, msg) {
  input.classList.add("field-input--error");
  errorEl.textContent = msg;
  errorEl.style.display = "block";
}

function clearFieldError(input, errorEl) {
  input.classList.remove("field-input--error");
  errorEl.textContent = "";
  errorEl.style.display = "none";
}

function showFormError(msg) {
  formError.textContent = `⚠ ${msg}`;
  formError.hidden = false;
  formError.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function clearFormError() {
  formError.textContent = "";
  formError.hidden = true;
}

function setLoading(isLoading) {
  submitBtn.disabled = isLoading;
  btnLabel.hidden    = isLoading;
  btnSpinner.hidden  = !isLoading;
  if (isLoading) {
    submitBtn.setAttribute("aria-busy", "true");
  } else {
    submitBtn.removeAttribute("aria-busy");
  }
}

async function checkEpisode(episodeId, scriptText) {
  const res = await fetch(`${API_BASE_URL}/check-episode`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ episode_id: episodeId, script_text: scriptText }),
  });

  if (!res.ok) {
    let detail = `Server returned HTTP ${res.status}`;
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        detail = Array.isArray(errJson.detail)
          ? errJson.detail.map(d => d.msg).join("; ")
          : String(errJson.detail);
      }
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

// ─── Results Rendering & Filtering ────────────────────────────────────────
function hideResults() {
  resultsSection.hidden = true;
  issueList.innerHTML   = "";
  allClear.hidden       = true;
  if (rewritePanel) rewritePanel.hidden = true;
  if (rewriteOutput) rewriteOutput.hidden = true;
}

function renderReport(report) {
  summaryEpisode.textContent = report.episode_id;
  summaryText.textContent    = report.summary;
  summaryTime.textContent    = formatTimestamp(report.generated_at);

  const issues = report.results || [];
  const internalCount = issues.filter(i => i.claim.claim_type === "internal").length;
  const realWorldCount = issues.filter(i => i.claim.claim_type === "real_world").length;

  badgeAllCount.textContent = issues.length;
  badgeInternalCount.textContent = internalCount;
  badgeRealWorldCount.textContent = realWorldCount;

  if (issues.length === 0) {
    allClear.hidden = false;
    summaryStatusTag.innerHTML = '<span class="dot dot--active"></span> 100% Canon Verified';
    summaryStatusTag.style.background = "rgba(16, 185, 129, 0.12)";
    summaryStatusTag.style.borderColor = "rgba(16, 185, 129, 0.3)";
    summaryStatusTag.style.color = "var(--color-emerald-light)";
    if (rewritePanel) rewritePanel.hidden = true;
  } else {
    allClear.hidden = false;
    allClear.hidden = true;
    summaryStatusTag.innerHTML = `<span class="dot dot--warning"></span> ${issues.length} Issue${issues.length === 1 ? "" : "s"} Flagged`;
    summaryStatusTag.style.background = "var(--color-gold-bg)";
    summaryStatusTag.style.borderColor = "rgba(245, 158, 11, 0.3)";
    summaryStatusTag.style.color = "var(--color-gold-light)";

    renderFilteredIssues();

    if (rewritePanel) {
      rewritePanel.hidden = false;
      if (rewriteOutput) rewriteOutput.hidden = true;
    }
  }

  resultsSection.hidden = false;
  resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderFilteredIssues() {
  issueList.innerHTML = "";
  if (!currentReport) return;

  const all = currentReport.results || [];
  const filtered = all.filter(r => {
    if (currentFilter === "internal") return r.claim.claim_type === "internal";
    if (currentFilter === "real_world") return r.claim.claim_type === "real_world";
    return true;
  });

  filtered.forEach(result => {
    issueList.appendChild(buildIssueCard(result));
  });
}

// Filter Tab Click Handlers
[filterAllBtn, filterInternalBtn, filterRealWorldBtn].forEach(btn => {
  btn.addEventListener("click", () => {
    [filterAllBtn, filterInternalBtn, filterRealWorldBtn].forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentFilter = btn.dataset.filter;
    renderFilteredIssues();
  });
});

function buildIssueCard(result) {
  const li = document.createElement("li");
  li.className = "issue-card";

  const confidencePct = Math.round(result.confidence * 100);
  const confidenceLevel = result.confidence >= 0.7 ? "high" : "medium";
  const isRealWorld = result.claim.claim_type === "real_world";

  li.innerHTML = `
    <div class="issue-card-header">
      <span class="issue-badge ${isRealWorld ? "issue-badge--realworld" : "issue-badge--internal"}">
        ${isRealWorld ? "🌐 Real-World Factual Error" : "📖 Show Bible Contradiction"}
      </span>
      <div class="confidence-meter">
        <span class="confidence-percent">${confidencePct}% confidence</span>
        <div class="confidence-bar-track">
          <div class="confidence-bar-fill" data-level="${confidenceLevel}" style="width: ${confidencePct}%"></div>
        </div>
      </div>
    </div>

    <div class="issue-claim">"${escHtml(result.claim.text)}"</div>

    <div class="issue-label-small">Detected Inconsistency</div>
    <p class="issue-explanation">${escHtml(result.explanation)}</p>

    ${result.suggested_fix ? `
      <div class="fix-box">
        <div class="fix-label">Suggested Script Revision</div>
        <div class="fix-text">${escHtml(result.suggested_fix)}</div>
      </div>
    ` : ""}
  `;
  return li;
}

// ─── Script Doctor Auto-Rewrite ────────────────────────────────────────────
if (btnRunRewrite) {
  btnRunRewrite.addEventListener("click", handleRunRewrite);
}
if (btnCopyRewrite) {
  btnCopyRewrite.addEventListener("click", handleCopyRewrite);
}

async function handleRunRewrite() {
  if (!currentReport || !currentScript) return;

  btnRunRewrite.disabled = true;
  if (rewriteBtnLabel) rewriteBtnLabel.innerHTML = '<span>⏳</span> Script Doctor Revising...';
  if (rewriteBtnSpinner) rewriteBtnSpinner.hidden = false;

  try {
    const res = await fetch(`${API_BASE_URL}/rewrite-script`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        episode_id: currentReport.episode_id,
        original_script: currentScript,
        issues: currentReport.results || []
      })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    rewriteSummaryText.textContent = data.changes_summary || "Resolved flagged screenplay contradictions.";
    rewrittenContent.textContent = data.rewritten_script || currentScript;
    rewriteOutput.hidden = false;
    rewriteOutput.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (err) {
    alert("Script rewrite failed: " + err.message);
  } finally {
    btnRunRewrite.disabled = false;
    if (rewriteBtnLabel) rewriteBtnLabel.innerHTML = '<span>🪄</span> Auto-Fix &amp; Rewrite Script';
    if (rewriteBtnSpinner) rewriteBtnSpinner.hidden = true;
  }
}

function handleCopyRewrite() {
  const text = rewrittenContent.textContent;
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    const orig = btnCopyRewrite.textContent;
    btnCopyRewrite.textContent = "✓ Copied Screenplay!";
    setTimeout(() => btnCopyRewrite.textContent = orig, 2500);
  });
}

// Export Studio Markdown Report
if (btnExportReport) {
  btnExportReport.addEventListener("click", () => {
    if (!currentReport) return;
    const md = generateMarkdownReport(currentReport, currentScript);
    navigator.clipboard.writeText(md).then(() => {
      const orig = btnExportReport.textContent;
      btnExportReport.textContent = "✓ Markdown Copied!";
      setTimeout(() => btnExportReport.textContent = orig, 2500);
    });
  });
}

function generateMarkdownReport(report, script) {
  let out = `# CONTINUITY GUARDIAN — STUDIO INSPECTION REPORT\n\n`;
  out += `**Episode:** ${report.episode_id}\n`;
  out += `**Generated:** ${report.generated_at}\n`;
  out += `**Status:** ${report.results.length} issues flagged\n\n`;
  out += `## Executive Summary\n${report.summary}\n\n`;
  out += `## Flagged Issues\n`;
  report.results.forEach((r, idx) => {
    out += `### ${idx + 1}. [${r.claim.claim_type.toUpperCase()}] "${r.claim.text}"\n`;
    out += `- **Confidence:** ${Math.round(r.confidence * 100)}%\n`;
    out += `- **Finding:** ${r.explanation}\n`;
    if (r.suggested_fix) out += `- **Suggested Fix:** ${r.suggested_fix}\n`;
    out += `\n`;
  });
  return out;
}

// ─── Show Bible Modal ──────────────────────────────────────────────────────
if (btnOpenBible && showBibleModal) {
  btnOpenBible.addEventListener("click", openShowBibleModal);
  btnCloseModal.addEventListener("click", () => showBibleModal.hidden = true);
  if (btnModalCloseAction) {
    btnModalCloseAction.addEventListener("click", () => showBibleModal.hidden = true);
  }
  showBibleModal.addEventListener("click", (e) => {
    if (e.target === showBibleModal) showBibleModal.hidden = true;
  });
}

async function openShowBibleModal() {
  showBibleModal.hidden = false;
  modalBody.innerHTML = `
    <div class="modal-loading">
      <span class="loading-spinner"></span>
      <p class="loading-text">Loading Show Bible canon from Firestore...</p>
    </div>
  `;

  try {
    const res = await fetch(`${API_BASE_URL}/show-bible`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const episodes = await res.json();

    if (!episodes || episodes.length === 0) {
      modalBody.innerHTML = `
        <div class="canon-episode-card">
          <p><strong>Show Bible is unseeded.</strong> Run <code>python scripts/seed_database.py</code> to populate initial canon facts.</p>
        </div>
      `;
      return;
    }

    let html = "";
    episodes.forEach(ep => {
      html += `
        <div class="canon-episode-card">
          <div class="canon-ep-title">
            <span class="canon-ep-name">Episode: ${escHtml(ep.episode_id)}</span>
            <span class="canon-date">${escHtml(ep.date_added || "")}</span>
          </div>

          <div class="canon-list-title">Characters Established</div>
          <div class="character-tags-row">
            ${(ep.characters_mentioned || []).map(c => `<span class="character-tag">${escHtml(c)}</span>`).join("")}
          </div>

          <div class="canon-list-title">Established Narrative Facts</div>
          <ul class="canon-list">
            ${(ep.key_facts || []).map(f => `<li>${escHtml(f)}</li>`).join("")}
          </ul>

          ${(ep.real_world_claims && ep.real_world_claims.length > 0) ? `
            <div class="canon-list-title">Real-World Facts Grounded</div>
            <ul class="canon-list">
              ${ep.real_world_claims.map(f => `<li>${escHtml(f)}</li>`).join("")}
            </ul>
          ` : ""}
        </div>
      `;
    });
    modalBody.innerHTML = html;
  } catch (err) {
    modalBody.innerHTML = `
      <div class="canon-episode-card">
        <p style="color: var(--color-coral-light)">Error connecting to Show Bible endpoint: ${escHtml(err.message)}</p>
      </div>
    `;
  }
}

// ─── Utilities ─────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatTimestamp(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch (_) {
    return iso;
  }
}

// ─── Query Param Handler ───────────────────────────────────────────────────
// If user arrived from an accidental GET submission, populate inputs and clean URL
if (window.location.search) {
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get("episode_id") && episodeInput) {
      episodeInput.value = params.get("episode_id");
    }
    if (params.get("script_text") && scriptInput) {
      scriptInput.value = params.get("script_text");
      if (typeof updateCharCount === "function") {
        updateCharCount();
      }
    }
    window.history.replaceState({}, document.title, window.location.pathname);
  } catch (_) {}
}
