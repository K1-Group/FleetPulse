export type VehicleStatus = 'active' | 'idle' | 'parked' | 'offline'
export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical'
export type TrendDirection = 'improving' | 'declining' | 'stable'

export interface VehiclePosition {
  latitude: number
  longitude: number
  bearing: number
  speed: number
}

export interface Vehicle {
  id: string
  name: string
  status: VehicleStatus
  position: VehiclePosition | null
  location_name: string | null
  odometer_km: number
  last_contact: string | null
}

export interface FleetOverview {
  total_vehicles: number
  active: number
  idle: number
  parked: number
  offline: number
  total_trips_today: number
  total_stops_today: number
  total_distance_miles: number
  avg_trip_duration_min: number
  avg_trip_duration_hours: number
  avg_trip_distance_miles: number
  target_trip_duration_hours: number
  trips_meeting_target: number
  trips_under_target: number
  trip_definition: string
}

export interface AuthSessionUser {
  display_name: string
  email: string | null
  principal_id: string | null
}

export interface AuthSeat {
  display_name: string
  id: string
  tabs: string[]
}

export interface AuthSeatAccess {
  allowed_tabs: string[]
  authorization_mode: 'optional' | 'enforced'
  authorized: boolean
  config_ready: boolean
  denied_reason: string | null
  primary_seat: AuthSeat | null
  projection_mode: 'read_only'
  public_tabs: string[]
  seats: AuthSeat[]
  source_authority: string
  write_back_allowed: boolean
}

export interface AuthSession {
  auth_mode: 'required' | 'optional' | 'disabled'
  auth_required: boolean
  login_enabled: boolean
  authenticated: boolean
  identity_provider: string | null
  seat_access: AuthSeatAccess
  user: AuthSessionUser | null
  login_url: string | null
  logout_url: string | null
  source_authority: string
  projection_mode: 'read_only'
}

export interface DataConnectorVehicleKpiSummary {
  total_vehicles: number
  total_distance_miles?: number
  total_distance_km?: number
  total_drive_hours: number
  total_idle_hours: number
  utilization_pct: number
}

export interface DataConnectorVehicleKpiResponse {
  vehicles: Array<{
    vehicle_id?: string
    vehicle_name: string
    distance_miles?: number
    distance_km?: number
    drive_hours: number
    idle_hours: number
    trips: number
    fuel_litres: number
  }>
  summary: DataConnectorVehicleKpiSummary
  period_days: number
  feed_status?: string
  message?: string
  source_authority?: string
  projection_mode?: 'read_only' | string
}

export interface LocationStats {
  name: string
  address: string
  latitude: number
  longitude: number
  radius_miles: number
  radius_meters: number
  vehicle_count: number
  active: number
  safety_score: number
}

export type DashboardValidationStatus = 'verified' | 'pending' | 'pending_no_data' | 'pending_no_audit' | 'stale' | 'failed'

export interface DashboardValidationItem {
  blocked_by: string | null
  checked_at: string
  contract: Record<string, unknown>
  key: string
  label: string
  message: string
  metrics: string[]
  next_check: string | null
  projection_mode: 'read_only'
  required_config: string[]
  row_count: number | null
  source_authority: string
  status: DashboardValidationStatus
  verified: boolean
}

export interface DashboardValidationResponse {
  generated_at: string
  projection_mode: 'read_only'
  sections: Record<string, DashboardValidationItem>
  metrics: Record<string, DashboardValidationItem>
  pending_ledger?: Array<{
    blocked_by: string
    key: string
    message: string
    next_check: string
    panel_name: string
    status: DashboardValidationStatus
    contract?: Record<string, unknown>
  }>
  summary: Record<DashboardValidationStatus, number>
}

export type DriverWorkforceStatus =
  | 'scheduled'
  | 'working'
  | 'near_limit'
  | 'overdue'
  | 'late_start'
  | 'complete'
  | 'active_without_ticket'
  | 'ticket_no_activity'
  | 'unmatched'

export interface DriverWorkforceKpis {
  scheduled_today: number
  working_now: number
  late_start: number
  near_limit: number
  overdue: number
  avg_time_worked_minutes: number | null
  active_without_ticket: number
  ticket_no_activity: number
}

