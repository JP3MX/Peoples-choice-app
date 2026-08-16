# Squawk King IA — Product Requirements Document

## Original Problem Statement
Build Squawk King IA as a full-stack hybrid aircraft maintenance troubleshooting agent with chat as the primary front end, connected to approved maintenance manuals, a reference corpus of historical maintenance records and troubleshooting cases, maintenance records, manual uploads, ATA citations, relevant history, and logbook tools. Initial coverage: Cessna 152/172/182; Piper PA-28/PA-34/PA-44; Lycoming IO-360/IO-320/O-360/O-320; Rotax 912-series. Mechanic-first responses: most-likely cause first (one sentence), up to two clarifying questions only when needed, numbered troubleshooting steps with expected results, decision points, and next likely cause. Aircraft-specific guidance only from current approved sources (AMM, service manuals, ICA, wiring diagrams, TCDS, ADs, mfr troubleshooting), each instruction citing document name + ATA chapter-section-subject; current source controlling, superseded shown as historical. Preliminary reasoning allowed before applicability confirmed; no aircraft-specific steps until make/model/year/serial/config + approved references confirmed; if approved data unavailable, output exactly: "Approved maintenance data required. Please provide or upload the applicable manual before continuing."

## User Choices
- Model: OpenAI GPT-5.4 (Emergent LLM universal key)
- Manuals: PDF upload + server-side text extraction (pypdf) + citations
- Auth: JWT email/password
- Corpus: seeded with sample piston-aircraft records
- Scope: full MVP (chat + manual upload + ATA citations + logbook)

## Architecture
- Backend: FastAPI (`/app/backend/server.py`), MongoDB (motor), pypdf extraction, Emergent Object Storage for PDFs, emergentintegrations LlmChat (gpt-5.4) with SSE streaming.
- Frontend: React (CRA/craco), Tailwind, dark "Swiss Brutalist / tactical" theme (Chivo + IBM Plex Sans/Mono), 3-pane layout (Sidebar | Chat | Workbench). Auth via localStorage `sk_token` Bearer.
- Collections: users, aircraft, manuals (with extracted `pages`), corpus, logbook, sessions, messages.

## User Personas
- A&P mechanics / maintenance techs troubleshooting piston training aircraft.

## Core Requirements (static)
- Chat-primary mechanic-first responses with strict format.
- Historical corpus used ONLY for symptom matching/prioritization (never cited as authority).
- Aircraft-specific guidance only from approved sources with document + ATA citations; superseded shown as historical.
- Applicability gating + exact STOP message when approved data unavailable.

## Implemented (2026-08-16)
- JWT auth (register/login/me); demo admin seeded (mechanic@squawkking.io / squawk123).
- Aircraft profiles CRUD + confirm-applicability gating (make/model/year/serial/config).
- PDF manual upload → object storage + pypdf text extraction; doc type, ATA, current/superseded status; view + soft-delete; ownership-scoped download.
- Historical corpus (12 seeded records) with keyword+aircraft scoring; searchable History tab.
- Logbook entries CRUD per aircraft.
- Chat sessions + messages; SSE streaming GPT-5.4 with system prompt enforcing mechanic-first format, approved-data rule, citations, and exact STOP message.
- Retrieval: relevant manual excerpts + corpus matches injected into prompt; citations + matched-history surfaced in UI.
- Verified: 100% backend (11/11) and all critical frontend flows (testing agent iteration_1).

## Backlog (prioritized)
- P1: In-app PDF viewer panel in Workbench (currently opens in new tab).
- P1: Highlight/deep-link cited manual page from a chat citation chip.
- P2: Export a troubleshooting session to a logbook entry in one click.
- P2: Signed short-lived download URLs instead of query-param token.
- P2: AD/TCDS applicability checker by serial number range.

## Next Tasks
- Gather user feedback on chat quality and citation formatting.
- Add per-aircraft manual applicability filters to retrieval.
