"""Pydantic v2 models for FleetPulse API responses."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────
class VehicleStatus(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    PARKED = "parked"
    OFFLINE = "offline"


class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TrendDirection(str, Enum):
    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"


# ── Vehicles ───────────────────────────────────────────────────
class VehiclePosition(BaseModel):
    latitude: float
    longitude: float
    bearing: float = 0
    speed: float = 0


class Vehicle(BaseModel):
    id: str
    name: str
    status: VehicleStatus = VehicleStatus.PARKED
    position: Optional[VehiclePosition] = None
    location_name: Optional[str] = None
    odometer_km: float = 0
    last_contact: Optional[datetime] = None


# ── Fleet Overview ─────────────────────────────────────────────
class FleetOverview(BaseModel):
    total_vehicles: int = 0
    active: int = 0
    idle: int = 0
    parked: int = 0
    offline: int = 0
    total_trips_today: int = 0
    total_stops_today: int = 0
    total_distance_miles: float = 0
    avg_trip_duration_min: float = 0
    avg_trip_duration_hours: float = 0
    avg_trip_distance_miles: float = 0
    target_trip_duration_hours: float = 12
    trips_meeting_target: int = 0
    trips_under_target: int = 0
    trip_definition: str = "geotab_trip_segment"
    source_authority: str = "Geotab"
    source_mode: str = "live_filtered"
    raw_device_count: int = 0
    scoped_device_count: int = 0
    raw_status_count: int = 0
    stale_status_count: int = 0
    device_scope: str = "active_lifecycle_group_vehicle"


class LocationStats(BaseModel):
    name: str
    address: str
    latitude: float
    longitude: float
    vehicle_count: int = 0
    active: int = 0
    safety_score: float = 100.0


# ── Safety ─────────────────────────────────────────────────────
class SafetyBreakdown(BaseModel):
    speeding: int = 0
    harsh_braking: int = 0
    harsh_acceleration: int = 0
    harsh_cornering: int = 0


class VehicleSafetyScore(BaseModel):
    vehicle_id: str
    vehicle_name: str
    score: float = Field(ge=0, le=100, default=100)
    breakdown: SafetyBreakdown = Field(default_factory=SafetyBreakdown)
    trend: TrendDirection = TrendDirection.STABLE
    event_count: int = 0


# ── Gamification ───────────────────────────────────────────────
class Badge(BaseModel):
    id: str
    name: str
    description: str
    icon: str  # emoji
    earned: bool = False
    earned_at: Optional[datetime] = None


class DriverScore(BaseModel):
    driver_id: str
    driver_name: str
    points: int = 0
    safety_score: float = 100.0
    badges: list[Badge] = Field(default_factory=list)
    rank: int = 0


class Challenge(BaseModel):
    id: str
    title: str
    description: str
    start_date: datetime
    end_date: datetime
    target_metric: str
    current_value: float = 0
    target_value: float = 0


class LocationRanking(BaseModel):
    location_name: str
    avg_safety_score: float
    total_points: int
    rank: int


# ── Alerts ─────────────────────────────────────────────────────
class Alert(BaseModel):
    id: str
    vehicle_id: str
    vehicle_name: str
    alert_type: str
    severity: AlertSeverity
    message: str
    timestamp: datetime
    acknowledged: bool = False


class AlertRule(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool = True
    threshold: Optional[float] = None
    alert_type: str
    severity: AlertSeverity = AlertSeverity.MEDIUM


# ── Maintenance ────────────────────────────────────────────────
class MaintenanceType(str, Enum):
    OIL_CHANGE = "oil_change"
    BRAKE_SERVICE = "brake_service"
    TIRE_ROTATION = "tire_rotation"
    TRANSMISSION_SERVICE = "transmission_service"
    TIRES_REPLACEMENT = "tires_replacement"


class UrgencyLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class UpcomingService(BaseModel):
    service_type: str
    due_date: datetime
    is_overdue: bool = False
    urgency: UrgencyLevel
    estimated_cost: float


class MaintenancePrediction(BaseModel):
    vehicle_id: str
    vehicle_name: str
    current_odometer: float
    engine_hours: float
    upcoming_services: list[UpcomingService]
    has_active_fault_codes: bool = False
    active_fault_count: int = 0


class MaintenanceHistoryItem(BaseModel):
    service_type: str
    date: datetime
    odometer_at_service: float
    cost: float
    notes: Optional[str] = None


class FaultCode(BaseModel):
    code: str
    description: str
    timestamp: datetime
    severity: str


class VehicleMaintenanceDetail(BaseModel):
    vehicle_id: str
    vehicle_name: str
    current_odometer: float
    engine_hours: float
    upcoming_services: list[UpcomingService]
    maintenance_history: list[MaintenanceHistoryItem]
    active_fault_codes: list[FaultCode]
    last_service_date: Optional[datetime] = None


class MaintenanceCost(BaseModel):
    total_cost_next_month: float
    total_cost_next_3_months: float
    cost_breakdown: dict[str, dict[str, float]]  # service_type -> {count, total_cost}
    average_monthly_cost: float


class UrgentMaintenanceAlert(BaseModel):
    vehicle_id: str
    vehicle_name: str
    urgency: UrgencyLevel
    active_fault_codes: list[dict[str, str]]  # {code, description}
    overdue_services: list[dict]  # service details
    urgent_services: list[dict]  # service details
    estimated_repair_cost: float


# ── Driver Coaching ────────────────────────────────────────────
class CoachingStatus(str, Enum):
    NEEDS_ATTENTION = "needs_attention"
    ON_TRACK = "on_track"
    IMPROVED = "improved"


class CoachingCategory(str, Enum):
    HARSH_BRAKING = "harsh_braking"
    HARSH_ACCELERATION = "harsh_acceleration"
    SPEEDING = "speeding"
    CORNERING = "cornering"
    SEATBELT = "seatbelt"


class CoachingScores(BaseModel):
    harsh_braking: float = Field(ge=0, le=100, default=100)
    harsh_acceleration: float = Field(ge=0, le=100, default=100)
    speeding: float = Field(ge=0, le=100, default=100)
    cornering: float = Field(ge=0, le=100, default=100)
    seatbelt: float = Field(ge=0, le=100, default=100)


class CoachingRecommendation(BaseModel):
    category: CoachingCategory
    priority: int = Field(ge=1, le=5, description="1=highest, 5=lowest")
    message: str
    fuel_impact_pct: float = Field(ge=0, le=30, description="Estimated fuel cost increase %")


class CoachingTrend(BaseModel):
    current_week: float
    last_week: float
    four_weeks_avg: float
    direction: TrendDirection


class DriverCoachingProfile(BaseModel):
    driver_id: str
    driver_name: str
    status: CoachingStatus
    scores: CoachingScores
    overall_score: float = Field(ge=0, le=100)
    recommendations: list[CoachingRecommendation] = Field(default_factory=list)
    trend: CoachingTrend
    events_this_week: int = 0
    fuel_waste_pct: float = Field(ge=0, le=30, description="Estimated fuel waste due to poor driving %")
    acknowledged: bool = False


class CoachingEventDetail(BaseModel):
    timestamp: datetime
    category: CoachingCategory
    location: str
    severity: AlertSeverity
    description: str


class DriverCoachingDetail(BaseModel):
    driver_id: str
    driver_name: str
    scores: CoachingScores
    trend: CoachingTrend
    recommendations: list[CoachingRecommendation] = Field(default_factory=list)
    recent_events: list[CoachingEventDetail] = Field(default_factory=list)
    weekly_stats: dict[str, int] = Field(default_factory=dict, description="Event counts by week")


class FleetCoachingSummary(BaseModel):
    total_drivers: int
    needs_attention: int
    on_track: int
    improved: int
    average_score: float = Field(ge=0, le=100)
    best_improved: list[str] = Field(default_factory=list, description="Driver names")
    worst_performers: list[str] = Field(default_factory=list, description="Driver names")
    fleet_fuel_savings_potential: float = Field(ge=0, le=30, description="Potential fuel savings %")


# ── Control Tower ──────────────────────────────────────────────
class ControlTowerStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    AWAITING_FEED = "awaiting_feed"
    UNAVAILABLE = "unavailable"


class ControlTowerFeedStatus(BaseModel):
    name: str
    source_authority: str
    status: ControlTowerStatus = ControlTowerStatus.AWAITING_FEED
    message: str
    required_config: list[str] = Field(default_factory=list)
    last_updated: Optional[datetime] = None


class ControlTowerSectionSummary(BaseModel):
    key: str
    label: str
    status: ControlTowerStatus
    source_authority: str
    item_count: int = 0
    message: str


class ControlTowerOverview(BaseModel):
    generated_at: datetime
    projection_mode: str = "read_only"
    sections: list[ControlTowerSectionSummary] = Field(default_factory=list)


class ControlTowerAttentionItem(BaseModel):
    id: str
    category: str
    severity: AlertSeverity
    action: str
    message: str
    source_authority: str
    timestamp: Optional[datetime] = None


class ControlTowerAttentionResponse(BaseModel):
    generated_at: datetime
    projection_mode: str = "read_only"
    items: list[ControlTowerAttentionItem] = Field(default_factory=list)
    feeds: list[ControlTowerFeedStatus] = Field(default_factory=list)


class ControlTowerTrailerSummary(BaseModel):
    total_trailers: int = 0
    gps_active: int = 0
    gps_inactive: int = 0
    geofence_events_today: int = 0
    yards_reporting: int = 0
    last_email_received: Optional[str] = None


class ControlTowerYardLocation(BaseModel):
    name: str
    latitude: float
    longitude: float
    trailer_count: int = 0


class ControlTowerTrailerEvent(BaseModel):
    id: str
    trailer_id: str
    event_type: str
    location: Optional[str] = None
    timestamp: Optional[datetime] = None
    source_authority: str = "Outlook/XTRA"


class ControlTowerTrailerCustody(BaseModel):
    vehicle_id: Optional[str] = None
    vehicle_name: Optional[str] = None
    driver_id: Optional[str] = None
    driver_name: Optional[str] = None
    vehicle_position: Optional[VehiclePosition] = None
    distance_meters: Optional[float] = None
    confidence: str = "none"
    source: str = "none"
    note: str = "No current Geotab proximity match."


class ControlTowerTrailerLiveAsset(BaseModel):
    trailer_id: str
    trailer_name: str
    geotab_device_id: Optional[str] = None
    gps_status: VehicleStatus = VehicleStatus.OFFLINE
    position: Optional[VehiclePosition] = None
    location_name: Optional[str] = None
    speed: float = 0
    bearing: float = 0
    geotab_last_contact: Optional[datetime] = None
    xtra_last_event: Optional[ControlTowerTrailerEvent] = None
    custody: ControlTowerTrailerCustody = Field(default_factory=ControlTowerTrailerCustody)
    source_authorities: list[str] = Field(default_factory=list)


class ControlTowerTrailerTrackingSummary(BaseModel):
    total_trailers: int = 0
    gps_active: int = 0
    gps_inactive: int = 0
    xtra_event_trailers: int = 0
    custody_inferred: int = 0
    custody_unassigned: int = 0
    last_geotab_contact: Optional[datetime] = None
    last_email_received: Optional[str] = None


class ControlTowerTrailerTrackingResponse(BaseModel):
    generated_at: datetime
    projection_mode: str = "read_only"
    summary: ControlTowerTrailerTrackingSummary = Field(default_factory=ControlTowerTrailerTrackingSummary)
    trailers: list[ControlTowerTrailerLiveAsset] = Field(default_factory=list)
    feeds: list[ControlTowerFeedStatus] = Field(default_factory=list)


class ControlTowerTrailersResponse(BaseModel):
    generated_at: datetime
    projection_mode: str = "read_only"
    summary: ControlTowerTrailerSummary = Field(default_factory=ControlTowerTrailerSummary)
    yard_locations: list[ControlTowerYardLocation] = Field(default_factory=list)
    geofence_events: list[ControlTowerTrailerEvent] = Field(default_factory=list)
    bobtail_alerts: list[ControlTowerAttentionItem] = Field(default_factory=list)
    feeds: list[ControlTowerFeedStatus] = Field(default_factory=list)


class ControlTowerFinancialBucket(BaseModel):
    bucket: str
    amount: Optional[float] = None
    count: int = 0


class ControlTowerFinancialSummary(BaseModel):
    pending_amount: Optional[float] = None
    pending_bills: int = 0
    overdue_amount: Optional[float] = None
    overdue_count: int = 0
    total: Optional[float] = None


class ControlTowerFinancialResponse(BaseModel):
    generated_at: datetime
    projection_mode: str = "read_only"
    source_authority: str = "K1 Group LLC / Xcelerator / QuickBooks"
    accounts_payable: ControlTowerFinancialSummary = Field(default_factory=ControlTowerFinancialSummary)
    accounts_receivable: list[ControlTowerFinancialBucket] = Field(default_factory=list)
    cash_flow: dict[str, Optional[float]] = Field(default_factory=dict)
    audit_queue: dict[str, Union[int, list[str]]] = Field(default_factory=dict)
    feeds: list[ControlTowerFeedStatus] = Field(default_factory=list)


class ControlTowerAgentFlow(BaseModel):
    name: str
    status: ControlTowerStatus
    detail: str


class ControlTowerAgentSystem(BaseModel):
    name: str
    status: ControlTowerStatus
    usage: Optional[str] = None
    flows: list[ControlTowerAgentFlow] = Field(default_factory=list)


class ControlTowerAgentsResponse(BaseModel):
    generated_at: datetime
    projection_mode: str = "read_only"
    systems: list[ControlTowerAgentSystem] = Field(default_factory=list)


class ControlTowerCodexResponse(BaseModel):
    generated_at: datetime
    projection_mode: str = "read_only"
    overall_status: ControlTowerStatus
    repository: Optional[str] = None
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    run_id: Optional[str] = None
    message: str
    feeds: list[ControlTowerFeedStatus] = Field(default_factory=list)


# ── K1 Seat-Based Operating System ─────────────────────────────
class OperatingSystemSourceBoundary(BaseModel):
    system: str
    entity: str
    authority: list[str] = Field(default_factory=list)
    portal_rule: str


class OperatingSystemPortalStep(BaseModel):
    step: int
    name: str
    contract: str


class OperatingSystemSeatContract(BaseModel):
    seat_id: str
    label: str
    seat_type: str
    primary_score: str
    entity_scope: str
    source_authorities: list[str] = Field(default_factory=list)
    manager_seat_id: Optional[str] = None
    managed_seat_ids: list[str] = Field(default_factory=list)
    daily_work: list[str] = Field(default_factory=list)
    targets: dict[str, str] = Field(default_factory=dict)
    access_bundle: list[str] = Field(default_factory=list)
    scorecard_weights: dict[str, int] = Field(default_factory=dict)


class OperatingSystemManagerNode(BaseModel):
    manager_seat_id: str
    manager_label: str
    functional_seat_ids: list[str] = Field(default_factory=list)
    functional_seats: list[OperatingSystemSeatContract] = Field(default_factory=list)


class OperatingSystemOrgChartResponse(BaseModel):
    generated_at: datetime
    projection_mode: str = "read_only"
    source_document: dict[str, str]
    targets: dict[str, Union[int, float]]
    total_seats: int
    accountability_seats: int
    functional_seats: int
    seats: list[OperatingSystemSeatContract] = Field(default_factory=list)
    management_tree: list[OperatingSystemManagerNode] = Field(default_factory=list)
    source_boundaries: list[OperatingSystemSourceBoundary] = Field(default_factory=list)
    portal_workflow: list[OperatingSystemPortalStep] = Field(default_factory=list)
    endpoint_contract: list[str] = Field(default_factory=list)


class OperatingSystemTaskKpiMatrixResponse(BaseModel):
    generated_at: datetime
    projection_mode: str = "read_only"
    seats: list[OperatingSystemSeatContract] = Field(default_factory=list)
    scorecard_weights: dict[str, int] = Field(default_factory=dict)


class OperatingSystemSeatResponse(BaseModel):
    generated_at: datetime
    projection_mode: str = "read_only"
    seat: OperatingSystemSeatContract
    source_boundaries: list[OperatingSystemSourceBoundary] = Field(default_factory=list)


class OperatingSystemConfigurationItem(BaseModel):
    name: str
    env_var: str
    fallback_env_var: Optional[str] = None
    system: str
    secret: bool = False
    configured: bool = False
    purpose: str


class OperatingSystemConfigurationResponse(BaseModel):
    generated_at: datetime
    projection_mode: str = "read_only"
    api_key_required: bool
    auth_headers: list[str] = Field(default_factory=list)
    items: list[OperatingSystemConfigurationItem] = Field(default_factory=list)
    source_boundaries: list[OperatingSystemSourceBoundary] = Field(default_factory=list)
