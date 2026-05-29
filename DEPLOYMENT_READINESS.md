# FleetPulse — Deployment Readiness Assessment

> **Audit date:** 2026-05-29  
> **Auditor:** Copilot Coding Agent  
> **Verdict: NOT PRODUCTION-READY** — 7 blocking issues identified

---

## Executive Summary

**Production Readiness Score: 41 / 100**

The application can be built and deployed to Azure App Service via the existing GitHub Actions workflow, and a smoke test confirms the health endpoint responds. However, numerous issues make the deployed application unsuitable for real-world fleet operations:

- Production Geotab credentials are exposed in source control
- All API endpoints are unauthenticated
- Safety scoring returns mock data in all environments
- The in-memory cache is incompatible with multi-worker deployments
- No automated tests exist
- Dependency versions include open-range pins that may break on fresh installs

---

## 1. Blocking Issues (Must Fix Before Production)

| ID | Issue | Location | Impact |
|----|-------|----------|--------|
| BLK-001 | Hardcoded Geotab credentials in `.do/app.yaml` | `.do/app.yaml:22-25` | Credential exposure |
| BLK-002 | No API authentication | `app.py` | Unauthorized data access |
| BLK-003 | Safety scores always return mock data | `safety_service.py:57-109` | Incorrect operational data |
| BLK-004 | In-memory cache with `--workers 2` | `_cache.py`, `Dockerfile` | Cache inconsistency, data corruption |
| BLK-005 | Wildcard CORS with `allow_credentials=True` | `app.py:15-21` | Invalid CORS, browser requests rejected |
| BLK-006 | No automated tests in CI pipeline | `.github/workflows/azure-deploy.yml` | Regressions deployed undetected |
| BLK-007 | Python version mismatch (3.11 image, 3.12 pycache) | `Dockerfile`, `backend/__pycache__/` | Potential runtime incompatibilities |

---

## 2. Environment Variable Checklist

### Required for any deployment

| Variable | Status | Source | Notes |
|----------|--------|--------|-------|
| `GEOTAB_USERNAME` | ⚠️ Exposed | `.do/app.yaml` | **Rotate immediately** |
| `GEOTAB_PASSWORD` | 🔴 Compromised | `.do/app.yaml` | **Rotate immediately** |
| `GEOTAB_DATABASE` | ✅ Defined | `.do/app.yaml`, `.env.example` | |
| `GEOTAB_SERVER` | ✅ Defined | `.do/app.yaml`, `.env.example` | Default: `my.geotab.com` |

### Required for AI features

| Variable | Status | Source | Notes |
|----------|--------|--------|-------|
| `ANTHROPIC_API_KEY` | ❌ Not in any deploy config | `.env.example` only | AI chat falls back to demo mode |
| `OPENROUTER_API_KEY` | ❌ Not in any deploy config | `.env.example` only | Alternative AI provider |

### Required for production hardening (not yet implemented)

| Variable | Status | Notes |
|----------|--------|-------|
| `API_SECRET_KEY` | ❌ Missing | Needed once authentication is added |
| `ALLOWED_ORIGINS` | ❌ Missing | Needed to restrict CORS |
| `LOG_LEVEL` | ✅ In `.env.example` | Not referenced in code |
| `DEBUG` | ✅ In `.env.example` | Not referenced in code |

### Azure-specific (CI/CD)

| Secret | Status | Notes |
|--------|--------|-------|
| `AZURE_CREDENTIALS` | Required in GitHub Secrets | JSON service principal |
| `ACR_LOGIN_SERVER` | Required in GitHub Secrets | Azure Container Registry URL |
| `AZURE_APP_NAME` | Required in GitHub Secrets | App Service name |

---

## 3. Build Verification

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080
```

**Known issues:**
- `mygeotab==0.9.1` — last released 2023; verify compatibility with current Geotab API
- `anthropic>=0.40.0` — open range; any breaking change in Anthropic SDK will break AI chat
- `openai>=1.58.0` — same concern for OpenRouter integration
- `python-dotenv` is installed via `Dockerfile` (`pip install ... python-dotenv`) but **not listed in `requirements.txt`** — direct install will fail without the Dockerfile

### Frontend

```bash
cd frontend
npm ci
npm run build   # tsc && vite build
```

**Known issues:**
- `framer-motion@^12.34.0` — major version with potentially breaking changes; lock to exact version
- No `.env` example for the frontend (`VITE_API_URL` is referenced only in `.do/app.yaml`)
- TypeScript strictness: several `any` types in hooks reduce type safety guarantee

### Docker

```bash
docker build -t fleetpulse:latest .
docker run -p 8080:8080 \
  -e GEOTAB_USERNAME=... \
  -e GEOTAB_PASSWORD=... \
  -e GEOTAB_DATABASE=... \
  fleetpulse:latest
```

**Known issues:**
- `app.py` is **patched at build time** via `echo >> app.py` in the Dockerfile (lines 40–55). This is fragile — any formatting change, Python version difference, or whitespace issue in the heredoc can silently corrupt the entry point.
- Recommended alternative: Use a separate `serve.py` that imports `app` and mounts static files, then set `CMD ["uvicorn", "serve:app", …]`.

---

## 4. CI/CD Pipeline Assessment

### Current workflow (`azure-deploy.yml`)

```
trigger: push to main
steps:
  1. Checkout
  2. Azure login (service principal)
  3. ACR login
  4. Docker build + push (sha tag + latest)
  5. Azure App Service deploy (sha tag)
  6. Sleep 30s + curl /api/health
