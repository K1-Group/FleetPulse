import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  BarChart3,
  Check,
  Copy,
  DollarSign,
  FileDown,
  Minus,
  RefreshCw,
  Route,
  ShieldCheck,
  Timer,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

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

interface UnifiedRouteLHGapWindow {
  source_row: number
  entity: string
  route: string
  date: string
  gap_type: string
  gap_from: string
  gap_to: string
  gap_window: string
  missed_hours: number
  company_avg_revenue_per_hour: number
  missed_hour_revenue: number
  paid_window_basis: string
}

interface UnifiedRouteLHGapRouteSummary {
  entity: string
  route: string
  window_count: number
  missed_hours: number
  missed_hour_revenue: number
  gap_types: string[]
  sample_windows: string[]
}

interface UnifiedRouteLHGapTypeSummary {
  gap_type: string
  window_count: number
  missed_hours: number
  missed_hour_revenue: number
}

interface UnifiedRouteLHGapDetail {
  source_sheet: string
  status: 'healthy' | 'missing' | 'unavailable' | 'awaiting_feed'
  message: string
  total_windows: number
  total_missed_hours: number
  total_missed_hour_revenue: number
  route_summary: UnifiedRouteLHGapRouteSummary[]
  gap_type_summary: UnifiedRouteLHGapTypeSummary[]
  windows: UnifiedRouteLHGapWindow[]
}

type ComparisonStatus = 'healthy' | 'awaiting_prior_scorecard' | 'unavailable'

interface UnifiedRouteLHComparisonMetric {
  key: string
  label: string
  value_type: 'money' | 'number' | 'percent'
  current: number | null
  prior: number | null
  delta: number | null
  delta_pct: number | null
  direction: 'up' | 'down' | 'flat' | 'not_scored'
}

interface UnifiedRouteLHComparison {
  status: ComparisonStatus
  message: string
  period_end_current: string
  period_end_prior: string
  source_file_prior: string
  metrics: UnifiedRouteLHComparisonMetric[]
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
  optional_config: string[]
  summary: UnifiedRouteLHScorecardSummary
  items: UnifiedRouteLHScorecardItem[]
  action_summary: UnifiedRouteLHActionSummary[]
  comparison: UnifiedRouteLHComparison
  gap_detail: UnifiedRouteLHGapDetail
  source_notes: UnifiedRouteLHSourceNote[]
  source_boundaries: UnifiedRouteLHSourceBoundary[]
}

const SOURCE_NOTE_KEYS = new Set(['Source Boundary', 'Safety Source Audit', 'Attendance Source Audit', 'No-match rule'])
const ACTION_COLORS = ['#f59e0b', '#22c55e', '#38bdf8', '#a78bfa', '#f97316']
const ROUTE_COLOR = '#fb923c'
const CHART_AXIS = '#9ca3af'

interface RevenueChartRow {
  name: string
  missed_hour_revenue: number
  missed_hours?: number
  action?: string
}

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

function formatCompactMoney(value: number | null | undefined): string {
  return Number(value ?? 0).toLocaleString(undefined, {
    currency: 'USD',
    maximumFractionDigits: 1,
    notation: 'compact',
    style: 'currency',
  })
}

function benchmarkWatchlistHref(route: string): string {
  const params = new URLSearchParams({ route, days: '180', source: 'stability-gap' })
  return `#address-benchmarks?${params.toString()}`
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

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value?: number; name?: string; color?: string }>; label?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-gray-700 bg-gray-950/95 p-3 text-xs shadow-xl light:border-gray-200 light:bg-white">
      <p className="mb-2 font-semibold text-white light:text-gray-900">{label}</p>
      {payload.map(entry => (
        <div key={`${entry.name}-${entry.value}`} className="flex items-center justify-between gap-4">
          <span style={{ color: entry.color }}>{entry.name}</span>
          <span className="font-medium text-white light:text-gray-900">{formatMoney(entry.value)}</span>
        </div>
      ))}
    </div>
  )
}

function formatComparisonValue(metric: UnifiedRouteLHComparisonMetric): string {
  if (metric.delta === null || metric.delta === undefined) return 'Awaiting source'
  if (metric.value_type === 'money') return formatMoney(metric.delta)
  if (metric.value_type === 'percent') return `${metric.delta > 0 ? '+' : ''}${(metric.delta * 100).toFixed(1)} pp`
  return `${metric.delta > 0 ? '+' : ''}${formatNumber(metric.delta, 1)}`
}

