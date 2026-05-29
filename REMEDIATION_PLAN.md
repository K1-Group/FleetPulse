# FleetPulse — 30-Day Remediation Plan

> **Issued:** 2026-05-29  
> **Based on:** ARCHITECTURE_AUDIT.md · SECURITY_AUDIT.md · DEPLOYMENT_READINESS.md

---

## Executive Summary

This plan converts FleetPulse from a demo-grade prototype into a production-ready fleet intelligence platform over 30 days organized into three weekly sprints. The first sprint is entirely security- and stability-focused; subsequent sprints address reliability, quality, and feature completeness.

---

## Top 10 Risks

| # | Risk | Likelihood | Impact | Sprint |
|---|------|-----------|--------|--------|
| R1 | Geotab credentials (`e.aldrich@budgetlasvegas.com / Painkiller69!`) already exposed in Git history → unauthorized fleet access | High | Critical | Week 1 |
| R2 | Wildcard CORS + no auth → any internet caller can read/write fleet data | High | Critical | Week 1 |
| R3 | Safety scoring always returns mock data → fleet managers act on false information | High | High | Week 1 |
| R4 | In-memory cache incompatible with `--workers 2` → stale/inconsistent data served | Medium | High | Week 1 |
| R5 | Zero automated tests → undetected regressions ship on every push | High | High | Week 2 |
| R6 | AI API key accepted without auth → any caller can inject a key and incur costs | High | Medium | Week 1 |
| R7 | `mcp-server/venv/` in repo → stale CVE-laden packages, bloated clones | Medium | Medium | Week 1 |
| R8 | No observability → failures are invisible until a user reports them | Medium | High | Week 2 |
| R9 | `Dockerfile` patches `app.py` with `echo >>` → fragile build, silent corruption | Medium | Medium | Week 2 |
| R10 | DigitalOcean instance `apps-s-1vcpu-0.5gb` → OOM crash under real traffic | Low | High | Week 3 |

---

## Top 10 Quick Wins

| # | Action | Effort | Risk Reduced |
|---|--------|--------|-------------|
| QW1 | Rotate Geotab password and remove from `.do/app.yaml` | 30 min | R1 |
| QW2 | Add `mcp-server/venv/` and `**/__pycache__/` to `.gitignore` | 5 min | R7 |
| QW3 | Add `python-dotenv` to `backend/requirements.txt` | 2 min | Deployment reliability |
| QW4 | Fix CORS: replace `allow_origins=["*"]` with explicit origin list | 10 min | R2 |
| QW5 | Re-enable production safety scoring in `safety_service.py` | 15 min | R3 |
| QW6 | Add `pip-audit` and `npm audit` step to GitHub Actions | 20 min | Dependency CVEs |
| QW7 | Change uvicorn to `--workers 1` until Redis cache is in place | 5 min | R4 |
| QW8 | Add `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` headers | 30 min | XSS surface |
| QW9 | Add `ruff` linting step to CI | 15 min | Code quality gate |
| QW10 | Pin `anthropic` and `openai` to exact versions in `requirements.txt` | 10 min | Dependency breakage |

---

## Week 1 — Security & Stability (Days 1–7)

**Goal:** Stop the bleeding. Every item here is a blocker for any production use.

### Day 1 — Credential Incident Response

- [ ] **Immediately rotate** Geotab password for `e.aldrich@budgetlasvegas.com`
- [ ] Audit Geotab access logs for unauthorized access since first commit
- [ ] Remove credentials from `.do/app.yaml` — replace with DigitalOcean secret references:
  ```yaml
  - key: GEOTAB_PASSWORD
    value: ${geotab_password}
    type: SECRET
  ```
- [ ] Purge credentials from Git history:
  ```bash
  git filter-repo --replace-text <(echo 'Painkiller69!==>{REDACTED}')
  git filter-repo --replace-text <(echo 'e.aldrich@budgetlasvegas.com==>{REDACTED}')
  git push --force --all
  ```
- [ ] Force-push to all remote branches and notify all collaborators to re-clone

### Day 2 — API Authentication