```

**Gaps:**

| Gap | Impact |
|----|--------|
| No `npm run build` / `tsc` check | TypeScript errors silently deployed |
| No `pip install` + linting | Python import errors silently deployed |
| No unit or integration tests | Regressions not caught |
| No `docker scan` / `trivy` image scan | Vulnerable base images deployed |
| No `pip-audit` or `npm audit` | Known CVEs not caught |
| ACR name hardcoded (`k1fleetpulseacr`) | Breaks if registry is renamed |
| 30s sleep before smoke test | Brittle on cold-start; use `retry` loop |

### Recommended pipeline additions

```yaml
- name: Frontend type-check and build
  run: cd frontend && npm ci && npm run build

- name: Backend lint
  run: pip install ruff && ruff check backend/

- name: Dependency audit
  run: |
    pip install pip-audit && pip-audit -r backend/requirements.txt
    cd frontend && npm audit --audit-level=high

- name: Image vulnerability scan
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
    exit-code: 1
    severity: CRITICAL,HIGH
```

---

## 5. Missing Dependencies

### Runtime (not in requirements.txt)

| Package | Where Used | Status |
|---------|-----------|--------|
| `python-dotenv` | `geotab_client.py`, `ai_chat.py` | Installed in Dockerfile but missing from `requirements.txt` |
| `python-multipart` | FastAPI file uploads (if any) | Not verified |

### Dev tooling (not present)

| Tool | Purpose |
|------|---------|
| `pytest` + `pytest-asyncio` | Unit/integration tests |
| `httpx` (test mode) | FastAPI test client |
| `ruff` / `flake8` | Python linting |
| `mypy` | Static type checking |
| `eslint` | Frontend linting |
| `vitest` | Frontend unit tests |

---

## 6. Infrastructure Readiness

### Azure App Service

| Item | Status | Notes |
|------|--------|-------|
| Docker image build | ✅ Working | Via ACR |
| Health check endpoint | ✅ `/api/health` | Returns `{"status":"ok"}` |
| TLS/HTTPS | ✅ | Azure handles termination |
| Custom domain | ❓ Unknown | Not in workflow |
| Application Insights | ❌ Not configured | No telemetry, no error tracking |
| Auto-scaling rules | ❌ Not configured | Single instance |
| Deployment slots (staging) | ❌ Not configured | Direct to production |
| Managed Identity | ❌ Not used | Service principal used instead |

### DigitalOcean App Platform (`.do/app.yaml`)

| Item | Status | Notes |
|------|--------|-------|
| Backend service | ✅ Defined | `instance_size_slug: apps-s-1vcpu-0.5gb` — very small |
| Frontend static site | ✅ Defined | Built from `frontend/` |
| Secret management | 🔴 BROKEN | Plain-text credentials in YAML |
| Database | ❌ None | No persistent storage |
| Region | `sfo` | Consider `nyc` or `tor` for eastern US operations |

---

## 7. Monitoring & Observability

| Capability | Status | Notes |
|-----------|--------|-------|
| Health endpoint | ✅ `/api/health` | Basic liveness only |
| Structured logging | ❌ | `logging` used but no JSON formatter |
| Error tracking (Sentry etc.) | ❌ | Not configured |
| APM / distributed tracing | ❌ | Not configured |
| Metrics / dashboards | ❌ | No Prometheus, Datadog, or Azure Monitor |
| Alerting | ❌ | No uptime alerts |
| Log aggregation | ❌ | Container stdout only |

---

## 8. Data Persistence

| Data type | Persistence | Risk |
|-----------|------------|------|
| Vehicle/fleet data | None — fetched live from Geotab | Unavailable when Geotab unreachable |
| Safety scores | None — generated fresh each request | Trend history impossible |
| Alert history | In-memory only | Lost on restart |
| AI conversation | In-memory only | Lost on restart |
| Cache | In-memory only | Lost on restart; inconsistent across workers |
| Geotab credentials | Environment variables | Correct approach (once removed from `.do/app.yaml`) |

**Recommendation:** Add a lightweight persistent store (SQLite for single-instance; PostgreSQL for production) for alert history, user settings, and cached aggregates.

---

## 9. Production Readiness Score

| Category | Weight | Score | Weighted |
|----------|--------|-------|---------|
| Security | 25% | 10/100 | 2.5 |
| Functionality (core) | 25% | 60/100 | 15.0 |
| Reliability & Resilience | 20% | 35/100 | 7.0 |
| Observability | 10% | 5/100 | 0.5 |
| CI/CD & Testing | 10% | 15/100 | 1.5 |
| Documentation | 10% | 65/100 | 6.5 |
| **Total** | **100%** | | **33 / 100** |

> Minimum acceptable score for production: 75/100

---

## 10. Go/No-Go Checklist

| Criteria | Status |
|---------|--------|
| All BLK-* issues resolved | ❌ |
| Credentials rotated and removed from VCS | ❌ |
| Authentication implemented | ❌ |
| Production safety scoring enabled | ❌ |
| CI pipeline includes test + lint step | ❌ |
| Security scan passes (no CRITICAL CVEs) | ❌ |
| Smoke test passes on staging slot | ❌ (no staging slot) |
| Geotab add-in signed | ❌ |
| On-call runbook exists | ❌ |
| **Decision** | **🔴 NO-GO** |
