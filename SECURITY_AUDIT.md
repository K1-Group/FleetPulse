# FleetPulse — Security Audit

> **Audit date:** 2026-05-29  
> **Auditor:** Copilot Coding Agent  
> **Severity scale:** 🔴 Critical · 🟠 High · 🟡 Medium · 🟢 Low · ℹ️ Informational

---

## Executive Summary

**Overall Security Score: 28 / 100**

The application has multiple critical and high-severity vulnerabilities that would expose it and its underlying fleet data to unauthorized access. The most urgent issue is a production Geotab password committed in plain text to a version-controlled configuration file. Combined with completely open API endpoints, a wildcard CORS policy, and AI API keys stored only in process memory, the attack surface is substantial. No automated security scanning, no dependency auditing, and no authentication layer are in place.

---

## 1. Critical Findings

### SEC-001 — Hardcoded Production Credentials in VCS 🔴

**File:** `.do/app.yaml` (lines 22–25)

```yaml
- key: GEOTAB_USERNAME
  value: e.aldrich@budgetlasvegas.com
  type: SECRET
- key: GEOTAB_PASSWORD
  value: Painkiller69!
  type: SECRET
```

A real Geotab username and password are committed in plain text in a DigitalOcean app config file that is tracked by Git. Anyone with read access to this repository — now or in future history — can authenticate directly to the Geotab fleet management platform as this user.

**Impact:** Full access to K1 Logistics / Budget Las Vegas Geotab account — live vehicle locations, driver data, fault codes, HOS records. Possible data exfiltration or manipulation.

**Remediation:**
1. **Immediately rotate** the Geotab password for `e.aldrich@budgetlasvegas.com`.
2. Remove the values from `.do/app.yaml` and replace with DigitalOcean secret references (`${geotab_password}`).
3. Run `git filter-repo` (or `git-secrets`/BFG) to purge the credential from all branches and tags.
4. Audit Geotab access logs for unauthorized login activity.

---

### SEC-002 — No API Authentication 🔴

**File:** `backend/app.py`

All 15 API routers — including fleet GPS positions, driver safety scores, HOS compliance data, and AI chat — are accessible without any form of authentication. The server is configured to listen on `0.0.0.0:8080`.

**Impact:** Any party that can reach the application URL can query, and in some cases modify (e.g., `PATCH /api/alerts/rules`), fleet operations data.

**Remediation:** Implement bearer token or session-based authentication. FastAPI's dependency injection makes this straightforward:

```python
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
security = HTTPBearer()

@app.middleware("http")
async def require_auth(request: Request, call_next):
    if not request.url.path.startswith("/api/health"):
        token = request.headers.get("authorization", "")
        if not validate_token(token):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)
```

---

### SEC-003 — Wildcard CORS 🔴

**File:** `backend/app.py` (lines 15–21)

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,   # ← invalid combination with allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`allow_origins=["*"]` with `allow_credentials=True` is an **invalid CORS configuration** according to the CORS spec; browsers will reject credentialed requests to a wildcard origin. More importantly, it allows any web page to make cross-origin requests to the API.

**Impact:** Cross-site request forgery (CSRF) from any origin; data leakage to malicious third-party sites.

**Remediation:**
```python
allow_origins=["https://your-app.azurewebsites.net"],
allow_credentials=False,  # or True only with explicit origins
```

---

## 2. High-Severity Findings

### SEC-004 — AI API Key Stored Only in Process Memory 🟠

**File:** `backend/routers/ai_chat.py` (lines 25–29)

```python
_ai_config = {
    "provider": "demo",
    "api_key": None,
    "client": None
}
```

The AI API key submitted via the settings endpoint is stored in a Python dict in process memory. It is never persisted and is lost on restart. More critically, the `/api/ai/settings` endpoint that accepts API keys has no authentication (see SEC-002), meaning any caller can set or overwrite the AI provider configuration and observe which key is currently active.

**Remediation:** Require authentication on the settings endpoint; persist AI provider selection to environment variables or a secrets manager; never log or return the full key value.

---

### SEC-005 — Sensitive Data in Error Responses 🟠

**Files:** `backend/routers/fuel.py` (line 92), `compliance.py` (line 155), `reports.py` (line 224)

```python
"error": str(e),   # Exception message exposed to client
```

Internal Python exception messages (which may include file paths, stack frames, connection strings, or internal hostnames) are returned to API clients in the `error` field of fallback responses.

**Remediation:** Log the full exception server-side; return only a generic user-facing message.

---

### SEC-006 — Geotab Client Re-auth Race Condition 🟠

**File:** `backend/geotab_client.py` (lines 51–65)

`_needs_auth()` and `authenticate()` are not protected by a lock. Under concurrent requests (normal with `--workers 2` and concurrent browser polls), multiple threads may simultaneously detect that auth has expired and all attempt to re-authenticate. This can cause token invalidation loops in Geotab.

**Remediation:** Add a `threading.Lock()` around the re-auth path.

---

### SEC-007 — Unvalidated `vehicle_id` Path Parameter 🟠

**File:** `backend/routers/vehicles.py` (line 16)

```python
@router.get("/{vehicle_id}", response_model=Vehicle)
async def get_vehicle(vehicle_id: str):
    vehicles = get_vehicles()
    for v in vehicles:
        if v.id == vehicle_id:
            return v
    return Vehicle(id=vehicle_id, name="Not Found")  # ← reflects unsanitized user input
```