- [ ] Add a `FLEETPULSE_API_KEY` environment variable
- [ ] Implement FastAPI dependency for bearer token validation:
  ```python
  # backend/auth.py
  from fastapi import Depends, HTTPException, status
  from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
  import os, secrets

  security = HTTPBearer(auto_error=False)
  _API_KEY = os.getenv("FLEETPULSE_API_KEY", "")

  def require_api_key(creds: HTTPAuthorizationCredentials | None = Depends(security)):
      if not _API_KEY:
          return  # auth disabled when key not set (dev mode)
      if not creds or not secrets.compare_digest(creds.credentials, _API_KEY):
          raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
  ```
- [ ] Add `dependencies=[Depends(require_api_key)]` to each router in `app.py`
- [ ] Exclude `/api/health` from auth requirement
- [ ] Update frontend `useGeotab.ts` to include `Authorization: ****** header
- [ ] Add `FLEETPULSE_API_KEY` to Azure App Service application settings and GitHub secrets

### Day 3 — CORS & Security Headers

- [ ] Fix CORS — replace wildcard with explicit origins:
  ```python
  allow_origins=[
      os.getenv("ALLOWED_ORIGIN", "http://localhost:5173"),
  ],
  allow_credentials=False,
  ```
- [ ] Add security headers middleware:
  ```python
  @app.middleware("http")
  async def security_headers(request, call_next):
      response = await call_next(request)
      response.headers["X-Content-Type-Options"] = "nosniff"
      response.headers["X-Frame-Options"] = "DENY"
      response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
      return response
  ```

### Day 4 — Fix Safety Scoring

- [ ] Remove mock-data block from `safety_service.py` (lines 57–109)
- [ ] Uncomment and activate the production Geotab ExceptionEvents path (lines 112–168)
- [ ] Test with real Geotab credentials in staging
- [ ] Verify the frontend `SafetyScorecard` component renders live data correctly

### Day 5 — Cache & Worker Stability

- [ ] Change `Dockerfile` CMD to `--workers 1` (prevents cache inconsistency):
  ```dockerfile
  CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
  ```
- [ ] Add thread lock to `GeotabClient.authenticate()`:
  ```python
  import threading
  _auth_lock = threading.Lock()
  
  def authenticate(self) -> mygeotab.API:
      with _auth_lock:
          if not self._needs_auth():
              return self._api
          # … existing auth code
  ```
- [ ] Add `python-dotenv` to `backend/requirements.txt`

### Day 6 — Clean Repository

- [ ] Add `mcp-server/venv/` to `.gitignore`
- [ ] Add `backend/__pycache__/` and `**/__pycache__/` to `.gitignore`
- [ ] Remove committed venv: `git rm -r --cached mcp-server/venv/`
- [ ] Pin all open-range Python dependencies to exact versions (`pip freeze > requirements.txt` in clean venv)
- [ ] Run `npm audit fix` in `frontend/` and commit updated `package-lock.json`

### Day 7 — AI Chat Security

- [ ] Add authentication requirement to `/api/ai/settings` endpoint
- [ ] Move AI provider selection to environment variables (not runtime HTTP endpoint for production)
- [ ] Stop returning full exception messages to clients in error responses — log server-side only

---

## Week 2 — Quality & Observability (Days 8–14)

**Goal:** Make the application trustworthy by adding tests, fixing the Dockerfile, and enabling monitoring.

### Day 8–9 — Fix Dockerfile Build Process

- [ ] Create `backend/serve.py` to replace the fragile `echo >>` patch:
  ```python
  # backend/serve.py
  from app import app
  from fastapi.staticfiles import StaticFiles
  from fastapi.responses import FileResponse
  import os
  
  _static = os.path.join(os.path.dirname(__file__), "static")
  if os.path.isdir(_static):
      app.mount("/assets", StaticFiles(directory=os.path.join(_static, "assets")), name="assets")
  
      @app.get("/{full_path:path}")
      async def spa(full_path: str):
          fp = os.path.join(_static, full_path)
          return FileResponse(fp) if os.path.isfile(fp) else FileResponse(os.path.join(_static, "index.html"))
  ```
- [ ] Update `Dockerfile` CMD: `CMD ["uvicorn", "serve:app", …]`
- [ ] Remove the heredoc `RUN echo '...' >> app.py` block from Dockerfile
- [ ] Verify `docker build` succeeds cleanly and SPA routing works

### Day 10–11 — Automated Tests

- [ ] Add `pytest`, `pytest-asyncio`, `httpx` to dev dependencies (separate `requirements-dev.txt`)
- [ ] Write smoke tests for each of the 15 routers (at minimum: assert HTTP 200 and response shape):
  ```python
  # backend/tests/test_health.py
  from httpx import AsyncClient, ASGITransport
  from app import app
  import pytest
  
  @pytest.mark.asyncio
  async def test_health():
      async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
          r = await c.get("/api/health")
      assert r.status_code == 200
      assert r.json()["status"] == "ok"
  ```
- [ ] Add `pytest` step to GitHub Actions before Docker build

### Day 12 — CI Pipeline Hardening

- [ ] Add frontend type-check step: `cd frontend && tsc --noEmit`
- [ ] Add `ruff check backend/` linting step
- [ ] Add `pip-audit -r backend/requirements.txt` step (fail on HIGH or CRITICAL)
- [ ] Add `npm audit --audit-level=high` step
- [ ] Replace `sleep 30` smoke test with retry loop (max 10 attempts, 10s apart)
- [ ] Add Trivy image vulnerability scan step

### Day 13–14 — Observability

- [ ] Add structured JSON logging:
  ```python
  import json, logging
  class JSONFormatter(logging.Formatter):
      def format(self, record):
          return json.dumps({"level": record.levelname, "msg": record.getMessage(), "logger": record.name})
  ```
- [ ] Configure Azure Application Insights or Sentry SDK:
  ```python
  # requirements.txt
  sentry-sdk[fastapi]>=2.0.0
  
  # app.py
  import sentry_sdk
  sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), traces_sample_rate=0.1)
  ```
- [ ] Add `/api/health/detailed` endpoint returning dependency status (Geotab reachable, OData reachable)
- [ ] Set up uptime monitoring (e.g., Azure Monitor alert on `api/health` HTTP 200)

---

## Week 3 — Reliability & Features (Days 15–21)

**Goal:** Move from single-instance fragility toward a resilient, scalable deployment.

### Day 15–16 — Replace In-Memory Cache with Redis

- [ ] Add `redis[asyncio]` to `requirements.txt`
- [ ] Create `backend/cache.py` with Redis-backed TTL cache:
  ```python
  import redis.asyncio as redis
  import os, json
  
  _redis = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
  
  async def get_cached(key: str) -> dict | None:
      val = await _redis.get(key)
      return json.loads(val) if val else None
  
  async def set_cached(key: str, value: dict, ttl: int = 300):
      await _redis.setex(key, ttl, json.dumps(value, default=str))
  ```
- [ ] Add Redis to Azure (Azure Cache for Redis Basic C0 — ~$16/month)
- [ ] Set `REDIS_URL` environment variable in App Service
- [ ] Revert `--workers 1` to `--workers 2` once Redis is in place
- [ ] Test cache consistency under concurrent requests

### Day 17–18 — Frontend Improvements

- [ ] Add ESLint + TypeScript strict config
- [ ] Replace `any` types in `useGeotab.ts` with proper interfaces
- [ ] Add React Router v6 for tab navigation (enables deep-linking, browser history)
- [ ] Add basic ARIA roles and keyboard navigation to tab nav and data tables
- [ ] Add `VITE_API_URL` env support for split frontend/backend deployment

### Day 19–20 — Fix Path Parameters and Validation

- [ ] Add `constr` validation to `vehicle_id` path parameters
- [ ] Add response schema validation tests
- [ ] Validate and sanitize the `period` query parameter in `reports.py` (`enum` validator)
- [ ] Add structured error responses — remove raw `str(e)` from all fallback responses

### Day 21 — Geotab Add-in Signing

- [ ] Generate signing keys via Geotab Developer tools
- [ ] Sign `addin/config.json` and update `isSigned: true` / `signature`
- [ ] Replace `supportEmail` with a team distribution list (not personal email)
- [ ] Test add-in installation in a Geotab sandbox database

---

## Week 4 — Production Hardening & Documentation (Days 22–30)

**Goal:** Complete the remaining gaps and document the operational runbook.

### Day 22–23 — Rate Limiting & Abuse Prevention

- [ ] Add `slowapi` rate limiting:
  ```python
  from slowapi import Limiter
  from slowapi.util import get_remote_address
  limiter = Limiter(key_func=get_remote_address)
  app.state.limiter = limiter
  ```
- [ ] Apply stricter limits to AI chat endpoint (`10/minute`) and OData endpoints (`60/minute`)

### Day 24–25 — Azure Deployment Improvements

- [ ] Add staging deployment slot to App Service
- [ ] Update CI workflow to deploy to staging first, then swap to production
- [ ] Add Managed Identity for ACR pull (replace long-lived service principal credentials where possible)
- [ ] Configure Application Insights alerting for error rate > 1% and p99 latency > 5s
- [ ] Add auto-scaling rule: scale out at CPU > 70% for 5 minutes

### Day 26–27 — Power BI Integration (if required)

- [ ] Determine if Power BI is a committed deliverable or a future roadmap item
- [ ] If required: embed Power BI report using Azure Active Directory embedded token
- [ ] Create `frontend/src/components/PowerBIReport.tsx` wrapper using `powerbi-client-react`
- [ ] Expose a `/api/powerbi/token` endpoint that generates an embed token (requires Azure AD app registration)

### Day 28–29 — Final Testing & Security Review

- [ ] Run `pip-audit` and `npm audit` — resolve all HIGH/CRITICAL findings
- [ ] Run OWASP ZAP or Burp Suite scan against staging environment
- [ ] Verify all BLK-* blocking issues from `DEPLOYMENT_READINESS.md` are resolved
- [ ] Load test with `locust` (simulate 50 concurrent users; verify no OOM or 5xx errors)
- [ ] Perform final smoke test on production after deploy

### Day 30 — Documentation & Runbook

- [ ] Write operations runbook: startup, shutdown, credential rotation, Geotab re-auth, cache flush
- [ ] Document all required environment variables with descriptions and examples
- [ ] Update README with accurate setup instructions for local dev, Docker, and Azure
- [ ] Archive demo/placeholder `.md` files (`COMPLETION_SUMMARY.md`, `QUICK_FIX_TABS.md`, `PROMPTS.md`) or move to `docs/`

---

## Resource & Cost Estimate (Monthly — Azure)

| Resource | SKU | Estimated Cost |
|----------|-----|---------------|
| App Service (Docker) | B2s (2 vCPU, 4 GB) | ~$60 |
| Azure Container Registry | Basic | ~$5 |
| Azure Cache for Redis | Basic C0 | ~$16 |
| Application Insights | Pay-as-you-go (5 GB free) | ~$0–$10 |
| Azure Monitor alerts | Basic | ~$0 |
| **Total** | | **~$81–$91/month** |

---

## KPI Targets (Post-Remediation)

| Metric | Current | Target (Day 30) |
|--------|---------|----------------|
| Production Readiness Score | 33/100 | ≥ 80/100 |
| Security Score | 28/100 | ≥ 75/100 |
| Test coverage | 0% | ≥ 60% |
| CI pipeline pass rate | N/A (no tests) | ≥ 95% |
| API error rate (prod) | Unknown | < 0.5% |
| p99 API latency | Unknown | < 2s |
| Authenticated endpoints | 0% | 100% |
| Blocking issues resolved | 0/7 | 7/7 |

---

## Owner & Priority Matrix

| Sprint | Focus | Owner | Priority |
|--------|-------|-------|---------|
| Week 1 | Security & stability | Backend dev + DevOps | 🔴 Critical |
| Week 2 | Quality & observability | Backend dev + Frontend dev | 🟠 High |
| Week 3 | Reliability & features | Full team | 🟡 Medium |
| Week 4 | Hardening & documentation | Full team | 🟢 Normal |