export interface DriverWorkforceWorkday {
  driver_id: string | null
  driver_name: string | null
  vehicle_id: string | null
  vehicle_name: string | null
  ticket_id: string | null
  route_status: string
  pickup_location: string | null
  delivery_location: string | null
  planned_start: string
  planned_finish: string
  planned_hours: number
  actual_start_time: string | null
  actual_last_seen: string | null
  actual_worked_minutes: number | null
  remaining_minutes: number | null
  variance_minutes: number | null
  completion_time: string | null
  source: string
  status: DriverWorkforceStatus
  status_label: string
  time_worked_display: string
  remaining_display: string
  overlap_issue: boolean
}

export interface DriverWorkforceValidation {
  state: string
  status: DashboardValidationStatus
  message: string
  row_count: number
  joined_count: number
  invalid_ticket_count: number
  required_config?: string[]
  source_status?: string
}

export interface DriverWorkforceResponse {
  generated_at: string
  projection_mode: 'read_only'
  source_authority: string
  config: Record<string, number | string>
  operating_day: {
    start: string
    end: string
    timezone: string
  }
  source_freshness: {
    xcelerator_tickets: string | null
    geotab: string | null
  }
  kpis: DriverWorkforceKpis
  workdays: DriverWorkforceWorkday[]
  alerts: Alert[]
  insights: string[]
  validation: DriverWorkforceValidation
}

export interface EmployeeWorkforceEmployee {
  employee_id: string
  employee_name: string
  email: string | null
  department: string | null
  worked_hours: number
  productive_hours: number | null
  idle_hours: number
  productivity_pct: number | null
  days_reported: number
  active_today: boolean
  latest_activity_date: string | null
  top_projects: string[]
  source: string
}

export interface EmployeeWorkforceResponse {
  generated_at: string
  projection_mode: 'read_only'
  source_authority: string
  period: {
    start: string
    end: string
    days: number
    timezone: string
  }
  config: Record<string, number | string | boolean>
  summary: {
    employees: number
    active_today: number
    worked_hours: number
    idle_hours: number
    avg_productivity_pct: number | null
    activity_rows: number
    invalid_rows: number
    missing_timesheet_count: number
  }
  employees: EmployeeWorkforceEmployee[]
  source_status: {
    status: string
    message: string
    required_config: string[]
    row_count?: number
    api_token_configured?: boolean
    company_id_configured?: boolean
    api_base_url_configured?: boolean
  }
  validation: {
    status: DashboardValidationStatus
    state: string
    message: string
    row_count: number
    required_config?: string[]
  }
}

export type DriverComplianceDocumentStatus = 'valid' | 'warning' | 'expired' | 'missing' | string

export interface DriverComplianceDocument {
  expires_on: string | null
  days_remaining: number | null
  status: DriverComplianceDocumentStatus
}

export interface DriverComplianceDriver {
  driver_id: string
  driver_name: string
  email: string | null
  phone: string | null
  terminal: string | null
  documents: {
    medical_card: DriverComplianceDocument
    drug_test: DriverComplianceDocument
    mvr: DriverComplianceDocument
  }
  overall_status: DriverComplianceDocumentStatus
  next_expiration_date: string | null
  source: string
}

export interface DriverComplianceResponse {
  generated_at: string
  projection_mode: 'read_only'
  source_authority: string
  config: Record<string, number | string>
  summary: {
    drivers: number
    valid: number
    warning: number
    expired: number
    missing: number
    invalid_rows: number
    medical_card_expiring: number
    drug_test_expiring: number
    mvr_expiring: number
    document_status_counts: Record<string, Record<string, number>>
  }
  document_types: Array<{ key: 'medical_card' | 'drug_test' | 'mvr'; label: string; warning_days: number }>
  drivers: DriverComplianceDriver[]
  source_status: {
    status: string
    message: string
    required_config: string[]
    row_count?: number
    document_fields?: string[]
    warning_days?: number
  }
  validation: {
    status: DashboardValidationStatus
    state: string
    message: string
    row_count: number
    required_config?: string[]
  }
}

export interface AddressBenchmarkEvidenceMatch {
  source_system: string | null
  order_id: string | null
  driver_id: string | null
  occurred_at: string | null
  subject: string | null
  summary: string | null
  transcript_available: boolean
  source_uri: string | null
}

export interface AddressBenchmarkEvidenceBucket {
  status: 'matched' | 'no_matching_evidence' | string
  match_count: number
  matches: AddressBenchmarkEvidenceMatch[]
  message: string
}

