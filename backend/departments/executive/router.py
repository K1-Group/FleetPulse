"""Executive department router facade.

Re-exports the FastAPI routers that compose the Executive Command Seat
dashboard. Application mounting continues to happen in `backend/app.py` against
the original module paths; this facade exists for organizational discovery and
for tests that want a single import surface per department.
"""

from routers.ai_chat import router as ai_chat_router
from routers.alerts import router as alerts_router
from routers.dashboard import router as dashboard_router
from routers.gamification import router as gamification_router
from routers.monitor import router as monitor_router

ROUTERS = [
    ("dashboard", "/api/dashboard", ["Dashboard"], dashboard_router),
    ("alerts", "/api/alerts", ["Alerts"], alerts_router),
    ("gamification", "/api/gamification", ["Gamification"], gamification_router),
    ("ai_chat", "/api/ai", ["AI Chat & Intelligence"], ai_chat_router),
    ("monitor", "/api/monitor", ["Agentic Monitor"], monitor_router),
]

__all__ = [
    "ROUTERS",
    "dashboard_router",
    "alerts_router",
    "gamification_router",
    "ai_chat_router",
    "monitor_router",
]
