# SupportIQ

**Drop-in AI support for any website.** Upload your docs, paste a script tag, and your customers get instant answers powered by RAG — no training required.

[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)

---

## The problem

Most AI chatbot tools either cost a fortune, lock you into their cloud, or take weeks to set up. Small teams end up choosing between expensive SaaS or building from scratch.

## What SupportIQ does

SupportIQ is a self-hosted AI support platform you can deploy on a single $20/mo VPS. It gives you:

- **A chat widget** you embed on your site with one script tag
- **RAG-powered answers** from your own docs, PDFs, URLs, and files
- **Multi-agent support** — spin up separate agents for different products or teams
- **Live session monitoring** with human takeover when the AI needs help
- **Any LLM provider** — OpenAI, Anthropic, Gemini, DeepSeek, and more

No GPU needed. All inference happens via external APIs.

## Quick start

### One-command deploy (Ubuntu/Debian)

```bash
curl -fsSL https://raw.githubusercontent.com/kvksatish/supportiq/main/install-deploy.sh | sudo sh
```

Or if you've cloned the repo:

```bash
sudo sh install-deploy.sh
```

This spins up everything — backend, frontend, vector DB, Redis, nginx. First user to register becomes the super admin.

### Docker Compose (dev)

```bash
cp .env.example .env
# Add your LLM API keys to .env
docker compose --profile dev up -d
```

- Dashboard: `http://localhost:3000`
- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

### Run locally (no Docker)

```bash
# Backend
cd backend && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt && python3 main.py

# Frontend (separate terminal)
cd frontend-nextjs && npm install && npm run dev

# Widget (separate terminal)
cd widget && npm install && npm run dev
```

## How it works

1. **Create an agent** in the dashboard — pick your LLM provider, set a system prompt
2. **Feed it knowledge** — upload PDFs/DOCX/CSVs, or point it at URLs to crawl
3. **Embed the widget** — copy the script tag into your site's HTML
4. Visitors ask questions, SupportIQ retrieves relevant chunks from your knowledge base, and streams back answers in real-time via SSE

Under the hood: documents get chunked and embedded (via Jina or SiliconFlow), stored in Qdrant with per-tenant isolation, and retrieved at query time with cosine similarity search.

## Architecture

```
widget (JS)  -->  FastAPI backend  -->  LLM provider (OpenAI/Anthropic/etc.)
                      |
                  Qdrant (vectors)
                  SQLite (app data)
                  Redis (rate limiting)
                  Scrapling service (web crawling)
```

Three services, one Docker Compose:
- `backend/` — FastAPI. Auth, chat, RAG pipeline, scheduling, all the business logic
- `frontend-nextjs/` — Next.js 14 admin dashboard
- `widget/` — Zero-dependency TypeScript chat widget, compiled to a single JS file

Plus infrastructure: Qdrant for vectors, Redis for rate limiting, nginx for reverse proxy, and an isolated scrapling microservice for safe web content extraction.

## What's in the box

| Feature | Details |
|---------|---------|
| Multi-provider LLM | OpenAI, Anthropic, Gemini, DeepSeek, xAI, OpenRouter, + more |
| RAG pipeline | Chunk, embed, store, retrieve — works with PDF, DOCX, XLSX, TXT, CSV, MD, URLs |
| Embeddable widget | One script tag. Cross-origin. Session persistence. Auto-translates to visitor's locale |
| Live sessions | Monitor conversations in real-time, take over from AI when needed |
| Multi-agent | Each agent gets its own knowledge base, LLM config, and widget appearance |
| Domain whitelist | Control which sites can embed your widget |
| i18n | English and Chinese out of the box |
| Auth | JWT with role-based access — super admin, admin, and support operator roles |
| Self-hosted | Deploy on your own infra. Your data stays yours |

## Project structure

```
backend/              FastAPI app — models, services, API, migrations
frontend-nextjs/      Next.js admin dashboard
widget/               Embeddable chat widget (TypeScript + esbuild)
scrapling-service/    Isolated web scraping microservice
nginx/                Reverse proxy config
docker-compose.yml    Dev and prod orchestration
```

## System requirements

Runs on anything that runs Docker. No GPU needed.

| | Minimum | Recommended |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB | 50 GB |

## Development

```bash
# Frontend
cd frontend-nextjs
npm run dev          # dev server
npm run test         # vitest
npm run lint         # eslint
npm run typecheck    # tsc

# Widget
cd widget
npm run dev          # dev server + example page
npm run build        # typecheck + dev + prod bundles
npm run test         # vitest

# Backend
cd backend
python3 -m pytest    # test suite

# E2E
npm run test:e2e     # playwright
```

## Contributing

We're building this in the open. If you're interested in contributing, open an issue first so we can discuss the approach before you spend time on a PR.

## License

MIT
