# FleetPulse — Architecture Audit

> **Audit date:** 2026-05-29  
> **Auditor:** Copilot Coding Agent  
> **Scope:** Full repository — backend, frontend, MCP server, add-in, deployment pipeline

---

## Executive Summary

FleetPulse is a full-stack fleet management dashboard built for K1 Logistics. It integrates with Geotab telematics via two paths: the native Geotab SDK (mygeotab) for real-time vehicle/trip/event data and the Geotab OData Data Connector add-in for pre-aggregated KPI tables. An AI chat interface (Anthropic/OpenRouter) and an MCP server for Claude Desktop complete the feature set.

The codebase is a functional prototype at **demo-grade quality**. Core patterns are sound — FastAPI routers, Pydantic models, React hooks, demo-data fallbacks — but several architectural weaknesses must be resolved before the product can be trusted in production: hardcoded credentials, wildcard CORS, in-process in-memory caching, a single-worker container, and pervasive mock-data paths left active in production code.

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (React 18 + Vite + Tailwind + Recharts + Leaflet)      │
│  PWA-enabled (manifest.json, service worker registerSW.ts)       │
└───────────────────────┬─────────────────────────────────────────┘
                        │ HTTPS /api/*  (proxy in dev, same origin in prod)
┌───────────────────────▼─────────────────────────────────────────┐
│  FastAPI (Python 3.11)  — single Docker container               │
│  Serves static frontend build + 15 API routers                  │
│                                                                  │
│  Routers (prefixed /api/*):                                      │
│  dashboard, vehicles, safety, gamification, alerts, monitor,    │
│  ai_chat, coaching, maintenance, trips, reports, geofences,      │
│  fuel, compliance, data_connector                               │
│                                                                  │
│  Services: fleet_service, safety_service, alert_service,         │
│            gamification_service, monitor_service, coaching,      │
│            safety                                                │
│                                                                  │
│  In-memory TTL cache (_cache.py)                                 │
│  Singleton GeotabClient (connection pool: 4 threads)             │
└─────────────┬────────────────────────┬────────────────────────┘
              │ mygeotab SDK           │ httpx (OData REST)
              ▼                        ▼
     Geotab my.geotab.com      Geotab OData Connector
     (Devices, Trips,          servers 1-7
      ExceptionEvents,         (VehicleKpi_Daily,
      StatusData, Zones,        FleetSafety_Daily,
      FaultData …)              FaultCode_Daily …)

              ┌────────────────────────────────┐
              │  External AI APIs              │
              │  Anthropic / OpenRouter        │
              └────────────────────────────────┘

              ┌────────────────────────────────┐
              │  MCP Server (Python, stdio)    │
              │  Claude Desktop integration    │
              └────────────────────────────────┘
```

### Deployment targets

| Target | Config | Status |
|--------|--------|--------|
| Azure App Service (Docker) | `.github/workflows/azure-deploy.yml` + `Dockerfile` | Primary path |
| DigitalOcean App Platform | `.do/app.yaml` | Secondary (contains plain-text secrets — see Security Audit) |
| Local dev | `vite dev` + `uvicorn` | Working |

---

## 2. Backend

### Framework & Structure

| Aspect | Finding |
|--------|---------|
| Framework | FastAPI 0.115, Pydantic v2, uvicorn |
| Python version | 3.11 (Dockerfile) vs 3.12 (`__pycache__` paths) — mismatch |
| Router loading | Dynamic import loop with bare `except Exception` — swallows all import errors silently |
| Dependency injection | None — routers import services directly; `GeotabClient` is a global singleton |
| Authentication | **None** — all API endpoints are fully public |
| Input validation | Pydantic models + FastAPI `Query()` constraints — adequate for existing endpoints |
| Rate limiting | None |
| Error handling | Mix of `HTTPException` propagation and broad `except Exception` swallowed into demo data |

### Geotab Integration

- **Auth caching**: 1-hour token refresh cycle via `GeotabClient._needs_auth()`. Re-auth is not thread-safe (no lock).
- **Timeout wrapper**: `_executor.submit()` with `concurrent.futures.ThreadPoolExecutor(max_workers=4)` — correct approach for blocking SDK calls, but the pool is module-global and never shut down cleanly.
- **OData connector**: Probes servers 1–7; caches the working URL in a module global (`_ODATA_SERVER`). If the cached server goes down between requests the client will keep failing until the process restarts.
- **Demo mode**: All three OData endpoints fall back to seeded `random.Random(42)` data. The safety scoring service (`safety_service.py`) uses `random.seed(42)` with **production code path disabled** (commented out). This means production deployments return fake data.

### Caching (`_cache.py`)

- Simple in-process dict with TTL checked on read.
- **Data lost on every restart** — no Redis, no disk persistence.
- Not thread-safe (dict operations may race under multiple uvicorn workers).
- `Dockerfile` starts with `--workers 2`, which means two separate cache dicts — cache misses are doubled and data can be inconsistent between workers.

### Services

Most services in `services/` are thin wrappers over `GeotabClient` calls with in-memory fallback. `monitor_service.py` starts a background thread on startup, which will conflict with `--workers 2` (each process starts its own thread, doubling background work).

### Missing routers

Several routers referenced in `app.py` exist (`coaching`, `compliance`, `fuel`, `geofences`, `reports`, `trips`) but have no unit tests and some (`geofences.py`) are minimal stubs.

---

## 3. Frontend

### Stack

React 18 + TypeScript, Vite 6, Tailwind CSS 3, Recharts 2, React-Leaflet, Framer Motion, Lucide icons.

### Architecture

- **Single-page application** — one `App.tsx` root component with tab state (`activeTab`).
- **Data fetching** — custom `useFetch` hook with 30-second polling intervals (10 s for alerts/monitor). No React Query / SWR — cache invalidation is entirely time-based.
- **No routing library** — tab navigation is a string `useState`. Deep-linking and browser back/forward are unsupported.
- **No state management library** — all data is prop-drilled from `App.tsx`.
- **PWA** — `manifest.json` + `registerSW.ts` present; service worker strategy is not audited (file not in tree).

### Component count

23 components identified. Several are large (e.g., `DataConnector.tsx`, `FleetChat.tsx`, `AgenticMonitor.tsx`) with no sub-components, making them difficult to maintain.

### Type safety

`useGeotab.ts` uses `any` for several hooks (`useMonitorStatus`, `useMaintenancePredictions`, etc.). No ESLint config present.

### Accessibility

No `aria-*` attributes or keyboard navigation patterns observed in reviewed components.

---

## 4. MCP Server

- **Language**: Python 3.12, MCP 1.26, requests (sync).
- **Transport**: stdio — designed for Claude Desktop local use only; not accessible over network.
- **Coverage**: Calls FleetPulse API via HTTP — duplicates backend logic and is vulnerable to the same auth gaps.
- **No authentication** between MCP server and backend API — relies entirely on network isolation.
- **venv committed to repo** — `mcp-server/venv/` is in the repository (hundreds of files). This inflates clone size and should be `.gitignore`d.

---

## 5. Geotab Add-in

- Config at `addin/config.json` — `isSigned: false` / empty `signature`. Add-in must be signed before submission to Geotab Marketplace.
- `supportEmail` field contains an employee personal email — should be a team alias.
- `addin/fleetpulse/index.html` — minimal iframe wrapper pointing to the deployed app URL (not present in repo).

---

## 6. Power BI

No Power BI files, `.pbix`, or embedded reports found in the repository. References in `COMPLETION_SUMMARY.md` mention a Power BI integration, but no implementation exists. This is an **unimplemented feature**.

---

## 7. CI/CD (GitHub Actions)

- Single workflow: `azure-deploy.yml` — triggers on `main` push or `workflow_dispatch`.
- Steps: checkout → Azure login → ACR login → `docker build & push` → `az webapp deploy` → smoke test.
- **No test step** — the pipeline deploys without running any tests.
- **No lint or type-check step**.
- **Smoke test** sleeps 30 s then checks `/api/health` — HTTP 200 is possible even when Geotab credentials are wrong.
- ACR name (`k1fleetpulseacr`) is hardcoded in the `az acr login` step rather than using the secret.

---

## 8. Technical Debt Summary

| Category | Items |
|----------|-------|
| Security | Hardcoded credentials in `.do/app.yaml`; wildcard CORS; no API auth; AI key stored in memory |
| Demo/prod parity | `safety_service.py` production code is commented out; `_demo_*` fallbacks fire on any error |
| Architecture | In-memory cache incompatible with multi-worker; global singletons not thread-safe |
| Testing | Zero automated tests in the repository |
| Documentation | `mcp-server/venv/` committed; stale placeholder docs in several `.md` files |
| Dependency management | `requirements.txt` mixes exact pins (`fastapi==0.115.6`) with open ranges (`anthropic>=0.40.0`) |
| Frontend | No router; `any` types; no linting config; no accessibility |

---

## 9. Component Dependency Map

```
App.tsx
├── Dashboard.tsx           ← useFleetOverview, useDashboard
├── FleetAnalytics.tsx      ← (hardcoded mock data)
├── FleetMap.tsx            ← useVehicles, useLocations (react-leaflet)
├── AlertFeed.tsx           ← useAlerts
├── AgenticMonitor.tsx      ← useMonitorAlerts, useMonitorStatus
├── SafetyScorecard.tsx     ← useSafetyScores
├── Leaderboard.tsx         ← useLeaderboard
├── VehicleList.tsx         ← useVehicles
├── LocationCard.tsx        ← useLocations
├── MaintenancePredictor.tsx← useMaintenancePredictions, useMaintenanceCosts, useUrgentMaintenance
├── DriverCoaching.tsx      ← useCoachingDrivers, useCoachingReports
├── RouteReplay.tsx         ← standalone (fetches trips internally)
├── FleetReports.tsx        ← standalone
├── GeofenceManager.tsx     ← standalone
├── FuelAnalytics.tsx       ← standalone
├── ComplianceDashboard.tsx ← standalone
├── DataConnector.tsx       ← standalone (fetches /api/data-connector/*)
└── FleetChat.tsx           ← standalone (AI chat)
```

---

## 10. Recommendations (Architecture)

1. **Add API authentication** — even a shared secret / JWT is better than fully open endpoints.
2. **Replace in-memory cache** with Redis (Azure Cache for Redis or DO Managed Redis) to support multi-worker deployments and survive restarts.
3. **Introduce a routing library** (React Router v6) to enable deep-linking.
4. **Re-enable production safety scoring** in `safety_service.py`.
5. **Add automated tests** — at minimum smoke tests for each router using `pytest` + `httpx.AsyncClient`.
6. **Restrict CORS** to the actual frontend origin(s) instead of `*`.
7. **Gitignore `mcp-server/venv/`** and `**/__pycache__/`.
8. **Pin all Python dependencies** or use a lock file (pip-compile / Poetry).
