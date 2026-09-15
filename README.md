# SOWv2 — AI-Powered Statement of Work Generator

An intelligent document generation platform that uses multi-agent AI (AWS Bedrock + LangGraph) to automatically produce Statements of Work (SOW) and Proof-of-Concept (POC) documents from company research, templates, and uploaded reference materials.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [Running the App](#running-the-app)
- [Features](#features)
- [API Overview](#api-overview)
- [Security Notes](#security-notes)

---

## Overview

SOWv2 automates the creation of professional SOW and POC documents by:

1. Researching a target company via web scraping and RAG
2. Running a multi-agent LangGraph pipeline (company research, objectives, rules engine, POC writing)
3. Generating polished `.docx` / `.pdf` output using branded templates
4. Storing documents in AWS S3 and optionally syncing to Google Drive
5. Tracking accounts and document history in AWS DynamoDB

---

## Architecture

```
┌─────────────────────┐        ┌──────────────────────────────────────────┐
│   React Frontend    │ ──────▶│            Flask Backend                 │
│  (TypeScript + MUI) │  HTTP  │                                          │
└─────────────────────┘        │  ┌─────────────┐   ┌──────────────────┐ │
                                │  │  LangGraph  │   │   RAG Pipeline   │ │
                                │  │  Agents     │   │  (Bedrock + S3)  │ │
                                │  └──────┬──────┘   └──────────────────┘ │
                                │         │                                │
                                │  ┌──────▼──────┐   ┌──────────────────┐ │
                                │  │ AWS Bedrock │   │    DynamoDB      │ │
                                │  │ multi-model │   │  (accounts/docs) │ │
                                │  └─────────────┘   └──────────────────┘ │
                                │                                          │
                                │  ┌─────────────┐   ┌──────────────────┐ │
                                │  │  python-docx│   │   Google Drive   │ │
                                │  │  reportlab  │   │   / AWS S3       │ │
                                │  └─────────────┘   └──────────────────┘ │
                                └──────────────────────────────────────────┘
```

---

## Tech Stack

### Frontend
| Tool | Version |
|------|---------|
| React | 19 |
| TypeScript | 4.9 |
| Material UI (MUI) | v7 |
| React Router | v7 |
| react-toastify | latest |
| Build tool | Create React App (Webpack) |

### Backend
| Tool | Version |
|------|---------|
| Python | 3.12 |
| Flask | 3.x |
| LangGraph | 0.2.x |
| LangChain | 0.3.x |
| boto3 (AWS SDK) | 1.35.x |
| pydantic | v2 |
| python-docx | latest |
| reportlab | latest |
| pypdf | latest |
| beautifulsoup4 | latest |

### Cloud & Infrastructure
| Service | Purpose |
|---------|---------|
| AWS Bedrock | Multi-model LLM inference (Nova + Claude Sonnet 4) |
| AWS DynamoDB | Account and document metadata storage |
| AWS S3 | Document file storage |
| Google Drive API | Optional document sync |

---

## Project Structure

```
SOWv2/
├── backend/
│   ├── app/
│   │   ├── agents/          # LangGraph agent nodes (research, objectives, POC writer, rules)
│   │   ├── api/             # REST API handlers (accounts, history)
│   │   ├── core/            # Flask server, LangGraph graph, state, streaming
│   │   ├── db/              # DynamoDB handler
│   │   ├── document/        # Document reading and building (docx/pdf)
│   │   ├── preview/         # Async document preview generation
│   │   ├── rag/             # RAG ingestion and retrieval
│   │   ├── storage/         # S3 and Google Drive upload
│   │   └── utils/           # Health checks, helpers
│   ├── assets/              # Logo and font files for document branding
│   ├── config/
│   │   ├── .env             # AWS credentials (DO NOT COMMIT)
│   │   ├── credentials.json # Google OAuth client (DO NOT COMMIT)
│   │   ├── token.pickle     # Google OAuth token (DO NOT COMMIT)
│   │   └── requirements_clean.txt
│   ├── scripts/             # DynamoDB table setup script
│   ├── templates/           # POC rules and document templates (JSON/Markdown)
│   └── venv/                # Python virtual environment (not committed)
│
├── frontend/
│   ├── public/              # Static assets
│   ├── src/
│   │   ├── components/      # React page components (Dashboard, SOWForm, Accounts, etc.)
│   │   ├── config/          # API base URL config
│   │   ├── contexts/        # Auth context
│   │   ├── services/        # API service layer
│   │   └── styles/          # Global CSS theme
│   ├── .env                 # REACT_APP_API_URL
│   ├── package.json
│   └── tsconfig.json
│
├── shared/
│   ├── uploads/             # User-uploaded source documents (runtime, not committed)
│   └── output/              # Generated SOW/POC output files (runtime, not committed)
│
├── .gitignore
└── README.md
```

---

## Prerequisites

- **Node.js** >= 18 and **npm** >= 9
- **Python** >= 3.11
- **AWS account** with:
  - Bedrock access enabled for the configured Nova and Claude Sonnet 4 inference profiles
  - Permission to use DynamoDB and S3
- **Google Cloud project** with Drive API enabled (optional, for Drive sync)

---

## Setup & Installation

### 1. Clone the repository

```bash
git clone <repo-url>
cd SOWv2
```

### 2. Backend setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r config/requirements_clean.txt
```

### 3. Frontend setup

```bash
cd frontend
npm install
```

### 3a. AWS Pricing Calculator setup

The calculator adapter is vendored under `tools/aws-pricing-calculator` from
AWS's MIT-0 sample. It uses the public AWS Pricing Calculator APIs; it does not
deploy infrastructure or require AWS credentials. Install its pinned Node
dependencies and the local Chromium worker once:

```powershell
powershell -ExecutionPolicy Bypass -File tools/aws-pricing-calculator/setup.ps1
```

This is intentionally separate from Python `requirements_clean.txt`: pip cannot
install Node packages or a Chromium binary. The generated calculator URL works
without Chromium; Chromium is only used to read the rendered monthly total back
into the preview. If that read fails, the SOW keeps the validated calculator URL
and reports that the total must be opened in AWS Pricing Calculator.

Pricing is evidence-gated. Services, usage values, environments, and region must
come from the uploaded documents/additional details or an explicit region choice.
Missing rate-driving inputs are left as confirmation items—no default capacity or
cost is invented. A preview can be recalculated after correcting those inputs.

### 4. AWS storage setup (once per AWS account)

Configure `backend/config/.env` first, including a globally unique S3 bucket
name, and then run:

```bash
cd backend
python scripts/setup_dynamodb_table.py
```

---

## Configuration

### Backend — `backend/config/.env`

Create this file (never commit it):

```env
AWS_REGION=us-east-1
BEDROCK_REGION=us-east-1
BEDROCK_MODEL_ID=arn:aws:bedrock:us-east-1:106611079163:application-inference-profile/20kstbja9ona
BEDROCK_FAST_MODEL_ID=arn:aws:bedrock:us-east-1:106611079163:application-inference-profile/20kstbja9ona
BEDROCK_ANALYSIS_MODEL_ID=arn:aws:bedrock:us-east-1:106611079163:application-inference-profile/20kstbja9ona
BEDROCK_WRITER_MODEL_ID=arn:aws:bedrock:us-east-1:106611079163:application-inference-profile/20kstbja9ona
BEDROCK_DIAGRAM_MODEL_ID=arn:aws:bedrock:us-east-1:106611079163:application-inference-profile/20kstbja9ona
BEDROCK_EDITOR_MODEL_ID=arn:aws:bedrock:us-east-1:106611079163:application-inference-profile/20kstbja9ona
BEDROCK_FALLBACK_MODEL_ID=arn:aws:bedrock:us-east-1:106611079163:application-inference-profile/20kstbja9ona
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
# AWS_SESSION_TOKEN=your_session_token  # only if using temporary credentials

# Resource names can differ between AWS accounts/environments.
DYNAMODB_TABLE_ACCOUNTS=agentic-sow-v2
DYNAMODB_TABLE_POC_DOCUMENTS=agentic-poc
DYNAMODB_TABLE_RAG_SCHEMA=rag-schema
DYNAMODB_TABLE_RBAC=agentic-sow-rbac
S3_BUCKET_NAME=your-globally-unique-sow-bucket

# Use a long random value outside local development.
AUTH_TOKEN_SECRET=replace-with-a-long-random-secret
# Email verification links are valid for 24 hours by default. AUTH_FROM_EMAIL
# must be a verified Amazon SES identity in the configured AWS region.
AUTH_VERIFICATION_TTL_SECONDS=86400
# Password reset links are single-use and valid for one hour by default.
AUTH_PASSWORD_RESET_TTL_SECONDS=3600
AUTH_FROM_EMAIL=no-reply@shellkode.ai
FRONTEND_URL=https://your-sow-portal.example.com
# Disable the built-in test-login fallback after testing.
ENABLE_SAMPLE_USERS=true

# Organisation-required resource creation tags (defaults shown).
RESOURCE_TAG_CUSTOMER=shellkode
RESOURCE_TAG_CREATED_BY=arnaav.a@shellkode.com

# Optional: point generated edit links at a self-hosted draw.io instance.
DRAWIO_EDITOR_URL=https://app.diagrams.net
```

Every Bedrock task is routed through the approved Claude Sonnet application inference
profile. That profile must retain the tags `createdby=arnaav.a@shellkode.com` and
`customer=agentic-sow-inference`. Source documents are analysed in
overlapping chunks and merged; each writer call receives the structured baseline plus
section-relevant source evidence instead of a lossy fixed prefix.

Changing accounts only requires changing these values and running the AWS
storage setup command in the target account. If the default table names are
acceptable, only the credentials, region, and S3 bucket name need to change.

The setup command creates the RBAC table, seeds the existing admin, BU, and
individual-user test accounts, and stores the administrator-managed SOW section catalogue. All seeded
users initially use `Shellkode@123`; disable sample-user fallback and replace
these credentials before deployment. Existing DynamoDB tables do not need a
key-schema change: DynamoDB profile records now also store `employee_id`, `roles`,
`business_units`, and verification state, while legacy profiles are read compatibly. Assign old
records with the dry-run-first `backend/scripts/backfill_business_units.py`
utility if BU users need to access them.

Self-signup requires conditional `dynamodb:PutItem`/`DeleteItem` access on the
RBAC table and `ses:SendEmail` in the configured AWS region. Verify `AUTH_FROM_EMAIL` (or its
domain) in Amazon SES and move SES out of sandbox, or verify every recipient,
before production signup and password-reset emails can be delivered.

### Frontend — `frontend/.env`

```env
REACT_APP_API_URL=http://localhost:9000
REACT_APP_ENV=development
# Optional: self-hosted draw.io embed endpoint.
REACT_APP_DRAWIO_EMBED_URL=https://embed.diagrams.net
```

When Architecture Diagram is selected, the backend makes one additional
Bedrock call to create a small validated diagram model. It deterministically
renders the image and draw.io XML; if that call or rendering fails, SOW content
generation and finalisation continue without a diagram. The default editor
requires internet access. Set both draw.io variables when using a self-hosted
instance.

### Google Drive (optional)

Place your `credentials.json` (OAuth2 client) in `backend/config/`. On first run the app will prompt for OAuth consent and save `token.pickle`.

---

## Running the App

### Backend

```bash
cd backend
venv\Scripts\activate   # Windows
python app/core/server.py
# Server starts on http://localhost:5000
```

### Frontend

```bash
cd frontend
npm start
# App opens on http://localhost:3000
```

---

## Features

- **Company Research Agent** — scrapes and summarizes target company information
- **Objective Agent** — drafts project objectives tailored to the company
- **Rules Engine Agent** — applies configurable POC rules from `templates/poc_rules.json`
- **POC Writer Agent** — assembles the final document narrative
- **RAG Pipeline** — ingests uploaded reference documents and retrieves relevant context
- **Document Generation** — produces branded `.docx` and `.pdf` files using company assets
- **Preview System** — async preview generation with status monitoring
- **Account Management** — tracks clients and their document history via DynamoDB
- **Google Drive Sync** — optionally uploads generated documents to a Drive folder
- **S3 Storage** — stores all generated files in AWS S3

---

## API Overview

The Flask backend exposes REST endpoints at `http://localhost:5000`:

| Method | Path | Description |
|--------|------|-------------|
| POST | `/generate` | Trigger SOW/POC generation pipeline |
| GET | `/accounts` | List all accounts |
| GET | `/history` | Fetch document generation history |
| GET | `/preview/:id` | Get document preview status |
| GET | `/health` | Health check |

---

## Security Notes

- **Never commit** `backend/config/.env`, `credentials.json`, or `token.pickle` — all three are listed in `.gitignore`
- Rotate AWS credentials immediately if they have ever been committed to a public or shared repository
- Use IAM roles with least-privilege for production deployments instead of static access keys
- The `shared/uploads/` and `shared/output/` directories contain user data and generated documents — they are excluded from git
