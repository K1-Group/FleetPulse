import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts'
import {
  Database, TrendingUp, TrendingDown, Minus, AlertTriangle,
  Truck, Clock, Activity, ChevronUp, ChevronDown, Shield,
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface VehicleKpi {
  vehicle_name: string
  distance_km: number
  drive_hours: number
  idle_hours: number
  trips: number
  fuel_litres: number
}

interface KpiSummary {
  total_vehicles: number
  total_distance_km: number
  total_drive_hours: number
  total_idle_hours: number
  utilization_pct: number
}

interface VehicleKpiResponse {
  vehicles: VehicleKpi[]
  summary: KpiSummary
  period_days: number
  demo?: boolean
}

interface VehicleScore {
  VehicleName?: string
  DriverName?: string
  SafetyScore?: number
  Score?: number
  Trend?: string
}

interface SafetyResponse {
  fleet_daily: any[]
  vehicle_scores: VehicleScore[]
  fleet_avg_score?: number | null
  period_days: number
  demo?: boolean
}

interface FaultRow {
  VehicleName?: string
  FaultCode?: string
  DiagnosticName?: string
  Severity?: string
  Count?: number
  FaultCount?: number
  Date?: string
  Day?: string
}

interface FaultResponse {
  faults: FaultRow[]
  period_days: number
  demo?: boolean
}

type SortKey = keyof VehicleKpi
type SortDir = 'asc' | 'desc'

// ── Small helpers ─────────────────────────────────────────────────────────────

function utilColor(pct: number) {
  if (pct >= 70) return 'text-emerald-400'
  if (pct >= 40) return 'text-amber-400'
  return 'text-red-400'
}

function utilBarColor(pct: number) {
  if (pct >= 70) return '#10b981'
  if (pct >= 40) return '#f59e0b'
  return '#ef4444'
}

function scoreColor(s: number) {
  if (s >= 90) return 'text-emerald-400'
  if (s >= 70) return 'text-amber-400'
  return 'text-red-400'
}

function scoreBgColor(s: number) {
  if (s >= 90) return '#10b981'
  if (s >= 70) return '#f59e0b'
  return '#ef4444'
}

function severityColor(sev?: string) {
  if (!sev) return 'text-gray-400'
  const s = sev.toLowerCase()
  if (s === 'critical') return 'text-red-400'
  if (s === 'high') return 'text-orange-400'
  if (s === 'medium') return 'text-amber-400'
  return 'text-blue-400'
}

function TrendIcon({ trend }: { trend?: string }) {
  if (!trend) return <Minus className="w-4 h-4 text-gray-500" />
  const t = trend.toLowerCase()
  if (t === 'improving') return <TrendingUp className="w-4 h-4 text-emerald-400" />
  if (t === 'declining') return <TrendingDown className="w-4 h-4 text-red-400" />
  return <Minus className="w-4 h-4 text-gray-400" />
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ChevronDown className="w-3 h-3 text-gray-600 inline ml-1" />
  return dir === 'asc'
    ? <ChevronUp className="w-3 h-3 text-blue-400 inline ml-1" />
    : <ChevronDown className="w-3 h-3 text-blue-400 inline ml-1" />
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload?.length) {
    return (
      <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 shadow-xl text-sm">
        <p className="text-gray-300 mb-1">{label}</p>
        {payload.map((e: any, i: number) => (
          <p key={i} style={{ color: e.color || e.fill }}>
            {e.name}: {typeof e.value === 'number' ? e.value.toFixed(1) : e.value}
          </p>
        ))}
      </div>
    )
  }
  return null
}

// ── Main component ────────────────────────────────────────────────────────────

