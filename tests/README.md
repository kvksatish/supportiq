

```bash
cd backend
pytest
```


```bash
cd backend
pytest tests/test_api.py
```


```bash
cd backend
pytest tests/test_api.py::test_name
```


```bash
pytest -v                     # Verbose output
pytest -x                     # Stop on first failure
pytest --tb=short             # Compact traceback
pytest -k "pattern"           # Filter tests by name
pytest -v -x --tb=short       # Combined usage
```


| Layer | Location | Framework | Run Command |
|-------|----------|-----------|-------------|
| Backend unit tests | `backend/tests/unit/` | pytest | `cd backend && pytest tests/unit/` |
| Backend contract tests | `backend/tests/contracts/` | pytest | `cd backend && pytest tests/contracts/` |
| Backend integration tests | `backend/tests/integration/` | pytest | `cd backend && pytest tests/integration/` |
| Backend security/stress/robustness | `backend/tests/` root | pytest | `cd backend && pytest tests/test_*.py` |
| Frontend typecheck + tests | `frontend-nextjs/` | tsc + vitest | `npm run typecheck && npm run test` |
| Widget typecheck + tests | `widget/` | tsc + vitest | `npm run typecheck && npm run test` |
| E2E tests (root) | `tests/e2e/` | Playwright | `npm run test:e2e` |


Backend test configuration (`backend/pytest.ini` + `backend/tests/conftest.py`):

- Automatically sets `BASJOO_TEST_MODE=1`
- Each test uses an isolated SQLite database (`backend/.pytest_dbs/`)
- Monkeypatches Qdrant/Jina/LLM integrations; most API tests require no external services
- Redis/Qdrant hostnames auto-fallback between Docker container names and localhost
- Use `client` fixture for admin-authenticated requests, `public_client` fixture for unauthenticated/public route tests


E2E tests support two run modes:

| Mode | Target | Entry URL | Purpose |
|------|--------|-----------|---------|
| **smoke (default)** | Docker dev stack | `http://localhost:3000` | Quick functional verification |
| **prod-like** | Docker production stack | `http://localhost:80` (nginx) | Production-approximate testing |


```bash
npm run test:e2e
```



```bash
docker compose --profile prod up -d

curl http://localhost/health  # Should return 200

npm run test:e2e:prod
```

| Variable | smoke | prod-like |
|----------|-------|-----------|
| `E2E_ENV` | unset | `prod` |
| `API_BASE_URL` | `localhost:8000` | `localhost` (via nginx) |
| `BASE_URL` | `localhost:3000` | `localhost:80` |


```bash
npm run test:e2e:widget
HOST_ALLOWED_URL=http://allowed.local \
HOST_BLOCKED_URL=http://blocked.local \
npx playwright test --config=tests/e2e/playwright.config.ts --project=widget-cross-origin
```


Widget cross-origin tests require two host pages served from different origins.


Add the following entries to `/etc/hosts`:

```
127.0.0.1 allowed.local
127.0.0.1 blocked.local
```


```bash
docker compose --profile dev up -d allowed-host blocked-host
```

Or serve the host pages manually:

```bash
cd tests/environments/host-pages/allowed-host
python3 -m http.server 8080

cd tests/environments/host-pages/blocked-host
python3 -m http.server 8081
```


```bash
export HOST_ALLOWED_URL=http://allowed.local:8080
export HOST_BLOCKED_URL=http://blocked.local:8081
```


```bash
npm run test:e2e:widget
```


```bash
npm run test:e2e:all
npx playwright test --config=tests/e2e/playwright.config.ts
```


```
tests/
├── e2e/
│   ├── playwright.config.ts    # Playwright configuration
│   ├── global.setup.ts         # Global setup (create admin, seed data)
│   ├── fixtures/
│   │   ├── admin.fixture.ts    # Admin login helper
│   │   └── widget.fixture.ts   # Widget interaction helper
│   └── specs/
│       ├── admin-auth.spec.ts           # Admin authentication flow
│       ├── playground-streaming.spec.ts # Playground autosave + streaming chat
│       ├── knowledge-indexing.spec.ts   # KB import -> index -> retrieval
│       ├── sessions-takeover.spec.ts    # Sessions center + human takeover
│       └── widget-cross-origin.spec.ts  # Widget cross-origin embedding
├── environments/
│   ├── host-pages/
│   │   ├── allowed-host/       # Allowed embed host page
│   │   └── blocked-host/       # Blocked host page
│   └── stubs/
│       └── crawl-target/       # Test site for URL crawling
└── README.md
```


| Variable | Description | Default |
|----------|-------------|---------|
| `BASE_URL` | Admin dashboard URL | `http://localhost:3000` |
| `API_BASE_URL` | Backend API URL | `http://localhost:8000` |
| `ADMIN_EMAIL` | Test admin email | `test@example.com` |
| `ADMIN_PASSWORD` | Test admin password | `testpassword123` |
| `E2E_ENV` | Test environment (`dev`/`prod`) | `dev` |
| `HOST_ALLOWED_URL` | Allowed embed host page URL | - |
| `HOST_BLOCKED_URL` | Blocked host page URL | - |
| `CRAWL_TARGET_URL` | URL crawl test site | `http://host.docker.internal:8081` |
