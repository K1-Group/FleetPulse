import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { AlertTriangle, DollarSign, Loader2, RefreshCw, ShieldCheck, Target, TrendingUp } from 'lucide-react'
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

type PerformanceWindow = 42 | 91 | 182 | 364

interface EntityMarginWeeklyRow {
  week_start: string
  week_end: string
  fuel_cost: number
  maintenance_cost?: number
  insurance_cost: number
  employee_cost?: number
  rental_trucks_trailers_cost?: number
  other_expense_cost: number
  k1l_orders: number
  k1l_grand_total: number
  k1l_driver_pay: number
  k1g_orders: number
  k1g_grand_total: number
  k1g_driver_pay: number
  k1g_target_gross_margin: number
  k1g_actual_gross_margin_before_overhead: number
  k1g_actual_gross_margin_pct_before_overhead: number | null
}

interface EntityMarginSummary {
  fuel_cost: number
  maintenance_cost?: number
  insurance_cost: number
  employee_cost?: number
  rental_trucks_trailers_cost?: number
  other_expense_cost: number
  k1l_orders: number
  k1l_grand_total: number
  k1l_driver_pay: number
  k1g_orders: number
  k1g_grand_total: number
  k1g_driver_pay: number
  k1g_target_gross_margin: number
  k1g_actual_gross_margin_before_overhead: number
  k1g_actual_gross_margin_pct_before_overhead: number | null
}

interface EntityMarginResponse {
  period_start: string
  period_end: string
  generated_at: string
  projection_mode: 'read_only'
  source_authority: string
  k1g_margin_target_pct: number
  sources: Record<string, { status?: string; source_authority?: string; message?: string; row_count?: number }>
  summary: EntityMarginSummary
  weekly: EntityMarginWeeklyRow[]
}

interface FinancialBucket {
  bucket: string
  amount: number | null
  count: number
}

interface FinancialSummary {
  pending_amount: number | null
  pending_bills: number
  overdue_amount: number | null
  overdue_count: number
  total: number | null
}

interface ControlTowerFinancialResponse {
  generated_at: string
  accounts_payable: FinancialSummary
  accounts_receivable: FinancialBucket[]
  cash_flow: Record<string, number | null>
  feeds: Array<{ name: string; status: string; message: string; source_authority: string }>
}

interface ChartRow extends EntityMarginWeeklyRow {
  label: string
  marginPct: number | null
  targetPct: number
  targetGap: number
  orgRevenue: number
  orgDriverPay: number
  orgQboCost: number
  orgTotalCost: number
  orgProfit: number
  orgMarginPct: number | null
}

const WINDOWS: { label: string; value: PerformanceWindow }[] = [
  { label: '6W', value: 42 },
  { label: '13W', value: 91 },
  { label: '26W', value: 182 },
  { label: '52W', value: 364 },
]

const CARD_CLASS = 'rounded-lg border border-gray-800/70 bg-gray-900/55 p-5 shadow-lg shadow-black/10 light:border-gray-200 light:bg-white'

function numberValue(value: number | null | undefined): number {
  return Number.isFinite(Number(value)) ? Number(value) : 0
}

function asPercent(value: number | null | undefined): number | null {
  if (value === null || value === undefined) return null
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return null
  return Math.abs(numeric) <= 1 ? numeric * 100 : numeric
}

function formatPercent(value: number | null | undefined): string {
  const pct = asPercent(value)
  return pct === null ? 'Pending' : `${pct.toFixed(1)}%`
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'Pending'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value)
}

function formatNumber(value: number | null | undefined): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(numberValue(value))
}

function formatScore(value: number | null): string {
  return value === null ? 'Pending' : `${Math.round(value)} / 100`
}

function formatDateLabel(value: string): string {
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(date)
}

function clamp(value: number, min = 0, max = 100): number {
  return Math.min(max, Math.max(min, value))
}

function buildChartRows(rows: EntityMarginWeeklyRow[], targetPct: number): ChartRow[] {
  return rows.map((row) => {
    const orgRevenue = numberValue(row.k1l_grand_total) + numberValue(row.k1g_grand_total)
    const orgDriverPay = numberValue(row.k1l_driver_pay) + numberValue(row.k1g_driver_pay)
    const orgQboCost =
      numberValue(row.fuel_cost)
      + numberValue(row.maintenance_cost)
      + numberValue(row.insurance_cost)
      + numberValue(row.employee_cost)
      + numberValue(row.rental_trucks_trailers_cost)
    const orgTotalCost = orgDriverPay + orgQboCost
    const orgProfit = orgRevenue - orgTotalCost
    const orgMarginPct = orgRevenue > 0 ? (orgProfit / orgRevenue) * 100 : null
    const targetGap = orgProfit - orgRevenue * (targetPct / 100)
    return {
      ...row,
      label: formatDateLabel(row.week_start),
      marginPct: orgMarginPct,
      targetPct,
      targetGap,
      orgRevenue,
      orgDriverPay,
      orgQboCost,
      orgTotalCost,
      orgProfit,
      orgMarginPct,
    }
  })
}

