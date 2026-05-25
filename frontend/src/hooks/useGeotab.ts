import { useState, useEffect, useCallback } from 'react'
import type {
  Alert,
  AuthSession,
  ControlTowerAgentsResponse,
  ControlTowerAttentionResponse,
  ControlTowerCodexResponse,
  ControlTowerFinancialResponse,
  ControlTowerOverview,
  ControlTowerSeatKpiCoverageResponse,
  ControlTowerTrailerTrackingResponse,
  ControlTowerTrailersResponse,
  DataConnectorSafetyResponse,
  DataConnectorVehicleKpiResponse,
  DashboardValidationResponse,
  DeliveryCenterPerformanceSnapshot,
  DepartmentCallAnalysisDataset,
  DriverWorkforceResponse,
  DriverCoachingDetail,
  DriverCoachingProfile,
  EntityMarginSnapshot,
  DriverScore,
  FleetCoachingSummary,
  FleetOverview,
  FuelTrend,
  HrCallAnalysisDataset,
  HrRecruitingDataset,
  LaneStabilityPayload,
  OperatingSystemConfigurationResponse,
  LocationStats,
  OperatingSystemOrgChartResponse,
  OperatingSystemTaskKpiMatrixResponse,
  OperatingCostSnapshot,
  Vehicle,
  VehicleSafetyScore,
} from '../types/fleet'

const API = '/api'

function currentYearStart() {
  return `${new Date().getFullYear()}-01-01`
}

function currentReturnTo() {
  if (typeof window === 'undefined') return '/'
  return `${window.location.pathname}${window.location.search}${window.location.hash || ''}`
}

// Fetch with timeout to prevent infinite loading
const fetchWithTimeout = async (url: string, timeout = 10000) => {
  const controller = new AbortController()
  const id = setTimeout(() => controller.abort(), timeout)
  
  try {
    const response = await fetch(url, { signal: controller.signal })
    clearTimeout(id)
    return response
  } catch (error: any) {
    clearTimeout(id)
    if (error.name === 'AbortError') {
      throw new Error('Request timeout - data may be unavailable')
    }
    throw error
  }
}

function useFetch<T>(url: string, interval = 30000, enabled = true, timeout = 10000) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    if (!enabled) {
      setLoading(false)
      return
    }
    try {
      const res = await fetchWithTimeout(url, timeout)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setData(await res.json())
      setError(null)
    } catch (e: any) {
      setError(e.message)
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [enabled, timeout, url])

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return undefined
    }
    fetchData()
    const id = setInterval(fetchData, interval)
    return () => clearInterval(id)
  }, [enabled, fetchData, interval])

  return { data, loading, error, refresh: fetchData }
}

export function useFleetOverview(enabled = true) {
  return useFetch<FleetOverview>(`${API}/dashboard/overview`, 30000, enabled)
}

export function useAuthSession(enabled = true) {
  const returnTo = encodeURIComponent(currentReturnTo())
  return useFetch<AuthSession>(`${API}/auth/session?return_to=${returnTo}`, 60000, enabled)
}

export function useVehicles(enabled = true) {
  return useFetch<Vehicle[]>(`${API}/vehicles/`, 30000, enabled)
}

export function useSafetyScores(enabled = true) {
  return useFetch<VehicleSafetyScore[]>(`${API}/safety/scores`, 30000, enabled)
}

export function useLeaderboard(enabled = true) {
  return useFetch<DriverScore[]>(`${API}/gamification/leaderboard`, 30000, enabled)
}

export function useAlerts(enabled = true) {
  return useFetch<Alert[]>(`${API}/alerts/recent`, 15000, enabled)
}

export function useLocations(enabled = true) {
  return useFetch<LocationStats[]>(`${API}/dashboard/locations`, 30000, enabled)
}

export function useDashboardValidation(enabled = true) {
  return useFetch<DashboardValidationResponse>(`${API}/dashboard/validation`, 60000, enabled)
}

export function useFuelTrends(enabled = true) {
  return useFetch<FuelTrend[]>(`${API}/fuel/trends`, 300000, enabled, 25000)
}

export function useDataConnectorVehicleKpis(days = 7, enabled = true) {
  return useFetch<DataConnectorVehicleKpiResponse>(
    `${API}/data-connector/vehicle-kpis?days=${days}`,
    300000,
    enabled,
    25000,
  )
}

export function useDataConnectorSafetyScores(days = 7, enabled = true) {
  return useFetch<DataConnectorSafetyResponse>(
    `${API}/data-connector/safety-scores?days=${days}`,
    300000,
    enabled,
    25000,
  )
}

export function useDriverWorkforce(enabled = true) {
  return useFetch<DriverWorkforceResponse>(`${API}/driver-workforce`, 30000, enabled)
}

export function useMonitorAlerts(enabled = true) {
  return useFetch<Alert[]>(`${API}/monitor/alerts`, 15000, enabled)
}

export function useMonitorStatus(enabled = true) {
  return useFetch<any>(`${API}/monitor/status`, 15000, enabled)
}

