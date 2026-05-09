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