export interface AddressBenchmarkDriver {
  driver_id: string | null
  driver_name: string
  measured_orders: number
  avg_route_minutes: number | null
  best_route_minutes: number | null
  worst_route_minutes: number | null
  variance_vs_pair_average_minutes: number | null
  opportunity_minutes_vs_pair_average: number | null
  estimated_opportunity_cost_vs_pair_average: number | null
  stop_events_over_threshold: number
  coaching_direction: string
}

export interface AddressBenchmarkRecentOrder {
  order_id: string
  route_date: string
  driver_id: string | null
  driver_name: string | null
  route_minutes: number | null
  duration_source: string | null
  stop_minutes: number | null
  stop_over_threshold: boolean
}

export interface AddressBenchmarkPair {
  address_pair_key: string
  pickup_address: string
  delivery_address: string
  orders: number
  measured_orders: number
  missing_actual_time_orders: number
  avg_route_minutes: number | null
  median_route_minutes: number | null
  best_route_minutes: number | null
  worst_route_minutes: number | null
  route_minutes_source: string
  stop_threshold_minutes: number
  stop_events_over_threshold: number
  opportunity_minutes_vs_pair_average: number | null
  estimated_opportunity_cost_vs_pair_average: number | null
  revenue_total: number
  driver_pay_total: number
  driver_benchmarks: AddressBenchmarkDriver[]
  recent_orders: AddressBenchmarkRecentOrder[]
  evidence: {
    voice_recordings: AddressBenchmarkEvidenceBucket
    emails: AddressBenchmarkEvidenceBucket
  }
  source_authority: string
  projection_mode: 'read_only'
}

export interface AddressBenchmarkResponse {
  generated_at: string
  projection_mode: 'read_only'
  source_authority: string
  period: {
    start: string
    end: string
    days: number
  }
  thresholds: {
    stop_threshold_minutes: number
    minimum_history_samples: number
    cost_per_truck_hour: number | null
  }
  filters: {
    pickup: string | null
    delivery: string | null
  }
  summary: {
    address_pairs: number
    route_rows_read: number
    route_rows_in_period: number
    invalid_route_rows: number
    measured_orders: number
    drivers_compared: number
    opportunity_minutes_vs_pair_average: number
    estimated_opportunity_cost_vs_pair_average: number | null
    evidence_matches: number
  }
  address_pairs: AddressBenchmarkPair[]
  evidence_sources: {
    status: string
    source_authority: string
    projection_mode: 'read_only'
    message: string
    required_config: string[]
    path: string | null
    voice_recordings: number
    emails: number
  }
  source_meta: Record<string, any>
  recommendations: string[]
}

export interface SafetyBreakdown {
  speeding: number
  harsh_braking: number
  harsh_acceleration: number
  harsh_cornering: number
}

export interface VehicleSafetyScore {
  vehicle_id: string
  vehicle_name: string
  score: number
  breakdown: SafetyBreakdown
  trend: TrendDirection
  event_count: number
}

export interface DataConnectorSafetySummary {
  safety_rank_pct: number | null
  latest_safety_rank_pct?: number | null
  latest_date: string | null
  period_start_date?: string | null
  period_end_date?: string | null
  fleet_row_count: number
  vehicle_score_count: number
  total_collision_count: number | null
  predicted_collisions_per_1m_miles: number | null
  calculation?: string
}

export interface DataConnectorSafetyResponse {
  fleet_daily: Record<string, unknown>[]
  vehicle_scores: Record<string, unknown>[]
  summary: DataConnectorSafetySummary
  period_days: number
  feed_status?: string
  source_authority?: string
  projection_mode?: 'read_only'
  message?: string
}

export interface Badge {
  id: string
  name: string
  description: string
  icon: string
  earned: boolean
  earned_at: string | null
}

export interface DriverScore {
  driver_id: string
  driver_name: string
  points: number
  safety_score: number
  badges: Badge[]
  rank: number
}

export interface Alert {
  id: string
  vehicle_id: string
  vehicle_name: string
  alert_type: string
  severity: AlertSeverity
  message: string
  timestamp: string
  acknowledged: boolean
}

export interface LocationRanking {
  location_name: string
  avg_safety_score: number
  total_points: number
  rank: number
}

