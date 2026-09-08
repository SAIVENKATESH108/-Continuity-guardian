"""
api/main.py

FastAPI application for Continuity Guardian.

This is the HTTP boundary layer — it translates incoming JSON requests into
calls on the agent pipeline and serialises the results back to JSON.  No
business logic lives here; this file only handles:

  - Request validation (Pydantic models + FastAPI).
  - Routing to the correct pipeline or repository method.
  - Response shaping (keeping payloads small where the full model isn't needed).
  - Cross-origin headers so the standalone frontend can call this API.

Run with:
    uvicorn api.main:app --reload
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field, field_validator
import google.generativeai as genai

from agent.pipeline import ContinuityPipeline
from agent.repository import ShowBibleRepository

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
# These mirror the agent/models.py dataclasses but are Pydantic BaseModels
# so FastAPI can validate, document, and serialise them automatically.


class CheckEpisodeRequest(BaseModel):
    """Request body for POST /check-episode."""

    episode_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the episode being analysed (e.g. 's01e04', 'pilot', 's02e01').",
        examples=["s01e04"],
    )
    script_text: str = Field(
        ...,
        min_length=20,
        description=(
            "The raw screenplay scene draft, treatment, or synopsis in standard industry format. "
            "Must be at least 20 characters long."
        ),
        examples=[
            "INT. MAYA'S APARTMENT — NIGHT\n\n"
            "MAYA (30s) paces the narrow hallway, her hand trembling as she grips the telephone receiver.\n\n"
            "MAYA\n"
            "(into phone)\n"
            "Daniel, is that you? I need to tell you what happened at the docks.\n\n"
            "DETECTIVE CARTER (50s) enters, shaking rain from his trench coat.\n\n"
            "CARTER\n"
            "Maya, who are you talking to? Daniel died in that car crash back in 2021.\n\n"
            "MAYA\n"
            "No! He's alive! He called me from Chicago! He told me Dr. Fleming gave him penicillin in 1985!"
        ],
    )

    @field_validator("script_text")
    @classmethod
    def script_text_must_be_substantial(cls, v: str) -> str:
        """Reject trivially short scripts before they reach the pipeline."""
        stripped = v.strip()
        if len(stripped) < 20:
            raise ValueError(
                "script_text must be at least 20 characters long. "
                "Please provide the actual script or synopsis content."
            )
        return stripped


class RewriteScriptRequest(BaseModel):
    """Request body for POST /rewrite-script."""

    episode_id: str = Field(
        ...,
        description="Unique identifier for the episode draft being repaired.",
        examples=["s01e04"],
    )
    original_script: str = Field(
        ...,
        description="The original screenplay scene containing flagged continuity or factual contradictions.",
        examples=[
            "INT. MAYA'S APARTMENT — NIGHT\n\n"
            "MAYA\n"
            "Daniel called me from Chicago! He's alive! He said Dr. Fleming found penicillin in 1985!"
        ],
    )
    issues: list[dict] = Field(
        default_factory=list,
        description="List of flagged contradiction records containing 'explanation' and 'suggested_fix' guidance.",
        examples=[
            [
                {
                    "explanation": "Contradicts S01E01 where Daniel died in 2021 car crash.",
                    "suggested_fix": "Have Maya realize it was an imposter or refer to Daniel in the past tense.",
                },
                {
                    "explanation": "Alexander Fleming discovered penicillin in 1928, not 1985.",
                    "suggested_fix": "Correct the year to 1928 or reference modern antibiotics.",
                },
            ]
        ],
    )


class RewriteScriptResponse(BaseModel):
    """Response body for POST /rewrite-script."""

    rewritten_script: str = Field(
        ...,
        description="The autonomously revised screenplay draft with all continuity errors resolved.",
        examples=[
            "INT. MAYA'S APARTMENT — NIGHT\n\n"
            "MAYA\n"
            "Someone called me claiming to be Daniel. But Daniel died in 2021... It has to be an imposter.\n\n"
            "CARTER\n"
            "What did they say?\n\n"
            "MAYA\n"
            "Nonsense about medical history. Claimed Alexander Fleming discovered penicillin in 1985 instead of 1928. Whoever is on that line isn't my brother."
        ],
    )
    changes_summary: str = Field(
        ...,
        description="Studio editorial changelog explaining the dramatic and factual repairs made to the scene.",
        examples=[
            "Preserved dramatic tension by framing Daniel's voice as an imposter phone call, resolving the 2021 fatal accident contradiction from S01E01, and corrected the historical discovery of penicillin to 1928."
        ],
    )


class ClaimOut(BaseModel):
    """Output representation of an individual extracted screenplay claim."""

    text: str = Field(
        ...,
        description="The factual or narrative claim statement extracted from dialogue or action lines.",
        examples=["Daniel is alive"],
    )
    claim_type: str = Field(
        ...,
        description="Classification category: 'internal' (show bible canon) or 'real_world' (external reality).",
        examples=["internal"],
    )
    source_line: int = Field(
        ...,
        description="1-indexed line number in the submitted script draft where this claim appears.",
        examples=[3],
    )


class CheckResultOut(BaseModel):
    """Output representation of an individual claim verification verdict."""

    claim: ClaimOut
    is_contradiction: bool = Field(
        ...,
        description="True if the claim breaks established canon or real-world facts; False if verified consistent.",
        examples=[True],
    )
    explanation: str = Field(
        ...,
        description="Detailed studio continuity analysis explaining why this statement conflicts with lore or reality.",
        examples=["Contradicts S01E01 canon where Daniel died in 2021 car accident."],
    )
    suggested_fix: str = Field(
        ...,
        description="Actionable screenplay recommendation for the writer to resolve the issue without stalling pacing.",
        examples=["Acknowledge Daniel's death or reveal this caller as an imposter."],
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Bayesian confidence score (0.00 to 1.00) calculated by Gemini based on source alignment.",
        examples=[0.95],
    )


class ContinuityReportOut(BaseModel):
    """Full studio executive continuity brief generated by the multi-agent pipeline."""

    episode_id: str = Field(..., description="Episode identifier analysed.", examples=["s01e04"])
    results: list[CheckResultOut] = Field(..., description="Ranked list of verified claims and contradictions, sorted highest confidence first.")
    summary: str = Field(
        ...,
        description="Executive summary synthesized by the ReportBuilder Agent for producers and script supervisors.",
        examples=[
            "Analysis of S01E04 flagged 2 critical continuity errors: a major timeline contradiction regarding Daniel's status, and a historical inaccuracy regarding penicillin's discovery year."
        ],
    )
    generated_at: str = Field(
        ...,
        description="ISO 8601 UTC timestamp when the report was generated.",
        examples=["2026-09-08T16:00:00Z"],
    )


class EpisodeSummary(BaseModel):
    """Lightweight episode listing item — IDs and dates only, no full detail."""

    episode_id: str = Field(..., description="Episode ID stored in the Firestore Show Bible.", examples=["s01e01"])
    date_added: str = Field(..., description="ISO 8601 date string when this episode was seeded.", examples=["2026-09-08"])


# ---------------------------------------------------------------------------
# Application lifespan — initialise shared, expensive singletons once
# ---------------------------------------------------------------------------

class _AppState:
    """Holds shared singletons that are created once and reused across requests."""

    pipeline: ContinuityPipeline
    repository: ShowBibleRepository


_state = _AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    Resources created here (pipeline, repository) are shared across all
    requests — creating a new ContinuityPipeline per request would be very
    wasteful because each constructor call authenticates with Gemini and
    Firestore.
    """
    logger.info("Starting up Continuity Guardian API…")

    _state.pipeline = ContinuityPipeline()
    _state.repository = ShowBibleRepository()

    logger.info("API startup complete — ready to accept requests.")
    yield
    logger.info("Shutting down Continuity Guardian API.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

API_DESCRIPTION = """
# 🎬 Continuity Guardian — Cinema Multi-Agent Continuity & Studio Script Doctor Engine

**Continuity Guardian** is an enterprise-grade agentic cinema workflow platform engineered with **Google Gemini 3.5**, the **Google Agent Development Kit (ADK)**, **Google Cloud Firestore**, and **Parallel AI MCP**.

Designed specifically for Hollywood screenwriters, script supervisors, showrunners, and studio executive producers, Continuity Guardian catches costly narrative contradictions, character timeline fractures, and real-world factual errors **before the cameras roll**.

---

### 🌟 Executive Overview: The Studio Continuity Problem

In film and television production, narrative continuity errors cost studios hundreds of thousands to millions of dollars in emergency script revisions, delayed shoots, and expensive reshoots:
* **Lore Fractures**: Characters referencing deceased relatives as living, misremembering past episodes, or violating established character canon.
* **Timeline Collisions**: Historical dates, medical timelines, and technology mismatches that break audience immersion.
* **Script Supervisor Fatigue**: Hundreds of pages across multiple seasons make manual cross-referencing error-prone.

Continuity Guardian solves this by automating script supervision through an **autonomous, concurrent multi-agent network** that checks every line of dialogue and action against persistent studio canon and live web knowledge bases.

---

### 🧠 Autonomous Multi-Agent Architecture Topology

```
                               ┌──────────────────────────────────┐
                               │   Raw Episode Script / Draft     │
                               │  (Sluglines, Action, Dialogue)   │
                               └────────────────┬─────────────────┘
                                                │
                                                ▼
                               ┌──────────────────────────────────┐
                               │       FactExtractor Agent        │
                               │   • Google Gemini 3.5 Flash      │
                               │   • Entity & Claim Extraction    │
                               │   • 1-Indexed Line Tracking      │
                               └────────────────┬─────────────────┘
                                                │
                       ┌────────────────────────┴────────────────────────┐
                       │                                                 │
                       ▼ (claims: internal)                              ▼ (claims: real_world)
        ┌──────────────────────────────┐                  ┌──────────────────────────────┐
        │    InternalChecker Agent     │                  │    RealWorldChecker Agent    │
        │   • Google Cloud Firestore   │                  │   • Parallel AI MCP Search   │
        │   • Multi-Season Show Bible  │                  │   • Live Web Fact-Checking   │
        │   • Character Trait Canon    │                  │   • 6-Hour SHA-256 Cache     │
        │   • Gemini 3.5 Reasoning     │                  │   • Gemini 3.5 Reasoning     │
        └──────────────┬───────────────┘                  └──────────────┬───────────────┘
                       │                                                 │
                       └────────────────────────┬────────────────────────┘
                                                │ (asyncio.gather parallel execution)
                                                ▼
                               ┌──────────────────────────────────┐
                               │       ReportBuilder Agent        │
                               │   • Bayesian Confidence Scoring  │
                               │   • Executive Studio Brief       │
                               │   • Actionable Editorial Fixes   │
                               └────────────────┬─────────────────┘
                                                │
                                                ▼
                               ┌──────────────────────────────────┐
                               │       Script Doctor Agent        │
                               │   • Hollywood Scene Rewriter     │
                               │   • Character Voice Preservation │
                               │   • Clean Slugline & Beat Repair │
                               └──────────────────────────────────┘
```

---

### 📊 Claim Classification Matrix

Every extracted claim is routed to a specialized verification agent based on its jurisdictional scope:

| Claim Type | Scope & Verification Source | Screenplay Demonstration Example | Handling Agent Subsystem |
|---|---|---|---|
| **`internal`** | Narrative canon stored in Firestore Show Bible | *"Daniel called me from Chicago; he's alive!"* *(Contradicts S01E01 car death in 2021)* | `InternalChecker` (Firestore + Gemini 3.5) |
| **`real_world`** | External history, science, medicine, geography | *"Alexander Fleming discovered penicillin in 1985."* *(Discovered in 1928)* | `RealWorldChecker` (Parallel AI MCP + Gemini 3.5) |

---

### 📖 Cloud Firestore Show Bible Data Model

The persistent Show Bible is hosted in **Google Cloud Firestore** under the `episodes` collection, enabling instant cross-season continuity recall:

```json
{
  "episode_id": "s01e01",
  "characters": ["Maya Vance", "Daniel Vance", "Detective Carter"],
  "key_facts": [
    "Daniel Vance died in a fatal car accident in 2021",
    "Detective Carter is assigned to the Vance family investigation",
    "Maya has a severe allergic reaction to penicillin"
  ],
  "timeline": {
    "2021": "Daniel's fatal accident on the rain-slicked highway",
    "2023": "Carter reopens the cold case file"
  },
  "established_traits": {
    "Maya Vance": "Left-handed, photographic memory, severe penicillin allergy",
    "Detective Carter": "Heavy smoker, aquaphobia (fear of open water)"
  },
  "date_added": "2026-09-08"
}
```

---

### 🔍 Parallel AI MCP Web Grounding & Smart Caching

For real-world factual claims, the **RealWorldChecker** invokes **Parallel AI MCP Search** to ground reasoning on live web evidence:
* **Zero Cost Caching**: All web queries are hashed using **SHA-256** and cached for **6 hours** in memory to protect API quota and conserve MCP search credits.
* **Deterministic Verification**: Gemini 3.5 Flash evaluates the retrieved search excerpts against the screenplay claim, citing discovery years, geographical coordinates, or medical guidelines.

---

### ⚡ Screenplay Formatting & Industry Standards

The API accepts screenplay scenes formatted according to standard Hollywood conventions:
* **Scene Headings / Sluglines**: `INT. APARTMENT — NIGHT` or `EXT. DOCKS — DAWN`
* **Action Lines**: Third-person present tense descriptions
* **Character Cues & Parentheticals**: Uppercase names (`MAYA`, `CARTER`) with emotional parentheticals `(into phone)`
* **Dialogue Blocks**: Spoken lines, tracked with 1-indexed line numbers for precise editor feedback

---

### 🚀 Quickstart Guide

#### Option 1: `curl` CLI

```bash
curl -X POST "http://localhost:8000/check-episode" \\
  -H "Content-Type: application/json" \\
  -d '{
    "episode_id": "s01e04",
    "script_text": "INT. APARTMENT — NIGHT\\n\\nMAYA\\n(into phone)\\nDaniel, is that you? I need to tell you what happened at the docks.\\n\\nCARTER\\nMaya, Daniel died in that car crash in 2021.\\n\\nMAYA\\nHe is alive! He says Alexander Fleming gave him penicillin in 1985!"
  }'
```

#### Option 2: Python Client (`requests`)

```python
import requests

payload = {
    "episode_id": "s01e04",
    "script_text": (
        "INT. OFFICE — DAY\\n"
        "MAYA: Daniel called from Chicago. He said Fleming found penicillin in 1985."
    )
}

response = requests.post("http://localhost:8000/check-episode", json=payload)
data = response.json()

print(f"Executive Summary: {data['summary']}")
for issue in data['results']:
    if issue['is_contradiction']:
        print(f"❌ [Line {issue['claim']['source_line']}] {issue['explanation']}")
        print(f"💡 Fix: {issue['suggested_fix']}\\n")
```

---

### 🛡️ Error Handling & Status Code Matrix

| Status Code | Reason | Resolution |
|---|---|---|
| **`200 OK`** | Analysis or revision succeeded | Report generated with confidence-ranked contradictions. |
| **`422 Unprocessable Entity`** | Script text < 20 characters or malformed JSON | Provide a valid screenplay draft of at least 20 characters. |
| **`500 Internal Server Error`** | Server configuration or API key missing | Verify `GEMINI_API_KEY` and Firebase credentials in environment. |
| **`503 Service Unavailable`** | Firestore database connectivity drop | Auto-falls back to local seed canon or retries connection. |
"""

TAGS_METADATA = [
    {
        "name": "🎬 Continuity Engine",
        "description": "Core multi-agent pipeline: extracts structured claims, queries Firestore canon, and cross-references live web facts via Parallel AI MCP.",
    },
    {
        "name": "✍️ Script Doctor",
        "description": "Autonomous screenplay revision agent that rewrites scenes to fix flagged contradictions while preserving character voice and dramatic tension.",
    },
    {
        "name": "📖 Show Bible",
        "description": "Access the persistent Firestore canon database storing character traits, relationships, established timeline events, and episode registries.",
    },
    {
        "name": "⚙️ System & Health",
        "description": "Liveness probes, deployment readiness checks, service discovery, and cloud orchestrator telemetry.",
    },
]

# Custom Cinema Dark styling for Swagger UI
SWAGGER_DARK_CSS = """
body {
  background-color: #08070d !important;
  color: #e2e8f0 !important;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
  margin: 0 !important;
  padding: 0 !important;
}

/* Custom Studio Topbar */
.studio-topbar {
  background: #110f1c;
  border-bottom: 1px solid rgba(255, 255, 255, 0.09);
  padding: 12px 28px;
  position: sticky;
  top: 0;
  z-index: 1000;
  box-shadow: 0 4px 25px rgba(0, 0, 0, 0.7);
}
.studio-topbar-inner {
  max-width: 1440px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.studio-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.studio-badge {
  font-family: 'Outfit', sans-serif;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  background: rgba(139, 92, 246, 0.18);
  border: 1px solid rgba(139, 92, 246, 0.4);
  color: #a78bfa;
  padding: 4px 10px;
  border-radius: 999px;
}
.studio-title {
  font-family: 'Outfit', sans-serif;
  font-size: 1.15rem;
  font-weight: 700;
  color: #ffffff;
}
.studio-nav-links {
  display: flex;
  align-items: center;
  gap: 10px;
}
.studio-status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 999px;
  background: rgba(16, 185, 129, 0.12);
  border: 1px solid rgba(16, 185, 129, 0.3);
  color: #34d399;
  font-size: 0.75rem;
  font-weight: 600;
}
.studio-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 8px #10b981;
}
.studio-btn {
  font-family: 'Inter', sans-serif;
  font-size: 0.82rem;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 999px;
  text-decoration: none;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.studio-btn--studio {
  background: linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%);
  color: #ffffff !important;
  box-shadow: 0 0 15px rgba(124, 58, 237, 0.4);
}
.studio-btn--studio:hover {
  transform: translateY(-1px);
  box-shadow: 0 0 22px rgba(124, 58, 237, 0.7);
}
.studio-btn--alt {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #cbd5e1 !important;
}
.studio-btn--alt:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #ffffff !important;
}

/* Swagger UI Global Resets */
.swagger-ui {
  color: #cbd5e1 !important;
  max-width: 1440px;
  margin: 0 auto;
  padding: 24px;
}
.swagger-ui .topbar { display: none !important; }
.swagger-ui .wrapper {
  padding: 0 !important;
  max-width: 100% !important;
}

/* Info container & Description */
.swagger-ui .info {
  background: #12101e !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  border-radius: 20px !important;
  padding: 38px !important;
  margin: 20px 0 35px 0 !important;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.6) !important;
}
.swagger-ui .info .title {
  color: #ffffff !important;
  font-family: 'Outfit', sans-serif !important;
  font-size: 2.3rem !important;
  font-weight: 800 !important;
  letter-spacing: -0.02em !important;
  line-height: 1.2 !important;
}
.swagger-ui .info .title small {
  background: rgba(139, 92, 246, 0.2) !important;
  border: 1px solid rgba(139, 92, 246, 0.5) !important;
  color: #a78bfa !important;
  font-size: 0.75rem !important;
  font-weight: 700 !important;
  padding: 4px 10px !important;
  border-radius: 999px !important;
  vertical-align: middle !important;
  margin-left: 12px !important;
}
.swagger-ui .info p, .swagger-ui .info li, .swagger-ui .info td {
  color: #94a3b8 !important;
  font-size: 0.95rem !important;
  line-height: 1.75 !important;
}
.swagger-ui .info h1, .swagger-ui .info h2, .swagger-ui .info h3, .swagger-ui .info h4 {
  color: #ffffff !important;
  font-family: 'Outfit', sans-serif !important;
  font-weight: 700 !important;
  margin-top: 1.8rem !important;
  margin-bottom: 0.8rem !important;
}
.swagger-ui .info table {
  background: #0b0914 !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  border-radius: 12px !important;
  overflow: hidden !important;
  width: 100% !important;
  margin: 18px 0 !important;
  border-collapse: collapse !important;
}
.swagger-ui .info table th {
  background: #181529 !important;
  color: #f8fafc !important;
  font-weight: 700 !important;
  padding: 12px 16px !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important;
}
.swagger-ui .info table td {
  padding: 12px 16px !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
  color: #cbd5e1 !important;
}
.swagger-ui .info code {
  background: #08070d !important;
  color: #fbbf24 !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  padding: 3px 8px !important;
  border-radius: 6px !important;
  font-family: 'JetBrains Mono', monospace !important;
  font-size: 0.88em !important;
}
.swagger-ui .info pre {
  background: #08070d !important;
  border: 1px solid rgba(255, 255, 255, 0.09) !important;
  border-radius: 12px !important;
  padding: 18px !important;
  overflow-x: auto !important;
}
.swagger-ui .info pre code {
  color: #38bdf8 !important;
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
}
.swagger-ui .info a {
  color: #a78bfa !important;
  text-decoration: none !important;
  border-bottom: 1px dotted rgba(167, 139, 250, 0.5) !important;
}

/* Schemes & Filter Controls */
.swagger-ui .scheme-container {
  background: #12101e !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  border-radius: 14px !important;
  box-shadow: none !important;
  padding: 16px 24px !important;
  margin-bottom: 24px !important;
}
.swagger-ui .schemes-title {
  color: #94a3b8 !important;
}
.swagger-ui .filter-container {
  padding: 0 !important;
  margin-bottom: 20px !important;
}
.swagger-ui .filter-container input {
  background: #12101e !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  color: #ffffff !important;
  border-radius: 10px !important;
  padding: 10px 16px !important;
  font-family: 'Inter', sans-serif !important;
}

/* Tags (Sections) */
.swagger-ui .opblock-tag {
  color: #ffffff !important;
  font-family: 'Outfit', sans-serif !important;
  font-size: 1.45rem !important;
  font-weight: 700 !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.09) !important;
  padding: 20px 0 12px 0 !important;
}
.swagger-ui .opblock-tag small {
  color: #64748b !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 0.88rem !important;
}

/* Operation Blocks (Endpoints) */
.swagger-ui .opblock {
  background: #12101e !important;
  border-radius: 16px !important;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4) !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  margin-bottom: 20px !important;
  overflow: hidden !important;
}
.swagger-ui .opblock .opblock-summary {
  padding: 12px 20px !important;
  border-bottom: 1px solid transparent !important;
}
.swagger-ui .opblock.is-open .opblock-summary {
  border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
}

/* Method Styles */
.swagger-ui .opblock.opblock-post {
  border-left: 5px solid #10b981 !important;
  background: rgba(16, 185, 129, 0.04) !important;
}
.swagger-ui .opblock.opblock-post .opblock-summary-method {
  background: #10b981 !important;
  color: #ffffff !important;
  font-weight: 800 !important;
  box-shadow: 0 0 14px rgba(16, 185, 129, 0.4) !important;
  border-radius: 8px !important;
  min-width: 80px !important;
}
.swagger-ui .opblock.opblock-get {
  border-left: 5px solid #06b6d4 !important;
  background: rgba(6, 182, 212, 0.04) !important;
}
.swagger-ui .opblock.opblock-get .opblock-summary-method {
  background: #06b6d4 !important;
  color: #ffffff !important;
  font-weight: 800 !important;
  box-shadow: 0 0 14px rgba(6, 182, 212, 0.4) !important;
  border-radius: 8px !important;
  min-width: 80px !important;
}

.swagger-ui .opblock-summary-path {
  color: #ffffff !important;
  font-family: 'JetBrains Mono', monospace !important;
  font-weight: 700 !important;
  font-size: 1.05rem !important;
}
.swagger-ui .opblock-summary-description {
  color: #94a3b8 !important;
  font-size: 0.9rem !important;
}

/* Opblock Body */
.swagger-ui .opblock-body {
  background: #151224 !important;
}
.swagger-ui .opblock-section-header {
  background: rgba(0, 0, 0, 0.3) !important;
  color: #ffffff !important;
  font-weight: 700 !important;
  padding: 10px 20px !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06) !important;
}
.swagger-ui .opblock-section-header h4 {
  color: #ffffff !important;
  font-family: 'Outfit', sans-serif !important;
}
.swagger-ui .opblock-description-wrapper p {
  color: #cbd5e1 !important;
  font-size: 0.95rem !important;
  line-height: 1.7 !important;
}

/* Parameters Table & Body */
.swagger-ui .parameters-container {
  background: transparent !important;
  padding: 16px 20px !important;
}
.swagger-ui table.parameters {
  background: transparent !important;
}
.swagger-ui table.parameters th {
  color: #94a3b8 !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
  font-size: 0.85rem !important;
  text-transform: uppercase !important;
  letter-spacing: 0.05em !important;
}
.swagger-ui table.parameters td {
  border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
  color: #cbd5e1 !important;
  padding: 14px 10px !important;
}
.swagger-ui .parameter__name {
  color: #ffffff !important;
  font-family: 'JetBrains Mono', monospace !important;
  font-weight: 700 !important;
}
.swagger-ui .parameter__type {
  color: #fbbf24 !important;
  font-family: 'JetBrains Mono', monospace !important;
}
.swagger-ui .parameter__deprecated {
  color: #ef4444 !important;
}

/* Inputs, Textareas, and Selects */
.swagger-ui select, .swagger-ui input[type=text], .swagger-ui textarea {
  background: #08070d !important;
  color: #ffffff !important;
  border: 1px solid rgba(255, 255, 255, 0.15) !important;
  border-radius: 8px !important;
  font-family: 'JetBrains Mono', monospace !important;
  padding: 10px 14px !important;
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.5) !important;
}
.swagger-ui select:focus, .swagger-ui input[type=text]:focus, .swagger-ui textarea:focus {
  border-color: #8b5cf6 !important;
  outline: none !important;
  box-shadow: 0 0 12px rgba(139, 92, 246, 0.4) !important;
}

/* Buttons */
.swagger-ui .btn {
  border-radius: 999px !important;
  font-family: 'Inter', sans-serif !important;
  font-weight: 600 !important;
  transition: all 0.2s ease !important;
}
.swagger-ui .btn.try-out__btn {
  background: rgba(255, 255, 255, 0.06) !important;
  border: 1px solid rgba(255, 255, 255, 0.18) !important;
  color: #ffffff !important;
  padding: 6px 16px !important;
}
.swagger-ui .btn.try-out__btn:hover {
  background: rgba(255, 255, 255, 0.12) !important;
}
.swagger-ui .btn.execute {
  background: linear-gradient(135deg, #7c3aed, #4f46e5) !important;
  border: none !important;
  color: #ffffff !important;
  padding: 10px 28px !important;
  box-shadow: 0 0 18px rgba(124, 58, 237, 0.5) !important;
}
.swagger-ui .btn.execute:hover {
  transform: translateY(-1px) !important;
  box-shadow: 0 0 25px rgba(124, 58, 237, 0.7) !important;
}
.swagger-ui .btn.btn-clear {
  background: rgba(255, 255, 255, 0.05) !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  color: #cbd5e1 !important;
}

/* Responses Section */
.swagger-ui .responses-wrapper {
  background: transparent !important;
  padding: 16px 20px !important;
}
.swagger-ui table.responses-table {
  background: transparent !important;
}
.swagger-ui table.responses-table th {
  color: #94a3b8 !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
}
.swagger-ui table.responses-table td {
  border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
  color: #cbd5e1 !important;
}
.swagger-ui .response-col_status {
  color: #10b981 !important;
  font-family: 'JetBrains Mono', monospace !important;
  font-weight: 700 !important;
  font-size: 1rem !important;
}
.swagger-ui .response-col_description__inner p {
  color: #cbd5e1 !important;
}

/* Code Highlight Boxes, Curl & Responses */
.swagger-ui .microlight, .swagger-ui .highlight-code, .swagger-ui .curl-command {
  background: #08070d !important;
  color: #f1f5f9 !important;
  border-radius: 10px !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  padding: 14px 18px !important;
}
.swagger-ui .curl-command span, .swagger-ui .curl-command div {
  color: #38bdf8 !important;
  font-family: 'JetBrains Mono', monospace !important;
}
.swagger-ui .copy-to-clipboard {
  background: rgba(255, 255, 255, 0.08) !important;
  border-radius: 6px !important;
}

/* Tabs */
.swagger-ui .tabli button {
  color: #94a3b8 !important;
  font-weight: 600 !important;
}
.swagger-ui .tabli.active button {
  color: #ffffff !important;
  border-bottom: 2px solid #8b5cf6 !important;
}

/* Models / Schemas Drawer */
.swagger-ui section.models {
  background: #12101e !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  border-radius: 16px !important;
  padding: 16px 24px !important;
  margin-top: 36px !important;
}
.swagger-ui section.models h4 {
  color: #ffffff !important;
  font-family: 'Outfit', sans-serif !important;
  font-size: 1.3rem !important;
}
.swagger-ui .model-container {
  background: #0d0b18 !important;
  border-radius: 10px !important;
  margin: 10px 0 !important;
  border: 1px solid rgba(255, 255, 255, 0.06) !important;
}
.swagger-ui .model-box {
  background: transparent !important;
  padding: 12px 16px !important;
}
.swagger-ui .model-title {
  color: #a78bfa !important;
  font-weight: 700 !important;
  font-family: 'Outfit', sans-serif !important;
}
.swagger-ui .prop-type {
  color: #fbbf24 !important;
  font-family: 'JetBrains Mono', monospace !important;
}
.swagger-ui .prop-format {
  color: #64748b !important;
}
"""

# Custom Cinema Dark styling for ReDoc
REDOC_DARK_CSS = """
body, html {
  background-color: #08070d !important;
  color: #e2e8f0 !important;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
  margin: 0 !important;
  padding: 0 !important;
}

.studio-topbar {
  background: #110f1c;
  border-bottom: 1px solid rgba(255, 255, 255, 0.09);
  padding: 12px 28px;
  position: sticky;
  top: 0;
  z-index: 1000;
  box-shadow: 0 4px 25px rgba(0, 0, 0, 0.7);
}
.studio-topbar-inner {
  max-width: 1440px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.studio-brand { display: flex; align-items: center; gap: 12px; }
.studio-badge {
  font-family: 'Outfit', sans-serif;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  background: rgba(139, 92, 246, 0.18);
  border: 1px solid rgba(139, 92, 246, 0.4);
  color: #a78bfa;
  padding: 4px 10px;
  border-radius: 999px;
}
.studio-title {
  font-family: 'Outfit', sans-serif;
  font-size: 1.15rem;
  font-weight: 700;
  color: #ffffff;
}
.studio-nav-links { display: flex; align-items: center; gap: 10px; }
.studio-status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 999px;
  background: rgba(16, 185, 129, 0.12);
  border: 1px solid rgba(16, 185, 129, 0.3);
  color: #34d399;
  font-size: 0.75rem;
  font-weight: 600;
}
.studio-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 8px #10b981;
}
.studio-btn {
  font-family: 'Inter', sans-serif;
  font-size: 0.82rem;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 999px;
  text-decoration: none;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.studio-btn--studio {
  background: linear-gradient(135deg, #7c3aed, #4f46e5);
  color: #ffffff !important;
  box-shadow: 0 0 15px rgba(124, 58, 237, 0.4);
}
.studio-btn--studio:hover {
  transform: translateY(-1px);
  box-shadow: 0 0 22px rgba(124, 58, 237, 0.7);
}
.studio-btn--alt {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #cbd5e1 !important;
}
.studio-btn--alt:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #ffffff !important;
}

/* ReDoc Component Overrides */
#redoc-container, .redoc-wrap {
  background-color: #0c0a17 !important;
}
.api-content {
  background-color: #0c0a17 !important;
}
.api-content > div {
  background-color: #0c0a17 !important;
}
.menu-content {
  background-color: #08070d !important;
  border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
}
"""

app = FastAPI(
    title="🎬 Continuity Guardian API",
    description=API_DESCRIPTION,
    version="1.0.0",
    openapi_tags=TAGS_METADATA,
    contact={
        "name": "Continuity Guardian Studio Engineering Team",
        "url": "https://github.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

# ---------------------------------------------------------------------------
# Favicon & Custom Swagger UI & ReDoc Documentation Routes
# ---------------------------------------------------------------------------

@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.png", include_in_schema=False)
async def favicon() -> FileResponse:
    """Serves the studio cinema slate favicon."""
    favicon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "favicon.png")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Favicon not found")


@app.get("/spec.pdf", include_in_schema=False)
@app.get("/ContinuityGuardian_System_Documentation.pdf", include_in_schema=False)
async def get_system_pdf() -> FileResponse:
    """Serves the publication-quality System Documentation PDF."""
    pdf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "ContinuityGuardian_System_Documentation.pdf")
    if os.path.exists(pdf_path):
        return FileResponse(pdf_path, media_type="application/pdf", filename="ContinuityGuardian_System_Documentation.pdf")
    raise HTTPException(status_code=404, detail="System PDF not found")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """Renders custom Cinema Dark themed Swagger UI with navigation to the Studio app."""
    response = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="🎬 Continuity Guardian API — Interactive OpenAPI Console",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
        swagger_favicon_url="/favicon.png",
    )
    custom_head = f"""
    <link rel="icon" type="image/png" href="/favicon.png">
    <link rel="shortcut icon" type="image/png" href="/favicon.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
    <style>{SWAGGER_DARK_CSS}</style>
    """
    html = response.body.decode("utf-8").replace("</head>", f"{custom_head}</head>")
    topbar = """
    <div class="studio-topbar">
      <div class="studio-topbar-inner">
        <div class="studio-brand">
          <span class="studio-badge">STUDIO API</span>
          <span class="studio-title">🎬 Continuity Guardian — Interactive OpenAPI Console</span>
        </div>
        <div class="studio-nav-links">
          <div class="studio-status-pill">
            <span class="studio-status-dot"></span>
            <span>API Online · Port 8000</span>
          </div>
          <a href="http://localhost:3000" class="studio-btn studio-btn--studio">← Open Script Studio</a>
          <a href="/ContinuityGuardian_System_Documentation.pdf" target="_blank" class="studio-btn studio-btn--alt">📑 PDF Spec ↗</a>
          <a href="/redoc" class="studio-btn studio-btn--alt">Switch to ReDoc ↗</a>
        </div>
      </div>
    </div>
    """
    html = html.replace("<body>", f"<body>{topbar}")
    return HTMLResponse(content=html)


