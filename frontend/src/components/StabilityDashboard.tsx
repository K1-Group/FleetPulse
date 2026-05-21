import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { AlertTriangle, Database, GitBranch, Loader2, RefreshCw, Route, TrendingUp } from 'lucide-react'
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

type StabilityWindow = 42 | 91 | 182 | 364

interface LaneStabilityRow {
  snapshot_date: string
  stable_cov_pct: number
  critical_lanes: number
  cross_route_lanes: number
  total_orders: number
  scored_lanes: number
  stable_lanes: number
  total_revenue: number
  delta_cov_pp: number
}

interface LaneStabilitySummary {
  today_stable_cov_pct: number
  wow_delta_pp: number
  critical_today: number
  cross_route_today: number
  revenue_wtd: number
}

interface LaneStabilityPayload {
  window: StabilityWindow
  generated_at: string
  rows: LaneStabilityRow[]
  summary: LaneStabilitySummary
}

interface ChartRow extends LaneStabilityRow {
  label: string
  stableCovPct: number
  stableCovMa4: number | null
}

const WINDOWS: { label: string; value: StabilityWindow }[] = [
  { label: '6W', value: 42 },
  { label: '13W', value: 91 },
  { label: '26W', value: 182 },
  { label: '52W', value: 364 },
]

const CARD_CLASS = 'rounded-xl border border-gray-800/70 bg-gray-900/55 p-5 shadow-lg shadow-black/10 light:border-gray-200 light:bg-white'

function asPercent(value: number | null | undefined): number {
  const numeric = Number(value ?? 0)
  return Math.abs(numeric) <= 1 ? numeric * 100 : numeric
}

function formatPercent(value: number | null | undefined): string {
  return `${asPercent(value).toFixed(1)}%`
}

function formatDelta(value: number | null | undefined): string {
  const numeric = Number(value ?? 0)
  const sign = numeric > 0 ? '+' : ''
  return `${sign}${numeric.toFixed(1)} pp`
}

function formatNumber(value: number | null | undefined): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(Number(value ?? 0))
}

function formatMoney(value: number | null | undefined): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(Number(value ?? 0))
}

function formatDateLabel(value: string): string {
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(date)
}

function buildChartRows(rows: LaneStabilityRow[]): ChartRow[] {
  return rows.map((row, index) => {
    const stableCovPct = asPercent(row.stable_cov_pct)
    const rollingRows = rows.slice(Math.max(0, index - 27), index + 1)
    const movingAverage =
      rollingRows.reduce((total, item) => total + asPercent(item.stable_cov_pct), 0) / rollingRows.length
    return {
      ...row,
      label: formatDateLabel(row.snapshot_date),
      stableCovPct,
      stableCovMa4: Number.isFinite(movingAverage) ? Number(movingAverage.toFixed(2)) : null,
    }
  })
}

function SkeletonBlock({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-gray-800/70 light:bg-gray-200 ${className}`} />
}

function StatTile({
  label,
  value,
  helper,
  tone = 'neutral',
}: {
  label: string
  value: string
  helper?: string
  tone?: 'neutral' | 'good' | 'bad'
}) {
  const toneClass = tone === 'good' ? 'text-emerald-300' : tone === 'bad' ? 'text-red-300' : 'text-white light:text-gray-900'
  return (
    <div className={CARD_CLASS} data-testid={`stability-kpi-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500 light:text-gray-500">{label}</p>
      <p className={`mt-3 text-2xl font-semibold ${toneClass}`}>{value}</p>
      {helper && <p className="mt-2 text-xs text-gray-500 light:text-gray-500">{helper}</p>}
    </div>
  )
}

