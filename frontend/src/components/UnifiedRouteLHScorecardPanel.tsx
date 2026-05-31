import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, DollarSign, RefreshCw, Route, ShieldCheck } from 'lucide-react'

type FeedStatus = 'healthy' | 'awaiting_feed' | 'unavailable'

interface UnifiedRouteLHScorecardSummary {
  scorecard_units: number
  local_routes: number
  lh_lanes: number
  company_avg_revenue_per_hour: number
  missed_hours: number
  missed_hour_revenue: number
  local_missed_hour_revenue: number
  lh_missed_hour_revenue: number
  avg_stability_pct: number | null
  avg_on_time_pct: number | null
  avg_tech_pct: number | null
  safety_status: string
  attendance_status: string
}

interface UnifiedRouteLHScorecardItem {
  work_type: 'Local Route' | 'LH Lane'
  entity: string
  route_lh: string
  service: string
  customer_relationship: string
  primary_driver: string
  current_sales: number
  missed_hours: number
  missed_hour_revenue: number
  stability_pct: number | null
  on_time_pct: number | null
  safety_data_status: string
  tech_pct: number | null
  attendance_data_status: string
  gross_margin_pct: number | null
  relationship_band: string
  risk_management_band: string
  sales_relationship_action: string
  capacity_status: string
  source_boundary: string
}

interface UnifiedRouteLHActionSummary {
  action: string
  units: number
  missed_hours: number
  missed_hour_revenue: number
}

interface UnifiedRouteLHSourceNote {
  metric: string
  definition: string
}

interface UnifiedRouteLHSourceBoundary {
  system: string
  entity: string
  authority: string[]
  rule: string
}

interface UnifiedRouteLHScorecardPayload {
  generated_at: string
  period_end: string
  projection_mode: 'read_only'
  feed_status: FeedStatus
  feed_message: string
  source_authority: string
  source_file: string
  required_config: string[]
  summary: UnifiedRouteLHScorecardSummary
  items: UnifiedRouteLHScorecardItem[]
  action_summary: UnifiedRouteLHActionSummary[]
  source_notes: UnifiedRouteLHSourceNote[]
  source_boundaries: UnifiedRouteLHSourceBoundary[]
}

const SOURCE_NOTE_KEYS = new Set(['Source Boundary', 'Safety Source Audit', 'Attendance Source Audit', 'No-match rule'])

function asPercent(value: number | null | undefined): number | null {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return null
  const numeric = Number(value)
  return Math.abs(numeric) <= 1 ? numeric * 100 : numeric
}

function formatPercent(value: number | null | undefined): string {
  const percent = asPercent(value)
  return percent === null ? 'Not scored' : `${percent.toFixed(1)}%`
}

function formatMoney(value: number | null | undefined): string {
  return Number(value ?? 0).toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  })
}

function formatNumber(value: number | null | undefined, digits = 0): string {
  return Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: digits })
}

function statusClass(status: FeedStatus) {
  if (status === 'healthy') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200 light:text-emerald-700'
  if (status === 'awaiting_feed') return 'border-amber-500/30 bg-amber-500/10 text-amber-200 light:text-amber-700'
  return 'border-red-500/30 bg-red-500/10 text-red-200 light:text-red-700'
}

