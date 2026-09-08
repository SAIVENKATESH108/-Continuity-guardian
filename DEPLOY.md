# Continuity Guardian — Deployment Guide

This guide covers deploying both the **FastAPI Backend Agent** and the **Static Frontend** for production and hackathon demos at **$0 cost**.

---

## Architecture Overview

```
                        ┌─────────────────────────────────────────┐
                        │      Frontend (Vercel / GitHub Pages)   │
                        │        HTML / CSS / Vanilla JS          │
                        └────────────────────┬────────────────────┘
                                             │ HTTP (Fetch API)
                                             ▼
                        ┌─────────────────────────────────────────┐
                        │      Backend (Cloud Run / HF Spaces)    │
                        │       FastAPI + Google ADK Pipeline     │
                        └───────┬─────────────────┬───────────────┘
                                │                 │
               ┌────────────────┴──────┐   ┌──────┴───────────────┐
               ▼                       ▼   ▼                      ▼
        Google Gemini 3.5      Firestore Show Bible       Parallel AI MCP
      (Script Doctor & LLM)       (Database Canon)       (Web Fact Verifier)
```

---

## Backend Deployment

Choose **Option A** (Google Cloud Run — recommended for Google Hackathons) or **Option B** (Hugging Face Spaces — completely card-free).

---

### Option A: Google Cloud Run (Google Cloud Ecosystem)

Google Cloud Run offers a generous permanent free tier: **2 million requests/month**, 360,000 GB-seconds of memory, and 180,000 vCPU-seconds free every month.

> **Important Billing Card Notice:**
> Google Cloud requires adding a credit/debit card to verify your identity upon account creation. However, as long as your usage stays within the monthly free tier limits (which a hackathon demo comfortably will), you will be charged **$0.00**.

#### Step 1: Install & Authenticate `gcloud` CLI
```bash
# Login to your Google Cloud account
gcloud auth login

# Set your project ID
gcloud config set project continuity-guardian-e4064

# Enable required Google Cloud APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com
```

#### Step 2: Store API Keys Securely in Secret Manager
Never bake secrets into container images. Use Google Cloud Secret Manager:

```bash
# 1. Gemini API Key
echo -n "YOUR_GEMINI_API_KEY" | gcloud secrets create GEMINI_API_KEY \
  --data-file=- \
  --replication-policy="automatic"

# 2. Parallel AI Key
echo -n "YOUR_PARALLEL_API_KEY" | gcloud secrets create PARALLEL_API_KEY \
  --data-file=- \
  --replication-policy="automatic"

# 3. Firebase Service Account JSON
gcloud secrets create FIREBASE_SA_KEY \
  --data-file=data/continuity-guardian-e4064-firebase-adminsdk-fbsvc-92cf7f3c1e.json \
  --replication-policy="automatic"
```

#### Step 3: Build & Deploy Container to Cloud Run
Run this from the project root (`continuity-guardian/`):

```bash
gcloud run deploy continuity-guardian-api \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 2 \
  --memory 1Gi \
  --cpu 1 \
  --set-env-vars="FIREBASE_PROJECT_ID=continuity-guardian-e4064,FIREBASE_CREDENTIALS_PATH=/secrets/firebase-sa.json" \
  --set-secrets="GEMINI_API_KEY=GEMINI_API_KEY:latest,PARALLEL_API_KEY=PARALLEL_API_KEY:latest,/secrets/firebase-sa.json=FIREBASE_SA_KEY:latest"
```

Once deployment completes, Cloud Run outputs your live API URL:
```text
Service [continuity-guardian-api] revision has been deployed and is serving 100 percent of traffic.
Service URL: https://continuity-guardian-api-xyz-uc.a.run.app
```

---

### Option B: Hugging Face Spaces (100% Free — No Credit Card Needed)

If you prefer not to enter a credit card, Hugging Face Spaces provides free Docker hosting:

