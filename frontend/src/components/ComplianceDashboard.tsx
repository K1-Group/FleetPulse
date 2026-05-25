import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Shield, Clock, AlertTriangle, CheckCircle2, XCircle, ClipboardCheck } from 'lucide-react'

interface HOSSummary {
  summary: {
    total_drivers: number
    compliant: number
    warnings: number
    violations: number
    compliance_rate: number
  }
  limits: Record<string, number>
  violations: Array<{
    vehicle: string
    type: string
    hours: number
    limit: number
    severity: string
  }>
  drivers: Array<{
    vehicle_id: string
    vehicle_name: string
    status: string
    today_hours: number
    today_remaining: number
    today_pct: number
    week_hours: number
    week_remaining: number
    week_pct: number
  }>
  last_updated: string
  source_authority?: string
  projection_mode?: 'read_only' | string
  evidence_mode?: string
  source_status?: {
    status: string
    message: string
    device_count?: number
    trip_count_7d?: number
    trip_count_today?: number
  }
}

interface InspectionReadiness {
  overall_score: number
  status: string
  checklist: Array<{
    item: string
    status: string
    source?: string
    detail?: string
    icon: string
  }>
  total_vehicles: number
  vehicles_inspected_today: number | null
  last_audit_date: string | null
  next_audit_date: string | null
  source_authority?: string
  projection_mode?: 'read_only' | string
  source_status?: {
    status: string
    message: string
    device_count?: number
    device_status_count?: number
    trip_count_7d?: number
    awaiting_feed_count?: number
  }
}