function MetricTile({
  label,
  value,
  helper,
  tone = 'neutral',
}: {
  label: string
  value: string
  helper?: string
  tone?: 'neutral' | 'good' | 'warning'
}) {
  const toneClass = {
    neutral: 'text-white light:text-gray-900',
    good: 'text-emerald-300 light:text-emerald-700',
    warning: 'text-amber-300 light:text-amber-700',
  }[tone]

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-3 light:border-gray-200 light:bg-gray-50">
      <p className="text-[10px] uppercase text-gray-500 light:text-gray-600">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${toneClass}`}>{value}</p>
      {helper && <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{helper}</p>}
    </div>
  )
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-dashed border-gray-700 p-5 text-center text-sm text-gray-400 light:border-gray-300 light:text-gray-600">
      {label}
    </div>
  )
}

export default function UnifiedRouteLHScorecardPanel() {
  const [payload, setPayload] = useState<UnifiedRouteLHScorecardPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchScorecard = useCallback(async (silent = false) => {
    if (silent) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    setError(null)

    try {
      const response = await fetch('/api/lane-stability/unified-scorecard')
      if (!response.ok) throw new Error(`Unified scorecard API returned ${response.status}`)
      setPayload((await response.json()) as UnifiedRouteLHScorecardPayload)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unified scorecard API unavailable')
      setPayload(null)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    fetchScorecard()
  }, [fetchScorecard])

  const topItems = useMemo(() => (payload?.items ?? []).slice(0, 12), [payload])
  const sourceNotes = useMemo(
    () => (payload?.source_notes ?? []).filter(note => SOURCE_NOTE_KEYS.has(note.metric)),
    [payload],
  )
  const status = payload?.feed_status ?? (error ? 'unavailable' : 'awaiting_feed')
  const summary = payload?.summary

  return (
    <section className="rounded-lg border border-gray-800/70 bg-gray-900/55 p-5 shadow-lg shadow-black/10 light:border-gray-200 light:bg-white">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Route className="h-5 w-5 text-cyan-300" />
            <h3 className="text-lg font-semibold text-white light:text-gray-900">May 23 Unified Route/LH Scorecard</h3>
          </div>
          <p className="mt-1 text-sm text-gray-400 light:text-gray-600">
            {payload?.source_file ?? 'K1_Unified_Route_LH_Scorecard_WE_2026-05-23.xlsx'} · {payload?.source_authority ?? 'Xcelerator ReviewOrders export'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full border px-3 py-1 text-xs font-medium capitalize ${statusClass(status)}`}>
            {status.replace('_', ' ')}
          </span>
          <span className="rounded-full border border-gray-700 px-3 py-1 text-xs text-gray-300 light:border-gray-300 light:text-gray-700">
            WE {payload?.period_end || '2026-05-23'}
          </span>
          <button
            type="button"
            onClick={() => fetchScorecard(true)}
            className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-700 px-3 text-xs text-gray-300 transition hover:border-cyan-500/50 hover:text-white light:border-gray-300 light:text-gray-700 light:hover:text-gray-900"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200 light:bg-red-50 light:text-red-700">
          {error}
        </div>
      )}

      {loading && !payload ? (
        <EmptyState label="Loading unified route/LH scorecard..." />
      ) : payload && payload.feed_status !== 'healthy' ? (
        <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200 light:text-amber-700">
          <div className="flex gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p>{payload.feed_message}</p>
              <p className="mt-1 font-mono text-xs">{payload.required_config.join(', ')}</p>
            </div>
          </div>
        </div>
      ) : null}

      {summary && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <MetricTile
            label="Missed-Hour Revenue"
            value={formatMoney(summary.missed_hour_revenue)}
            helper={`${formatMoney(summary.local_missed_hour_revenue)} local · ${formatMoney(summary.lh_missed_hour_revenue)} LH`}
            tone="warning"
          />
          <MetricTile
            label="Missed Hours"
            value={formatNumber(summary.missed_hours, 1)}
            helper={`${formatNumber(summary.scorecard_units)} units reviewed`}
          />
          <MetricTile
            label="Route/LH Mix"
            value={`${formatNumber(summary.local_routes)} / ${formatNumber(summary.lh_lanes)}`}
            helper="Local routes / LH lanes"
          />
          <MetricTile
            label="Avg Stability"
            value={formatPercent(summary.avg_stability_pct)}
            helper={`On-time ${formatPercent(summary.avg_on_time_pct)}`}
            tone="good"
          />
          <MetricTile
            label="Safety"
            value={summary.safety_status || 'Needs Geotab'}
            helper={`Attendance ${summary.attendance_status || 'Not scored'}`}
            tone="warning"
          />
        </div>
      )}

      {payload?.action_summary.length ? (
        <div className="mt-5 grid grid-cols-1 gap-3 lg:grid-cols-3">
          {payload.action_summary.slice(0, 3).map(action => (
            <div key={action.action} className="rounded-lg border border-gray-800 bg-gray-950/35 p-3 light:border-gray-200 light:bg-gray-50">
              <p className="text-xs font-semibold text-white light:text-gray-900">{action.action}</p>
              <p className="mt-2 text-sm text-amber-200 light:text-amber-700">
                {formatMoney(action.missed_hour_revenue)} · {formatNumber(action.missed_hours, 1)} hours
              </p>
              <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{action.units} route/LH units</p>
            </div>
          ))}
        </div>
      ) : null}

      {topItems.length ? (
        <div className="mt-5 overflow-x-auto rounded-lg border border-gray-800 light:border-gray-200">
          <table className="min-w-[980px] divide-y divide-gray-800 text-sm light:divide-gray-200">
            <thead className="bg-gray-950/60 light:bg-gray-50">
              <tr className="text-left text-xs uppercase text-gray-500 light:text-gray-600">
                <th className="px-3 py-2 font-medium">Route/LH</th>
                <th className="px-3 py-2 font-medium">Entity</th>
                <th className="px-3 py-2 font-medium">Missed Revenue</th>
                <th className="px-3 py-2 font-medium">Metrics</th>
                <th className="px-3 py-2 font-medium">Band</th>
                <th className="px-3 py-2 font-medium">Action Guidance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800 light:divide-gray-200">
              {topItems.map(item => (
                <tr key={`${item.work_type}-${item.entity}-${item.route_lh}-${item.primary_driver}`} className="align-top">
                  <td className="px-3 py-3">
                    <p className="font-semibold text-white light:text-gray-900">{item.route_lh}</p>
                    <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{item.work_type} · Driver {item.primary_driver || 'Unassigned'}</p>
                  </td>
                  <td className="px-3 py-3">
                    <p className="text-gray-300 light:text-gray-700">{item.entity}</p>
                    <p className="mt-1 max-w-[220px] text-xs text-gray-500 light:text-gray-600">{item.customer_relationship || item.service}</p>
                  </td>
                  <td className="px-3 py-3">
                    <p className="font-semibold text-amber-200 light:text-amber-700">{formatMoney(item.missed_hour_revenue)}</p>
                    <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{formatNumber(item.missed_hours, 1)} hours</p>
                  </td>
                  <td className="px-3 py-3 text-xs text-gray-400 light:text-gray-600">
                    <p>Stable {formatPercent(item.stability_pct)}</p>
                    <p>OTD {formatPercent(item.on_time_pct)}</p>
                    <p>Tech {formatPercent(item.tech_pct)}</p>
                    <p>Safety {item.safety_data_status || 'Not scored'}</p>
                  </td>
                  <td className="px-3 py-3">
                    <p className="text-gray-200 light:text-gray-800">{item.relationship_band || 'Unbanded'}</p>
                    <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{item.risk_management_band || 'No risk band'}</p>
                  </td>
                  <td className="px-3 py-3">
                    <p className="max-w-[320px] text-gray-300 light:text-gray-700">{item.sales_relationship_action || 'No action guidance'}</p>
                    {item.capacity_status && <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{item.capacity_status}</p>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : payload?.feed_status === 'healthy' ? (
        <EmptyState label="Unified scorecard loaded, but no route/LH rows were returned." />
      ) : null}

      <div className="mt-5 grid grid-cols-1 gap-3 lg:grid-cols-3">
        {(payload?.source_boundaries ?? []).map(boundary => (
          <div key={boundary.system} className="rounded-lg border border-gray-800 bg-gray-950/35 p-3 light:border-gray-200 light:bg-gray-50">
            <div className="flex items-start gap-2">
              {boundary.system === 'FleetPulse' ? (
                <DollarSign className="mt-0.5 h-4 w-4 shrink-0 text-gray-400" />
              ) : (
                <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-cyan-300" />
              )}
              <div>
                <p className="text-sm font-semibold text-white light:text-gray-900">{boundary.system}</p>
                <p className="text-xs text-gray-500 light:text-gray-600">{boundary.entity}</p>
              </div>
            </div>
            <p className="mt-2 text-xs leading-5 text-gray-400 light:text-gray-700">{boundary.rule}</p>
          </div>
        ))}
      </div>

      {sourceNotes.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {sourceNotes.map(note => (
            <span key={note.metric} className="max-w-full break-words rounded-full border border-gray-700 px-3 py-1 text-xs text-gray-400 light:border-gray-300 light:text-gray-600">
              {note.metric}: {note.definition}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  )
}