// Driver Coaching Types
export type CoachingStatus = 'needs_attention' | 'on_track' | 'improved'
export type CoachingCategory = 'harsh_braking' | 'harsh_acceleration' | 'speeding' | 'cornering' | 'seatbelt'

export interface CoachingScores {
  harsh_braking: number
  harsh_acceleration: number
  speeding: number
  cornering: number
  seatbelt: number
}

export interface CoachingRecommendation {
  category: CoachingCategory
  priority: number
  message: string
  fuel_impact_pct: number
}

export interface CoachingTrend {
  current_week: number
  last_week: number
  four_weeks_avg: number
  direction: TrendDirection
}

export interface DriverCoachingProfile {
  driver_id: string
  driver_name: string
  status: CoachingStatus
  scores: CoachingScores
  overall_score: number
  recommendations: CoachingRecommendation[]
  trend: CoachingTrend
  events_this_week: number
  fuel_waste_pct: number
  acknowledged: boolean
}

export interface CoachingEventDetail {
  timestamp: string
  category: CoachingCategory
  location: string
  severity: AlertSeverity
  description: string
}

export interface DriverCoachingDetail {
  driver_id: string
  driver_name: string
  scores: CoachingScores
  trend: CoachingTrend
  recommendations: CoachingRecommendation[]
  recent_events: CoachingEventDetail[]
  weekly_stats: Record<string, number>
}

export interface FleetCoachingSummary {
  total_drivers: number
  needs_attention: number
  on_track: number
  improved: number
  average_score: number
  best_improved: string[]
  worst_performers: string[]
  fleet_fuel_savings_potential: number
}

// Control Tower projections
export type ControlTowerStatus = 'healthy' | 'warning' | 'critical' | 'awaiting_feed' | 'unavailable'

export interface ControlTowerFeedStatus {
  name: string
  source_authority: string
  status: ControlTowerStatus
  message: string
  required_config: string[]
  last_updated: string | null
}

export interface ControlTowerSectionSummary {
  key: 'attention' | 'trailers' | 'financial' | 'agents' | 'codex'
  label: string
  status: ControlTowerStatus
  source_authority: string
  item_count: number
  message: string
}

export interface ControlTowerOverview {
  generated_at: string
  projection_mode: 'read_only'
  sections: ControlTowerSectionSummary[]
}

export interface ControlTowerAttentionItem {
  id: string
  category: string
  severity: AlertSeverity
  action: string
  message: string
  source_authority: string
  timestamp: string | null
}

export interface ControlTowerAttentionResponse {
  generated_at: string
  projection_mode: 'read_only'
  items: ControlTowerAttentionItem[]
  feeds: ControlTowerFeedStatus[]
}

export interface ControlTowerTrailerSummary {
  total_trailers: number
  gps_active: number
  gps_inactive: number
  geofence_events_today: number
  yards_reporting: number
  last_email_received: string | null
}

export interface ControlTowerYardLocation {
  name: string
  latitude: number
  longitude: number
  trailer_count: number
}

export interface ControlTowerTrailerEvent {
  id: string
  trailer_id: string
  event_type: string
  location: string | null
  timestamp: string | null
  source_authority: string
}

export interface ControlTowerTrailerCustody {
  vehicle_id: string | null
  vehicle_name: string | null
  driver_id: string | null
  driver_name: string | null
  vehicle_position: VehiclePosition | null
  distance_meters: number | null
  confidence: string
  source: string
  note: string
}

export interface ControlTowerTrailerLiveAsset {
  trailer_id: string
  trailer_name: string
  geotab_device_id: string | null
  gps_status: VehicleStatus
  position: VehiclePosition | null
  location_name: string | null
  speed: number
  bearing: number
  geotab_last_contact: string | null
  xtra_last_event: ControlTowerTrailerEvent | null
  custody: ControlTowerTrailerCustody
  source_authorities: string[]
}

export interface ControlTowerTrailerTrackingSummary {
  total_trailers: number
  gps_active: number
  gps_inactive: number
  xtra_event_trailers: number
  custody_inferred: number
  custody_unassigned: number
  last_geotab_contact: string | null
  last_email_received: string | null
}

export interface ControlTowerTrailerTrackingResponse {
  generated_at: string
  projection_mode: 'read_only'
  summary: ControlTowerTrailerTrackingSummary
  trailers: ControlTowerTrailerLiveAsset[]
  feeds: ControlTowerFeedStatus[]
}