function currentArRatio(financial: ControlTowerFinancialResponse | null): number | null {
  const buckets = financial?.accounts_receivable ?? []
  const total = buckets.reduce((sum, bucket) => sum + numberValue(bucket.amount), 0)
  if (total <= 0) return null
  const current = buckets
    .filter((bucket) => bucket.bucket === '0-30')
    .reduce((sum, bucket) => sum + numberValue(bucket.amount), 0)
  return current / total
}

function overdueApRatio(financial: ControlTowerFinancialResponse | null): number | null {
  const ap = financial?.accounts_payable
  const total = numberValue(ap?.pending_amount ?? ap?.total)
  if (total <= 0) return null
  return numberValue(ap?.overdue_amount) / total
}

function financialDisciplineScore(
  marginPct: number | null,
  targetPct: number,
  arRatio: number | null,
  apOverdueRatio: number | null,
  onTargetWeeksPct: number | null,
): number | null {
  const scores: number[] = []
  if (marginPct !== null && targetPct > 0) scores.push(clamp((marginPct / targetPct) * 100))
  if (arRatio !== null) scores.push(clamp(arRatio * 100))
  if (apOverdueRatio !== null) scores.push(clamp(100 - apOverdueRatio * 100))
  if (onTargetWeeksPct !== null) scores.push(clamp(onTargetWeeksPct * 100))
  if (!scores.length) return null
  return scores.reduce((sum, score) => sum + score, 0) / scores.length
}

