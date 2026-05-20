# ============================================================
# FleetPulse Production Dockerfile
# Single container: React frontend (built) + FastAPI backend
# Target: Azure App Service (Linux, Docker)
# ============================================================

# ---------- Stage 1: Build frontend ----------
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --production=false
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: Production runtime ----------
FROM python:3.11-slim

# System deps, including Microsoft ODBC for read-only Fabric Warehouse SQL.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    unixodbc \
    unixodbc-dev \
    && version_id="$(. /etc/os-release && echo "$VERSION_ID" | cut -d '.' -f 1)" \
    && curl -fsSLO "https://packages.microsoft.com/config/debian/${version_id}/packages-microsoft-prod.deb" \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -r fleetpulse

WORKDIR /app

# Install Python deps
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt python-dotenv

# Copy backend source
COPY backend/ ./backend/
COPY powerbi/ ./powerbi/
COPY .env.example ./.env.example

# Copy built frontend into backend static dir
COPY --from=frontend-build /app/frontend/dist ./backend/static

# Patch app.py to serve frontend static files.
RUN cat ./backend/static_frontend_mount.py >> ./backend/app.py

# Set ownership
RUN chown -R fleetpulse:fleetpulse /app
USER fleetpulse

# Runtime config
ENV PYTHONUNBUFFERED=1
ENV FLEETPULSE_ENV=production
EXPOSE 8080

# Health check for Azure App Service
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

WORKDIR /app/backend
# Basic B1 App Service is memory-constrained; keep one process and use bounded
# Geotab worker threads for upstream concurrency.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