@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html():
    """Renders custom Cinema Dark themed ReDoc with navigation to the Studio app."""
    return HTMLResponse(
        content=f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>🎬 Continuity Guardian API — Architecture &amp; Specification Hub (ReDoc)</title>
  <link rel="icon" type="image/png" href="/favicon.png">
  <link rel="shortcut icon" type="image/png" href="/favicon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
  <style>
    {REDOC_DARK_CSS}
  </style>
</head>
<body>
  <div class="studio-topbar">
    <div class="studio-topbar-inner">
      <div class="studio-brand">
        <span class="studio-badge">STUDIO API</span>
        <span class="studio-title">🎬 Continuity Guardian — ReDoc Architecture Specification</span>
      </div>
      <div class="studio-nav-links">
        <div class="studio-status-pill">
          <span class="studio-status-dot"></span>
          <span>API Online · Port 8000</span>
        </div>
        <a href="http://localhost:3000" class="studio-btn studio-btn--studio">← Open Script Studio</a>
        <a href="/ContinuityGuardian_System_Documentation.pdf" target="_blank" class="studio-btn studio-btn--alt">📑 PDF Spec ↗</a>
        <a href="/docs" class="studio-btn studio-btn--alt">Switch to Swagger UI ↗</a>
      </div>
    </div>
  </div>

  <div id="redoc-container"></div>

  <script src="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"></script>
  <script>
    Redoc.init('/openapi.json', {{
      theme: {{
        spacing: {{ unit: 5, sectionHorizontal: 40, sectionVertical: 35 }},
        breakpoints: {{ small: '50rem', medium: '75rem', large: '105rem' }},
        colors: {{
          tonalOffset: 0.2,
          primary: {{ main: '#a78bfa' }},
          success: {{ main: '#10b981' }},
          warning: {{ main: '#f59e0b' }},
          error: {{ main: '#ef4444' }},
          text: {{ primary: '#f8fafc', secondary: '#94a3b8' }},
          border: {{ dark: 'rgba(255,255,255,0.12)', light: 'rgba(255,255,255,0.06)' }},
          responses: {{
            success: {{ color: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.08)' }},
            error: {{ color: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.08)' }}
          }},
          http: {{
            get: '#06b6d4',
            post: '#10b981',
            put: '#f59e0b',
            delete: '#ef4444'
          }}
        }},
        typography: {{
          fontSize: '14px',
          lineHeight: '1.65em',
          fontWeightRegular: '400',
          fontWeightBold: '700',
          fontFamily: "'Inter', -apple-system, sans-serif",
          headings: {{
            fontFamily: "'Outfit', sans-serif",
            fontWeight: '700',
            lineHeight: '1.3em'
          }},
          code: {{
            fontSize: '13px',
            fontFamily: "'JetBrains Mono', monospace",
            color: '#fbbf24',
            backgroundColor: '#05040a',
            wrap: true
          }}
        }},
        sidebar: {{
          width: '280px',
          backgroundColor: '#08070d',
          textColor: '#94a3b8',
          activeTextColor: '#a78bfa'
        }},
        rightPanel: {{
          backgroundColor: '#07060c',
          width: '44%',
          textColor: '#f8fafc'
        }}
      }},
      hideDownloadButton: false,
      expandResponses: '200,201',
      nativeScrollbars: true,
      scrollYOffset: '.studio-topbar'
    }}, document.getElementById('redoc-container'));
  </script>
</body>
</html>
        """
    )

# ---------------------------------------------------------------------------
# CORS — allow all origins so the standalone frontend can call this API
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten to specific domains before production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get(
    "/",
    summary="System discovery & endpoint registry",
    tags=["⚙️ System & Health"],
    response_model=dict[str, Any],
)
async def root() -> dict[str, Any]:
    """
    **Root Discovery Endpoint**

    Returns a high-level system overview, active engine version, and a catalog of
    available endpoints for client discovery and service health verification.
    """
    return {
        "name": "Continuity Guardian API",
        "version": "1.0.0",
        "description": (
            "Enterprise-grade multi-agent continuity supervision and autonomous screenplay "
            "repair engine powered by Google Gemini 3.5, Google ADK, Google Cloud Firestore, "
            "and Parallel AI MCP."
        ),
        "engine": "Google Gemini 3.5 Flash",
        "canon_database": "Google Cloud Firestore (continuity-guardian-e4064)",
        "web_grounding": "Parallel AI MCP Search (SHA-256 Cached)",
        "endpoints": {
            "POST /check-episode": "Analyse a screenplay scene draft and return a structured ContinuityReport.",
            "POST /rewrite-script": "Script Doctor Agent: autonomously rewrite screenplay scenes to resolve contradictions.",
            "GET  /show-bible":     "Retrieve the complete multi-season Show Bible canon from Cloud Firestore.",
            "GET  /episodes":       "List registered canonical episodes stored in the Show Bible.",
            "GET  /health":         "Liveness and deployment readiness probe.",
            "GET  /docs":           "Interactive OpenAPI developer console (Swagger UI).",
            "GET  /redoc":          "ReDoc architecture specification.",
        },
    }


@app.get(
    "/health",
    summary="Liveness and deployment readiness probe",
    tags=["⚙️ System & Health"],
    response_model=dict[str, str],
)
async def health() -> dict[str, str]:
    """
    **Liveness and Deployment Readiness Probe**

    Used by container orchestrators (Google Cloud Run, Kubernetes, Docker Compose,
    or Hugging Face Spaces) to verify the service is running and ready to accept traffic.

    - Returns HTTP `200 OK` with `{"status": "ok"}` on success.
    """
    return {"status": "ok"}


@app.post(
    "/check-episode",
    summary="Analyse screenplay draft for continuity & factual errors",
    tags=["🎬 Continuity Engine"],
    response_model=ContinuityReportOut,
    status_code=200,
)
async def check_episode(body: CheckEpisodeRequest) -> ContinuityReportOut:
    """
    **Execute Full Multi-Agent Continuity & Factual Verification Pipeline**

    Takes an episode script draft or treatment and routes it through a concurrent 5-agent pipeline:

    1. **FactExtractor Agent (Gemini 3.5 Flash)**: Parses scene sluglines, action descriptions,
       and dialogue cues. Extracts declarative statements, identifies character entities,
       tracks 1-indexed source line numbers, and classifies claims into `internal` or `real_world`.
    2. **InternalChecker Agent (Firestore + Gemini 3.5)**: Queries the persistent Firestore
       Show Bible using character names and keywords. Cross-references the claim against established
       past episode facts, character medical history, phobias, and timeline records.
    3. **RealWorldChecker Agent (Parallel AI MCP + Gemini 3.5)**: Validates real-world historical dates,
       medical facts, geography, and science using live web search, protected by a 6-hour SHA-256 cache.
    4. **ReportBuilder Agent (Gemini 3.5 Flash)**: Synthesizes verdicts, computes Bayesian
       confidence scores (0.0 to 1.0), and crafts an actionable studio executive brief with recommended fixes.

    **Response Structure**:
    - `episode_id`: Identifier of the episode draft analysed.
    - `summary`: High-level plain-English executive summary formulated for producers and script supervisors.
    - `results`: List of verified claims and flagged contradictions ranked from highest confidence to lowest.
    - `generated_at`: ISO 8601 UTC timestamp.
    """
    logger.info(
        "POST /check-episode — episode_id=%r, script_length=%d chars.",
        body.episode_id,
        len(body.script_text),
    )

    try:
        report = await _state.pipeline.run(
            episode_id=body.episode_id,
            script_text=body.script_text,
        )
    except EnvironmentError as exc:
        # Missing API keys etc. — surface as 500 with a clear message
        logger.error("Configuration error during pipeline run: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=(
                f"Server configuration error: {exc}. "
                "Check that all required environment variables are set."
            ),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unexpected error running pipeline for episode_id=%r: %s",
            body.episode_id,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during analysis. See server logs.",
        ) from exc

    return _report_to_out(report)


@app.get(
    "/episodes",
    summary="List registered show-bible episodes",
    tags=["📖 Show Bible"],
    response_model=list[EpisodeSummary],
)
async def list_episodes() -> list[EpisodeSummary]:
    """
    **List Canonical Episodes Stored in the Show Bible**

    Returns a lightweight registry of all episodes registered in the Firestore canon database.
    Useful for populating UI dropdowns, script selectors, and checking database synchronization.
    """
    logger.info("GET /episodes — fetching all episodes from show bible.")

    try:
        episodes = _state.repository.get_all_episodes()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch episodes from Firestore: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Could not retrieve episodes from the database. Try again shortly.",
        ) from exc

    summaries = [
        EpisodeSummary(
            episode_id=ep.episode_id,
            date_added=ep.date_added,
        )
        for ep in episodes
    ]
    logger.info("GET /episodes — returning %d episode(s).", len(summaries))
    return summaries


@app.get(
    "/show-bible",
    summary="Retrieve full multi-season canon database",
    tags=["📖 Show Bible"],
)
async def get_show_bible() -> list[dict]:
    """
    **Retrieve Complete Firestore Show Bible Canon**

    Returns full `EpisodeRecord` objects containing:
    - `characters`: Complete list of introduced dramatis personae.
    - `key_facts`: Irrevocable narrative milestones established in the episode.
    - `timeline`: Chronological dates and years when canonical events occurred.
    - `established_traits`: Character habits, medical conditions, allergies, handedness, and phobias.
    """
    try:
        episodes = _state.repository.get_all_episodes()
        return [ep.to_dict() for ep in episodes]
    except Exception as exc:
        logger.error("Failed to load show bible: %s", exc)
        return []


@app.post(
    "/rewrite-script",
    summary="Autonomous screenplay revision via Gemini Script Doctor",
    tags=["✍️ Script Doctor"],
    response_model=RewriteScriptResponse,
)
async def rewrite_script(body: RewriteScriptRequest) -> RewriteScriptResponse:
    """
    **AI Script Doctor: Autonomous Screenplay Repair & Polish**

    Acts as an autonomous Hollywood script doctor and continuity editor. Takes the original
    screenplay draft and the list of flagged contradictions, and synthesizes a revised scene:

    - **Continuity Compliance**: Seamlessly fixes every flagged contradiction (both internal lore and real-world facts).
    - **Voice & Rhythm Preservation**: Faithfully respects each character's speech patterns, vocabulary, and subtext.
    - **Screenplay Formatting**: Preserves industry standard sluglines (`INT. / EXT.`), character cues, and parentheticals.
    - **Editorial Changelog**: Returns a 2-sentence summary of the dramatic repairs made for the showrunner's review.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        system_instruction=(
            "You are an expert Hollywood Script Doctor and Continuity Editor. "
            "Your task is to take a screenplay scene containing continuity errors "
            "and factual mistakes, and rewrite it so that all contradictions are cleanly "
            "fixed while preserving character voices, dramatic tension, and screenplay formatting."
        ),
    )

    issues_text = "\n".join(
        f"- Issue: {item.get('explanation', '')} | Suggested fix: {item.get('suggested_fix', '')}"
        for item in body.issues
    ) if body.issues else "Ensure general continuity and polish."

    prompt = (
        f"ORIGINAL SCRIPT:\n{body.original_script}\n\n"
        f"FLAGGED CONTINUITY / FACTUAL CONTRADICTIONS TO FIX:\n{issues_text}\n\n"
        "TASK:\n"
        "1. Rewrite the script to fix every flagged contradiction seamlessly.\n"
        "2. Provide a 2-sentence summary of what you changed.\n\n"
        "Respond in strict JSON with this exact schema:\n"
        "{\n"
        '  "rewritten_script": "The full revised screenplay scene here",\n'
        '  "changes_summary": "Summary of specific continuity fixes made"\n'
        "}"
    )

    candidates = [
        os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
        "gemini-flash-latest",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-3.6-flash",
    ]
    seen = set()
    text = ""
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            m = genai.GenerativeModel(
                model_name=name,
                system_instruction=(
                    "You are an expert Hollywood Script Doctor and Continuity Editor. "
                    "Your task is to take a screenplay scene containing continuity errors "
                    "and factual mistakes, and rewrite it so that all contradictions are cleanly "
                    "fixed while preserving character voices, dramatic tension, and screenplay formatting."
                ),
            )
            response = m.generate_content(prompt)
            if response and response.text:
                text = response.text.strip()
                break
        except Exception as exc:
            logger.warning("Script doctor candidate %s failed: %s — trying next.", name, exc)
            continue

    try:
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        data = json.loads(text.strip()) if text else {}
        return RewriteScriptResponse(
            rewritten_script=data.get("rewritten_script", body.original_script),
            changes_summary=data.get("changes_summary", "Continuity fixes applied."),
        )
    except Exception as exc:
        logger.error("Script rewrite parse failed: %s", exc)
        return RewriteScriptResponse(
            rewritten_script=body.original_script,
            changes_summary=f"Could not automatically rewrite script: {exc}",
        )


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------

def _report_to_out(report) -> ContinuityReportOut:
    """
    Convert an agent-layer ContinuityReport dataclass into the Pydantic
    output model FastAPI needs to serialise the response.

    A converter function is used (rather than having the dataclass inherit
    from BaseModel) to keep the agent layer completely free of FastAPI/Pydantic
    imports — the API layer is the only place that should know about HTTP.
    """
    return ContinuityReportOut(
        episode_id=report.episode_id,
        results=[
            CheckResultOut(
                claim=ClaimOut(
                    text=r.claim.text,
                    claim_type=r.claim.claim_type,
                    source_line=r.claim.source_line,
                ),
                is_contradiction=r.is_contradiction,
                explanation=r.explanation,
                suggested_fix=r.suggested_fix,
                confidence=r.confidence,
            )
            for r in report.results
        ],
        summary=report.summary,
        generated_at=report.generated_at,
    )
