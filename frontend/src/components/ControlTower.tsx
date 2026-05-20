import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock,
  Code2,
  Database,
  DollarSign,
  GitBranch,
  Layers3,
  MapPin,
  RadioTower,
  TrendingUp,
  Truck,
} from 'lucide-react'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  useControlTowerAgents,
  useControlTowerAttention,
  useControlTowerCodex,
  useControlTowerFinancial,
  useControlTowerSeatKpis,
  useControlTowerTrailerTracking,
  useControlTowerOverview,
  useControlTowerTrailers,
  useLaneStabilityWindow,
  useOperatingCostWindow,
} from '../hooks/useGeotab'
import type {
  ControlTowerFeedStatus,
  ControlTowerSeatKpiCoverageResponse,
  ControlTowerSeatKpiItem,
  ControlTowerSectionSummary,
  ControlTowerStatus,
  LaneStabilityPayload,
  OperatingCostSnapshot,
  OperatingCostWeeklyRow,
} from '../types/fleet'

type SectionKey = 'attention' | 'trailers' | 'financial' | 'agents' | 'codex'

const sections: Array<{ key: SectionKey; label: string; icon: typeof AlertTriangle }> = [
  { key: 'attention', label: 'Attention', icon: AlertTriangle },
  { key: 'trailers', label: 'Trailers', icon: Truck },
  { key: 'financial', label: 'Financial', icon: DollarSign },
  { key: 'agents', label: 'Agents', icon: Bot },
  { key: 'codex', label: 'Codex', icon: Code2 },
]

const statusStyles: Record<ControlTowerStatus, string> = {
  healthy: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  warning: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  critical: 'bg-red-500/15 text-red-300 border-red-500/30',
  awaiting_feed: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  unavailable: 'bg-gray-500/15 text-gray-300 border-gray-500/30',
}

const severityStyles = {
  critical: 'border-red-500/40 bg-red-500/10 text-red-200',
  high: 'border-orange-500/40 bg-orange-500/10 text-orange-200',
  medium: 'border-amber-500/40 bg-amber-500/10 text-amber-200',
  low: 'border-blue-500/40 bg-blue-500/10 text-blue-200',
}

function humanStatus(status: ControlTowerStatus) {
  return status.replace('_', ' ')
}

function formatTime(value: string | null | undefined) {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return parsed.toLocaleString()
}

function money(value: number | null | undefined) {
  if (value === null || value === undefined) return 'Awaiting feed'
  return value.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
}

function compactMoney(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Awaiting feed'
  return Number(value).toLocaleString(undefined, {
    currency: 'USD',
    maximumFractionDigits: 1,
    notation: 'compact',
    style: 'currency',
  })
}

function rate(value: number | null | undefined, suffix = '/mi') {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Awaiting feed'
  return `$${Number(value).toFixed(2)}${suffix}`
}

function number(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Awaiting feed'
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits })
}

function percent(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Awaiting feed'
  const numeric = Math.abs(Number(value)) <= 1 ? Number(value) * 100 : Number(value)
  return `${numeric.toFixed(1)}%`
}

function dateLabel(value: string | null | undefined) {
  if (!value) return '—'
  const parsed = new Date(`${value}T00:00:00Z`)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

function finite(value: number | null | undefined) {
  return Number.isFinite(Number(value)) ? Number(value) : null
}

function average(values: Array<number | null | undefined>) {
  const usable = values.map(finite).filter((value): value is number => value !== null)
  if (!usable.length) return null
  return usable.reduce((sum, value) => sum + value, 0) / usable.length
}

function stablePct(value: number | null | undefined) {
  const numeric = finite(value) ?? 0
  return Math.abs(numeric) <= 1 ? numeric * 100 : numeric
}

function weekKey(value: string) {
  const parsed = new Date(`${value}T00:00:00Z`)
  if (Number.isNaN(parsed.getTime())) return value
  const day = parsed.getUTCDay()
  parsed.setUTCDate(parsed.getUTCDate() - day)
  return parsed.toISOString().slice(0, 10)
}

function StatusPill({ status }: { status: ControlTowerStatus }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize ${statusStyles[status]}`}>
      {status === 'healthy' ? <CheckCircle2 className="h-3 w-3" /> : <Clock className="h-3 w-3" />}
      {humanStatus(status)}
    </span>
  )
}

function Panel({ children, className = '' }: { children?: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-gray-700/50 bg-gray-900/70 p-4 shadow-lg shadow-black/10 light:bg-white light:border-gray-200 ${className}`}>
      {children}
    </div>
  )
}