export default function ComplianceDashboard() {
  const [hos, setHos] = useState<HOSSummary | null>(null)
  const [inspection, setInspection] = useState<InspectionReadiness | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch('/api/compliance/hos-summary').then(r => r.json()),
      fetch('/api/compliance/inspection-readiness').then(r => r.json()),
    ]).then(([h, i]) => {
      setHos(h)
      setInspection(i)
    }).finally(() => setLoading(false))
  }, [])

  const statusBg = (status: string) => {
    switch (status) {
      case 'compliant': return 'bg-emerald-500/20 text-emerald-400'
      case 'pass': return 'bg-emerald-500/20 text-emerald-400'
      case 'warning': return 'bg-amber-500/20 text-amber-400'
      case 'violation': return 'bg-red-500/20 text-red-400'
      case 'fail': return 'bg-red-500/20 text-red-400'
      case 'unavailable': return 'bg-red-500/20 text-red-400'
      case 'awaiting_feed': return 'bg-sky-500/20 text-sky-300'
      default: return 'bg-gray-500/20 text-gray-400'
    }
  }

  const pctBarColor = (pct: number) => {
    if (pct >= 90) return 'bg-red-500'
    if (pct >= 75) return 'bg-amber-500'
    return 'bg-emerald-500'
  }

  const sourceBadgeClass = (status?: string) => {
    switch (status) {
      case 'healthy': return 'bg-emerald-500/20 text-emerald-400'
      case 'partial': return 'bg-amber-500/20 text-amber-300'
      case 'unavailable': return 'bg-red-500/20 text-red-300'
      default: return 'bg-gray-500/20 text-gray-300'
    }
  }

  const checklistStatusIcon = (status: string) => {
    if (status === 'pass') return <CheckCircle2 className="w-5 h-5 text-emerald-400" />
    if (status === 'unavailable' || status === 'fail') return <XCircle className="w-5 h-5 text-red-400" />
    return <AlertTriangle className="w-5 h-5 text-amber-400" />
  }

  const inspectedLabel = inspection?.vehicles_inspected_today === null || inspection?.vehicles_inspected_today === undefined
    ? 'Awaiting DVIR feed'
    : `${inspection.vehicles_inspected_today}/${inspection.total_vehicles}`

  const nextAuditLabel = inspection?.next_audit_date || 'Awaiting audit feed'
  const complianceRateLabel = hos?.source_status?.status === 'healthy' && hos.summary.total_drivers > 0
    ? `${hos.summary.compliance_rate}%`
    : 'Pending'

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Compliance Score Banner */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gradient-to-r from-blue-900/50 to-purple-900/50 border border-blue-800/30 rounded-xl p-6"
      >
        <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
          <span className={`rounded-full px-2 py-1 font-medium ${sourceBadgeClass(hos?.source_status?.status)}`}>
            HOS source: {hos?.source_status?.status || 'pending'}
          </span>
          <span className="rounded-full bg-gray-800/70 px-2 py-1 text-gray-300">
            {hos?.evidence_mode?.replace(/_/g, ' ') || 'Geotab trip activity proxy'}
          </span>
        </div>
        <div className="flex flex-col md:flex-row items-center gap-6">
          <div className="text-center">
            <div className="text-5xl font-bold text-white">{complianceRateLabel}</div>
            <div className="text-sm text-blue-300 mt-1">Fleet Compliance Rate</div>
          </div>
          <div className="flex-1 grid grid-cols-3 gap-4">
            <div className="text-center">
              <div className="flex items-center justify-center gap-1">
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                <span className="text-2xl font-bold text-emerald-400">{hos?.summary.compliant}</span>
              </div>
              <div className="text-xs text-gray-400">Compliant</div>
            </div>
            <div className="text-center">
              <div className="flex items-center justify-center gap-1">
                <AlertTriangle className="w-5 h-5 text-amber-400" />
                <span className="text-2xl font-bold text-amber-400">{hos?.summary.warnings}</span>
              </div>
              <div className="text-xs text-gray-400">Warnings</div>
            </div>
            <div className="text-center">
              <div className="flex items-center justify-center gap-1">
                <XCircle className="w-5 h-5 text-red-400" />
                <span className="text-2xl font-bold text-red-400">{hos?.summary.violations}</span>
              </div>
              <div className="text-xs text-gray-400">Violations</div>
            </div>
          </div>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* HOS Driver Status */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
        >
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Clock className="w-5 h-5 text-blue-400" />
            Hours of Service Status
          </h3>
          <p className="mb-4 text-xs text-gray-500">
            {hos?.source_status?.message || 'Awaiting source status from Geotab.'}
          </p>
          <div className="space-y-3">
            {hos?.drivers.length ? hos.drivers.slice(0, 10).map((driver, i) => (
              <motion.div
                key={driver.vehicle_id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.3 + i * 0.05 }}
                className="bg-gray-800/30 rounded-lg p-3"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{driver.vehicle_name}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${statusBg(driver.status)}`}>
                      {driver.status}
                    </span>
                  </div>
                  <span className="text-xs text-gray-400">{driver.today_remaining}h remaining</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 w-12">Today</span>
                  <div className="flex-1 bg-gray-700/50 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full transition-all ${pctBarColor(driver.today_pct)}`}
                      style={{ width: `${Math.min(driver.today_pct, 100)}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-400 w-12 text-right">{driver.today_hours}h</span>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs text-gray-500 w-12">Week</span>
                  <div className="flex-1 bg-gray-700/50 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full transition-all ${pctBarColor(driver.week_pct)}`}
                      style={{ width: `${Math.min(driver.week_pct, 100)}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-400 w-12 text-right">{driver.week_hours}h</span>
                </div>
              </motion.div>
            )) : (
              <div className="rounded-lg border border-dashed border-gray-800 px-4 py-8 text-center text-sm text-gray-500">
                No source-backed HOS proxy rows returned.
              </div>
            )}
          </div>
        </motion.div>

        {/* Inspection Readiness */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
          className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
        >
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <ClipboardCheck className="w-5 h-5 text-emerald-400" />
            Inspection Readiness
          </h3>
          <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
            <span className={`rounded-full px-2 py-1 font-medium ${sourceBadgeClass(inspection?.source_status?.status)}`}>
              Source: {inspection?.source_status?.status || 'pending'}
            </span>
            <span className="rounded-full bg-gray-800/70 px-2 py-1 text-gray-300">
              Read-only
            </span>
          </div>
          
          {/* Score Circle */}
          <div className="flex items-center gap-6 mb-6">
            <div className="relative w-24 h-24">
              <svg className="w-24 h-24 transform -rotate-90" viewBox="0 0 36 36">
                <path
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  fill="none"
                  stroke="#374151"
                  strokeWidth="3"
                />
                <path
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  fill="none"
                  stroke={inspection?.overall_score && inspection.overall_score >= 80 ? '#10b981' : '#f59e0b'}
                  strokeWidth="3"
                  strokeDasharray={`${inspection?.overall_score || 0}, 100`}
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-xl font-bold">{inspection?.overall_score}%</span>
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-400">Vehicles inspected today</div>
              <div className="text-lg font-semibold">{inspectedLabel}</div>
              <div className="text-xs text-gray-500 mt-1">Next audit: {nextAuditLabel}</div>
            </div>
          </div>
          <p className="mb-4 text-xs text-gray-500">
            {inspection?.source_status?.message || 'Awaiting inspection source status.'}
          </p>

          {/* Checklist */}
          <div className="space-y-2">
            {inspection?.checklist.map((item, i) => (
              <motion.div
                key={item.item}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4 + i * 0.05 }}
                className="flex items-center gap-3 py-2 px-3 bg-gray-800/20 rounded-lg"
              >
                <span className="text-lg">{item.icon}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm">{item.item}</span>
                  <span className="block truncate text-xs text-gray-500">{item.detail || item.source}</span>
                </span>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${statusBg(item.status)}`}>
                  {item.status.replace(/_/g, ' ')}
                </span>
                {checklistStatusIcon(item.status)}
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Violations Detail */}
      {hos?.violations && hos.violations.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="bg-red-900/20 border border-red-800/30 rounded-xl p-6"
        >
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2 text-red-400">
            <XCircle className="w-5 h-5" />
            Active Violations
          </h3>
          <div className="space-y-2">
            {hos.violations.map((v, i) => (
              <div key={i} className="flex items-center gap-4 bg-red-900/20 rounded-lg px-4 py-3">
                <span className="font-medium">{v.vehicle}</span>
                <span className="text-sm text-red-300">{v.type.replace(/_/g, ' ')}</span>
                <span className="ml-auto text-sm">
                  <span className="text-red-400 font-bold">{v.hours}h</span>
                  <span className="text-gray-500"> / {v.limit}h limit</span>
                </span>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  )
}
