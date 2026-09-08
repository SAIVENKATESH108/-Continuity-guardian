# 🎬 Continuity Guardian — Cinema Multi-Agent Continuity & Script Doctor Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Google Gemini](https://img.shields.io/badge/Google%20Gemini-3.5%20Flash-4285F4.svg?style=flat&logo=google)](https://ai.google.dev)
[![Google Cloud](https://img.shields.io/badge/Google%20Cloud-Firestore-FFA611.svg?style=flat&logo=firebase)](https://cloud.google.com/firestore)
[![Parallel AI](https://img.shields.io/badge/Parallel%20AI-MCP%20Search-6366F1.svg?style=flat)](https://parallel.ai)
[![Vercel](https://img.shields.io/badge/Vercel-Fullstack%20Deployment-000000.svg?style=flat&logo=vercel)](https://vercel.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Continuity Guardian** is an enterprise-grade agentic cinema workflow platform engineered with **Google Gemini 3.5**, the **Google Agent Development Kit (ADK)**, **Google Cloud Firestore**, and **Parallel AI MCP**. 

Designed specifically for Hollywood screenwriters, script supervisors, showrunners, and studio executive producers, Continuity Guardian catches narrative contradictions, character timeline fractures, and real-world factual errors **before the cameras roll**.

---

## 🌟 Key Features

* **Autonomous Multi-Agent Supervision**: Deconstructs raw screenplay drafts into atomic factual statements and runs concurrent verification agents across canon and external reality.
* **Firestore Persistent Show Bible**: Centralized lore registry maintaining multi-season character traits, timelines, deceased personnel, and narrative milestones.
* **Parallel AI MCP Live Web Verification**: Verifies historical, medical, legal, and technological facts against live web knowledge.
* **Autonomous AI Script Doctor**: Automatically repairs flagged narrative contradictions and writes a polished revision preserving character voice, dramatic pacing, and screenplay formatting.
* **Publication-Grade PDF Export**: Generates executive continuity briefs and multi-page technical specification PDF reports.
* **Unified Vercel Ready**: Fullstack monorepo configured to deploy both Python FastAPI backend and glassmorphic Studio frontend simultaneously on Vercel.

---

## 🏗️ Multi-Agent Architecture

```
                               ┌──────────────────────────────────┐
                               │   Raw Episode Script / Draft     │
                               │  (Sluglines, Action, Dialogue)   │
                               └────────────────┬─────────────────┘
                                                │
                                                ▼
                               ┌──────────────────────────────────┐
                               │     FactExtractor Agent          │
                               │      (Google Gemini 3.5)         │
                               └───────┬──────────────────┬───────┘
                                       │                  │
                Internal Lore Claims   │                  │  Real-World Factual Claims
                                       ▼                  ▼
              ┌───────────────────────────┐    ┌──────────────────────────┐
              │    InternalChecker Agent  │    │  RealWorldChecker Agent  │
              │  (Firestore Show Bible)   │    │  (Parallel AI Search)    │
              └──────────────┬────────────┘    └──────────┬───────────────┘
                             │                            │
                             └────────────┬───────────────┘
                                          │  Concurrent Results
                                          ▼
                               ┌──────────────────────────────────┐
                               │       ReportBuilder Agent        │
                               │  (Synthesis, Confidence Ranking) │
                               └────────────────┬─────────────────┘
                                                │
                                                ▼
                               ┌──────────────────────────────────┐
                               │    Continuity Analysis Report    │
                               │  & AI Script Doctor Auto-Rewrite │
                               └──────────────────────────────────┘
```

---

## 🚀 Quick Start (Local Development)

### 1. Clone the repository
```bash
git clone https://github.com/SAIVENKATESH108/-Continuity-guardian.git
cd -Continuity-guardian
```

### 2. Set up Python virtual environment
```bash
python -m venv .venv
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On macOS / Linux:
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
Create a `.env` file based on `.env.example`:
```ini
GEMINI_API_KEY=your_gemini_api_key_here
PARALLEL_API_KEY=your_parallel_api_key_here
FIREBASE_PROJECT_ID=continuity-guardian-e4064
FIREBASE_CREDENTIALS_PATH=data/continuity-guardian-e4064-firebase-adminsdk-fbsvc-92cf7f3c1e.json
```

### 5. Run the servers
```bash
# Terminal 1 — Backend FastAPI server (port 8000)
uvicorn api.main:app --reload --port 8000

# Terminal 2 — Frontend client server (port 3000)
python -m http.server 3000 --directory frontend
```

* **Studio UI**: `http://localhost:3000` (or `http://localhost:8000`)
* **Interactive Swagger API Docs**: `http://localhost:8000/docs`
* **Interactive ReDoc**: `http://localhost:8000/redoc`

---

## ⚡ Deployment on Vercel

Continuity Guardian is configured with [vercel.json](./vercel.json) to deploy both the Python FastAPI backend and static frontend together on Vercel.

1. Push this repository to GitHub.
2. Go to [vercel.com/new](https://vercel.com/new) and import the repository.
3. Configure your **Environment Variables** in the Vercel project settings:
   * `GEMINI_API_KEY`: Your Gemini API key.
   * `PARALLEL_API_KEY`: Your Parallel AI search key.
   * `FIREBASE_PROJECT_ID`: Your Firebase project ID (optional, falls back to seed canon).
   * `FIREBASE_CREDENTIALS_JSON`: The raw JSON string of your Firebase service account (optional).
4. Click **Deploy**.

For Google Cloud Run and Hugging Face deployment alternatives, refer to [DEPLOY.md](./DEPLOY.md).

---

## 📚 Technical Documentation

A comprehensive, publication-grade 9-page system documentation PDF is generated at `docs/ContinuityGuardian_System_Documentation.pdf` and available directly through the web UI and at `/ContinuityGuardian_System_Documentation.pdf`.

---

## ⚖️ License

Distributed under the MIT License. See `LICENSE` for more information.