export interface ControlTowerTrailersResponse {
  generated_at: string
  projection_mode: 'read_only'
  summary: ControlTowerTrailerSummary
  yard_locations: ControlTowerYardLocation[]
  geofence_events: ControlTowerTrailerEvent[]
  bobtail_alerts: ControlTowerAttentionItem[]
  feeds: ControlTowerFeedStatus[]
}

export interface ControlTowerFinancialBucket {
  bucket: string
  amount: number | null
  count: number
}

export interface ControlTowerFinancialSummary {
  pending_amount: number | null
  pending_bills: number
  overdue_amount: number | null
  overdue_count: number
  total: number | null
}

export interface ControlTowerFinancialResponse {
  generated_at: string
  projection_mode: 'read_only'
  source_authority: string
  accounts_payable: ControlTowerFinancialSummary
  accounts_receivable: ControlTowerFinancialBucket[]
  cash_flow: Record<string, number | null>
  audit_queue: Record<string, number | string[]>
  feeds: ControlTowerFeedStatus[]
}

export interface ControlTowerSeatKpiItem {
  key: string
  label: string
  seat_id: string
  seat_label: string
  manager_seat_id: string | null
  target: string
  source_authority: string
  source_route: string | null
  status: ControlTowerStatus
  blocker: string | null
  required_config: string[]
  owner_action: string
  metric_summary: Record<string, string | number | boolean | null>
}

export interface ControlTowerSeatKpiCoverageSummary {
  total: number
  healthy: number
  warning: number
  awaiting_feed: number
  unavailable: number
  coverage_pct: number
  seats_with_missing: number
}

export interface ControlTowerSeatKpiCoverageResponse {
  generated_at: string
  projection_mode: 'read_only'
  source_authority: string
  summary: ControlTowerSeatKpiCoverageSummary
  kpis: ControlTowerSeatKpiItem[]
  feeds: ControlTowerFeedStatus[]
}

export interface OperatingCostSource {
  status: string
  source_authority?: string
  message?: string
  row_count?: number | null
  table?: string
}

export interface FuelTrend {
  date: string
  miles?: number
  gallons?: number
  cost?: number
  fuel_cost_source?: string
  transaction_count?: number
}

export interface EntityMarginSummary {
  miles: number
  drive_hours: number
  idle_hours: number
  operating_hours: number
  fuel_cost: number
  fuel_card_audit_cost: number
  maintenance_cost: number
  insurance_cost: number
  posted_insurance_cost: number
  insurance_cost_per_mile: number | null
  employee_cost: number
  rental_trucks_trailers_cost: number
  other_expense_cost: number
  k1l_orders: number
  k1l_grand_total: number
  k1l_driver_pay: number
  k1l_target_gross_margin: number
  k1l_actual_gross_margin_before_fuel: number
  k1l_actual_gross_margin_pct_before_fuel: number | null
  k1l_actual_gross_margin_after_fuel: number
  k1l_actual_gross_margin_pct_after_fuel: number | null
  k1g_orders: number
  k1g_grand_total: number
  k1g_driver_pay: number
  k1g_target_gross_margin: number
  k1g_actual_gross_margin_before_overhead: number
  k1g_actual_gross_margin_pct_before_overhead: number | null
  qbo_expenses_available: boolean
}

export interface EntityMarginSnapshot {
  period_start: string
  period_end: string
  generated_at: string
  source_authority: string
  projection_mode: 'read_only'
  grain: 'weekly'
  k1l_margin_target_pct: number
  k1g_margin_target_pct: number
  complete_k1l_cpm_available: boolean
  complete_k1l_true_cpm_available: boolean
  unresolved_sources: string[]
  true_cpm_unresolved_sources: string[]
  xcelerator_source_type?: string
  sources: Record<string, OperatingCostSource>
  summary: EntityMarginSummary | null
  weekly: Record<string, unknown>[]
  excluded_delivery_centers: Record<string, number>
  row_counts: Record<string, number>
}