export function useHrRecruitingWorklist(enabled = true, weekStart?: string) {
  const query = weekStart ? `?week_start=${encodeURIComponent(weekStart)}` : ''
  return useFetch<HrRecruitingDataset>(`${API}/hr-recruiting/worklist${query}`, 60000, enabled, 60000)
}

export function useHrCallAnalysis(enabled = true) {
  return useFetch<HrCallAnalysisDataset>(`${API}/hr-call-analysis/dashboard`, 60000, enabled, 60000)
}

export function useDepartmentCallAnalysis(department?: string, enabled = true) {
  const query = department ? `?department=${encodeURIComponent(department)}` : ''
  return useFetch<DepartmentCallAnalysisDataset>(`${API}/department-call-analysis/dashboard${query}`, 60000, enabled, 60000)
}

// Driver Coaching hooks
export function useCoachingDrivers() {
  return useFetch<DriverCoachingProfile[]>(`${API}/coaching/drivers`, 60000) // Update every minute
}

export function useCoachingDriver(driverId: string) {
  return useFetch<DriverCoachingDetail>(`${API}/coaching/driver/${driverId}`, 30000)
}

export function useCoachingReports() {
  return useFetch<FleetCoachingSummary>(`${API}/coaching/reports`, 60000)
}

// Function to acknowledge coaching for a driver
export async function acknowledgeCoaching(driverId: string) {
  try {
    const response = await fetch(`${API}/coaching/acknowledge/${driverId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    })
    if (!response.ok) {
      throw new Error(`${response.status}`)
    }
    return await response.json()
  } catch (error) {
    console.error('Failed to acknowledge coaching:', error)
    throw error
  }
}

// Maintenance hooks
export function useMaintenancePredictions() {
  return useFetch<any[]>(`${API}/maintenance/predictions`)
}

export function useMaintenanceIntelligence(enabled = true) {
  return useFetch<any>(`${API}/maintenance/intelligence`, 300000, enabled, 25000)
}

export function useMaintenanceCosts() {
  return useFetch<any>(`${API}/maintenance/costs`)
}

export function useUrgentMaintenance() {
  return useFetch<any[]>(`${API}/maintenance/urgent`)
}

export function useVehicleMaintenance(vehicleId: string) {
  return useFetch<any>(`${API}/maintenance/vehicle/${vehicleId}`)
}

// Original Control Tower surfaces
export function useControlTowerOverview() {
  return useFetch<ControlTowerOverview>(`${API}/control-tower/overview`, 60000)
}

export function useControlTowerAttention() {
  return useFetch<ControlTowerAttentionResponse>(`${API}/control-tower/attention`, 30000)
}

export function useControlTowerTrailers() {
  return useFetch<ControlTowerTrailersResponse>(`${API}/control-tower/trailers`, 60000)
}

export function useControlTowerTrailerTracking(enabled = true) {
  return useFetch<ControlTowerTrailerTrackingResponse>(`${API}/control-tower/trailers/live`, 30000, enabled)
}

export function useControlTowerFinancial(enabled = true) {
  return useFetch<ControlTowerFinancialResponse>(`${API}/control-tower/financial`, 60000, enabled, 60000)
}

export function useControlTowerSeatKpis(enabled = true) {
  return useFetch<ControlTowerSeatKpiCoverageResponse>(`${API}/control-tower/seat-kpis`, 300000, enabled, 60000)
}

export function useOperatingCostWindow(days = 364, enabled = true) {
  return useFetch<OperatingCostSnapshot>(`${API}/fuel/operating-cost?days=${days}`, 300000, enabled, 300000)
}

export function useLaneStabilityWindow(windowDays: 42 | 91 | 182 | 364 = 364, enabled = true) {
  return useFetch<LaneStabilityPayload>(`${API}/lane-stability?window=${windowDays}`, 300000, enabled, 60000)
}

export function useEntityMarginYtd(enabled = true) {
  return useFetch<EntityMarginSnapshot>(
    `${API}/fuel/entity-margin?start=${currentYearStart()}`,
    300000,
    enabled,
    90000,
  )
}

export function useDeliveryCenterPerformanceYtd(enabled = true) {
  return useFetch<DeliveryCenterPerformanceSnapshot>(
    `${API}/fuel/delivery-center-performance?start=${currentYearStart()}`,
    300000,
    enabled,
    90000,
  )
}

export function useControlTowerAgents() {
  return useFetch<ControlTowerAgentsResponse>(`${API}/control-tower/agents`, 30000)
}

export function useControlTowerCodex() {
  return useFetch<ControlTowerCodexResponse>(`${API}/control-tower/codex`, 60000)
}

// K1 Seat-Based Operating System hooks
export function useOperatingSystemOrgChart() {
  return useFetch<OperatingSystemOrgChartResponse>(`${API}/operating-system/org-chart`, 60000)
}

export function useOperatingSystemTaskKpiMatrix(enabled = true) {
  return useFetch<OperatingSystemTaskKpiMatrixResponse>(`${API}/operating-system/task-kpi-matrix`, 60000, enabled)
}

export function useOperatingSystemConfiguration() {
  return useFetch<OperatingSystemConfigurationResponse>(`${API}/operating-system/configuration`, 60000)
}