#### Step 1: Create a Space
1. Sign up / log in to [Hugging Face](https://huggingface.co/).
2. Click **New Space** (`https://huggingface.co/new-space`).
3. Set **Space Name**: `continuity-guardian-api`
4. Select **License**: `MIT`
5. Select **Space SDK**: Choose **Docker** -> **Blank**.
6. Set **Space hardware**: `CPU Basic · 2 vCPU · 16 GB · Free`.
7. Click **Create Space**.

#### Step 2: Configure Space Secrets
Go to **Settings** → **Variables and secrets** in your Space:
Create the following **New secret** entries:
* `GEMINI_API_KEY`: Your Google Gemini API key
* `PARALLEL_API_KEY`: Your Parallel AI API key
* `FIREBASE_PROJECT_ID`: `continuity-guardian-e4064`
* `FIREBASE_CREDENTIALS_PATH`: `data/continuity-guardian-e4064-firebase-adminsdk-fbsvc-92cf7f3c1e.json`

#### Step 3: Push Code to Space
Clone your Space repository and copy this project's files into it:
```bash
git clone https://huggingface.co/spaces/YOUR_USERNAME/continuity-guardian-api
cd continuity-guardian-api

# Copy files from continuity-guardian (including Dockerfile, requirements.txt, agent/, api/, data/)
git add .
git commit -m "Deploy Continuity Guardian API"
git push
```
Your Space will build the Docker container and be accessible at:
`https://YOUR_USERNAME-continuity-guardian-api.hf.space`

---

## Frontend Deployment

### Method 1: Unified Vercel Deployment (Frontend + Python Backend Together)

The repository includes a ready-to-deploy [vercel.json](file:///d:/Freshstart/Agentic-Cinema/continuity-guardian/vercel.json) that compiles both the FastAPI Python backend (`api/main.py`) via `@vercel/python` and serves the static studio frontend (`frontend/`) via `@vercel/static` in a single monorepo deployment!

#### 1. Import Project to Vercel
1. Go to [vercel.com/new](https://vercel.com/new) and click **Import** next to your GitHub repository `https://github.com/SAIVENKATESH108/-Continuity-guardian.git`.
2. Framework Preset: Leave as **Other** (Vercel automatically detects `vercel.json`).
3. Root Directory: `./` (root).

#### 2. Configure Environment Variables in Vercel
Under **Environment Variables**, add the following keys:

| Variable Name | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | **Yes** | Your Google Gemini API Key from Google AI Studio |
| `PARALLEL_API_KEY` | **Yes** | Your Parallel AI Search API Key for real-world web fact verification |
| `FIREBASE_PROJECT_ID` | Optional | `continuity-guardian-e4064` (or your GCP Project ID) |
| `FIREBASE_CREDENTIALS_JSON` | Optional | The raw JSON string of your Firebase service account key. If omitted, the app automatically falls back to local seed canon (`data/seed_episodes.json`). |

#### 3. Deploy
Click **Deploy**! Once completed, your entire application (Studio UI at `/`, REST API at `/check-episode`, `/show-bible`, `/rewrite-script`, and documentation at `/docs`) will be live at `https://your-project.vercel.app`.

---

### Method 2: GitHub Pages (100% Free)

1. Commit your changes and push to GitHub.
2. In `frontend/app.js`, ensure `API_BASE_URL` is set to your deployed backend URL.
3. In GitHub repo settings: **Settings** → **Pages** → **Source**:
   * Branch: `main`
   * Folder: `/docs` (or configure a simple GitHub Action to deploy `frontend/` to GitHub Pages).
4. Your site will be live at `https://YOUR_USERNAME.github.io/REPO_NAME`.

---

## Post-Deployment Checklist

- [ ] Visit `<BACKEND_URL>/health` — should return `{"status": "ok"}`.
- [ ] Visit `<BACKEND_URL>/docs` — should open the interactive Swagger UI.
- [ ] Open the deployed frontend URL, select the **Hero Contradictions** sample script, and click **Check continuity**.
- [ ] Click **"Auto-Fix & Rewrite Script"** to verify the Script Doctor Agent rewrite.
- [ ] Click **"Inspect Show Bible Canon"** to confirm the Show Bible modal displays characters and facts.