export interface DeliveryCenterPerformanceRow {
  delivery_center: string
  entity: string
  orders: number
  pickup_orders: number
  pickup_measured_orders: number
  pickup_on_time_orders: number
  pickup_late_orders: number
  pickup_missing_orders: number
  pickup_missing_schedule_orders: number
  pickup_missing_actual_orders: number
  pickup_on_time_pct: number | null
  pickup_late_pct: number | null
  pickup_proof_coverage_pct: number | null
  pickup_avg_late_minutes: number | null
  pickup_max_late_minutes: number | null
  delivery_orders: number
  delivery_measured_orders: number
  delivery_on_time_orders: number
  delivery_late_orders: number
  delivery_missing_orders: number
  delivery_missing_schedule_orders: number
  delivery_missing_actual_orders: number
  delivery_on_time_pct: number | null
  delivery_late_pct: number | null
  delivery_proof_coverage_pct: number | null
  delivery_avg_late_minutes: number | null
  delivery_max_late_minutes: number | null
}

export interface DeliveryCenterPerformanceSnapshot {
  period_start: string
  period_end: string
  generated_at: string
  source_authority: string
  projection_mode: 'read_only'
  grain: 'delivery_center'
  summary: DeliveryCenterPerformanceRow | null
  delivery_centers: DeliveryCenterPerformanceRow[]
  source: OperatingCostSource & {
    missing_column_families?: string[]
  }
}

export interface OperatingCostWeeklyRow {
  week_start: string
  week_end: string
  period_start: string
  period_end: string
  miles: number
  drive_hours: number
  idle_hours: number
  operating_hours: number
  trips: number
  fuel_cost: number
  fuel_card_audit_cost: number
  driver_pay: number
  maintenance_cost: number
  insurance_cost: number
  posted_insurance_cost: number
  employee_cost: number
  rental_trucks_trailers_cost: number
  other_expense_cost: number
  known_operating_cost: number
  true_operating_cost: number | null
  known_cost_per_mile: number | null
  true_cost_per_mile: number | null
  known_cost_per_operating_hour: number | null
  true_cost_per_operating_hour: number | null
}

export interface OperatingCostSummary {
  miles: number
  drive_hours: number
  idle_hours: number
  operating_hours: number
  trips: number
  fuel_cost: number
  fuel_card_audit_cost: number
  driver_pay: number
  maintenance_cost: number
  insurance_cost: number
  posted_insurance_cost: number
  insurance_cost_per_mile: number | null
  employee_cost: number
  rental_trucks_trailers_cost: number
  other_expense_cost: number
  known_operating_cost: number
  true_operating_cost: number | null
  known_cost_per_mile: number | null
  true_cost_per_mile: number | null
  known_cost_per_operating_hour: number | null
  true_cost_per_operating_hour: number | null
}

export interface OperatingCostSnapshot {
  period_start: string
  period_end: string
  generated_at: string
  source_authority: string
  projection_mode: 'read_only'
  grain: 'weekly'
  complete_cost_available: boolean
  unresolved_sources: string[]
  sources: Record<string, OperatingCostSource>
  summary: OperatingCostSummary
  weekly: OperatingCostWeeklyRow[]
  row_counts: Record<string, number>
}

export interface LaneStabilityRow {
  snapshot_date: string
  stable_cov_pct: number
  critical_lanes: number
  cross_route_lanes: number
  total_orders: number
  scored_lanes: number
  stable_lanes: number
  total_revenue: number
  delta_cov_pp: number
}

export interface LaneStabilitySummary {
  today_stable_cov_pct: number
  wow_delta_pp: number
  critical_today: number
  cross_route_today: number
  revenue_wtd: number
}

export interface LaneStabilityPayload {
  window: 42 | 91 | 182 | 364
  generated_at: string
  rows: LaneStabilityRow[]
  summary: LaneStabilitySummary
  source_authority?: string
  projection_mode?: 'read_only'
}

export interface ControlTowerAgentFlow {
  name: string
  status: ControlTowerStatus
  detail: string
}

export interface ControlTowerAgentSystem {
  name: string
  status: ControlTowerStatus
  usage: string | null
  flows: ControlTowerAgentFlow[]
}

export interface ControlTowerAgentsResponse {
  generated_at: string
  projection_mode: 'read_only'
  systems: ControlTowerAgentSystem[]
}

export interface ControlTowerCodexResponse {
  generated_at: string
  projection_mode: 'read_only'
  overall_status: ControlTowerStatus
  repository: string | null
  branch: string | null
  commit_sha: string | null
  run_id: string | null
  message: string
  feeds: ControlTowerFeedStatus[]
}

// K1 Seat-Based Operating System
export interface OperatingSystemSourceBoundary {
  system: string
  entity: string
  authority: string[]
  portal_rule: string
}

