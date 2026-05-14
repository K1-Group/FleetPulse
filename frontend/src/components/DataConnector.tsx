import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Database, TrendingUp, AlertTriangle, Truck, Fuel, Clock, Activity } from 'lucide-react'

interface VehicleKpi {
  vehicle_id?: string
  vehicle_name: string
  distance_miles?: number
  distance_km?: number
  drive_hours: number
  idle_hours: number
  trips: number
  fuel_litres: number
}

interface KpiSummary {
  total_vehicles: number
  total_distance_miles?: number
  total_distance_km?: number
  total_drive_hours: number
  total_idle_hours: number
  utilization_pct: number
}

interface VehicleKpiResponse {
  vehicles: VehicleKpi[]
  summary: KpiSummary
  period_days: number
}

interface SafetyResponse {
  fleet_daily: any[]
  vehicle_scores: any[]
  period_days: number
}

interface FaultResponse {
  faults: any[]
  period_days: number
}

type ConnectorEndpoint = 'vehicles' | 'safety' | 'faults'
type EndpointErrors = Record<ConnectorEndpoint, string | null>

const EMPTY_ENDPOINT_ERRORS: EndpointErrors = {
  vehicles: null,
  safety: null,
  faults: null,
}

export default function DataConnector() {
  const [kpis, setKpis] = useState<VehicleKpiResponse | null>(null)
  const [safety, setSafety] = useState<SafetyResponse | null>(null)
  const [faults, setFaults] = useState<FaultResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [endpointErrors, setEndpointErrors] = useState<EndpointErrors>(EMPTY_ENDPOINT_ERRORS)
  const [days, setDays] = useState(14)

  useEffect(() => {
    setLoading(true)
    setError(null)
    setEndpointErrors(EMPTY_ENDPOINT_ERRORS)
    // Helper: turn a fetch into either parsed JSON or a thrown Error so a
    // FastAPI 4xx body like { detail: "...Jurisdiction Mismatch..." } can no
    // longer slip past the .catch and crash downstream renders.
    const safeFetch = async <T,>(url: string): Promise<T> => {
      const res = await fetch(url)
      let body: any = null
      try { body = await res.json() } catch { /* non-JSON body */ }
      if (!res.ok) {
        const detail = (body && (body.detail || body.error)) || `${res.status} ${res.statusText}`
        const err: any = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
        err.status = res.status
        err.body = body
        throw err
      }
      // Defensive: even on 200, if the body looks like an error envelope, treat as error.
      if (body && typeof body === 'object' && 'detail' in body && !('vehicles' in body) && !('faults' in body) && !('vehicle_scores' in body)) {
        const err: any = new Error(String(body.detail))
        err.status = res.status
        err.body = body
        throw err
      }
      return body as T
    }

    const fetchWithRetry = async <T,>(url: string, attempts = 2): Promise<T> => {
      let lastError: unknown = null
      for (let attempt = 1; attempt <= attempts; attempt += 1) {
        try {
          return await safeFetch<T>(url)
        } catch (fetchError) {
          lastError = fetchError
          if (attempt < attempts) {
            await new Promise(resolve => window.setTimeout(resolve, 700))
          }
        }
      }
      throw lastError
    }

    const errorMessage = (reason: unknown): string => {
      return reason instanceof Error
        ? reason.message
        : String(reason || 'Unavailable')
    }

    const loadConnectorData = async () => {
      const [vehicleResult, safetyResult, faultResult] = await Promise.allSettled([
        fetchWithRetry<VehicleKpiResponse>(`/api/data-connector/vehicle-kpis?days=${days}`),
        fetchWithRetry<SafetyResponse>(`/api/data-connector/safety-scores?days=${days}`),
        fetchWithRetry<FaultResponse>(`/api/data-connector/fault-trends?days=${days}`),
      ])

      const nextErrors: EndpointErrors = { ...EMPTY_ENDPOINT_ERRORS }

      if (vehicleResult.status === 'fulfilled') {
        setKpis(vehicleResult.value)
      } else {
        setKpis(null)
        nextErrors.vehicles = errorMessage(vehicleResult.reason)
      }

      if (safetyResult.status === 'fulfilled') {
        setSafety(safetyResult.value)
      } else {
        setSafety(null)
        nextErrors.safety = errorMessage(safetyResult.reason)
      }

      if (faultResult.status === 'fulfilled') {
        setFaults(faultResult.value)
      } else {
        setFaults(null)
        nextErrors.faults = errorMessage(faultResult.reason)
      }

      setEndpointErrors(nextErrors)

      if (nextErrors.vehicles && nextErrors.safety && nextErrors.faults) {
        setError('All Data Connector feeds are temporarily unavailable.')
      }
    }

    loadConnectorData()
      .catch(e => {
        setError(e.message || 'Failed to load Data Connector')
      })
      .finally(() => setLoading(false))
  }, [days])

  const numeric = (value: unknown): number => {
    const parsed = Number(value ?? 0)
    return Number.isFinite(parsed) ? parsed : 0
  }

  const vehicleDistanceMiles = (vehicle: VehicleKpi): number => {
    if (vehicle.distance_miles !== undefined) {
      return numeric(vehicle.distance_miles)
    }
    return numeric(vehicle.distance_km) * 0.621371
  }

  const summaryDistanceMiles = (value?: KpiSummary): number => {
    if (!value) {
      return 0
    }
    if (value.total_distance_miles !== undefined) {
      return numeric(value.total_distance_miles)
    }
    return numeric(value.total_distance_km) * 0.621371
  }

  const summary = kpis?.summary
  const vehicles = kpis?.vehicles || []
  const topDistanceVehicle = vehicles[0]
  const highestIdleVehicle = vehicles.reduce<VehicleKpi | null>(
    (current, vehicle) => (current === null || numeric(vehicle.idle_hours) > numeric(current.idle_hours) ? vehicle : current),
    null,
  )
  const faultCount = faults?.faults?.length || 0
  const distanceLabel = summary ? `${(summaryDistanceMiles(summary) / 1000).toFixed(1)}k mi` : '0 mi'
  const totalDriveHours = numeric(summary?.total_drive_hours)
  const totalIdleHours = numeric(summary?.total_idle_hours)
  const utilizationPct = numeric(summary?.utilization_pct)
  const activeEndpointErrors = Object.entries(endpointErrors).filter(([, message]) => Boolean(message))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Database className="w-6 h-6 text-cyan-400" />
          <div>
            <h2 className="text-xl font-bold text-white">Data Connector Analytics</h2>
            <p className="text-sm text-gray-400">Pre-aggregated fleet metrics via Geotab OData</p>
          </div>
        </div>
        <select
          value={days}
          onChange={e => setDays(Number(e.target.value))}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
        >
          <option value={1}>Last 24h</option>
          <option value={7}>Last 7 days</option>
          <option value={14}>Last 14 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      {(error || activeEndpointErrors.length > 0) && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 mt-0.5" />
            <div>
              <p className="text-amber-200 font-medium">
                {error ? 'Data Connector is in degraded mode' : 'Some Data Connector panels are retrying'}
              </p>
              <p className="text-amber-100/70 text-sm mt-1">
                Live Geotab vehicle data remains read-only. Any temporary OData 500 will be isolated to its panel instead of blocking the full tab.
              </p>
              {activeEndpointErrors.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {activeEndpointErrors.map(([endpoint, message]) => (
                    <span
                      key={endpoint}
                      className="rounded-md bg-amber-500/10 px-2 py-1 text-xs text-amber-100/80"
                      title={message || undefined}
                    >
                      {endpoint}: {message}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="bg-gray-800/50 rounded-xl p-4 animate-pulse h-24" />
          ))}
        </div>
      ) : (
        <>
          {/* Summary KPI Cards */}
          {summary && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
              {[
                { label: 'Vehicles', value: summary.total_vehicles, icon: Truck, color: 'text-blue-400' },
                { label: 'Total Distance', value: distanceLabel, icon: TrendingUp, color: 'text-emerald-400' },
                { label: 'Drive Hours', value: `${totalDriveHours.toFixed(0)}h`, icon: Clock, color: 'text-purple-400' },
                { label: 'Idle Hours', value: `${totalIdleHours.toFixed(0)}h`, icon: Clock, color: 'text-amber-400' },
                { label: 'Utilization', value: `${utilizationPct}%`, icon: Activity, color: 'text-cyan-400' },
              ].map(({ label, value, icon: Icon, color }, i) => (
                <motion.div
                  key={label}
                  className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.1 }}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Icon className={`w-4 h-4 ${color}`} />
                    <span className="text-xs text-gray-400">{label}</span>
                  </div>
                  <p className="text-2xl font-bold text-white">{value}</p>
                </motion.div>
              ))}
            </div>
          )}

          {summary && (
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <motion.div
                className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2 }}
              >
                <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                  <Activity className="w-5 h-5 text-cyan-400" />
                  Daily Ops Review
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                  <div className="rounded-lg bg-gray-700/30 p-3">
                    <p className="text-gray-400">Utilization</p>
                    <p className="mt-1 text-xl font-semibold text-white">{utilizationPct}%</p>
                  </div>
                  <div className="rounded-lg bg-gray-700/30 p-3">
                    <p className="text-gray-400">Fault Items</p>
                    <p className="mt-1 text-xl font-semibold text-white">{faultCount}</p>
                  </div>
                  <div className="rounded-lg bg-gray-700/30 p-3">
                    <p className="text-gray-400">Top Miler</p>
                    <p className="mt-1 text-sm font-semibold text-white">{topDistanceVehicle?.vehicle_name || '—'}</p>
                    <p className="text-xs text-gray-400">{topDistanceVehicle ? `${vehicleDistanceMiles(topDistanceVehicle).toFixed(1)} mi` : 'Awaiting feed'}</p>
                  </div>
                  <div className="rounded-lg bg-gray-700/30 p-3">
                    <p className="text-gray-400">Idle Watch</p>
                    <p className="mt-1 text-sm font-semibold text-white">{highestIdleVehicle?.vehicle_name || '—'}</p>
                    <p className="text-xs text-gray-400">{highestIdleVehicle ? `${numeric(highestIdleVehicle.idle_hours).toFixed(1)}h idle` : 'Awaiting feed'}</p>
                  </div>
                </div>
              </motion.div>

              <motion.div
                className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.25 }}
              >
                <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                  <TrendingUp className="w-5 h-5 text-emerald-400" />
                  Weekly Management Review
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                  <div className="rounded-lg bg-gray-700/30 p-3">
                    <p className="text-gray-400">Period Distance</p>
                    <p className="mt-1 text-xl font-semibold text-white">{distanceLabel}</p>
                  </div>
                  <div className="rounded-lg bg-gray-700/30 p-3">
                    <p className="text-gray-400">Active Assets</p>
                    <p className="mt-1 text-xl font-semibold text-white">{summary.total_vehicles}</p>
                  </div>
                  <div className="rounded-lg bg-gray-700/30 p-3">
                    <p className="text-gray-400">Drive vs Idle</p>
                    <p className="mt-1 text-xl font-semibold text-white">{totalDriveHours.toFixed(0)}h / {totalIdleHours.toFixed(0)}h</p>
                  </div>
                  <div className="rounded-lg bg-gray-700/30 p-3">
                    <p className="text-gray-400">Review Window</p>
                    <p className="mt-1 text-xl font-semibold text-white">{days} day{days === 1 ? '' : 's'}</p>
                  </div>
                </div>
              </motion.div>
            </div>
          )}

          {/* Vehicle Utilization Table */}
          {kpis && Array.isArray(kpis.vehicles) && kpis.vehicles.length > 0 && (
            <motion.div
              className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3 }}
            >
              <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                <Truck className="w-5 h-5 text-blue-400" />
                Vehicle Utilization ({days}-day)
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-gray-400 border-b border-gray-700">
                      <th className="text-left py-2 px-2">Vehicle</th>
                      <th className="text-right py-2 px-2">Distance (mi)</th>
                      <th className="text-right py-2 px-2">Drive (h)</th>
                      <th className="text-right py-2 px-2">Idle (h)</th>
                      <th className="text-right py-2 px-2">Trips</th>
                      <th className="text-right py-2 px-2">Fuel (L)</th>
                      <th className="text-right py-2 px-2">Utilization</th>
                    </tr>
                  </thead>
                  <tbody>
                    {kpis.vehicles.slice(0, 20).map((v, i) => {
                      const driveHours = numeric(v.drive_hours)
                      const idleHours = numeric(v.idle_hours)
                      const util = driveHours + idleHours > 0
                        ? (driveHours / (driveHours + idleHours) * 100)
                        : 0
                      const geotabIdTitle = v.vehicle_id && v.vehicle_id !== v.vehicle_name
                        ? `Geotab id: ${v.vehicle_id}`
                        : undefined
                      return (
                        <tr
                          key={v.vehicle_id || v.vehicle_name || i}
                          className="border-b border-gray-700/30 hover:bg-gray-700/20"
                        >
                          <td
                            className="py-2 px-2 text-white"
                            title={geotabIdTitle}
                          >
                            {v.vehicle_name}
                          </td>
                          <td className="text-right py-2 px-2">{vehicleDistanceMiles(v).toFixed(1)}</td>
                          <td className="text-right py-2 px-2">{driveHours.toFixed(1)}</td>
                          <td className="text-right py-2 px-2 text-amber-400">{idleHours.toFixed(1)}</td>
                          <td className="text-right py-2 px-2">{v.trips}</td>
                          <td className="text-right py-2 px-2">{numeric(v.fuel_litres).toFixed(1)}</td>
                          <td className="text-right py-2 px-2">
                            <span className={util > 70 ? 'text-emerald-400' : util > 40 ? 'text-amber-400' : 'text-red-400'}>
                              {util.toFixed(0)}%
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </motion.div>
          )}

          {/* Safety Scores */}
          {safety && Array.isArray(safety.vehicle_scores) && safety.vehicle_scores.length > 0 && (
            <motion.div
              className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.4 }}
            >
              <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-amber-400" />
                Safety Scores (Data Connector)
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {safety.vehicle_scores.slice(0, 8).map((s: any, i: number) => (
                  <div key={i} className="bg-gray-700/30 rounded-lg p-3">
                    <p className="text-sm text-gray-400">{s.VehicleName || s.DriverName || `Vehicle ${i + 1}`}</p>
                    <p className="text-xl font-bold text-white">{s.SafetyScore ?? s.Score ?? '—'}</p>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {/* Fault Trends */}
          {faults && Array.isArray(faults.faults) && faults.faults.length > 0 && (
            <motion.div
              className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5 }}
            >
              <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-red-400" />
                Fault Code Trends
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-gray-400 border-b border-gray-700">
                      <th className="text-left py-2 px-2">Vehicle</th>
                      <th className="text-left py-2 px-2">Fault Code</th>
                      <th className="text-right py-2 px-2">Count</th>
                      <th className="text-left py-2 px-2">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {faults.faults.slice(0, 15).map((f: any, i: number) => (
                      <tr key={i} className="border-b border-gray-700/30">
                        <td className="py-2 px-2 text-white">{f.VehicleName || '—'}</td>
                        <td className="py-2 px-2">{f.FaultCode || f.DiagnosticName || '—'}</td>
                        <td className="text-right py-2 px-2 text-red-400">{f.Count || f.FaultCount || 1}</td>
                        <td className="py-2 px-2 text-gray-400">{f.Date || f.Day || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>
          )}

          {/* Empty state */}
          {kpis && Array.isArray(kpis.vehicles) && kpis.vehicles.length === 0 && (
            <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-8 text-center">
              <Database className="w-10 h-10 text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400">No Data Connector data available yet.</p>
              <p className="text-gray-500 text-sm mt-1">Data pipeline may take 2-3 hours to backfill after activation.</p>
            </div>
          )}

          {!kpis && endpointErrors.vehicles && (
            <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-8 text-center">
              <Database className="w-10 h-10 text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400">Vehicle KPI feed is temporarily unavailable.</p>
              <p className="text-gray-500 text-sm mt-1">The Connector tab will keep safety and fault panels available when those feeds respond.</p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