function SkeletonBlock({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-gray-800/70 light:bg-gray-200 ${className}`} />
}

function MetricTile({
  label,
  value,
  helper,
  tone = 'neutral',
  icon,
}: {
  label: string
  value: string
  helper?: string
  tone?: 'neutral' | 'good' | 'bad'
  icon?: React.ReactNode
}) {
  const toneClass = tone === 'good' ? 'text-emerald-300' : tone === 'bad' ? 'text-red-300' : 'text-white light:text-gray-900'
  return (
    <div className={CARD_CLASS}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium uppercase text-gray-500 light:text-gray-500">{label}</p>
        {icon}
      </div>
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
              {typeof entry.value === 'number' && String(entry.name || '').includes('%')
                ? `${entry.value.toFixed(1)}%`
                : typeof entry.value === 'number'
                  ? formatNumber(entry.value)
                  : entry.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex h-[280px] items-center justify-center rounded-lg border border-dashed border-gray-700 bg-gray-950/30 text-sm text-gray-500 light:border-gray-300 light:bg-gray-50">
      No financial rows returned for this window.
    </div>
  )
}

export default function FinancialPerformanceDashboard() {
  const [windowDays, setWindowDays] = useState<PerformanceWindow>(91)
  const [entityMargin, setEntityMargin] = useState<EntityMarginResponse | null>(null)
  const [financial, setFinancial] = useState<ControlTowerFinancialResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchFinancialPerformance = useCallback(
    async (signal?: AbortSignal, silent = false) => {
      if (silent) {
        setRefreshing(true)
      } else {
        setLoading(true)
      }
      setError(null)

      try {
        const [marginResponse, financialResponse] = await Promise.all([
          fetch(`/api/fuel/entity-margin?days=${windowDays}`, { signal }),
          fetch('/api/control-tower/financial', { signal }),
        ])
        if (!marginResponse.ok) throw new Error(`Entity margin API returned ${marginResponse.status}`)
        if (!financialResponse.ok) throw new Error(`Financial API returned ${financialResponse.status}`)
        setEntityMargin((await marginResponse.json()) as EntityMarginResponse)
        setFinancial((await financialResponse.json()) as ControlTowerFinancialResponse)
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return
        setError(err instanceof Error ? err.message : 'K1 Group financial performance APIs unavailable')
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
    fetchFinancialPerformance(controller.signal)
    return () => controller.abort()
  }, [fetchFinancialPerformance])

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      fetchFinancialPerformance(undefined, true)
    }, 15 * 60 * 1000)
    return () => window.clearInterval(intervalId)
  }, [fetchFinancialPerformance])

  const targetPct = asPercent(entityMargin?.k1g_margin_target_pct) ?? 20
  const chartRows = useMemo(() => buildChartRows(entityMargin?.weekly ?? [], targetPct), [entityMargin, targetPct])
  const summary = entityMargin?.summary
  const orgRevenue = numberValue(summary?.k1l_grand_total) + numberValue(summary?.k1g_grand_total)
  const orgDriverPay = numberValue(summary?.k1l_driver_pay) + numberValue(summary?.k1g_driver_pay)
  const qboK1lCost =
    numberValue(summary?.fuel_cost)
    + numberValue(summary?.maintenance_cost)
    + numberValue(summary?.insurance_cost)
    + numberValue(summary?.employee_cost)
    + numberValue(summary?.rental_trucks_trailers_cost)
  const orgTotalCost = orgDriverPay + qboK1lCost
  const orgProfit = orgRevenue - orgTotalCost
  const summaryMarginPct = orgRevenue > 0 ? (orgProfit / orgRevenue) * 100 : null
  const targetGap = orgProfit - orgRevenue * (targetPct / 100)
  const onTargetWeeks = chartRows.filter((row) => row.marginPct !== null && row.marginPct >= targetPct).length
  const onTargetWeeksPct = chartRows.length ? onTargetWeeks / chartRows.length : null
  const arCurrentRatio = currentArRatio(financial)
  const apOverdueRatio = overdueApRatio(financial)
  const disciplineScore = financialDisciplineScore(
    summaryMarginPct,
    targetPct,
    arCurrentRatio,
    apOverdueRatio,
    onTargetWeeksPct,
  )
  const arTotal = (financial?.accounts_receivable ?? []).reduce((sum, bucket) => sum + numberValue(bucket.amount), 0)
  const ap = financial?.accounts_payable

  return (
    <div className="space-y-6">
      <motion.section
        className="flex flex-col gap-4 rounded-lg border border-gray-800/70 bg-gray-900/40 p-5 shadow-lg light:border-gray-200 light:bg-white"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <DollarSign className="h-5 w-5 shrink-0 text-emerald-300" />
              <h2 className="text-xl font-semibold text-white light:text-gray-900">K1 Group Consolidated P&L</h2>
            </div>
            <p className="mt-1 text-sm text-gray-400 light:text-gray-600">Sales and driver pay from Xcelerator · K1 Logistics costs from QuickBooks</p>
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
                      ? 'bg-emerald-500 text-gray-950'
                      : 'text-gray-400 hover:bg-gray-800 hover:text-white light:text-gray-600 light:hover:bg-white light:hover:text-gray-900'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => fetchFinancialPerformance(undefined, true)}
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-gray-800 bg-gray-950/70 text-gray-300 transition-colors hover:border-emerald-400 hover:text-emerald-300 light:border-gray-200 light:bg-white light:text-gray-700"
              aria-label="Refresh K1 Group Consolidated P&L"
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

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-6">
        {loading && !entityMargin ? (
          Array.from({ length: 6 }).map((_, index) => <SkeletonBlock key={index} className="h-[126px]" />)
        ) : (
          <>
            <MetricTile label="Leadership Index" value={formatScore(disciplineScore)} helper={`${onTargetWeeks}/${chartRows.length} weeks on target`} icon={<ShieldCheck className="h-4 w-4 text-emerald-300" />} />
            <MetricTile label="Org Margin %" value={formatPercent(summaryMarginPct)} helper={`${targetPct.toFixed(1)}% target`} tone={summaryMarginPct !== null && summaryMarginPct >= targetPct ? 'good' : 'bad'} icon={<Target className="h-4 w-4 text-cyan-300" />} />
            <MetricTile label="Org Gross Profit" value={formatMoney(orgProfit)} helper={`${formatMoney(orgRevenue)} sales`} icon={<TrendingUp className="h-4 w-4 text-emerald-300" />} />
            <MetricTile label="Target Gap" value={formatMoney(targetGap)} helper={targetGap >= 0 ? 'Above target' : 'Below target'} tone={targetGap >= 0 ? 'good' : 'bad'} />
            <MetricTile label="Xcelerator Pay" value={formatMoney(orgDriverPay)} helper={`${formatNumber((summary?.k1l_orders ?? 0) + (summary?.k1g_orders ?? 0))} orders`} />
            <MetricTile label="QBO K1L Cost" value={formatMoney(qboK1lCost)} helper="Maintenance, fuel, insurance, employee, rentals" />
          </>
        )}
      </section>

      <section className={`${CARD_CLASS} min-h-[390px]`}>
        <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <h3 className="text-base font-semibold text-white light:text-gray-900">Weekly Org Sales / Driver Pay / QBO Cost / Margin</h3>
          <span className="text-xs text-gray-500 light:text-gray-500">{entityMargin?.period_start ?? 'Pending'} to {entityMargin?.period_end ?? 'Pending'}</span>
        </div>
        {loading && !entityMargin ? (
          <SkeletonBlock className="h-[300px]" />
        ) : chartRows.length === 0 ? (
          <EmptyState />
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={chartRows} margin={{ top: 12, right: 24, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
              <XAxis dataKey="label" stroke="#9ca3af" tickLine={false} axisLine={false} minTickGap={28} />
              <YAxis yAxisId="money" stroke="#9ca3af" tickLine={false} axisLine={false} tickFormatter={(value) => `$${Math.round(Number(value) / 1000)}k`} />
              <YAxis yAxisId="pct" orientation="right" domain={[0, 100]} stroke="#9ca3af" tickLine={false} axisLine={false} tickFormatter={(value) => `${value}%`} />
              <Tooltip content={<ChartTooltip />} />
              <Legend />
              <Bar yAxisId="money" dataKey="orgRevenue" name="Xcelerator Sales" fill="#14b8a6" radius={[4, 4, 0, 0]} />
              <Bar yAxisId="money" dataKey="orgDriverPay" name="Xcelerator Driver Pay" fill="#f43f5e" radius={[4, 4, 0, 0]} />
              <Bar yAxisId="money" dataKey="orgQboCost" name="QBO K1L Cost" fill="#38bdf8" radius={[4, 4, 0, 0]} />
              <Line yAxisId="pct" type="monotone" dataKey="orgMarginPct" name="Org Margin %" stroke="#facc15" strokeWidth={3} dot={false} />
              <Line yAxisId="pct" type="monotone" dataKey="targetPct" name="Target %" stroke="#93c5fd" strokeWidth={2} strokeDasharray="6 5" dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className={`${CARD_CLASS} min-h-[340px]`}>
          <h3 className="mb-4 text-base font-semibold text-white light:text-gray-900">QBO Cost Buckets</h3>
          {chartRows.length === 0 ? (
            <EmptyState />
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={chartRows} margin={{ top: 10, right: 20, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
                <XAxis dataKey="label" stroke="#9ca3af" tickLine={false} axisLine={false} minTickGap={28} />
                <YAxis stroke="#9ca3af" tickLine={false} axisLine={false} tickFormatter={(value) => `$${Math.round(Number(value) / 1000)}k`} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="maintenance_cost" name="Maintenance" fill="#38bdf8" radius={[4, 4, 0, 0]} />
                <Bar dataKey="fuel_cost" name="Fuel" fill="#14b8a6" radius={[4, 4, 0, 0]} />
                <Bar dataKey="insurance_cost" name="Insurance" fill="#a78bfa" radius={[4, 4, 0, 0]} />
                <Bar dataKey="employee_cost" name="Employee" fill="#facc15" radius={[4, 4, 0, 0]} />
                <Bar dataKey="rental_trucks_trailers_cost" name="Truck/Trailer Rental" fill="#fb7185" radius={[4, 4, 0, 0]} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className={`${CARD_CLASS} min-h-[340px]`}>
          <h3 className="mb-4 text-base font-semibold text-white light:text-gray-900">QBO AP / AR Pressure</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-gray-800 bg-gray-950/45 p-4 light:border-gray-200 light:bg-gray-50">
              <p className="text-sm text-gray-400 light:text-gray-600">Open AP</p>
              <p className="mt-2 text-2xl font-semibold text-white light:text-gray-900">{formatMoney(ap?.pending_amount ?? ap?.total)}</p>
              <p className="mt-1 text-xs text-gray-500 light:text-gray-500">{ap?.pending_bills ?? 0} bills open</p>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-950/45 p-4 light:border-gray-200 light:bg-gray-50">
              <p className="text-sm text-gray-400 light:text-gray-600">Open AR</p>
              <p className="mt-2 text-2xl font-semibold text-white light:text-gray-900">{formatMoney(arTotal)}</p>
              <p className="mt-1 text-xs text-gray-500 light:text-gray-500">{financial?.accounts_receivable.reduce((sum, bucket) => sum + bucket.count, 0) ?? 0} rows open</p>
            </div>
          </div>
          <div className="mt-5 space-y-3">
            {(financial?.accounts_receivable ?? []).map((bucket) => {
              const amount = numberValue(bucket.amount)
              const width = arTotal > 0 ? Math.max((amount / arTotal) * 100, amount > 0 ? 3 : 0) : 0
              return (
                <div key={bucket.bucket}>
                  <div className="mb-1 flex items-center justify-between text-xs text-gray-400 light:text-gray-600">
                    <span>{bucket.bucket}</span>
                    <span>{formatMoney(bucket.amount)} · {bucket.count}</span>
                  </div>
                  <div className="h-2 rounded-full bg-gray-800 light:bg-gray-200">
                    <div className="h-2 rounded-full bg-emerald-400" style={{ width: `${width}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </section>
    </div>
  )
}