export interface OperatingSystemPortalStep {
  step: number
  name: string
  contract: string
}

export interface OperatingSystemSeatContract {
  seat_id: string
  label: string
  seat_type: 'accountability' | 'functional'
  primary_score: string
  entity_scope: string
  source_authorities: string[]
  manager_seat_id: string | null
  managed_seat_ids: string[]
  daily_work: string[]
  targets: Record<string, string>
  access_bundle: string[]
  scorecard_weights: Record<string, number>
}

export interface OperatingSystemManagerNode {
  manager_seat_id: string
  manager_label: string
  functional_seat_ids: string[]
  functional_seats: OperatingSystemSeatContract[]
}

export interface OperatingSystemOrgChartResponse {
  generated_at: string
  projection_mode: 'read_only'
  source_document: Record<string, string>
  targets: Record<string, number>
  total_seats: number
  accountability_seats: number
  functional_seats: number
  seats: OperatingSystemSeatContract[]
  management_tree: OperatingSystemManagerNode[]
  source_boundaries: OperatingSystemSourceBoundary[]
  portal_workflow: OperatingSystemPortalStep[]
  endpoint_contract: string[]
}

export interface OperatingSystemTaskKpiMatrixResponse {
  generated_at: string
  projection_mode: 'read_only'
  seats: OperatingSystemSeatContract[]
  scorecard_weights: Record<string, number>
}

export interface OperatingSystemConfigurationItem {
  name: string
  env_var: string
  fallback_env_var: string | null
  system: string
  secret: boolean
  configured: boolean
  purpose: string
}

export interface OperatingSystemConfigurationResponse {
  generated_at: string
  projection_mode: 'read_only'
  api_key_required: boolean
  auth_headers: string[]
  items: OperatingSystemConfigurationItem[]
  source_boundaries: OperatingSystemSourceBoundary[]
}

// HR recruiting worklist monitor
export interface HrRecruitingSummary {
  active_leads: number
  new_leads_today: number
  avg_process_age_hours: number
  stale_leads: number
  completed_today: number
  new_hires_7d: number
  active_qualified_pipeline: number
  first_touch_24h_pct: number | null
  first_touch_eligible_count: number
  first_touch_within_24h_count: number
  stale_untouched_48h: number
  orientation_scheduled_count: number
  orientation_show_count: number
  orientation_show_rate: number | null
}

export type HrRecruitingHardTargetStatus = 'healthy' | 'warning' | 'awaiting_feed'

export interface HrRecruitingHardTarget {
  key: string
  label: string
  actual: number | null
  target: number
  operator: '>=' | '<=' | '=' | string
  unit: string
  cadence: string
  display_target: string
  status: HrRecruitingHardTargetStatus
}

export interface HrRecruitingWorklistRow {
  worklist: string
  active_leads: number
  new_leads_today: number
  avg_age_hours: number
  max_age_hours: number
  stale_24h: number
  stale_48h: number
  stale_72h: number
}

export interface HrRecruitingDailyRow {
  date: string
  worklist: string
  new_leads: number
  completed_leads: number
  active_leads: number
  avg_process_time_hours: number
}

export interface HrRecruitingStatusCount {
  status: string
  count: number
}

export interface HrRecruitingTrendRow {
  date: string
  active_leads: number
  new_leads: number
  stale_leads: number
  avg_age_hours: number
}

export interface HrRecruitingWorkbookBucket {
  bucket: string
  count: number
}

export interface HrRecruitingWorkbookMemberKpi {
  hr_member: string
  lead_count: number
  within_24h: number
  recovered_24_48h: number
  late_48_72h: number
  failed_over_72h: number
  avg_hours: number | null
  median_hours: number | null
  within_24h_rate: number | null
  total_outbound_attempts: number
}

export interface HrRecruitingWorkbookSourceQa {
  file: string
  row_count: number
  column_count: number
  used_for_mapping: boolean
  notes: string
  first_columns: string
}

export interface HrRecruitingPeriodFilter {
  grain: 'all' | 'week' | string
  week_start: string | null
  week_end: string | null
  timezone: string
  date_field: string | null
}

