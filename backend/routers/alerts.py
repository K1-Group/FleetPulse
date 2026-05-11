"""Alert endpoints — recent alerts, rule management."""

from fastapi import APIRouter, Query
from typing import Optional

from models import Alert, AlertRule
from services.alert_service import get_alert_rules, get_recent_alerts, update_alert_rule

router = APIRouter()


@router.get("/recent", response_model=list[Alert])
def recent_alerts(hours: int = Query(24, ge=1, le=168)):
    return get_recent_alerts(hours=hours)


@router.get("/rules", response_model=list[AlertRule])
async def rules():
    return get_alert_rules()


@router.patch("/rules/{rule_id}", response_model=Optional[AlertRule])
async def patch_rule(rule_id: str, enabled: Optional[bool] = None, threshold: Optional[float] = None):
    return update_alert_rule(rule_id, enabled=enabled, threshold=threshold)