function ComparisonIcon({ direction }: { direction: UnifiedRouteLHComparisonMetric['direction'] }) {
  if (direction === 'up') return <TrendingUp className="h-4 w-4 text-amber-300 light:text-amber-700" />
  if (direction === 'down') return <TrendingDown className="h-4 w-4 text-emerald-300 light:text-emerald-700" />
  return <Minus className="h-4 w-4 text-gray-400" />
}

function buildExecutiveSummary(payload: UnifiedRouteLHScorecardPayload): string {
  const summary = payload.summary
  const top = payload.items[0]
  const topAction = payload.action_summary[0]
  const gapDetail = payload.gap_detail
  const topGapRoute = gapDetail?.route_summary?.[0]
  return [
    `FleetPulse May 23 Unified Route/LH Scorecard (${payload.period_end})`,
    `Source: ${payload.source_file} / ${payload.source_authority}`,
    `Projection: ${payload.projection_mode}; FleetPulse is read-only.`,
    `Missed-hour revenue: ${formatMoney(summary.missed_hour_revenue)} across ${formatNumber(summary.missed_hours, 1)} missed hours.`,
    `Route/LH mix: ${formatNumber(summary.local_routes)} local routes / ${formatNumber(summary.lh_lanes)} LH lanes (${formatNumber(summary.scorecard_units)} units).`,
    `Average stability: ${formatPercent(summary.avg_stability_pct)}; on-time: ${formatPercent(summary.avg_on_time_pct)}; tech: ${formatPercent(summary.avg_tech_pct)}.`,
    `Safety: ${summary.safety_status || 'Needs Geotab'}; attendance: ${summary.attendance_status || 'Not scored'}.`,
    top ? `Top route/LH: ${top.route_lh} at ${formatMoney(top.missed_hour_revenue)} and ${formatNumber(top.missed_hours, 1)} missed hours.` : '',
    gapDetail?.status === 'healthy'
      ? `Gap Detail: ${formatNumber(gapDetail.total_windows)} capacity windows totaling ${formatMoney(gapDetail.total_missed_hour_revenue)}.`
      : '',
    topGapRoute ? `Top gap route: ${topGapRoute.route} with ${formatNumber(topGapRoute.window_count)} windows and ${formatMoney(topGapRoute.missed_hour_revenue)}.` : '',
    topAction ? `Top action bucket: ${topAction.action} (${formatMoney(topAction.missed_hour_revenue)}, ${topAction.units} units).` : '',
    payload.comparison?.status === 'healthy'
      ? `Prior comparison loaded: ${payload.comparison.period_end_prior}.`
      : `Prior comparison: ${payload.comparison?.message || 'Awaiting prior approved workbook.'}`,
    'Boundaries: Xcelerator remains operations/financial authority; Geotab remains telemetry/safety authority; FleetPulse does not write back.',
  ].filter(Boolean).join('\n')
}