export interface HrRecruitingWorkbookEvidence {
  workbook_name: string | null
  period_filter?: HrRecruitingPeriodFilter
  tabs: Array<{ sheet: string; row_count: number; status: string }>
  missing_tabs: string[]
  kpi_summary: Record<string, number | null>
  first_outreach_buckets: HrRecruitingWorkbookBucket[]
  real_discussion_buckets: HrRecruitingWorkbookBucket[]
  first_outreach_by_member: HrRecruitingWorkbookMemberKpi[]
  real_discussion_by_member: HrRecruitingWorkbookMemberKpi[]
  source_log_qa: HrRecruitingWorkbookSourceQa[]
}

export interface HrRecruitingDataset {
  generated_at: string
  projection_mode: 'read_only'
  source_profile: 'worklist_snapshot' | 'kpi_workbook' | string
  source_system: string
  source_authority: string
  source: string
  source_artifact: string | null
  table_id: string
  source_status: string
  source_message: string | null
  period_filter: HrRecruitingPeriodFilter
  pii_suppressed: boolean
  sla_hours: number[]
  hard_targets: Record<string, HrRecruitingHardTarget>
  hard_target_status: HrRecruitingHardTargetStatus
  hard_target_misses: string[]
  hard_target_pending: string[]
  summary: HrRecruitingSummary
  by_worklist: HrRecruitingWorklistRow[]
  daily: HrRecruitingDailyRow[]
  status_counts: HrRecruitingStatusCount[]
  trend: HrRecruitingTrendRow[]
  row_counts: Record<string, number>
  validation_errors: Record<string, number>
  workbook_evidence?: HrRecruitingWorkbookEvidence
}

// HR call-analysis and productivity monitor
export interface HrCallAnalysisSummary {
  total_call_legs: number
  total_minutes: number
  avg_call_seconds: number
  outbound_attempts: number
  connected_calls: number
  connect_rate_pct: number | null
  voicemails: number
  hangups: number
  active_employee_count: number
  analysis_reports: number
  coaching_flags: number
  urgent_flags: number
  unresolved_calls: number
  human_error_reports: number
  first_call_eligible_leads: number
  first_call_within_24h: number
  first_call_24h_pct: number | null
  stale_no_call_48h: number
}

export interface HrCallEmployeeProductivity {
  department?: string
  extension_id: string
  employee_name: string
  productivity_score_0_100: number
  call_legs: number
  voice_call_legs: number
  distinct_external_parties: number
  total_minutes: number
  outbound_legs: number
  connected_legs: number
  not_connected_legs: number
  voicemails: number
  hangups: number
  connected_rate_pct: number
  voicemail_rate_pct: number
  hangup_rate_pct: number
}

export interface HrCallDailyVolume {
  date: string
  call_legs: number
  outbound_attempts: number
  connected_calls: number
  voicemails: number
  total_minutes: number
}

export interface HrCallCoachingFlag {
  analysis_file_key: string
  department?: string
  call_date: string | null
  agent_name: string
  category: string
  sentiment: string
  resolved: boolean | null
  resolution_quality: string
  action_items_count: number
  flag_reasons: string
}

export interface HrCallAnalysisDataset {
  generated_at: string
  projection_mode: 'read_only'
  source_system: string
  source_authority: string
  department?: string
  department_key?: string
  source_status: string
  source_message: string | null
  last_imported_at: string | null
  pii_suppressed: boolean
  phone_numbers_stored: boolean
  active_extensions: string[]
  coverage: {
    start: string | null
    end: string | null
    months: string[]
  }
  summary: HrCallAnalysisSummary
  employee_productivity: HrCallEmployeeProductivity[]
  monthly_employee_productivity: Array<HrCallEmployeeProductivity & { month: string }>
  daily_volume: HrCallDailyVolume[]
  follow_up: Record<string, unknown>[]
  coaching_flags: HrCallCoachingFlag[]
  row_counts: Record<string, number>
  validation_notes: string[]
}

export interface DepartmentCallAnalysisRollup {
  department: string
  department_key: string
  source_status: string
  coverage: HrCallAnalysisDataset['coverage']
  summary: HrCallAnalysisSummary
  row_counts: Record<string, number>
  top_employees: HrCallEmployeeProductivity[]
  coaching_flags: HrCallCoachingFlag[]
}

export interface DepartmentCallAnalysisDataset extends HrCallAnalysisDataset {
  department: string
  department_key: string
  configured_departments: string[]
  department_rollups: DepartmentCallAnalysisRollup[]
}