export default function DataConnector() {
  const [kpis, setKpis] = useState<VehicleKpiResponse | null>(null)
  const [safety, setSafety] = useState<SafetyResponse | null>(null)
  const [faults, setFaults] = useState<FaultResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [days, setDays] = useState(14)

  // Table sort state
  const [sortCol, setSortCol] = useState<SortKey>('distance_km')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  useEffect(() => {
    setLoading(true)
    setError(null)
    Promise.all([
      fetch(`/api/data-connector/vehicle-kpis?days=${days}`).then(r => r.json()),
      fetch(`/api/data-connector/safety-scores?days=${days}`).then(r => r.json()),
      fetch(`/api/data-connector/fault-trends?days=${days}`).then(r => r.json()),
    ])
      .then(([k, s, f]) => {
        setKpis(k)
        setSafety(s)
        setFaults(f)
      })
      .catch(e => setError(e.message || 'Failed to load Data Connector'))
      .finally(() => setLoading(false))
  }, [days])

  // Sorted vehicle rows
  const sortedVehicles = useMemo(() => {
    if (!kpis?.vehicles) return []
    return [...kpis.vehicles].sort((a, b) => {
      const va = a[sortCol] as number
      const vb = b[sortCol] as number
      return sortDir === 'asc' ? va - vb : vb - va
    })
  }, [kpis, sortCol, sortDir])

  // Top-10 vehicles by utilization % for the bar chart
  const utilizationChartData = useMemo(() => {
    if (!kpis?.vehicles) return []
    return kpis.vehicles
      .map(v => {
        const total = v.drive_hours + v.idle_hours
        return {
          name: v.vehicle_name.replace('K1-', ''),
          utilization: total > 0 ? parseFloat((v.drive_hours / total * 100).toFixed(1)) : 0,
          drive_hours: v.drive_hours,
          idle_hours: v.idle_hours,
        }
      })
      .sort((a, b) => b.utilization - a.utilization)
      .slice(0, 10)
  }, [kpis])

  // Aggregate fault codes (group by code, sum count)
  const aggregatedFaults = useMemo(() => {
    if (!faults?.faults) return []
    const map = new Map<string, {
      code: string; description: string; severity?: string; count: number; vehicleCount: number
    }>()
    for (const f of faults.faults) {
      const key = f.FaultCode || f.DiagnosticName || 'Unknown'
      const cnt = f.Count ?? f.FaultCount ?? 1
      const existing = map.get(key)
      if (existing) {
        existing.count += cnt
        existing.vehicleCount += 1
      } else {
        map.set(key, {
          code: f.FaultCode || key,
          description: f.DiagnosticName || key,
          severity: f.Severity,
          count: cnt,
          vehicleCount: 1,
        })
      }
    }
    return Array.from(map.values())
      .sort((a, b) => b.count - a.count)
      .slice(0, 10)
  }, [faults])

  function handleSort(col: SortKey) {
    if (sortCol === col) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortCol(col)
      setSortDir('desc')
    }
  }

  const isDemo = kpis?.demo || safety?.demo || faults?.demo

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-center">
        <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-2" />
        <p className="text-red-300 font-medium">Data Connector Error</p>
        <p className="text-red-400/70 text-sm mt-1">{error}</p>
        <p className="text-gray-500 text-xs mt-3">
          Make sure the Data Connector add-in is activated in MyGeotab → Administration → System Settings → Add-Ins
        </p>
      </div>
    )
  }

  const summary = kpis?.summary

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Database className="w-6 h-6 text-cyan-400" />
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              Data Connector Analytics
              {isDemo && (
                <span className="text-xs bg-amber-500/20 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-full">
                  Demo data
                </span>
              )}
            </h2>
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

      {loading ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="bg-gray-800/50 rounded-xl p-4 animate-pulse h-24" />
            ))}
          </div>
          <div className="bg-gray-800/50 rounded-xl animate-pulse h-64" />
        </div>
      ) : (
        <>
          {/* ── Fleet Utilization KPI Cards ──────────────────────────── */}
          {summary && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
              {(
                [
                  { label: 'Vehicles', value: String(summary.total_vehicles), icon: Truck, color: 'text-blue-400', sub: 'tracked' },
                  { label: 'Total Distance', value: `${(summary.total_distance_km / 1000).toFixed(1)}k km`, icon: TrendingUp, color: 'text-emerald-400', sub: `${days}-day period` },
                  { label: 'Drive Hours', value: `${summary.total_drive_hours.toFixed(0)}h`, icon: Clock, color: 'text-purple-400', sub: 'engine on, moving' },
                  { label: 'Idle Hours', value: `${summary.total_idle_hours.toFixed(0)}h`, icon: Clock, color: 'text-amber-400', sub: 'engine on, stopped' },
                  { label: 'Utilization', value: `${summary.utilization_pct}%`, icon: Activity, color: 'text-cyan-400', sub: 'drive / (drive + idle)' },
                ] as const
              ).map(({ label, value, icon: Icon, color, sub }, i) => (
                <motion.div
                  key={label}
                  className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.08 }}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Icon className={`w-4 h-4 ${color}`} />
                    <span className="text-xs text-gray-400">{label}</span>
                  </div>
                  <p className="text-2xl font-bold text-white">{value}</p>
                  <p className="text-xs text-gray-500 mt-1">{sub}</p>
                  {label === 'Utilization' && (
                    <div className="mt-2 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all"
                        style={{
                          width: `${Math.min(summary.utilization_pct, 100)}%`,
                          backgroundColor: utilBarColor(summary.utilization_pct),
                        }}
                      />
                    </div>
                  )}
                </motion.div>
              ))}
            </div>
          )}

          {/* ── Utilization Bar Chart (top 10 vehicles) ──────────────── */}
          {utilizationChartData.length > 0 && (
            <motion.div
              className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.25 }}
            >
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Activity className="w-5 h-5 text-cyan-400" />
                Vehicle Utilization — Top 10
              </h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={utilizationChartData} layout="vertical" margin={{ left: 10, right: 30 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} stroke="#9ca3af" fontSize={11} />
                  <YAxis type="category" dataKey="name" stroke="#9ca3af" fontSize={11} width={70} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="utilization" name="Utilization %" radius={[0, 4, 4, 0]}>
                    {utilizationChartData.map((entry, index) => (
                      <Cell key={index} fill={utilBarColor(entry.utilization)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </motion.div>
          )}

          {/* ── Per-Vehicle Utilization Table ─────────────────────────── */}
          {kpis && kpis.vehicles.length > 0 && (
            <motion.div
              className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.35 }}
            >
              <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                <Truck className="w-5 h-5 text-blue-400" />
                Per-Vehicle Utilization — {days}-day
                <span className="text-xs text-gray-500 font-normal ml-1">(click column to sort)</span>
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-gray-400 border-b border-gray-700">
                      <th className="text-left py-2 px-2">Vehicle</th>
                      {(
                        [
                          ['distance_km', 'Distance (km)'],
                          ['drive_hours', 'Drive (h)'],
                          ['idle_hours', 'Idle (h)'],
                          ['trips', 'Trips'],
                          ['fuel_litres', 'Fuel (L)'],
                        ] as [SortKey, string][]
                      ).map(([col, label]) => (
                        <th
                          key={col}
                          className="text-right py-2 px-2 cursor-pointer hover:text-white select-none"
                          onClick={() => handleSort(col)}
                        >
                          {label}
                          <SortIcon active={sortCol === col} dir={sortDir} />
                        </th>
                      ))}
                      <th className="text-right py-2 px-2">Utilization</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedVehicles.slice(0, 25).map((v, i) => {
                      const total = v.drive_hours + v.idle_hours
                      const util = total > 0 ? (v.drive_hours / total * 100) : 0
                      return (
                        <tr key={i} className="border-b border-gray-700/30 hover:bg-gray-700/20">
                          <td className="py-2 px-2 text-white font-medium">{v.vehicle_name}</td>
                          <td className="text-right py-2 px-2">{v.distance_km.toFixed(1)}</td>
                          <td className="text-right py-2 px-2 text-purple-300">{v.drive_hours.toFixed(1)}</td>
                          <td className="text-right py-2 px-2 text-amber-400">{v.idle_hours.toFixed(1)}</td>
                          <td className="text-right py-2 px-2">{v.trips}</td>
                          <td className="text-right py-2 px-2 text-blue-300">{v.fuel_litres.toFixed(1)}</td>
                          <td className="text-right py-2 px-2 min-w-[120px]">
                            <div className="flex items-center gap-2 justify-end">
                              <div className="w-16 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                                <div
                                  className="h-full rounded-full"
                                  style={{
                                    width: `${Math.min(util, 100)}%`,
                                    backgroundColor: utilBarColor(util),
                                  }}
                                />
                              </div>
                              <span className={`w-10 text-right ${utilColor(util)}`}>{util.toFixed(0)}%</span>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </motion.div>
          )}

          {/* ── Aggregated Safety Scores ────────────────────────────── */}
          {safety && safety.vehicle_scores.length > 0 && (
            <motion.div
              className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.45 }}
            >
              <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Shield className="w-5 h-5 text-amber-400" />
                  Aggregated Safety Scores
                </h3>
                {safety.fleet_avg_score != null && (
                  <div className="flex items-center gap-2 bg-gray-700/40 rounded-lg px-3 py-1.5">
                    <span className="text-xs text-gray-400">Fleet Average</span>
                    <span className={`text-xl font-bold ${scoreColor(safety.fleet_avg_score)}`}>
                      {safety.fleet_avg_score.toFixed(1)}
                    </span>
                    <span className="text-xs text-gray-500">/ 100</span>
                  </div>
                )}
              </div>
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {[...safety.vehicle_scores]
                  .sort((a, b) => ((b.SafetyScore ?? b.Score ?? 0) - (a.SafetyScore ?? a.Score ?? 0)))
                  .slice(0, 20)
                  .map((s, i) => {
                    const score = s.SafetyScore ?? s.Score ?? 0
                    const name = s.VehicleName || s.DriverName || `Vehicle ${i + 1}`
                    return (
                      <div key={i} className="flex items-center gap-3">
                        <div className={`text-sm font-bold w-10 text-right tabular-nums ${scoreColor(score)}`}>
                          {score.toFixed(0)}
                        </div>
                        <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all"
                            style={{ width: `${score}%`, backgroundColor: scoreBgColor(score) }}
                          />
                        </div>
                        <div className="w-28 truncate text-sm text-gray-300">{name}</div>
                        <TrendIcon trend={s.Trend} />
                      </div>
                    )
                  })}
              </div>
            </motion.div>
          )}

          {/* ── Fault Code Trends ───────────────────────────────────── */}
          {faults && faults.faults.length > 0 && (
            <motion.div
              className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.55 }}
            >
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-red-400" />
                Fault Code Trends
              </h3>

              {/* Top-faults bar chart */}
              {aggregatedFaults.length > 0 && (
                <div className="mb-5">
                  <p className="text-xs text-gray-400 mb-2">
                    Top fault codes by occurrence count ({days}-day)
                  </p>
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart data={aggregatedFaults} margin={{ left: 0, right: 10 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                      <XAxis
                        dataKey="code"
                        stroke="#9ca3af"
                        fontSize={10}
                        angle={-30}
                        textAnchor="end"
                        height={50}
                      />
                      <YAxis stroke="#9ca3af" fontSize={11} allowDecimals={false} />
                      <Tooltip
                        content={({ active, payload }: any) => {
                          if (active && payload?.length) {
                            const d = payload[0]?.payload as typeof aggregatedFaults[0]
                            return (
                              <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 shadow-xl text-xs max-w-xs">
                                <p className="text-white font-medium mb-1">{d?.description}</p>
                                <p className="text-gray-400">Code: {d?.code}</p>
                                <p className="text-red-400">Count: {d?.count}</p>
                                <p className="text-gray-400">Vehicles affected: {d?.vehicleCount}</p>
                              </div>
                            )
                          }
                          return null
                        }}
                      />
                      <Bar dataKey="count" name="Occurrences" radius={[4, 4, 0, 0]}>
                        {aggregatedFaults.map((entry, idx) => (
                          <Cell
                            key={idx}
                            fill={
                              entry.severity === 'critical' ? '#ef4444'
                                : entry.severity === 'high' ? '#f97316'
                                  : entry.severity === 'medium' ? '#f59e0b'
                                    : '#3b82f6'
                            }
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Fault detail table */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-gray-400 border-b border-gray-700">
                      <th className="text-left py-2 px-2">Vehicle</th>
                      <th className="text-left py-2 px-2">Code</th>
                      <th className="text-left py-2 px-2">Description</th>
                      <th className="text-left py-2 px-2">Severity</th>
                      <th className="text-right py-2 px-2">Count</th>
                      <th className="text-left py-2 px-2">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {faults.faults.slice(0, 15).map((f, i) => (
                      <tr key={i} className="border-b border-gray-700/30 hover:bg-gray-700/20">
                        <td className="py-2 px-2 text-white">{f.VehicleName || '—'}</td>
                        <td className="py-2 px-2 font-mono text-xs text-blue-300">{f.FaultCode || '—'}</td>
                        <td className="py-2 px-2 text-gray-300 max-w-[200px] truncate">
                          {f.DiagnosticName || '—'}
                        </td>
                        <td className={`py-2 px-2 text-xs font-medium ${severityColor(f.Severity)}`}>
                          {f.Severity
                            ? f.Severity.charAt(0).toUpperCase() + f.Severity.slice(1)
                            : '—'}
                        </td>
                        <td className="text-right py-2 px-2 text-red-400 font-medium">
                          {f.Count ?? f.FaultCount ?? 1}
                        </td>
                        <td className="py-2 px-2 text-gray-400 text-xs">{f.Date || f.Day || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>
          )}

          {/* Empty state */}
          {kpis && kpis.vehicles.length === 0 && (
            <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-8 text-center">
              <Database className="w-10 h-10 text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400">No Data Connector data available yet.</p>
              <p className="text-gray-500 text-sm mt-1">
                Data pipeline may take 2–3 hours to backfill after activation.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