async function copyText(text: string) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // Browser permissions can deny Clipboard API writes even from a user click.
      // Fall back to a transient textarea so local capture still works.
    }
  }
  const element = document.createElement('textarea')
  element.value = text
  element.setAttribute('readonly', 'true')
  element.style.position = 'fixed'
  element.style.opacity = '0'
  document.body.appendChild(element)
  element.select()
  document.execCommand('copy')
  document.body.removeChild(element)
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
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle')

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

  const hasHealthyPayload = payload?.feed_status === 'healthy'
  const topItems = useMemo(() => (hasHealthyPayload ? (payload?.items ?? []).slice(0, 12) : []), [hasHealthyPayload, payload])
  const sourceNotes = useMemo(
    () => (payload?.source_notes ?? []).filter(note => SOURCE_NOTE_KEYS.has(note.metric)),
    [payload],
  )
  const status = payload?.feed_status ?? (error ? 'unavailable' : 'awaiting_feed')
  const summary = hasHealthyPayload ? payload?.summary : null
  const topActionRows: RevenueChartRow[] = useMemo(
    () => (hasHealthyPayload ? (payload?.action_summary ?? []).slice(0, 5).map(row => ({
      name: row.action.length > 34 ? `${row.action.slice(0, 31)}...` : row.action,
      missed_hour_revenue: row.missed_hour_revenue,
      missed_hours: row.missed_hours,
      action: row.action,
    })) : []),
    [hasHealthyPayload, payload],
  )
  const topRouteRows: RevenueChartRow[] = useMemo(
    () => topItems.slice(0, 8).map(row => ({
      name: row.route_lh,
      missed_hour_revenue: row.missed_hour_revenue,
      missed_hours: row.missed_hours,
      action: row.sales_relationship_action,
    })),
    [topItems],
  )
  const comparisonMetrics = useMemo(
    () => (payload?.comparison?.metrics ?? []).filter(metric => ['missed_hour_revenue', 'missed_hours', 'avg_stability_pct', 'avg_on_time_pct'].includes(metric.key)),
    [payload],
  )
  const gapDetail = hasHealthyPayload ? payload?.gap_detail : null
  const topGapRoutes = useMemo(
    () => (gapDetail?.status === 'healthy' ? gapDetail.route_summary.slice(0, 4) : []),
    [gapDetail],
  )
  const topGapTypes = useMemo(
    () => (gapDetail?.status === 'healthy' ? gapDetail.gap_type_summary.slice(0, 4) : []),
    [gapDetail],
  )
  const topGapWindows = useMemo(
    () => (gapDetail?.status === 'healthy' ? gapDetail.windows.slice(0, 12) : []),
    [gapDetail],
  )

  const copySummary = useCallback(async () => {
    if (!payload) return
    try {
      await copyText(buildExecutiveSummary(payload))
      setCopyStatus('copied')
      window.setTimeout(() => setCopyStatus('idle'), 2500)
    } catch {
      setCopyStatus('failed')
      window.setTimeout(() => setCopyStatus('idle'), 2500)
    }
  }, [payload])

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
          <button
            type="button"
            onClick={copySummary}
            disabled={!payload || payload.feed_status !== 'healthy'}
            className="inline-flex h-8 items-center gap-2 rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 text-xs text-blue-100 transition hover:bg-blue-500/20 disabled:cursor-not-allowed disabled:opacity-50 light:text-blue-700"
          >
            {copyStatus === 'copied' ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copyStatus === 'copied' ? 'Copied' : copyStatus === 'failed' ? 'Copy failed' : 'Copy Summary'}
          </button>
          <button
            type="button"
            onClick={() => window.print()}
            disabled={!payload || payload.feed_status !== 'healthy'}
            className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-700 px-3 text-xs text-gray-300 transition hover:border-emerald-500/50 hover:text-white disabled:cursor-not-allowed disabled:opacity-50 light:border-gray-300 light:text-gray-700 light:hover:text-gray-900"
          >
            <FileDown className="h-3.5 w-3.5" />
            Print / PDF
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

      {hasHealthyPayload && gapDetail ? (
        <div className="mt-5 rounded-lg border border-amber-500/20 bg-amber-500/10 p-4 light:bg-amber-50">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex items-start gap-2">
              <BarChart3 className="mt-0.5 h-4 w-4 shrink-0 text-amber-300 light:text-amber-700" />
              <div>
                <p className="text-sm font-semibold text-white light:text-gray-900">Gap Detail Evidence</p>
                <p className="mt-1 text-xs leading-5 text-amber-100/85 light:text-amber-800">
                  {gapDetail.message}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              <span className="rounded-full border border-amber-400/30 px-3 py-1 text-amber-100 light:text-amber-800">
                {gapDetail.source_sheet}
              </span>
              <span className="rounded-full border border-amber-400/30 px-3 py-1 text-amber-100 light:text-amber-800">
                {formatNumber(gapDetail.total_windows)} windows
              </span>
              <span className="rounded-full border border-amber-400/30 px-3 py-1 text-amber-100 light:text-amber-800">
                {formatMoney(gapDetail.total_missed_hour_revenue)}
              </span>
            </div>
          </div>

          {gapDetail.status === 'healthy' ? (
            <>
              <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-4">
                {topGapTypes.map(type => (
                  <div key={type.gap_type} className="rounded-lg border border-amber-400/20 bg-gray-950/30 p-3 light:bg-white">
                    <p className="text-xs font-semibold text-white light:text-gray-900">{type.gap_type}</p>
                    <p className="mt-2 text-sm text-amber-100 light:text-amber-800">
                      {formatMoney(type.missed_hour_revenue)} · {formatNumber(type.missed_hours, 1)} hours
                    </p>
                    <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{formatNumber(type.window_count)} capacity windows</p>
                  </div>
                ))}
              </div>

              {topGapRoutes.length ? (
                <div className="mt-4 overflow-x-auto rounded-lg border border-amber-400/20">
                  <table className="min-w-[1060px] divide-y divide-amber-400/20 text-sm">
                    <thead className="bg-gray-950/35 light:bg-white/70">
                      <tr className="text-left text-xs uppercase text-amber-100/70 light:text-amber-800">
                        <th className="px-3 py-2 font-medium">Route</th>
                        <th className="px-3 py-2 font-medium">Entity</th>
                        <th className="px-3 py-2 font-medium">Windows</th>
                        <th className="px-3 py-2 font-medium">Missed Revenue</th>
                        <th className="px-3 py-2 font-medium">Sample Capacity Windows</th>
                        <th className="px-3 py-2 font-medium">Benchmark</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-amber-400/20">
                      {topGapRoutes.map(route => (
                        <tr key={`${route.entity}-${route.route}`} className="align-top">
                          <td className="px-3 py-3 font-semibold text-white light:text-gray-900">{route.route}</td>
                          <td className="px-3 py-3 text-gray-300 light:text-gray-700">{route.entity}</td>
                          <td className="px-3 py-3 text-gray-300 light:text-gray-700">
                            {formatNumber(route.window_count)} · {formatNumber(route.missed_hours, 1)} hours
                          </td>
                          <td className="px-3 py-3 font-semibold text-amber-100 light:text-amber-800">{formatMoney(route.missed_hour_revenue)}</td>
                          <td className="px-3 py-3">
                            <div className="flex max-w-[420px] flex-wrap gap-1.5 text-xs text-gray-400 light:text-gray-600">
                              {route.sample_windows.map(window => (
                                <span key={`${route.route}-${window}`} className="rounded-full border border-amber-400/20 px-2 py-1">
                                  {window}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td className="px-3 py-3">
                            <a
                              href={benchmarkWatchlistHref(route.route)}
                              className="inline-flex h-8 items-center gap-2 rounded-lg border border-cyan-400/30 bg-cyan-400/10 px-3 text-xs font-semibold text-cyan-100 transition hover:bg-cyan-400/20 light:text-cyan-700"
                              title={`Open pickup/delivery benchmark watchlist for ${route.route}`}
                            >
                              <Timer className="h-3.5 w-3.5" aria-hidden="true" />
                              Open
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}

              {topGapWindows.length ? (
                <div className="mt-4 overflow-x-auto rounded-lg border border-amber-400/20">
                  <table className="min-w-[1100px] divide-y divide-amber-400/20 text-sm">
                    <thead className="bg-gray-950/35 light:bg-white/70">
                      <tr className="text-left text-xs uppercase text-amber-100/70 light:text-amber-800">
                        <th className="px-3 py-2 font-medium">Route</th>
                        <th className="px-3 py-2 font-medium">Date</th>
                        <th className="px-3 py-2 font-medium">Gap Window</th>
                        <th className="px-3 py-2 font-medium">Gap Type</th>
                        <th className="px-3 py-2 font-medium">Missed Revenue</th>
                        <th className="px-3 py-2 font-medium">Workbook Row</th>
                        <th className="px-3 py-2 font-medium">Benchmark</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-amber-400/20">
                      {topGapWindows.map(window => (
                        <tr key={`${window.source_row}-${window.route}-${window.gap_window}`} className="align-top">
                          <td className="px-3 py-3">
                            <p className="font-semibold text-white light:text-gray-900">{window.route}</p>
                            <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{window.entity}</p>
                          </td>
                          <td className="px-3 py-3 text-gray-300 light:text-gray-700">{window.date}</td>
                          <td className="px-3 py-3">
                            <p className="max-w-[260px] text-gray-200 light:text-gray-800">{window.gap_window}</p>
                            <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{window.paid_window_basis}</p>
                          </td>
                          <td className="px-3 py-3 text-gray-300 light:text-gray-700">{window.gap_type || 'Unspecified'}</td>
                          <td className="px-3 py-3">
                            <p className="font-semibold text-amber-100 light:text-amber-800">{formatMoney(window.missed_hour_revenue)}</p>
                            <p className="mt-1 text-xs text-gray-500 light:text-gray-600">
                              {formatNumber(window.missed_hours, 1)} hours at {formatMoney(window.company_avg_revenue_per_hour)}/hr
                            </p>
                          </td>
                          <td className="px-3 py-3 text-gray-400 light:text-gray-600">Row {window.source_row}</td>
                          <td className="px-3 py-3">
                            <a
                              href={benchmarkWatchlistHref(window.route)}
                              className="inline-flex h-8 items-center gap-2 rounded-lg border border-cyan-400/30 bg-cyan-400/10 px-3 text-xs font-semibold text-cyan-100 transition hover:bg-cyan-400/20 light:text-cyan-700"
                              title={`Open pickup/delivery benchmark watchlist for ${window.route}`}
                            >
                              <Timer className="h-3.5 w-3.5" aria-hidden="true" />
                              Open
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}

      {hasHealthyPayload && (
        <div className="mt-5 rounded-lg border border-blue-500/20 bg-blue-500/10 p-3 light:bg-blue-50">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex items-start gap-2">
              <BarChart3 className="mt-0.5 h-4 w-4 shrink-0 text-blue-300 light:text-blue-700" />
              <div>
                <p className="text-sm font-semibold text-white light:text-gray-900">KPI Trend Capture</p>
                <p className="mt-1 text-xs leading-5 text-blue-100/80 light:text-blue-800">
                  {payload.comparison.status === 'healthy'
                    ? `Comparing WE ${payload.period_end} with WE ${payload.comparison.period_end_prior}.`
                    : payload.comparison.message}
                </p>
              </div>
            </div>
            <span className="rounded-full border border-blue-400/30 px-3 py-1 text-xs text-blue-100 light:text-blue-700">
              Local capture only
            </span>
          </div>
          {comparisonMetrics.length ? (
            <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-4">
              {comparisonMetrics.map(metric => (
                <div key={metric.key} className="rounded-lg border border-blue-400/20 bg-gray-950/35 p-3 light:bg-white">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] uppercase text-gray-500 light:text-gray-600">{metric.label}</p>
                    <ComparisonIcon direction={metric.direction} />
                  </div>
                  <p className="mt-1 text-lg font-semibold text-white light:text-gray-900">{formatComparisonValue(metric)}</p>
                  <p className="mt-1 text-[11px] text-gray-500 light:text-gray-600">vs prior approved workbook</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-3 rounded-lg border border-dashed border-blue-400/30 p-3 text-xs leading-5 text-blue-100/80 light:text-blue-800">
              Trend deltas are held until `FLEETPULSE_UNIFIED_ROUTE_LH_SCORECARD_PRIOR_PATH` points to an approved prior workbook. The current KPIs remain source-backed from the May 23 artifact.
            </div>
          )}
        </div>
      )}

      {hasHealthyPayload && payload?.action_summary.length ? (
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

      {hasHealthyPayload && (topActionRows.length || topRouteRows.length) ? (
        <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-gray-800 bg-gray-950/35 p-4 light:border-gray-200 light:bg-gray-50">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h4 className="text-sm font-semibold text-white light:text-gray-900">Missed Revenue by Action</h4>
              <span className="text-xs text-gray-500 light:text-gray-600">{topActionRows.length} buckets</span>
            </div>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={topActionRows} margin={{ top: 8, right: 8, left: 0, bottom: 36 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
                <XAxis dataKey="name" stroke={CHART_AXIS} tick={{ fontSize: 10 }} interval={0} angle={-18} textAnchor="end" height={56} />
                <YAxis stroke={CHART_AXIS} tick={{ fontSize: 11 }} tickFormatter={value => formatCompactMoney(Number(value))} width={48} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="missed_hour_revenue" name="Missed revenue" radius={[5, 5, 0, 0]}>
                  {topActionRows.map((row, index) => <Cell key={row.name} fill={ACTION_COLORS[index % ACTION_COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950/35 p-4 light:border-gray-200 light:bg-gray-50">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h4 className="text-sm font-semibold text-white light:text-gray-900">Top Route/LH Missed Revenue</h4>
              <span className="text-xs text-gray-500 light:text-gray-600">Ranked by workbook revenue</span>
            </div>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={topRouteRows} layout="vertical" margin={{ top: 4, right: 12, left: 18, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" horizontal={false} />
                <XAxis type="number" stroke={CHART_AXIS} tick={{ fontSize: 11 }} tickFormatter={value => formatCompactMoney(Number(value))} />
                <YAxis type="category" dataKey="name" stroke={CHART_AXIS} tick={{ fontSize: 11 }} width={78} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="missed_hour_revenue" name="Missed revenue" fill={ROUTE_COLOR} radius={[0, 5, 5, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
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