The `vehicle_id` path parameter is reflected in the response body without validation. While the `Vehicle` model is Pydantic-validated, the `id` field is a plain `str` with no length or character restrictions.

**Remediation:** Validate `vehicle_id` with a regex or Pydantic `constr` to restrict to alphanumeric/dash characters.

---

### SEC-008 — `addin/config.json` is Unsigned 🟠

**File:** `addin/config.json` (line 25)

```json
"isSigned": false,
"signature": ""
```

The Geotab add-in is not signed. Geotab requires signed add-ins for production distribution via MyGeotab Administration. An unsigned add-in:
- Cannot be published to the Geotab Marketplace.
- May trigger security warnings in customer MyGeotab instances.
- Cannot be trusted as originating from the declared publisher.

---

## 3. Medium-Severity Findings

### SEC-009 — No Rate Limiting 🟡

Any client can call any endpoint at arbitrary frequency. The `/api/ai/chat` endpoint incurs real API costs (Anthropic/OpenRouter) per call. The `/api/data-connector/*` endpoints probe 7 external servers per cold-start.

**Remediation:** Add `slowapi` or a reverse-proxy-level rate limiter.

---

### SEC-010 — No HTTPS Enforcement in Local/DO Deployment 🟡

The DigitalOcean `app.yaml` does not explicitly enforce HTTPS. Credentials and session tokens sent over HTTP would be exposed.

**Remediation:** DigitalOcean App Platform enforces HTTPS by default, but the configuration should be explicit. For Azure, ensure the App Service TLS settings are enforced.

---

### SEC-011 — `python-dotenv` Loads `.env` from Filesystem 🟡

**File:** `backend/geotab_client.py` (lines 23–27)

```python
_env_geotab = Path.home() / ".openclaw" / ".env.geotab"
if _env_geotab.exists():
    load_dotenv(_env_geotab)
else:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
```

The code attempts to load `~/.openclaw/.env.geotab` — a developer-specific path. In a Docker container running as `fleetpulse` user, this path won't exist, but the fallback loads `../.env`. This path traversal could read unexpected env files in certain deployment layouts.

**Remediation:** Load only from explicit environment variables in production; don't call `load_dotenv` in production containers.

---

### SEC-012 — Demo Data Responses Leak Internal Vehicle Names 🟡

**File:** `backend/routers/data_connector.py` (lines 77–82)

```python
_DEMO_VEHICLE_NAMES = [
    "K1-FTW-001", "K1-FTW-002", …
]
```

The demo data hardcodes real K1 Logistics vehicle naming conventions. An attacker can infer the fleet's naming scheme and location codes (FTW = Fort Worth, JST = Justin, OKC, KC) from the publicly accessible demo response.

---

### SEC-013 — No Content-Security-Policy Header 🟡

No CSP, X-Frame-Options, X-Content-Type-Options, or other security headers are set by the FastAPI application. An attacker who finds an XSS vector could exfiltrate data freely.

**Remediation:**
```python
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
# and use starlette-security or a custom middleware to add headers
```

---

### SEC-014 — MCP Server venv Committed to Repository 🟡

**Path:** `mcp-server/venv/`

Hundreds of third-party package files are tracked in Git. Beyond the repo bloat, this creates a risk of shipping outdated packages with known CVEs without those packages appearing in any dependency scan.

**Remediation:** Add `mcp-server/venv/` to `.gitignore`; document `pip install -r requirements.txt` in the MCP README.

---

## 4. Low-Severity / Informational Findings

### SEC-015 — AI Chat Stores Messages in Memory Only ℹ️

Conversation history is stored per-process in `_ai_config`. This means conversations are lost on restart and shared across all concurrent users of the same process. In a multi-tenant or regulated environment this could cause data leakage between sessions.

---

### SEC-016 — No Dependency Vulnerability Scanning ℹ️

There is no `dependabot` configuration, no `pip-audit` run in CI, and no `npm audit` step. Dependencies such as `framer-motion@12.34.0` and `mygeotab==0.9.1` have not been audited for CVEs.

**Remediation:** Add `pip-audit` and `npm audit` to the CI pipeline.

---

### SEC-017 — Dockerfile Copies `.env.example` into Image ℹ️

**File:** `Dockerfile` (line 34)

```dockerfile
COPY .env.example ./.env.example
```

While this file contains only placeholder values, shipping any `.env` file in a production image is a security anti-pattern that should be avoided.

---

## 5. Security Score Breakdown

| Domain | Score | Notes |
|--------|-------|-------|
| Authentication & Authorization | 0/20 | No auth on any endpoint |
| Secrets Management | 2/20 | Credentials committed to VCS |
| Transport Security | 12/20 | HTTPS via Azure/DO; CORS misconfigured |
| Input Validation | 12/20 | Pydantic models used; path params unvalidated |
| Dependency Security | 6/20 | No scanning; venv committed; mixed pinning |
| **Total** | **32/100** | **Not production-ready** |

---

## 6. Immediate Action Checklist

- [ ] **Rotate** Geotab password for `e.aldrich@budgetlasvegas.com` immediately
- [ ] **Remove** credentials from `.do/app.yaml` and purge from Git history
- [ ] **Add authentication** to all API endpoints
- [ ] **Fix CORS** — replace `*` with explicit allowed origins
- [ ] **Add `mcp-server/venv/` to `.gitignore`**
- [ ] **Add security headers** middleware (CSP, X-Frame-Options, etc.)
- [ ] **Enable `pip-audit` and `npm audit`** in CI
- [ ] **Sign the Geotab add-in** before any production rollout
