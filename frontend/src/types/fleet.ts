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

export interface LocationStats {
  name: string
  address: string
  latitude: number
  longitude: number
  vehicle_count: number
  active: number
  safety_score: number
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

export interface HrRecruitingDataset {
  generated_at: string
  projection_mode: 'read_only'
  source_system: string
  source_authority: string
  source: string
  table_id: string
  source_status: string
  source_message: string | null
  pii_suppressed: boolean
  sla_hours: number[]
  summary: HrRecruitingSummary
  by_worklist: HrRecruitingWorklistRow[]
  daily: HrRecruitingDailyRow[]
  status_counts: HrRecruitingStatusCount[]
  trend: HrRecruitingTrendRow[]
  row_counts: Record<string, number>
  validation_errors: Record<string, number>
}
