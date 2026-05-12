# 🚗 FleetPulse — Multi-Location Fleet Intelligence Platform

**GeoTab Hackathon 2026 Entry** | Budget Rent a Car Las Vegas Demo

FleetPulse is an intelligent fleet management dashboard for multi-location rental operations. It connects to GeoTab's telematics API to provide real-time vehicle tracking, safety scoring, gamification, and **autonomous anomaly detection** across 8 Budget Rent a Car locations in Las Vegas.

![FleetPulse](https://img.shields.io/badge/Status-Live-green) ![GeoTab](https://img.shields.io/badge/GeoTab-Integrated-blue) ![Vehicles](https://img.shields.io/badge/Vehicles-50-orange)

> **📝 Demo Mode Note:** The safety scoring system currently uses **mock data** for realistic visualization in the demo. The Geotab demo database (`demo_fleetpulse`) has no ExceptionEvents configured, resulting in all vehicles having perfect 100% scores when using real API data. Mock data provides realistic score distributions (70-100 range) with varied violation counts that match the Alert Distribution chart. **Production mode** is preserved in comments within `backend/services/safety_service.py` and can be re-enabled by uncommenting the real API calls.

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────┐
│                   React + Vite Frontend              │
│  Dashboard │ Fleet Map │ Leaderboard │ Agent Monitor │
└────────────────────────┬─────────────────────────────┘
                         │ /api/* (Vite proxy)
┌────────────────────────▼─────────────────────────────┐
│                FastAPI Backend (8080)                 │
│  /dashboard │ /vehicles │ /safety │ /gamification    │
│  /alerts │ /monitor (agentic)                        │
├──────────────────────────────────────────────────────┤
│              Agentic Monitor (background)            │
│  Speed anomalies │ Idle detection │ Off-route alerts │
│  After-hours │ Fleet patterns │ Location imbalances  │
└────────────────────────┬─────────────────────────────┘
                         │ mygeotab SDK
                    ┌────▼────┐
                    │ GeoTab  │
                    │   API   │
                    └─────────┘
```

## ✨ Key Features

### 🤖 Agentic Monitor (Key Differentiator)
An autonomous intelligence layer that continuously analyzes fleet telemetry:
- **Speed Anomaly Detection** — Flags vehicles exceeding speed thresholds with severity levels
- **Excessive Idle Detection** — Identifies vehicles idle for extended periods
- **Off-Route Alerts** — Detects vehicles leaving the Las Vegas metro area
- **After-Hours Monitoring** — Flags activity during 11 PM – 5 AM
- **Fleet Pattern Analysis** — Identifies unusual fleet-wide activity patterns
- **Location Inventory Balancing** — Alerts when locations have zero or excess vehicles
- Runs every 60 seconds with full alert history and pattern tracking

### 🏆 FleetChamp Gamification
- Driver safety scoring with points (base 1000 × safety %, -50 per incident)
- Badges: 🏅 Speed Demon Free, 🎯 Smooth Operator, 🌿 Eco Champion, ⭐ Perfect Week
- Per-driver and per-location leaderboards
- Location vs location competition rankings
- Weekly challenges (Safe Week, Zero Speeding)

### 📊 Real-Time Dashboard
- KPI cards: total vehicles, active, idle, parked, trips, distance, avg duration
- Dark Leaflet map with vehicle markers (color-coded by status) and location zones
- Alert feed with severity-based styling (critical/high/medium/low)
- Safety scorecard with trend indicators and progress bars
- 30-second vehicle refresh, 15-second alert refresh

### 📍 8 Budget Rent a Car Locations
W Sahara · Golden Nugget · Center Strip · Tropicana · LAS Airport · Gibson · Henderson Executive · Losee

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- GeoTab credentials (set in `~/.openclaw/.env.geotab` or project `.env`)
- **Optional**: Anthropic API key for Claude AI integration

### Environment Variables

#### Basic Setup (`.env` file in backend/)
```env
GEOTAB_DATABASE=demo_fleetpulse
GEOTAB_USERNAME=your_username
GEOTAB_PASSWORD=your_password
GEOTAB_SERVER=my.geotab.com
```

#### AI-Enhanced Setup (Optional - choose one)
```env
# Option 1: OpenRouter (connects Claude Max/Pro subscriptions)
OPENROUTER_API_KEY=your-key-here
OPENROUTER_MODEL=anthropic/claude-sonnet-4
OPENROUTER_SITE_URL=https://k1-fleetpulse.azurewebsites.net
OPENROUTER_APP_NAME=FleetPulse

# Option 2: Anthropic Direct API (pay-per-use)  
ANTHROPIC_API_KEY=your-key-here
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

For production, store API keys in Azure Key Vault/App Settings. Do not commit
provider keys into `.env` files.

#### Live Fleet Data Scope
```env
# Count active Geotab power units, not inactive historical devices or trailers.
FLEETPULSE_DEVICE_GROUP_IDS=GroupVehicleId
FLEETPULSE_EXCLUDED_DEVICE_GROUP_IDS=GroupTrailerId
FLEETPULSE_REQUIRE_ACTIVE_LIFECYCLE=true
FLEETPULSE_STATUS_STALE_HOURS=24
FLEETPULSE_SAFETY_DEMO_MODE=false
FLEETPULSE_MONITOR_ENABLED=false
FLEETPULSE_GEOTAB_TIMEOUT_SECONDS=10
FLEETPULSE_GEOTAB_MAX_WORKERS=4
FLEETPULSE_CACHE_TTL_SECONDS=30
FLEETPULSE_CACHE_FALLBACK_SECONDS=300
```

The dashboard response includes source metadata such as `raw_device_count`,
`scoped_device_count`, and `stale_status_count` so operators can tell whether a
KPI is live and business-scoped. If Geotab times out, FleetPulse returns a
short-lived cached live response with `source_mode=cached_after_geotab_timeout`;
when no cache exists, it returns an explicit unavailable/empty response instead
of demo numbers.

#### XTRA Lease Geofence Feed
```env
FLEETPULSE_XTRA_INGESTION_ENABLED=true
FLEETPULSE_XTRA_OUTLOOK_MAILBOX=xtra-feed@example.com
FLEETPULSE_XTRA_GEOFENCE_FOLDER=XTRA Lease Tracking
FLEETPULSE_XTRA_INGESTION_API_KEY=store-in-key-vault
FLEETPULSE_GRAPH_TENANT_ID=tenant-id
FLEETPULSE_GRAPH_CLIENT_ID=app-client-id
FLEETPULSE_GRAPH_CLIENT_SECRET=store-in-key-vault
FLEETPULSE_XTRA_STATE_PATH=/home/data/fleetpulse_xtra_lease_ingestion_state.json
FLEETPULSE_XTRA_SHAREPOINT_LOG_WEBHOOK_URL=
FLEETPULSE_TEAMS_ALERT_WEBHOOK_URL=
FLEETPULSE_TWILIO_ACCOUNT_SID=
FLEETPULSE_TWILIO_AUTH_TOKEN=
FLEETPULSE_TWILIO_FROM_NUMBER=
FLEETPULSE_TWILIO_ALERT_TO_NUMBER=
```

The XTRA adapter reads one configured Outlook folder through Microsoft Graph,
stores only read-only geofence event references, and deduplicates each email by
idempotency key. Use a least-privilege app registration with mailbox-scoped
Graph access; grant only `Mail.Read` and constrain the service principal to the
configured XTRA mailbox with Exchange application RBAC or an application access
policy. Trigger ingestion from an approved scheduler with:

```bash
curl -X POST https://k1-fleetpulse.azurewebsites.net/api/control-tower/trailers/xtra/ingest \
  -H "X-FleetPulse-Xtra-Key: $FLEETPULSE_XTRA_INGESTION_API_KEY"
```

#### Live Trailer Tracking
```env
FLEETPULSE_TRAILER_GROUP_IDS=GroupTrailerId
FLEETPULSE_TRAILER_MATCH_RADIUS_METERS=150
FLEETPULSE_TRAILER_DRIVER_LOOKBACK_HOURS=12
```

`GET /api/control-tower/trailers/live` merges Geotab trailer GPS with the
latest XTRA geofence events as read-only references. Custody is proximity-based:
the nearest scoped Geotab tractor within `FLEETPULSE_TRAILER_MATCH_RADIUS_METERS`
is shown as a candidate tractor/driver, not as an authoritative dispatch
assignment. Xcelerator should remain the final dispatch/load owner when that
assignment feed is connected.

### Backend
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies (includes anthropic SDK)
pip install -r requirements.txt

# Copy and edit environment variables
cp backend/.env.example backend/.env
# Edit backend/.env with your credentials

# Start the backend
cd backend
uvicorn app:app --port 8080
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies API calls to the backend on port 8080.

## 🧠 AI Integration

FleetPulse supports **three AI modes** for enhanced fleet intelligence:

### 1. OpenRouter (Recommended 🌟)
- **Use your Claude Max ($100/mo) or Pro ($20/mo) subscription** 
- Connect existing subscription via OpenRouter for free tier usage
- Same Claude model quality without additional per-use charges
- Free tier credits available even without subscription

**Setup:**
1. Visit [openrouter.ai](https://openrouter.ai) and create an account
2. Generate an API key in your dashboard
3. Optionally: Connect your Claude subscription for enhanced usage
4. Configure the key in FleetPulse settings

### 2. Anthropic Direct API
- **Pay-per-use** pricing (~$3 per million tokens)
- Direct access to Anthropic's API
- Most reliable option with full feature set
- Best for high-volume usage with predictable costs

**Setup:**
1. Get an API key from [console.anthropic.com](https://console.anthropic.com)
2. Add credit to your account for billing
3. Configure the key in FleetPulse settings

### 3. Demo Mode
- **No API key required** — works out of the box
- Uses intelligent pattern matching for common fleet queries
- Great for testing and basic fleet analysis
- Automatically activated when no API key is configured

**Features in both modes:**
- Natural language fleet queries
- Data visualizations (charts, graphs)
- Safety analysis and recommendations
- Maintenance predictions
- Cost optimization insights
- Real-time fleet status integration

**Example queries:**
- "Which location has the best safety scores?"
- "Show me vehicles with high idle time"
- "What are the cost-saving recommendations?"
- "How is our fuel efficiency trending?"
- "Any vehicles need maintenance soon?"

## 🤖 Claude Desktop Integration (MCP)

FleetPulse includes a **Model Context Protocol (MCP) server** that allows Claude Desktop and other MCP clients to interact with fleet data conversationally.

### Features
- **Natural Language Queries**: "Which location has the best safety scores?" or "Show me vehicles with high idle time"
- **Rich Formatted Responses**: Markdown tables, insights, and contextual information
- **Real-time Data**: Direct access to live fleet information through the FastAPI backend
- **Fleet Summary Resource**: Claude can read current fleet status for context

### Available MCP Tools
| Tool | Description |
|------|-------------|
| `get_fleet_overview` | Vehicle counts, active/idle status, trip metrics |
| `get_vehicles` | List all vehicles with positions, status, speed, driver |
| `get_vehicle_details(vehicle_id)` | Deep dive into specific vehicle |
| `get_safety_scores` | All drivers' safety scores with violation breakdowns |
| `get_alerts(severity?, limit?)` | Recent alerts with filtering options |
| `get_location_stats(location?)` | Per-location metrics and statistics |
| `get_leaderboard` | Gamification rankings and achievements |
| `query_fleet(question)` | Natural language query processing with AI insights |
| `get_recommendations` | AI-generated cost-saving and safety recommendations |

### Setup Instructions

1. **Start FleetPulse backend** (must be running on localhost:8080):
   ```bash
   cd backend && uvicorn app:app --port 8080
   ```

2. **Test the MCP server**:
   ```bash
   cd mcp-server
   source venv/bin/activate
   python test_server.py
   ```

3. **Configure Claude Desktop**:
   
   **Linux**: `~/.config/claude-desktop/config.json`
   
   **macOS**: `~/Library/Application Support/Claude/config.json`
   
   ```json
   {
     "mcpServers": {
       "fleetpulse": {
         "command": "python",
         "args": ["mcp-server/server.py"],
         "cwd": "/path/to/FleetPulse",
         "env": {
           "FLEETPULSE_API_URL": "http://localhost:8080/api"
         }
       }
     }
   }
   ```

4. **Restart Claude Desktop** and look for "FleetPulse" in the MCP servers list

### Example Queries
- "Show me the current fleet status"
- "Which vehicles are currently active?"
- "What are the safety scores for all drivers?"
- "Give me recommendations to improve efficiency"
- "Show alerts from the last hour"
- "Which location has the most idle time?"

## 📡 API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check |
| `GET /api/dashboard/overview` | Fleet KPIs |
| `GET /api/dashboard/locations` | Per-location stats |
| `GET /api/vehicles/` | All vehicles with positions |
| `GET /api/vehicles/{id}` | Single vehicle |
| `GET /api/safety/scores` | Safety scores per vehicle |
| `GET /api/alerts/recent` | Exception-based alerts |
| `GET /api/gamification/leaderboard` | Driver rankings |
| `GET /api/gamification/challenges` | Active challenges |
| `GET /api/gamification/location-rankings` | Location competition |
| `GET /api/monitor/alerts` | Agentic monitor alerts |
| `GET /api/monitor/status` | Monitor status & patterns |
| `POST /api/monitor/check` | Trigger manual check |
| **🚚 Control Tower Endpoints** |
| `GET /api/control-tower/trailers` | Trailer GPS and XTRA geofence projection |
| `POST /api/control-tower/trailers/xtra/ingest` | Protected XTRA Outlook geofence ingestion trigger |
| **🧠 AI Endpoints** |
| `POST /api/ai/chat` | **Claude AI-powered chat** (with conversation history) |
| `POST /api/ai/chat/stream` | **Streaming AI responses** (Server-Sent Events) |
| `GET /api/ai/config` | Get AI configuration status |
| `POST /api/ai/config` | Set Anthropic API key (memory only) |
| `POST /api/ai/query` | Legacy natural language queries (pattern matching fallback) |
| `GET /api/ai/insights` | AI-generated recommendations |
| **🔁 Zapier Endpoints** |
| `GET /api/zapier/status` | Zapier readiness without exposing secrets |
| `GET /api/zapier/triggers/fleet-snapshot` | Zapier polling trigger: one FleetPulse snapshot row |
| `GET /api/zapier/triggers/risk-vehicles` | Zapier polling trigger: vehicles below safety threshold |
| `POST /api/zapier/actions/push-snapshot` | Optional feature-flagged push to a Zapier Catch Hook |
| `POST /api/zapier/actions/verify-snapshot` | Verify a pushed Catch Hook payload signature without exposing the signing secret |
| `POST /api/zapier/actions/verify-message` | Verify the compact signed Teams message before Zapier sends it |

## 🛠️ Tech Stack

- **Backend:** Python, FastAPI, mygeotab SDK, Pydantic v2
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, Leaflet, Recharts
- **Telemetry:** GeoTab API (50 vehicles, real-time DeviceStatusInfo, Trips, ExceptionEvents)
- **Architecture:** REST API with background agentic monitoring thread

## 🔁 Zapier Integration

FleetPulse exposes a Zapier-safe integration surface under `/api/zapier`.
Zapier remains an orchestration layer only; FleetPulse does not accept writes
from Zapier and does not overwrite Geotab.

### Recommended Zaps

1. **Fleet snapshot report**
   - Trigger: Schedule by Zapier
   - Action: Webhooks by Zapier `GET`
   - URL: `https://k1-fleetpulse.azurewebsites.net/api/zapier/triggers/fleet-snapshot`
   - Follow-up: send Teams/email summary, write to Sheets, or store in Power BI helper table.

2. **Risk vehicle alert**
   - Trigger: Schedule by Zapier
   - Action: Webhooks by Zapier `GET`
   - URL: `https://k1-fleetpulse.azurewebsites.net/api/zapier/triggers/risk-vehicles?max_score=85&min_events=1`
   - Follow-up: send to Teams first for operator validation.

3. **Catch Hook push**
   - Configure a Zapier Catch Hook URL in `FLEETPULSE_ZAPIER_WEBHOOK_URL`
   - Set `FLEETPULSE_ZAPIER_ENABLED=true`
   - Call `POST /api/zapier/actions/push-snapshot` from an approved scheduler or operator tool.
   - Add a guard step before Teams/email that calls
     `POST https://k1-fleetpulse.azurewebsites.net/api/zapier/actions/verify-snapshot`
     with the Catch Hook payload. Continue only when `valid=true`.
   - If Zapier cannot pass the full nested payload cleanly, use the compact guard:
     call `POST /api/zapier/actions/verify-message` with `teams_message` and
     `teams_message_signature`, then send only the verified `teams_message`.

### Zapier Environment Variables

```env
FLEETPULSE_ZAPIER_ENABLED=false
FLEETPULSE_ZAPIER_WEBHOOK_URL=
FLEETPULSE_ZAPIER_API_KEY=
FLEETPULSE_ZAPIER_SHARED_SECRET=
FLEETPULSE_ZAPIER_TIMEOUT_SECONDS=15
```

Security notes:

- `FLEETPULSE_ZAPIER_API_KEY` protects the push endpoint when configured.
- `FLEETPULSE_ZAPIER_SHARED_SECRET` signs outbound Catch Hook payloads with `payload_signature`
  and `X-FleetPulse-Signature`; it also signs a compact `teams_message`.
  Zapier can verify via FleetPulse without storing this secret.
- Polling trigger endpoints are read-only Geotab projections.

## 📂 Project Structure

```
FleetPulse/
├── backend/
│   ├── app.py                    # FastAPI app with CORS, router registration
│   ├── geotab_client.py          # GeoTab API wrapper with auth caching
│   ├── models.py                 # Pydantic v2 response models
│   ├── routers/                  # API route handlers
│   │   ├── dashboard.py
│   │   ├── vehicles.py
│   │   ├── safety.py
│   │   ├── gamification.py
│   │   ├── alerts.py
│   │   ├── monitor.py            # Agentic monitor endpoints
│   │   └── ai_chat.py            # Natural language query processing
│   └── services/                 # Business logic
│       ├── fleet_service.py      # Vehicle tracking, fleet overview
│       ├── safety_service.py     # Safety scoring, trend analysis
│       ├── gamification_service.py # Points, badges, leaderboards
│       ├── alert_service.py      # Exception-based alerting
│       └── monitor_service.py    # 🤖 Agentic anomaly detection
├── frontend/
│   ├── src/
│   │   ├── App.tsx               # Main layout
│   │   ├── hooks/useGeotab.ts    # Data fetching hooks with auto-refresh
│   │   ├── types/fleet.ts        # TypeScript interfaces
│   │   └── components/           # UI components
│   │       ├── Dashboard.tsx     # KPI cards
│   │       ├── FleetMap.tsx      # Leaflet map
│   │       ├── AlertFeed.tsx     # Alert stream
│   │       ├── SafetyScorecard.tsx
│   │       ├── Leaderboard.tsx
│   │       ├── VehicleList.tsx
│   │       ├── LocationCard.tsx
│   │       └── AgenticMonitor.tsx # 🤖 Monitor UI
│   └── vite.config.ts            # Proxy → backend:8080
├── mcp-server/                   # 🤖 Model Context Protocol server
│   ├── server.py                 # MCP server for Claude Desktop integration
│   ├── test_server.py            # Test suite for MCP functionality
│   ├── claude_desktop_config.json # Claude Desktop configuration example
│   └── venv/                     # Python virtual environment
├── scripts/                      # Setup scripts (zones, drivers)
├── requirements.txt
└── README.md
```

## 👥 Team

Built by **Vex** for the GeoTab Hackathon 2026.

## 📜 License

MIT

---

## 🔌 MyGeotab Add-In

FleetPulse includes a MyGeotab Add-In that runs **inside** the MyGeotab portal.

### Installation

1. In MyGeotab, go to **Administration → System Settings → Add-Ins**
2. Click **New Add-In** and paste the contents of `addin/config.json`
   - Or, if hosting the add-in files on a server, update the `url` fields to point to your hosted `addin/fleetpulse/` directory
3. Save and refresh MyGeotab — "FleetPulse" will appear in the navigation

### How It Works

- When loaded inside MyGeotab, the add-in receives the `api` and `state` objects from the SDK
- It calls the Geotab API directly (Get Device, Get Trip, Get ExceptionEvent) to render KPIs, vehicle lists, and safety data
- A "Full Dashboard" mode embeds the live FleetPulse web app in an iframe
- Works in standalone mode too (fetches from the FleetPulse API)

### Files

| File | Purpose |
|------|---------|
| `addin/config.json` | MyGeotab Add-In manifest (pages, icons, navigation) |
| `addin/fleetpulse/index.html` | The Add-In page (HTML/JS/CSS, no build step) |

---

## 📊 Data Connector Integration

FleetPulse integrates with the **Geotab Data Connector** (OData v4) for pre-aggregated fleet analytics.

### Activation

The Data Connector must be activated on your database:

1. In MyGeotab → **Administration → System Settings → Add-Ins**
2. Add: `{"url": "https://app.geotab.com/addins/geotab/dataConnector/manifest.json"}`
3. Save and wait 2-3 hours for the data pipeline to backfill

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/data-connector/tables` | List available OData tables |
| `GET /api/data-connector/vehicle-kpis?days=14` | Per-vehicle utilization: distance, drive/idle hours, trips, fuel |
| `GET /api/data-connector/safety-scores?days=14` | Fleet and vehicle safety scores |
| `GET /api/data-connector/fault-trends?days=14` | Fault code frequency and trends |
| `GET /api/data-connector/trip-summary?days=14` | Trip aggregates per vehicle |

### Frontend

Navigate to the **Connector** tab in the FleetPulse dashboard to see:
- Fleet utilization KPIs (distance, drive hours, idle hours, utilization %)
- Per-vehicle utilization table
- Aggregated safety scores
- Fault code trends