interface TooltipEntry {
  name?: string
  value?: number | string
  color?: string
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: TooltipEntry[]; label?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-gray-700 bg-gray-950/95 p-3 text-xs shadow-xl light:border-gray-200 light:bg-white">
      <p className="mb-2 font-semibold text-white light:text-gray-900">{label}</p>
      <div className="space-y-1">
        {payload.map((entry) => (
          <div key={`${entry.name}-${entry.color}`} className="flex items-center justify-between gap-5">
            <span style={{ color: entry.color }}>{entry.name}</span>
            <span className="font-medium text-white light:text-gray-900">
              {typeof entry.value === 'number' ? formatNumber(entry.value) : entry.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ChartCard({
  title,
  children,
  loading,
}: {
  title: string
  children: React.ReactNode
  loading?: boolean
}) {
  return (
    <section className={`${CARD_CLASS} min-h-[340px]`}>
      <h3 className="mb-4 text-base font-semibold text-white light:text-gray-900">{title}</h3>
      {loading ? <SkeletonBlock className="h-[260px]" /> : children}
    </section>
  )
}

export default function StabilityDashboard() {
  const [windowDays, setWindowDays] = useState<StabilityWindow>(42)
  const [payload, setPayload] = useState<LaneStabilityPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchStability = useCallback(
    async (signal?: AbortSignal, silent = false) => {
      if (silent) {
        setRefreshing(true)
      } else {
        setLoading(true)
      }
      setError(null)

      try {
        const response = await fetch(`/api/lane-stability?window=${windowDays}`, { signal })
        if (!response.ok) {
          throw new Error(`Lane Stability API returned ${response.status}`)
        }
        const nextPayload = (await response.json()) as LaneStabilityPayload
        setPayload(nextPayload)
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return
        setError(err instanceof Error ? err.message : 'Lane Stability API unavailable')
      } finally {
        if (silent) {
          setRefreshing(false)
        } else {
          setLoading(false)
        }
      }
    },
    [windowDays],
  )

  useEffect(() => {
    const controller = new AbortController()
    fetchStability(controller.signal)
    return () => controller.abort()
  }, [fetchStability])

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      fetchStability(undefined, true)
    }, 15 * 60 * 1000)
    return () => window.clearInterval(intervalId)
  }, [fetchStability])

  const chartRows = useMemo(() => buildChartRows(payload?.rows ?? []), [payload])
  const summary = payload?.summary
  const deltaTone = Number(summary?.wow_delta_pp ?? 0) >= 0 ? 'good' : 'bad'

  return (
    <div className="space-y-6">
      <motion.section
        className="flex flex-col gap-4 rounded-xl border border-gray-800/70 bg-gray-900/40 p-5 shadow-lg light:border-gray-200 light:bg-white"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <Database className="h-5 w-5 shrink-0 text-cyan-300" />
              <h2 className="text-xl font-semibold text-white light:text-gray-900">Lane Stability</h2>
            </div>
            <p className="mt-1 text-sm text-gray-400 light:text-gray-600">Daily - live from Xcelerator CEO Dashboard</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex rounded-lg border border-gray-800 bg-gray-950/70 p-1 light:border-gray-200 light:bg-gray-100">
              {WINDOWS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setWindowDays(option.value)}
                  className={`min-w-12 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    windowDays === option.value
                      ? 'bg-cyan-500 text-gray-950'
                      : 'text-gray-400 hover:bg-gray-800 hover:text-white light:text-gray-600 light:hover:bg-white light:hover:text-gray-900'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => fetchStability(undefined, true)}
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-gray-800 bg-gray-950/70 text-gray-300 transition-colors hover:border-cyan-400 hover:text-cyan-300 light:border-gray-200 light:bg-white light:text-gray-700"
              aria-label="Refresh Lane Stability"
              title="Refresh"
            >
              {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-950/30 px-3 py-2 text-sm text-red-200 light:bg-red-50 light:text-red-700">
            <AlertTriangle className="h-4 w-4" />
            <span>{error}</span>
          </div>
        )}
      </motion.section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {loading && !payload ? (
          Array.from({ length: 5 }).map((_, index) => <SkeletonBlock key={index} className="h-[126px]" />)
        ) : (
          <>
            <StatTile label="Today Stable Cov %" value={formatPercent(summary?.today_stable_cov_pct)} helper={`${formatNumber(payload?.rows.length ?? 0)} daily rows`} />
            <StatTile label="WoW Delta pp" value={formatDelta(summary?.wow_delta_pp)} tone={deltaTone} />
            <StatTile label="Critical Lanes" value={formatNumber(summary?.critical_today)} helper="Stable Cov < 50%" />
            <StatTile label="Cross-Route Lanes" value={formatNumber(summary?.cross_route_today)} helper="2+ truck slots" />
            <StatTile label="Revenue WTD" value={formatMoney(summary?.revenue_wtd)} />
          </>
        )}
      </section>

      <ChartCard title="Weighted Stable Coverage %" loading={loading && !payload}>
        {chartRows.length === 0 ? (
          <EmptyState />
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartRows} margin={{ top: 12, right: 24, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
              <ReferenceArea yAxisId="left" y1={0} y2={70} fill="#7f1d1d" fillOpacity={0.16} />
              <ReferenceArea yAxisId="left" y1={70} y2={80} fill="#854d0e" fillOpacity={0.18} />
              <ReferenceArea yAxisId="left" y1={80} y2={100} fill="#14532d" fillOpacity={0.18} />
              <XAxis dataKey="label" stroke="#9ca3af" tickLine={false} axisLine={false} minTickGap={28} />
              <YAxis yAxisId="left" domain={[0, 100]} stroke="#9ca3af" tickLine={false} axisLine={false} tickFormatter={(value) => `${value}%`} />
              <Tooltip content={<ChartTooltip />} />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="stableCovPct" name="Stable Cov %" stroke="#22d3ee" strokeWidth={3} dot={false} />
              <Line yAxisId="left" type="monotone" dataKey="stableCovMa4" name="4W MA" stroke="#f59e0b" strokeWidth={2} strokeDasharray="6 5" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </ChartCard>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <ColumnChart
          title="Critical Lanes (Stable Cov < 50%)"
          rows={chartRows}
          dataKey="critical_lanes"
          color="#ef4444"
          icon={<AlertTriangle className="h-5 w-5 text-red-300" />}
          loading={loading && !payload}
        />
        <ColumnChart
          title="Cross-Route Lanes (2+ truck slots)"
          rows={chartRows}
          dataKey="cross_route_lanes"
          color="#f59e0b"
          icon={<GitBranch className="h-5 w-5 text-amber-300" />}
          loading={loading && !payload}
        />
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <ChartCard title="Revenue per Day" loading={loading && !payload}>
          {chartRows.length === 0 ? (
            <EmptyState />
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={chartRows} margin={{ top: 10, right: 20, left: 0, bottom: 8 }}>
                <defs>
                  <linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#14b8a6" stopOpacity={0.45} />
                    <stop offset="95%" stopColor="#14b8a6" stopOpacity={0.04} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
                <XAxis dataKey="label" stroke="#9ca3af" tickLine={false} axisLine={false} minTickGap={28} />
                <YAxis stroke="#9ca3af" tickLine={false} axisLine={false} tickFormatter={(value) => `$${Math.round(Number(value) / 1000)}k`} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="total_revenue" name="Revenue" fill="url(#revenueFill)" stroke="#14b8a6" strokeWidth={2} />
                <Line type="monotone" dataKey="total_revenue" name="Revenue line" stroke="#67e8f9" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Orders vs Scored Lanes" loading={loading && !payload}>
          {chartRows.length === 0 ? (
            <EmptyState />
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={chartRows} margin={{ top: 10, right: 20, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
                <XAxis dataKey="label" stroke="#9ca3af" tickLine={false} axisLine={false} minTickGap={28} />
                <YAxis yAxisId="orders" stroke="#93c5fd" tickLine={false} axisLine={false} />
                <YAxis yAxisId="lanes" orientation="right" stroke="#5eead4" tickLine={false} axisLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Legend />
                <Bar yAxisId="orders" dataKey="total_orders" name="Orders" fill="#1d4ed8" radius={[4, 4, 0, 0]} />
                <Bar yAxisId="lanes" dataKey="scored_lanes" name="Scored Lanes" fill="#14b8a6" radius={[4, 4, 0, 0]} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </section>
    </div>
  )
}

function ColumnChart({
  title,
  rows,
  dataKey,
  color,
  icon,
  loading,
}: {
  title: string
  rows: ChartRow[]
  dataKey: 'critical_lanes' | 'cross_route_lanes'
  color: string
  icon: React.ReactNode
  loading?: boolean
}) {
  return (
    <ChartCard title={title} loading={loading}>
      <div className="mb-2 flex items-center gap-2 text-xs text-gray-500 light:text-gray-500">
        {icon}
        <Route className="h-4 w-4" />
        <TrendingUp className="h-4 w-4" />
      </div>
      {rows.length === 0 ? (
        <EmptyState />
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
            <XAxis dataKey="label" stroke="#9ca3af" tickLine={false} axisLine={false} minTickGap={28} />
            <YAxis stroke="#9ca3af" tickLine={false} axisLine={false} />
            <Tooltip content={<ChartTooltip />} />
            <Bar dataKey={dataKey} name={title} fill={color} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  )
}

function EmptyState() {
  return (
    <div className="flex h-[260px] items-center justify-center rounded-lg border border-dashed border-gray-700 bg-gray-950/30 text-sm text-gray-500 light:border-gray-300 light:bg-gray-50">
      No Xcelerator CEO Dashboard rows returned for this window.
    </div>
  )
}