function FeedList({ feeds }: { feeds: ControlTowerFeedStatus[] }) {
  return (
    <div className="space-y-2">
      {feeds.map(feed => (
        <div key={feed.name} className="rounded-lg border border-gray-700/40 bg-gray-800/40 p-3 light:bg-gray-50 light:border-gray-200">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-white light:text-gray-900">{feed.name}</p>
              <p className="text-xs text-gray-400 light:text-gray-600">{feed.source_authority}</p>
            </div>
            <StatusPill status={feed.status} />
          </div>
          <p className="mt-2 text-sm text-gray-300 light:text-gray-700">{feed.message}</p>
          {feed.required_config.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {feed.required_config.map(item => (
                <span key={item} className="rounded bg-gray-950/60 px-2 py-1 font-mono text-[11px] text-gray-300 light:bg-gray-200 light:text-gray-700">
                  {item}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function SummaryCard({ section }: { section: ControlTowerSectionSummary }) {
  return (
    <Panel>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase text-gray-500 light:text-gray-600">{section.label}</p>
          <p className="mt-1 text-2xl font-bold text-white light:text-gray-900">{section.item_count}</p>
        </div>
        <StatusPill status={section.status} />
      </div>
      <p className="mt-3 text-sm text-gray-300 light:text-gray-700">{section.message}</p>
      <p className="mt-2 text-xs text-gray-500 light:text-gray-600">{section.source_authority}</p>
    </Panel>
  )
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-dashed border-gray-700 p-5 text-center text-sm text-gray-400 light:border-gray-300 light:text-gray-600">
      {label}
    </div>
  )
}

interface FinancialTrendRow {
  week_start: string
  label: string
  total_cost: number
  driver_pay: number
  fuel_cost: number
  maintenance_cost: number
  fleet_overhead: number
  cost_per_mile: number | null
  miles: number
}

interface StabilityTrendRow {
  week_start: string
  label: string
  stable_cov_pct: number
  critical_lanes: number
  cross_route_lanes: number
}

function buildFinancialTrendRows(snapshot: OperatingCostSnapshot | null | undefined): FinancialTrendRow[] {
  return (snapshot?.weekly ?? []).slice(-52).map((row: OperatingCostWeeklyRow) => {
    const totalCost = finite(row.true_operating_cost) ?? finite(row.known_operating_cost) ?? 0
    const costPerMile = finite(row.true_cost_per_mile) ?? finite(row.known_cost_per_mile)
    const fleetOverhead = (
      Number(row.insurance_cost || 0)
      + Number(row.employee_cost || 0)
      + Number(row.rental_trucks_trailers_cost || 0)
      + Number(row.other_expense_cost || 0)
    )
    return {
      week_start: row.week_start,
      label: dateLabel(row.week_start),
      total_cost: totalCost,
      driver_pay: Number(row.driver_pay || 0),
      fuel_cost: Number(row.fuel_cost || row.fuel_card_audit_cost || 0),
      maintenance_cost: Number(row.maintenance_cost || 0),
      fleet_overhead: Number(fleetOverhead.toFixed(2)),
      cost_per_mile: costPerMile,
      miles: Number(row.miles || 0),
    }
  })
}

function buildStabilityTrendRows(payload: LaneStabilityPayload | null | undefined): StabilityTrendRow[] {
  const buckets = new Map<string, { count: number; stable: number; critical: number; crossRoute: number }>()
  for (const row of payload?.rows ?? []) {
    const key = weekKey(row.snapshot_date)
    const bucket = buckets.get(key) ?? { count: 0, stable: 0, critical: 0, crossRoute: 0 }
    bucket.count += 1
    bucket.stable += stablePct(row.stable_cov_pct)
    bucket.critical = Math.max(bucket.critical, Number(row.critical_lanes || 0))
    bucket.crossRoute = Math.max(bucket.crossRoute, Number(row.cross_route_lanes || 0))
    buckets.set(key, bucket)
  }
  return [...buckets.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .slice(-52)
    .map(([key, bucket]) => ({
      week_start: key,
      label: dateLabel(key),
      stable_cov_pct: bucket.count ? Number((bucket.stable / bucket.count).toFixed(1)) : 0,
      critical_lanes: bucket.critical,
      cross_route_lanes: bucket.crossRoute,
    }))
}

function latestValue<T>(rows: T[]): T | null {
  return rows.length ? rows[rows.length - 1] : null
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
  tone?: 'neutral' | 'good' | 'warning' | 'bad'
}) {
  const toneClass = {
    neutral: 'text-white light:text-gray-900',
    good: 'text-emerald-300 light:text-emerald-700',
    warning: 'text-amber-300 light:text-amber-700',
    bad: 'text-red-300 light:text-red-700',
  }[tone]

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-3 light:border-gray-200 light:bg-gray-50">
      <div className="text-[10px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`mt-1 text-xl font-semibold ${toneClass}`}>{value}</div>
      {helper && <div className="mt-1 text-xs text-gray-500 light:text-gray-600">{helper}</div>}
    </div>
  )
}

function FinancialOps52WeekPanel({
  operatingCost,
  laneStability,
  loading,
  error,
}: {
  operatingCost: OperatingCostSnapshot | null
  laneStability: LaneStabilityPayload | null
  loading: boolean
  error: string | null
}) {
  const costRows = useMemo(() => buildFinancialTrendRows(operatingCost), [operatingCost])
  const stabilityRows = useMemo(() => buildStabilityTrendRows(laneStability), [laneStability])
  const latestCost = latestValue(costRows)
  const latestStability = latestValue(stabilityRows)
  const previousFourCost = costRows.slice(-5, -1)
  const costAvg4 = average(previousFourCost.map(row => row.total_cost))
  const cpmAvg4 = average(previousFourCost.map(row => row.cost_per_mile))
  const unresolved = operatingCost?.unresolved_sources ?? []
  const mileageCoveragePending = unresolved.includes('telemetry')
  const summaryCpm = mileageCoveragePending
    ? null
    : operatingCost?.summary.true_cost_per_mile ?? operatingCost?.summary.known_cost_per_mile
  const costSpike = latestCost && costAvg4 ? latestCost.total_cost > costAvg4 * 1.15 : false
  const cpmSpike = !mileageCoveragePending && latestCost?.cost_per_mile && cpmAvg4 ? latestCost.cost_per_mile > cpmAvg4 * 1.1 : false
  const laneCoverageWarning = Number(laneStability?.summary.today_stable_cov_pct ?? latestStability?.stable_cov_pct ?? 100) < 80
  const criticalLaneWarning = Number(laneStability?.summary.critical_today ?? latestStability?.critical_lanes ?? 0) > 0
  const signals = [
    costSpike ? 'Weekly cost spike over 4-week average' : null,
    cpmSpike ? 'CPM spike over 4-week average' : null,
    laneCoverageWarning ? 'Stable coverage below 80%' : null,
    criticalLaneWarning ? 'Critical lanes need review' : null,
    unresolved.length ? `Unresolved source: ${unresolved.join(', ')}` : null,
  ].filter((item): item is string => Boolean(item))

  return (
    <Panel className="xl:col-span-3">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold text-white light:text-gray-900">
            <Activity className="h-5 w-5 text-emerald-300" />
            Financial Ops Cost + Lane Stability
          </h3>
          <p className="mt-1 text-sm text-gray-400 light:text-gray-600">
            Last 52 weeks · read-only from Geotab, Xcelerator, QBO, AtoB, and lane stability lakehouse
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusPill status={signals.length ? 'warning' : operatingCost ? 'healthy' : 'awaiting_feed'} />
          <span className="rounded-full border border-gray-700 px-2 py-1 text-[11px] text-gray-400 light:border-gray-200 light:text-gray-600">
            {operatingCost?.period_start ?? 'pending'} to {operatingCost?.period_end ?? 'pending'}
          </span>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200 light:bg-red-50 light:text-red-700">
          {error}
        </div>
      )}

      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <MetricTile
          label="52W Cost"
          value={compactMoney(operatingCost?.summary.true_operating_cost ?? operatingCost?.summary.known_operating_cost)}
          helper={operatingCost?.complete_cost_available ? 'Complete cost stack' : 'Known cost stack'}
          tone={signals.length ? 'warning' : 'neutral'}
        />
        <MetricTile
          label="52W CPM"
          value={rate(summaryCpm)}
          helper={mileageCoveragePending ? `Pending full Geotab miles (${number(operatingCost?.summary.miles)} captured)` : `${number(operatingCost?.summary.miles)} miles`}
          tone={mileageCoveragePending ? 'warning' : cpmSpike ? 'bad' : 'neutral'}
        />
        <MetricTile
          label="Latest Week"
          value={compactMoney(latestCost?.total_cost)}
          helper={latestCost?.week_start ? `Week of ${dateLabel(latestCost.week_start)}` : 'Awaiting feed'}
          tone={costSpike ? 'bad' : 'neutral'}
        />
        <MetricTile
          label="Stable Coverage"
          value={percent(laneStability?.summary.today_stable_cov_pct ?? latestStability?.stable_cov_pct)}
          helper={`${number(laneStability?.summary.critical_today ?? latestStability?.critical_lanes)} critical lanes`}
          tone={laneCoverageWarning || criticalLaneWarning ? 'warning' : 'good'}
        />
        <MetricTile
          label="Cross-Route"
          value={number(laneStability?.summary.cross_route_today ?? latestStability?.cross_route_lanes)}
          helper="Lanes with 2+ truck slots"
          tone={Number(laneStability?.summary.cross_route_today ?? latestStability?.cross_route_lanes ?? 0) > 0 ? 'warning' : 'neutral'}
        />
      </div>

      {signals.length > 0 && (
        <div className="mb-5 flex flex-wrap gap-2">
          {signals.map(signal => (
            <span key={signal} className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs text-amber-200 light:text-amber-700">
              {signal}
            </span>
          ))}
        </div>
      )}

      {loading && !costRows.length ? (
        <EmptyState label="Loading 52-week financial operating cost and lane stability..." />
      ) : costRows.length || stabilityRows.length ? (
        <div className="grid gap-5 2xl:grid-cols-2">
          <div className="rounded-lg border border-gray-800 bg-gray-950/30 p-3 light:border-gray-200 light:bg-gray-50">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-200 light:text-gray-800">
              <TrendingUp className="h-4 w-4 text-emerald-300" />
              Weekly Cost Stack
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={costRows}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="label" stroke="#9ca3af" tick={{ fontSize: 11 }} minTickGap={28} />
                <YAxis yAxisId="cost" stroke="#9ca3af" tick={{ fontSize: 11 }} tickFormatter={(value) => `$${Number(value) / 1000}k`} />
                <YAxis yAxisId="rate" orientation="right" stroke="#9ca3af" tick={{ fontSize: 11 }} tickFormatter={(value) => `$${Number(value).toFixed(2)}`} />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                  labelStyle={{ color: '#9ca3af' }}
                  formatter={(value: number, name: string) => [
                    name === 'CPM' ? rate(value) : compactMoney(value),
                    name,
                  ]}
                />
                <Legend />
                <Bar yAxisId="cost" dataKey="driver_pay" name="Driver Pay" stackId="cost" fill="#22c55e" />
                <Bar yAxisId="cost" dataKey="fuel_cost" name="Fuel" stackId="cost" fill="#38bdf8" />
                <Bar yAxisId="cost" dataKey="maintenance_cost" name="Maintenance" stackId="cost" fill="#f97316" />
                <Bar yAxisId="cost" dataKey="fleet_overhead" name="Fleet/Ops Overhead" stackId="cost" fill="#a78bfa" />
                <Line yAxisId="rate" type="monotone" dataKey="cost_per_mile" name="CPM" stroke="#f8fafc" strokeWidth={2.5} dot={false} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="rounded-lg border border-gray-800 bg-gray-950/30 p-3 light:border-gray-200 light:bg-gray-50">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-200 light:text-gray-800">
              <GitBranch className="h-4 w-4 text-cyan-300" />
              Lane Stability Risk
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={stabilityRows}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="label" stroke="#9ca3af" tick={{ fontSize: 11 }} minTickGap={28} />
                <YAxis yAxisId="pct" domain={[0, 100]} stroke="#9ca3af" tick={{ fontSize: 11 }} tickFormatter={(value) => `${Number(value).toFixed(0)}%`} />
                <YAxis yAxisId="lanes" orientation="right" stroke="#9ca3af" tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                  labelStyle={{ color: '#9ca3af' }}
                  formatter={(value: number, name: string) => [
                    name === 'Stable Coverage' ? percent(value) : number(value),
                    name,
                  ]}
                />
                <Legend />
                <Bar yAxisId="lanes" dataKey="critical_lanes" name="Critical Lanes" fill="#ef4444" radius={[3, 3, 0, 0]} />
                <Bar yAxisId="lanes" dataKey="cross_route_lanes" name="Cross-Route Lanes" fill="#f59e0b" radius={[3, 3, 0, 0]} />
                <Line yAxisId="pct" type="monotone" dataKey="stable_cov_pct" name="Stable Coverage" stroke="#22d3ee" strokeWidth={2.5} dot={false} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <EmptyState label="No 52-week cost or lane-stability rows returned yet." />
      )}
    </Panel>
  )
}

function SeatKpiNeedsPanel({
  coverage,
  loading,
  error,
}: {
  coverage: ControlTowerSeatKpiCoverageResponse | null
  loading: boolean
  error: string | null
}) {
  const kpis = coverage?.kpis ?? []
  const kpisBySeat = useMemo(() => {
    const map = new Map<string, ControlTowerSeatKpiItem[]>()
    kpis.forEach(item => {
      const current = map.get(item.seat_label) ?? []
      current.push(item)
      map.set(item.seat_label, current)
    })
    return [...map.entries()]
  }, [kpis])

  return (
    <Panel className="xl:col-span-3">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold text-white light:text-gray-900">
            <Database className="h-5 w-5 text-blue-300" />
            Seat KPI Coverage Needed
          </h3>
          <p className="mt-1 text-sm text-gray-400 light:text-gray-600">
            Fixed-seat scorecards need live KPI snapshots before FleetPulse can rank seat performance.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 text-sm xl:grid-cols-4">
          <MetricTile label="Coverage" value={loading ? '...' : percent(coverage?.summary.coverage_pct)} />
          <MetricTile label="Live" value={loading ? '...' : number(coverage?.summary.healthy)} tone="good" />
          <MetricTile label="Partial" value={loading ? '...' : number(coverage?.summary.warning)} tone="warning" />
          <MetricTile label="Missing" value={loading ? '...' : number(coverage?.summary.awaiting_feed)} tone="bad" />
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200 light:text-amber-700">
          Seat KPI coverage endpoint is not available to this session: {error}
        </div>
      )}

      {loading && !kpis.length ? (
        <EmptyState label="Loading seat KPI coverage..." />
      ) : kpisBySeat.length ? (
        <div className="grid gap-3 xl:grid-cols-5">
          {kpisBySeat.map(([seat, items]) => {
            const missing = items.filter(item => item.status === 'awaiting_feed' || item.status === 'unavailable').length
            return (
              <div key={seat} className="rounded-lg border border-gray-800 bg-gray-950/40 p-3 light:border-gray-200 light:bg-gray-50">
                <div className="flex items-start justify-between gap-2">
                  <div className="text-sm font-semibold text-white light:text-gray-900">{seat}</div>
                  <span className="rounded-full border border-gray-700 px-2 py-0.5 text-[11px] text-gray-400 light:border-gray-200 light:text-gray-600">
                    {missing} missing
                  </span>
                </div>
                <div className="mt-3 space-y-2">
                  {items.map(item => (
                    <div key={item.key} className="rounded-md border border-gray-800 bg-gray-900/60 p-2 light:border-gray-200 light:bg-white">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate text-xs font-semibold text-gray-100 light:text-gray-900">{item.label}</div>
                          <div className="mt-1 text-[11px] text-gray-500 light:text-gray-600">{item.target}</div>
                        </div>
                        <StatusPill status={item.status} />
                      </div>
                      <div className="mt-2 text-[11px] leading-4 text-gray-400 light:text-gray-700">{item.owner_action}</div>
                      <div className="mt-2 text-[11px] text-gray-500 light:text-gray-600">{item.source_authority}</div>
                      {item.source_route && (
                        <div className="mt-1 truncate font-mono text-[10px] text-cyan-300 light:text-cyan-700">{item.source_route}</div>
                      )}
                      {item.blocker && (
                        <div className="mt-1 truncate font-mono text-[10px] text-amber-300 light:text-amber-700">{item.blocker}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <EmptyState label="No seat KPI contracts returned yet." />
      )}
    </Panel>
  )
}

export default function ControlTower() {
  const [active, setActive] = useState<SectionKey>('trailers')
  const overview = useControlTowerOverview()
  const attention = useControlTowerAttention()
  const trailers = useControlTowerTrailers()
  const liveTrailers = useControlTowerTrailerTracking()
  const financialActive = active === 'financial'
  const financial = useControlTowerFinancial(financialActive)
  const financialReady = financialActive && Boolean(financial.data || financial.error)
  const laneStability52 = useLaneStabilityWindow(364, financialReady)
  const seatKpis = useControlTowerSeatKpis(financialReady)
  const operatingCostReady = financialReady && Boolean(laneStability52.data || laneStability52.error) && Boolean(seatKpis.data || seatKpis.error)
  const operatingCost52 = useOperatingCostWindow(364, operatingCostReady)
  const agents = useControlTowerAgents()
  const codex = useControlTowerCodex()

  const summaryByKey = useMemo(() => {
    const map = new Map<SectionKey, ControlTowerSectionSummary>()
    overview.data?.sections.forEach(section => {
      map.set(section.key, section)
    })
    return map
  }, [overview.data])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <RadioTower className="h-6 w-6 text-cyan-300" />
          <div>
            <h2 className="text-xl font-bold text-white light:text-gray-900">K1 Operations Hub</h2>
            <p className="text-sm text-gray-400 light:text-gray-600">FleetPulse replacement shell for K1 Command Center front-end surfaces</p>
          </div>
        </div>
        <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-200 light:text-cyan-700">
          Projection mode: read-only
        </span>
      </div>

      <div className="flex flex-col gap-3 rounded-lg border border-cyan-500/25 bg-cyan-500/10 p-4 text-sm text-cyan-100 light:bg-cyan-50 light:text-cyan-900 sm:flex-row sm:items-start">
        <Layers3 className="mt-0.5 h-5 w-5 shrink-0" />
        <div>
          <p className="font-semibold">Command Center front-end replacement is enabled as a read-only migration path.</p>
          <p className="mt-1 text-cyan-100/80 light:text-cyan-800">
            FleetPulse displays operating status only. AP/QBO writes, FinanceOps lineage, Xcelerator dispatch state, and Geotab telemetry remain in their owning services.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {sections.map(({ key }) => {
          const section = summaryByKey.get(key)
          return section ? (
            <SummaryCard key={key} section={section} />
          ) : (
            <Panel key={key} className="h-32 animate-pulse" />
          )
        })}
      </div>

      <nav className="flex flex-wrap gap-2 rounded-lg border border-gray-700/50 bg-gray-900/70 p-2 light:bg-white light:border-gray-200">
        {sections.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActive(key)}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition ${
              active === key
                ? 'bg-cyan-500 text-white'
                : 'text-gray-400 hover:bg-gray-800 hover:text-white light:text-gray-600 light:hover:bg-gray-100 light:hover:text-gray-900'
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </nav>

      {active === 'attention' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Panel className="xl:col-span-2">
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Exception Queue</h3>
            {attention.loading ? (
              <EmptyState label="Loading attention queue..." />
            ) : attention.data?.items.length ? (
              <div className="space-y-2">
                {attention.data.items.map(item => (
                  <div key={item.id} className={`rounded-lg border p-3 ${severityStyles[item.severity]}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold">{item.category}</p>
                        <p className="mt-1 text-sm text-gray-200 light:text-gray-800">{item.message}</p>
                      </div>
                      <span className="rounded bg-black/20 px-2 py-1 text-xs">{item.action}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-400 light:text-gray-600">
                      <span>{item.source_authority}</span>
                      <span>{formatTime(item.timestamp)}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState label="No live exception items returned by configured feeds." />
            )}
          </Panel>
          <Panel>
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Feeds</h3>
            <FeedList feeds={attention.data?.feeds || []} />
          </Panel>
        </motion.div>
      )}

      {active === 'trailers' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Panel className="xl:col-span-2">
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Trailer Geofence Tracker</h3>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {[
                ['Total Trailers', trailers.data?.summary.total_trailers ?? 0],
                ['GPS Active', trailers.data?.summary.gps_active ?? 0],
                ['GPS Inactive', trailers.data?.summary.gps_inactive ?? 0],
                ['Events Today', trailers.data?.summary.geofence_events_today ?? 0],
                ['Custody', liveTrailers.data?.summary.custody_inferred ?? 0],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border border-gray-700/50 bg-gray-800/50 p-3 light:bg-gray-50 light:border-gray-200">
                  <p className="text-xs text-gray-400 light:text-gray-600">{label}</p>
                  <p className="mt-1 text-2xl font-bold text-white light:text-gray-900">{value}</p>
                </div>
              ))}
            </div>
            <h4 className="mt-5 mb-2 text-sm font-semibold text-gray-200 light:text-gray-800">Live Custody</h4>
            <div className="max-h-72 overflow-auto rounded-lg border border-gray-700/40 light:border-gray-200">
              {(liveTrailers.data?.trailers || []).slice(0, 12).map(trailer => (
                <div key={trailer.geotab_device_id || trailer.trailer_id} className="grid grid-cols-1 gap-2 border-b border-gray-800/60 p-3 text-sm last:border-b-0 light:border-gray-200 md:grid-cols-4">
                  <span className="font-semibold text-white light:text-gray-900">{trailer.trailer_id}</span>
                  <span className="capitalize text-gray-300 light:text-gray-700">{trailer.gps_status}</span>
                  <span className="text-gray-300 light:text-gray-700">{trailer.custody.vehicle_name || 'Unassigned'}</span>
                  <span className="text-gray-400 light:text-gray-600">{trailer.custody.driver_name || trailer.custody.confidence}</span>
                </div>
              ))}
              {!liveTrailers.data?.trailers.length && <EmptyState label="No live trailer custody rows returned yet." />}
            </div>
            <h4 className="mt-5 mb-2 text-sm font-semibold text-gray-200 light:text-gray-800">Yards</h4>
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {(trailers.data?.yard_locations || []).map(yard => (
                <div key={yard.name} className="flex items-center justify-between rounded-lg bg-gray-800/40 p-3 light:bg-gray-50">
                  <span className="flex items-center gap-2 text-sm text-gray-200 light:text-gray-800">
                    <MapPin className="h-4 w-4 text-cyan-300" />
                    {yard.name}
                  </span>
                  <span className="font-mono text-sm text-white light:text-gray-900">{yard.trailer_count}</span>
                </div>
              ))}
            </div>
          </Panel>
          <Panel>
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Feeds</h3>
            <FeedList feeds={trailers.data?.feeds || []} />
          </Panel>
        </motion.div>
      )}

      {active === 'financial' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Panel className="xl:col-span-2">
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Financial Ops</h3>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
              <div className="rounded-lg bg-gray-800/50 p-4 light:bg-gray-50">
                <p className="text-xs text-gray-400 light:text-gray-600">AP Pending</p>
                <p className="mt-1 text-xl font-bold text-white light:text-gray-900">{money(financial.data?.accounts_payable.pending_amount)}</p>
                <p className="mt-1 text-xs text-gray-500">{financial.data?.accounts_payable.pending_bills ?? 0} bills</p>
              </div>
              <div className="rounded-lg bg-gray-800/50 p-4 light:bg-gray-50">
                <p className="text-xs text-gray-400 light:text-gray-600">AP Overdue</p>
                <p className="mt-1 text-xl font-bold text-white light:text-gray-900">{money(financial.data?.accounts_payable.overdue_amount)}</p>
                <p className="mt-1 text-xs text-gray-500">{financial.data?.accounts_payable.overdue_count ?? 0} bills</p>
              </div>
              <div className="rounded-lg bg-gray-800/50 p-4 light:bg-gray-50">
                <p className="text-xs text-gray-400 light:text-gray-600">Net Weekly</p>
                <p className="mt-1 text-xl font-bold text-white light:text-gray-900">{money(financial.data?.cash_flow.net_weekly)}</p>
                <p className="mt-1 text-xs text-gray-500">{financial.data?.source_authority || 'K1 Group LLC'}</p>
              </div>
              <div className="rounded-lg bg-gray-800/50 p-4 light:bg-gray-50">
                <p className="text-xs text-gray-400 light:text-gray-600">K1L Expenses</p>
                <p className="mt-1 text-xl font-bold text-white light:text-gray-900">{money(financial.data?.cash_flow.k1l_expense_total)}</p>
                <p className="mt-1 text-xs text-gray-500">QBO cost evidence</p>
              </div>
            </div>
            <h4 className="mt-5 mb-2 text-sm font-semibold text-gray-200 light:text-gray-800">AR Aging</h4>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              {(financial.data?.accounts_receivable || []).map(bucket => (
                <div key={bucket.bucket} className="rounded-lg border border-gray-700/40 p-3 light:border-gray-200">
                  <p className="text-xs text-gray-400 light:text-gray-600">{bucket.bucket}</p>
                  <p className="mt-1 font-semibold text-white light:text-gray-900">{money(bucket.amount)}</p>
                  <p className="text-xs text-gray-500">{bucket.count} rows</p>
                </div>
              ))}
            </div>
          </Panel>
          <Panel>
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Feeds</h3>
            <FeedList feeds={financial.data?.feeds || []} />
          </Panel>
          <FinancialOps52WeekPanel
            operatingCost={operatingCost52.data}
            laneStability={laneStability52.data}
            loading={financial.loading || operatingCost52.loading || laneStability52.loading}
            error={operatingCost52.error || laneStability52.error}
          />
          <SeatKpiNeedsPanel
            coverage={seatKpis.data}
            loading={seatKpis.loading}
            error={seatKpis.error}
          />
        </motion.div>
      )}

      {active === 'agents' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {(agents.data?.systems || []).map(system => (
            <Panel key={system.name}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold text-white light:text-gray-900">{system.name}</h3>
                  {system.usage && <p className="text-xs text-gray-400">{system.usage}</p>}
                </div>
                <StatusPill status={system.status} />
              </div>
              <div className="mt-4 space-y-2">
                {system.flows.map(flow => (
                  <div key={flow.name} className="rounded-lg bg-gray-800/40 p-3 light:bg-gray-50">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium text-white light:text-gray-900">{flow.name}</p>
                      <StatusPill status={flow.status} />
                    </div>
                    <p className="mt-1 text-xs text-gray-400 light:text-gray-600">{flow.detail}</p>
                  </div>
                ))}
              </div>
            </Panel>
          ))}
        </motion.div>
      )}

      {active === 'codex' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Panel className="xl:col-span-2">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-white light:text-gray-900">Codex / GitHub Runtime</h3>
                <p className="mt-1 text-sm text-gray-400 light:text-gray-600">{codex.data?.message || 'Loading runtime metadata...'}</p>
              </div>
              <StatusPill status={codex.data?.overall_status || 'awaiting_feed'} />
            </div>
            <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-2">
              {[
                ['Repository', codex.data?.repository || 'Awaiting feed'],
                ['Branch', codex.data?.branch || 'Awaiting feed'],
                ['Commit', codex.data?.commit_sha || 'Awaiting feed'],
                ['Run ID', codex.data?.run_id || 'Awaiting feed'],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg bg-gray-800/40 p-3 light:bg-gray-50">
                  <p className="text-xs text-gray-400 light:text-gray-600">{label}</p>
                  <p className="mt-1 font-mono text-sm text-white light:text-gray-900">{value}</p>
                </div>
              ))}
            </div>
          </Panel>
          <Panel>
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Feeds</h3>
            <FeedList feeds={codex.data?.feeds || []} />
          </Panel>
        </motion.div>
      )}
    </div>
  )
}
