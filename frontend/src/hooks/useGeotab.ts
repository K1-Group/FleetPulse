import { useState, useEffect, useCallback } from 'react'
import type {
  Alert,
  ControlTowerAgentsResponse,
  ControlTowerAttentionResponse,
  ControlTowerCodexResponse,
  ControlTowerFinancialResponse,
  ControlTowerOverview,
  ControlTowerTrailerTrackingResponse,
  ControlTowerTrailersResponse,
  DriverCoachingDetail,
  DriverCoachingProfile,
  DriverScore,
  FleetCoachingSummary,
  FleetOverview,
  LocationStats,
  Vehicle,
  VehicleSafetyScore,
} from '../types/fleet'

const API = '/api'

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

function useFetch<T>(url: string, interval = 30000) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const res = await fetchWithTimeout(url, 10000)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setData(await res.json())
      setError(null)
    } catch (e: any) {
      setError(e.message)
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [url])

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, interval)
    return () => clearInterval(id)
  }, [fetchData, interval])

  return { data, loading, error, refresh: fetchData }
}

export function useFleetOverview() {
  return useFetch<FleetOverview>(`${API}/dashboard/overview`)
}

export function useVehicles() {
  return useFetch<Vehicle[]>(`${API}/vehicles/`)
}

export function useSafetyScores() {
  return useFetch<VehicleSafetyScore[]>(`${API}/safety/scores`)
}

export function useLeaderboard() {
  return useFetch<DriverScore[]>(`${API}/gamification/leaderboard`)
}

export function useAlerts() {
  return useFetch<Alert[]>(`${API}/alerts/recent`, 15000)
}

export function useLocations() {
  return useFetch<LocationStats[]>(`${API}/dashboard/locations`)
}

export function useMonitorAlerts() {
  return useFetch<Alert[]>(`${API}/monitor/alerts`, 15000)
}

export function useMonitorStatus() {
  return useFetch<any>(`${API}/monitor/status`, 15000)
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

export function useControlTowerTrailerTracking() {
  return useFetch<ControlTowerTrailerTrackingResponse>(`${API}/control-tower/trailers/live`, 30000)
}

export function useControlTowerFinancial() {
  return useFetch<ControlTowerFinancialResponse>(`${API}/control-tower/financial`, 60000)
}

export function useControlTowerAgents() {
  return useFetch<ControlTowerAgentsResponse>(`${API}/control-tower/agents`, 30000)
}

export function useControlTowerCodex() {
  return useFetch<ControlTowerCodexResponse>(`${API}/control-tower/codex`, 60000)
}
