import { motion } from 'framer-motion'
import { useMemo, useState } from 'react'
import type { ChangeEvent, ReactNode } from 'react'
import {
  AlertTriangle,
  BarChart3,
  CalendarDays,
  Clock,
  Database,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  Users,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useHrRecruitingWorklist } from '../hooks/useGeotab'
import type { DashboardDateRangeParams } from '../hooks/useGeotab'
import DepartmentCallAnalysisPanel from './DepartmentCallAnalysisPanel'
import type {
  HrRecruitingConversionFunnel,
  HrRecruitingDailyRow,
  HrRecruitingHardTarget,
  HrRecruitingStatusCount,
  HrRecruitingTeamMember,
  HrRecruitingTrendRow,
  HrRecruitingWorkbookEvidence,
  HrRecruitingWorkbookMemberKpi,
  HrRecruitingWorklistRow,
} from '../types/fleet'

type DatePreset =
  | 'today'
  | 'yesterday'
  | 'last7'
  | 'last30'
  | 'thisMonth'
  | 'lastMonth'
  | 'thisQuarter'
  | 'custom'

const DATE_PRESETS: Array<{ key: DatePreset; label: string }> = [
  { key: 'today', label: 'Today' },
  { key: 'yesterday', label: 'Yesterday' },
  { key: 'last7', label: 'Last 7 Days' },
  { key: 'last30', label: 'Last 30 Days' },
  { key: 'thisMonth', label: 'This Month' },
  { key: 'lastMonth', label: 'Last Month' },
  { key: 'thisQuarter', label: 'This Quarter' },
  { key: 'custom', label: 'Custom Range' },
]

const DEPARTMENT_FILTERS = ['HR', 'Recruiting', 'Safety', 'Operations', 'Fleet Compliance', 'Sales']

const numberFormatter = new Intl.NumberFormat('en-US')

function formatCount(value: number | null | undefined) {
  return numberFormatter.format(Number(value || 0))
}

function formatHours(value: number | null | undefined) {
  return `${Number(value || 0).toFixed(1)}h`
}

function formatPercentValue(value: number | null | undefined) {
  if (value === null || value === undefined) return '--'
  return `${(Number(value) * 100).toFixed(1)}%`
}

function formatPercentFromPct(value: number | null | undefined) {
  if (value === null || value === undefined) return '--'
  return `${Number(value).toFixed(1)}%`
}

function recruitingSourceLabel(
  data: { source_artifact?: string | null; source?: string; table_id?: string } | null | undefined,
  workbookSource: boolean,
) {
  if (workbookSource) return data?.source_artifact || 'HR KPI workbook pending'
  if (data?.source === 'microsoft_365_sharepoint') return 'Microsoft 365 SharePoint state'
  return `Read-only snapshot ${data?.table_id || '01KR00WV4YHCB6BMYDE1EG7HEM'}`
}

function dateInputValue(value: Date) {
  const year = value.getFullYear()
  const month = `${value.getMonth() + 1}`.padStart(2, '0')
  const day = `${value.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

function localDateFromInput(value: string) {
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function startOfMonth(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), 1)
}

function endOfMonth(value: Date) {
  return new Date(value.getFullYear(), value.getMonth() + 1, 0)
}

function startOfQuarter(value: Date) {
  return new Date(value.getFullYear(), Math.floor(value.getMonth() / 3) * 3, 1)
}

function presetRange(preset: DatePreset, customStart: string, customEnd: string): DashboardDateRangeParams {
  const today = new Date()
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const start = new Date(end)
  if (preset === 'today') {
    return { startDate: dateInputValue(end), endDate: dateInputValue(end) }
  }
  if (preset === 'yesterday') {
    start.setDate(end.getDate() - 1)
    return { startDate: dateInputValue(start), endDate: dateInputValue(start) }
  }
  if (preset === 'last7') {
    start.setDate(end.getDate() - 6)
    return { startDate: dateInputValue(start), endDate: dateInputValue(end) }
  }
  if (preset === 'last30') {
    start.setDate(end.getDate() - 29)
    return { startDate: dateInputValue(start), endDate: dateInputValue(end) }
  }
  if (preset === 'thisMonth') {
    return { startDate: dateInputValue(startOfMonth(end)), endDate: dateInputValue(end) }
  }
  if (preset === 'lastMonth') {
    const previous = new Date(end.getFullYear(), end.getMonth() - 1, 1)
    return { startDate: dateInputValue(startOfMonth(previous)), endDate: dateInputValue(endOfMonth(previous)) }
  }
  if (preset === 'thisQuarter') {
    return { startDate: dateInputValue(startOfQuarter(end)), endDate: dateInputValue(end) }
  }
  return { startDate: customStart, endDate: customEnd }
}

function formatRangeDate(value: string | undefined) {
  if (!value) return '--'
  const parsed = localDateFromInput(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { month: '2-digit', day: '2-digit', year: 'numeric' })
}

function formatRangeLabel(start: string | undefined, end: string | undefined) {
  if (!start || !end) return ''
  const startLabel = formatRangeDate(start)
  const endLabel = formatRangeDate(end)
  return startLabel === endLabel ? startLabel : `${startLabel} - ${endLabel}`
}

function formatChange(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--'
  const numeric = Number(value)
  return `${numeric > 0 ? '+' : ''}${numeric.toFixed(1)}%`
}

function formatPointChange(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--'
  const numeric = Number(value)
  return `${numeric > 0 ? '+' : ''}${numeric.toFixed(1)} pts`
}

function targetValue(target: HrRecruitingHardTarget) {
  if (target.unit === 'pct') return formatPercentValue(target.actual)
  if (target.actual === null || target.actual === undefined) return '--'
  return formatCount(target.actual)
}

function sourceBackedTargets(targets: Record<string, HrRecruitingHardTarget> | undefined) {
  return Object.values(targets || {}).filter(
    target => target.status !== 'awaiting_feed' && target.actual !== null && target.actual !== undefined,
  )
}

function targetPresentation(target: HrRecruitingHardTarget) {
  if (target.key === 'new_hires_7d') {
    return { icon: <Users className="h-5 w-5 text-cyan-200" />, tone: 'bg-cyan-500/15' }
  }
  if (target.key === 'active_qualified_pipeline') {
    return { icon: <TrendingUp className="h-5 w-5 text-emerald-200" />, tone: 'bg-emerald-500/15' }
  }
  if (target.key === 'first_touch_24h_pct') {
    return { icon: <Clock className="h-5 w-5 text-blue-200" />, tone: 'bg-blue-500/15' }
  }
  if (target.key === 'stale_untouched_48h') {
    return { icon: <AlertTriangle className="h-5 w-5 text-amber-200" />, tone: 'bg-amber-500/15' }
  }
  if (target.key === 'orientation_show_rate') {
    return { icon: <ShieldCheck className="h-5 w-5 text-violet-200" />, tone: 'bg-violet-500/15' }
  }
  return { icon: <BarChart3 className="h-5 w-5 text-sky-200" />, tone: 'bg-sky-500/15' }
}

function statusLabel(status: HrRecruitingHardTarget['status']) {
  if (status === 'healthy') return 'On target'
  if (status === 'warning') return 'Off target'
  return 'Awaiting feed'
}

function statusClasses(status: HrRecruitingHardTarget['status']) {
  if (status === 'healthy') return 'border-emerald-500/40 text-emerald-200 light:text-emerald-700'
  if (status === 'warning') return 'border-amber-500/40 text-amber-200 light:text-amber-700'
  return 'border-gray-700 text-gray-400 light:border-gray-300 light:text-gray-600'
}

function compactDate(value: string) {
  const parsed = new Date(`${value}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function compactOptionalDate(value: string | null | undefined) {
  if (!value) return '--'
  const parsed = new Date(value.includes('T') ? value : `${value}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function workbookMetric(evidence: HrRecruitingWorkbookEvidence | undefined, key: string) {
  const value = evidence?.kpi_summary?.[key]
  return typeof value === 'number' ? value : null
}

function exceptionSeverityClasses(severity: string) {
  if (severity === 'critical') return 'border-red-500/30 bg-red-500/10 text-red-200 light:text-red-700'
  if (severity === 'warning') return 'border-amber-500/30 bg-amber-500/10 text-amber-200 light:text-amber-700'
  return 'border-gray-700 bg-gray-900/40 text-gray-300 light:border-gray-200 light:bg-gray-50 light:text-gray-700'
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-gray-700 bg-gray-950/95 px-3 py-2 shadow-xl">
      <p className="text-xs font-medium text-gray-200">{label}</p>
      <div className="mt-1 space-y-1">
        {payload.map((item: any) => (
          <p key={item.dataKey} className="text-xs" style={{ color: item.color }}>
            {item.name || item.dataKey}: {item.dataKey?.includes('hours') ? formatHours(item.value) : formatCount(item.value)}
          </p>
        ))}
      </div>
    </div>
  )
}

function KpiCard({
  icon,
  label,
  value,
  detail,
  tone,
  status,
}: {
  icon: ReactNode
  label: string
  value: string
  detail: string
  tone: string
  status?: HrRecruitingHardTarget['status']
}) {
  return (
    <motion.div
      className={`rounded-xl border bg-gray-900/65 p-4 shadow-lg light:bg-white ${status ? statusClasses(status) : 'border-gray-800/70 light:border-gray-200'}`}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <div className="flex items-center justify-between gap-3">
        <div className={`rounded-lg p-2 ${tone}`}>{icon}</div>
        <p className="text-2xl font-bold text-white light:text-gray-900">{value}</p>
      </div>
      <div className="mt-3 flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-gray-200 light:text-gray-800">{label}</p>
        {status && (
          <span className={`shrink-0 rounded-md border px-2 py-1 text-[11px] font-medium ${statusClasses(status)}`}>
            {statusLabel(status)}
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{detail}</p>
    </motion.div>
  )
}

function DateRangeFilter({
  preset,
  onPresetChange,
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
  department,
  onDepartmentChange,
}: {
  preset: DatePreset
  onPresetChange: (value: DatePreset) => void
  startDate: string
  endDate: string
  onStartDateChange: (value: string) => void
  onEndDateChange: (value: string) => void
  department: string
  onDepartmentChange: (value: string) => void
}) {
  const handleStartDateInput = (event: ChangeEvent<HTMLInputElement>) => {
    onStartDateChange(event.currentTarget.value)
  }
  const handleEndDateInput = (event: ChangeEvent<HTMLInputElement>) => {
    onEndDateChange(event.currentTarget.value)
  }

  return (
    <section className="rounded-xl border border-gray-800/70 bg-gray-900/55 p-4 light:border-gray-200 light:bg-white">
      <div className="flex flex-col gap-4 2xl:flex-row 2xl:items-center 2xl:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <div className="rounded-lg bg-sky-500/15 p-2">
            <CalendarDays className="h-5 w-5 text-sky-300" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white light:text-gray-900">Showing data from {formatRangeDate(startDate)} to {formatRangeDate(endDate)}</p>
            <p className="mt-1 text-xs text-gray-500 light:text-gray-600">Date filters apply server-side to the HR KPI workbook intake window and call-analysis panel before this read-only surface renders.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(180px,220px)_repeat(2,minmax(145px,170px))_minmax(170px,220px)]">
          <label className="text-xs font-medium text-gray-400 light:text-gray-600">
            Preset
            <select
              value={preset}
              onChange={event => onPresetChange(event.target.value as DatePreset)}
              className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white light:border-gray-300 light:bg-white light:text-gray-900"
            >
              {DATE_PRESETS.map(item => (
                <option key={item.key} value={item.key}>{item.label}</option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-gray-400 light:text-gray-600">
            Start Date
            <input
              type="date"
              value={startDate}
              onChange={handleStartDateInput}
              onInput={handleStartDateInput}
              className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white light:border-gray-300 light:bg-white light:text-gray-900"
            />
          </label>
          <label className="text-xs font-medium text-gray-400 light:text-gray-600">
            End Date
            <input
              type="date"
              value={endDate}
              onChange={handleEndDateInput}
              onInput={handleEndDateInput}
              className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white light:border-gray-300 light:bg-white light:text-gray-900"
            />
          </label>
          <label className="text-xs font-medium text-gray-400 light:text-gray-600">
            Department
            <select
              value={department}
              onChange={event => onDepartmentChange(event.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white light:border-gray-300 light:bg-white light:text-gray-900"
            >
              {DEPARTMENT_FILTERS.map(item => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </label>
        </div>
      </div>
    </section>
  )
}

function TrendComparisonStrip({ data }: { data: ReturnType<typeof useHrRecruitingWorklist>['data'] }) {
  const comparison = data?.trend_comparison
  if (!comparison) return null

  const currentWindow = formatRangeLabel(data?.date_range?.start, data?.date_range?.end)
  const previousWindow = formatRangeLabel(data?.date_range?.previous_start, data?.date_range?.previous_end)
  const cards = [
    {
      label: 'Lead Volume',
      value: comparison.lead_volume_change_pct,
      current: comparison.current.new_leads,
      previous: comparison.previous.new_leads,
    },
    {
      label: 'Hire Volume',
      value: comparison.hire_volume_change_pct,
      current: comparison.current.new_hires,
      previous: comparison.previous.new_hires,
    },
    {
      label: 'Follow-Ups',
      value: comparison.follow_up_change_pct,
      current: comparison.current.follow_ups,
      previous: comparison.previous.follow_ups,
    },
  ]
  return (
    <section className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {cards.map(card => {
        const positive = card.value === null || card.value === undefined || card.value >= 0
        return (
          <div key={card.label} className={`rounded-xl border bg-gray-900/45 p-4 light:bg-white ${positive ? 'border-emerald-500/25' : 'border-amber-500/30'}`}>
            <p className="text-xs font-medium uppercase text-gray-500 light:text-gray-600">{card.label}</p>
            <p className={`mt-2 text-2xl font-semibold ${positive ? 'text-emerald-200 light:text-emerald-700' : 'text-amber-200 light:text-amber-700'}`}>{formatChange(card.value)}</p>
            <p className="mt-1 text-xs text-gray-500 light:text-gray-600">
              Current{currentWindow ? ` (${currentWindow})` : ''} {formatCount(card.current)} | Prior{previousWindow ? ` (${previousWindow})` : ''} {formatCount(card.previous)}
            </p>
          </div>
        )
      })}
    </section>
  )
}

function PeriodMetricCards({ data }: { data: ReturnType<typeof useHrRecruitingWorklist>['data'] }) {
  const metrics = data?.period_metrics
  if (!metrics) return null
  const cards = [
    { label: 'New Leads', value: metrics.new_leads },
    { label: 'New Applicants', value: metrics.new_applicants },
    { label: 'Interviews Scheduled', value: metrics.interviews_scheduled },
    { label: 'New Hires', value: metrics.new_hires },
    { label: 'Recruiting Follow-Ups', value: metrics.follow_ups },
  ]
  return (
    <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {cards.map(card => (
        <div key={card.label} className="rounded-xl border border-gray-800/70 bg-gray-900/45 p-4 light:border-gray-200 light:bg-white">
          <p className="text-xs font-medium text-gray-500 light:text-gray-600">{card.label}</p>
          <p className="mt-2 text-2xl font-semibold text-white light:text-gray-900">{formatCount(card.value)}</p>
        </div>
      ))}
    </section>
  )
}

function EmptyPanel({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-dashed border-gray-700 bg-gray-900/35 p-8 text-center light:border-gray-300 light:bg-gray-50">
      <Database className="mx-auto h-8 w-8 text-gray-500" />
      <p className="mt-3 text-sm font-medium text-gray-300 light:text-gray-700">No HR recruiting rows available</p>
      <p className="mx-auto mt-1 max-w-2xl text-sm text-gray-500 light:text-gray-600">{message}</p>
    </div>
  )
}

function Skeleton() {
  return (
    <div className="space-y-6">
      <div className="h-20 animate-pulse rounded-xl bg-gray-800/60" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {[0, 1, 2, 3, 4].map(index => (
          <div key={index} className="h-32 animate-pulse rounded-xl bg-gray-800/60" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="h-80 animate-pulse rounded-xl bg-gray-800/60" />
        <div className="h-80 animate-pulse rounded-xl bg-gray-800/60" />
      </div>
    </div>
  )
}

function WorklistTable({ rows, workbookSource }: { rows: HrRecruitingWorklistRow[]; workbookSource: boolean }) {
  if (!rows.length) {
    return <EmptyPanel message={workbookSource ? 'The configured HR KPI workbook has no lead-level KPI rows after validation.' : 'The configured Microsoft 365/SharePoint snapshot has no active worklist leads after validation and dedupe.'} />
  }
  const firstColumn = workbookSource ? 'KPI Bucket' : 'Worklist'
  const countColumn = workbookSource ? 'Leads' : 'Active'
  const newColumn = workbookSource ? 'New Today' : 'New Today'
  const avgColumn = workbookSource ? 'Avg First Outreach' : 'Avg Age'
  const maxColumn = workbookSource ? 'Max First Outreach' : 'Max Age'
  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800/70 light:border-gray-200">
      <table className="min-w-full divide-y divide-gray-800 text-sm light:divide-gray-200">
        <thead className="bg-gray-900/80 light:bg-gray-100">
          <tr className="text-left text-xs uppercase tracking-wide text-gray-500 light:text-gray-600">
            <th className="px-4 py-3 font-medium">{firstColumn}</th>
            <th className="px-4 py-3 font-medium">{countColumn}</th>
            <th className="px-4 py-3 font-medium">{newColumn}</th>
            <th className="px-4 py-3 font-medium">{avgColumn}</th>
            <th className="px-4 py-3 font-medium">{maxColumn}</th>
            <th className="px-4 py-3 font-medium">24h</th>
            <th className="px-4 py-3 font-medium">48h</th>
            <th className="px-4 py-3 font-medium">72h</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/70 light:divide-gray-200">
          {rows.map(row => (
            <tr key={row.worklist} className="bg-gray-900/35 light:bg-white">
              <td className="max-w-[260px] px-4 py-3 font-medium text-gray-100 light:text-gray-900">{row.worklist}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.active_leads)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.new_leads_today)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatHours(row.avg_age_hours)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatHours(row.max_age_hours)}</td>
              <td className="px-4 py-3 text-amber-300 light:text-amber-700">{formatCount(row.stale_24h)}</td>
              <td className="px-4 py-3 text-orange-300 light:text-orange-700">{formatCount(row.stale_48h)}</td>
              <td className="px-4 py-3 text-red-300 light:text-red-700">{formatCount(row.stale_72h)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StaleWorklistTable({ rows, workbookSource }: { rows: HrRecruitingWorklistRow[]; workbookSource: boolean }) {
  const staleRows = rows
    .filter(row => row.stale_24h || row.stale_48h || row.stale_72h)
    .sort((a, b) => b.stale_72h - a.stale_72h || b.stale_48h - a.stale_48h || b.stale_24h - a.stale_24h)

  if (!staleRows.length) {
    return <EmptyPanel message={workbookSource ? 'No HR KPI workbook leads are in late or missing outreach buckets.' : 'No active worklist leads are over the configured stale thresholds.'} />
  }

  return (
    <div className="space-y-3">
      {staleRows.map(row => (
        <div key={row.worklist} className="rounded-xl border border-gray-800/70 bg-gray-900/50 p-4 light:border-gray-200 light:bg-white">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-medium text-white light:text-gray-900">{row.worklist}</p>
              <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{formatCount(row.active_leads)} {workbookSource ? 'leads' : 'active leads'} · max {workbookSource ? 'first outreach' : 'age'} {formatHours(row.max_age_hours)}</p>
            </div>
            <span className="rounded-md bg-amber-500/15 px-2 py-1 text-xs font-medium text-amber-200 light:text-amber-700">
              {formatCount(row.stale_24h)} over 24h
            </span>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
            <div className="rounded-lg bg-amber-500/10 p-3">
              <p className="text-xs text-amber-100/70 light:text-amber-700">24h</p>
              <p className="mt-1 text-lg font-semibold text-amber-200 light:text-amber-800">{formatCount(row.stale_24h)}</p>
            </div>
            <div className="rounded-lg bg-orange-500/10 p-3">
              <p className="text-xs text-orange-100/70 light:text-orange-700">48h</p>
              <p className="mt-1 text-lg font-semibold text-orange-200 light:text-orange-800">{formatCount(row.stale_48h)}</p>
            </div>
            <div className="rounded-lg bg-red-500/10 p-3">
              <p className="text-xs text-red-100/70 light:text-red-700">72h</p>
              <p className="mt-1 text-lg font-semibold text-red-200 light:text-red-800">{formatCount(row.stale_72h)}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function DailyTrendChart({ rows }: { rows: HrRecruitingTrendRow[] }) {
  if (!rows.length) {
    return <EmptyPanel message="Trend rows will appear after valid assignment events are present in the HR snapshot." />
  }

  const chartRows = rows.slice(-21).map(row => ({ ...row, date_label: compactDate(row.date) }))
  return (
    <div className="h-80">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartRows} margin={{ top: 10, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid stroke="#374151" strokeDasharray="3 3" />
          <XAxis dataKey="date_label" tick={{ fill: '#9ca3af', fontSize: 12 }} tickLine={false} axisLine={false} />
          <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} tickLine={false} axisLine={false} allowDecimals={false} />
          <Tooltip content={<ChartTooltip />} />
          <Line type="monotone" dataKey="active_leads" name="Active" stroke="#38bdf8" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="new_leads" name="New" stroke="#34d399" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="stale_leads" name="Stale" stroke="#f59e0b" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function StatusCountChart({ rows }: { rows: HrRecruitingStatusCount[] }) {
  if (!rows.length) {
    return <EmptyPanel message="Status counts are empty because no valid deduped leads were available." />
  }

  return (
    <div className="h-80">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows.slice(0, 10)} margin={{ top: 10, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid stroke="#374151" strokeDasharray="3 3" />
          <XAxis dataKey="status" tick={{ fill: '#9ca3af', fontSize: 12 }} tickLine={false} axisLine={false} />
          <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} tickLine={false} axisLine={false} allowDecimals={false} />
          <Tooltip content={<ChartTooltip />} />
          <Bar dataKey="count" name="Leads" fill="#a78bfa" radius={[5, 5, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function DailyVolumeTable({ rows, workbookSource }: { rows: HrRecruitingDailyRow[]; workbookSource: boolean }) {
  const recent = rows.slice(-8).reverse()
  if (!recent.length) return null

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800/70 light:border-gray-200">
      <table className="min-w-full divide-y divide-gray-800 text-sm light:divide-gray-200">
        <thead className="bg-gray-900/80 light:bg-gray-100">
          <tr className="text-left text-xs uppercase tracking-wide text-gray-500 light:text-gray-600">
            <th className="px-4 py-3 font-medium">Date</th>
            <th className="px-4 py-3 font-medium">{workbookSource ? 'KPI Bucket' : 'Worklist'}</th>
            <th className="px-4 py-3 font-medium">New</th>
            <th className="px-4 py-3 font-medium">{workbookSource ? 'Real Discuss.' : 'Completed'}</th>
            <th className="px-4 py-3 font-medium">{workbookSource ? 'Leads' : 'Active'}</th>
            <th className="px-4 py-3 font-medium">{workbookSource ? 'Avg Outreach' : 'Avg Process'}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/70 light:divide-gray-200">
          {recent.map(row => (
            <tr key={`${row.date}-${row.worklist}`} className="bg-gray-900/35 light:bg-white">
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{compactDate(row.date)}</td>
              <td className="max-w-[260px] px-4 py-3 font-medium text-gray-100 light:text-gray-900">{row.worklist}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.new_leads)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.completed_leads)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.active_leads)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatHours(row.avg_process_time_hours)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function MemberKpiTable({ rows, label }: { rows: HrRecruitingWorkbookMemberKpi[]; label: string }) {
  if (!rows.length) return null

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800/70 light:border-gray-200">
      <table className="min-w-full divide-y divide-gray-800 text-sm light:divide-gray-200">
        <thead className="bg-gray-900/80 light:bg-gray-100">
          <tr className="text-left text-xs uppercase tracking-wide text-gray-500 light:text-gray-600">
            <th className="px-4 py-3 font-medium">HR Member</th>
            <th className="px-4 py-3 font-medium">{label}</th>
            <th className="px-4 py-3 font-medium">Within 24h</th>
            <th className="px-4 py-3 font-medium">24-48h</th>
            <th className="px-4 py-3 font-medium">48-72h</th>
            <th className="px-4 py-3 font-medium">Over 72h</th>
            <th className="px-4 py-3 font-medium">Rate</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/70 light:divide-gray-200">
          {rows.map(row => (
            <tr key={`${label}-${row.hr_member}`} className="bg-gray-900/35 light:bg-white">
              <td className="px-4 py-3 font-medium text-gray-100 light:text-gray-900">{row.hr_member}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.lead_count)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.within_24h)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.recovered_24_48h)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.late_48_72h)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.failed_over_72h)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatPercentValue(row.within_24h_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function teamMemberStatusLabel(status: string) {
  if (status === 'source_backed') return 'Source-backed'
  return 'Roster'
}

function TeamMembersPanel({ members }: { members: HrRecruitingTeamMember[] }) {
  if (!members.length) return null

  return (
    <section className="rounded-xl border border-gray-800/70 bg-gray-900/45 p-5 light:border-gray-200 light:bg-white">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Users className="h-5 w-5 text-cyan-300" />
          <h3 className="font-semibold text-white light:text-gray-900">HR Team Members</h3>
        </div>
        <span className="text-xs text-gray-500 light:text-gray-600">Roster plus source-backed workbook activity</span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-gray-800/70 light:border-gray-200">
        <table className="min-w-full divide-y divide-gray-800 text-sm light:divide-gray-200">
          <thead className="bg-gray-900/80 light:bg-gray-100">
            <tr className="text-left text-xs uppercase tracking-wide text-gray-500 light:text-gray-600">
              <th className="px-4 py-3 font-medium">Team Member</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">First Outreach</th>
              <th className="px-4 py-3 font-medium">Real Discussion</th>
              <th className="px-4 py-3 font-medium">Within 24h</th>
              <th className="px-4 py-3 font-medium">Late/Failed</th>
              <th className="px-4 py-3 font-medium">Attempts</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/70 light:divide-gray-200">
            {members.map(member => (
              <tr key={member.name} className="bg-gray-900/35 light:bg-white">
                <td className="px-4 py-3 font-medium text-gray-100 light:text-gray-900">{member.name}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-md border px-2 py-1 text-xs font-medium ${member.status === 'source_backed' ? 'border-emerald-500/35 text-emerald-200 light:text-emerald-700' : 'border-gray-700 text-gray-400 light:border-gray-300 light:text-gray-600'}`}>
                    {teamMemberStatusLabel(member.status)}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(member.first_outreach_leads)}</td>
                <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(member.real_discussion_leads)}</td>
                <td className="px-4 py-3 text-gray-300 light:text-gray-700">
                  {formatCount(member.within_24h)} {member.within_24h_rate === null ? '' : `(${formatPercentValue(member.within_24h_rate)})`}
                </td>
                <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(member.late_48_72h + member.failed_over_72h)}</td>
                <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(member.total_outbound_attempts)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function WorkbookEvidencePanel({ evidence }: { evidence: HrRecruitingWorkbookEvidence | undefined }) {
  if (!evidence) return null
  const cards = [
    { label: 'Lead Forms', value: workbookMetric(evidence, 'unique_lead_forms') },
    { label: 'Call Attempts', value: workbookMetric(evidence, 'total_outbound_attempts') },
    { label: 'No Outbound', value: workbookMetric(evidence, 'no_outbound_found') },
    { label: 'No Real Discussion', value: workbookMetric(evidence, 'no_real_discussion_found') },
  ]

  return (
    <section className="rounded-xl border border-gray-800/70 bg-gray-900/45 p-5 light:border-gray-200 light:bg-white">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Database className="h-5 w-5 text-blue-300" />
          <h3 className="font-semibold text-white light:text-gray-900">Workbook Evidence</h3>
        </div>
        <span className="text-xs text-gray-500 light:text-gray-600">{evidence.workbook_name || 'pending workbook'}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {cards.map(card => (
          <div key={card.label} className="rounded-lg border border-gray-800/70 bg-gray-950/40 p-3 light:border-gray-200 light:bg-gray-50">
            <p className="text-xs text-gray-500 light:text-gray-600">{card.label}</p>
            <p className="mt-1 text-xl font-semibold text-white light:text-gray-900">{formatCount(card.value)}</p>
          </div>
        ))}
      </div>
      {!!evidence.missing_tabs.length && (
        <p className="mt-3 text-sm text-amber-200 light:text-amber-700">
          Missing workbook tabs: {evidence.missing_tabs.join(', ')}
        </p>
      )}
      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-2">
        <MemberKpiTable rows={evidence.first_outreach_by_member} label="First Outreach" />
        <MemberKpiTable rows={evidence.real_discussion_by_member} label="Real Discussion" />
      </div>
      {!!evidence.source_log_qa.length && (
        <div className="mt-5 overflow-x-auto rounded-xl border border-gray-800/70 light:border-gray-200">
          <table className="min-w-full divide-y divide-gray-800 text-sm light:divide-gray-200">
            <thead className="bg-gray-900/80 light:bg-gray-100">
              <tr className="text-left text-xs uppercase tracking-wide text-gray-500 light:text-gray-600">
                <th className="px-4 py-3 font-medium">Source File</th>
                <th className="px-4 py-3 font-medium">Rows</th>
                <th className="px-4 py-3 font-medium">Mapping</th>
                <th className="px-4 py-3 font-medium">QA Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/70 light:divide-gray-200">
              {evidence.source_log_qa.map(row => (
                <tr key={row.file} className="bg-gray-900/35 light:bg-white">
                  <td className="px-4 py-3 font-medium text-gray-100 light:text-gray-900">{row.file}</td>
                  <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.row_count)}</td>
                  <td className="px-4 py-3 text-gray-300 light:text-gray-700">{row.used_for_mapping ? 'Used' : 'Reference only'}</td>
                  <td className="max-w-[520px] px-4 py-3 text-gray-300 light:text-gray-700">{row.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function ConversionGroupTable({
  rows,
  labelKey,
  label,
}: {
  rows: NonNullable<HrRecruitingConversionFunnel['by_source']>
  labelKey: 'source_bucket' | 'sla_result'
  label: string
}) {
  if (!rows.length) return null

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800/70 light:border-gray-200">
      <table className="min-w-full divide-y divide-gray-800 text-sm light:divide-gray-200">
        <thead className="bg-gray-900/80 light:bg-gray-100">
          <tr className="text-left text-xs uppercase tracking-wide text-gray-500 light:text-gray-600">
            <th className="px-4 py-3 font-medium">{label}</th>
            <th className="px-4 py-3 font-medium">Eligible</th>
            <th className="px-4 py-3 font-medium">Converted</th>
            <th className="px-4 py-3 font-medium">Rate</th>
            <th className="px-4 py-3 font-medium">Still Driving</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/70 light:divide-gray-200">
          {rows.slice(0, 8).map(row => (
            <tr key={`${label}-${row[labelKey]}`} className="bg-gray-900/35 light:bg-white">
              <td className="max-w-[320px] px-4 py-3 font-medium text-gray-100 light:text-gray-900">{row[labelKey] || 'Unknown'}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.eligible_leads)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.converted_leads)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatPercentValue(row.conversion_rate)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.still_driving_count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ConversionFunnelPanel({ funnel }: { funnel: HrRecruitingConversionFunnel | null | undefined }) {
  if (!funnel) return null
  const summary = funnel.summary
  const trendSummary = funnel.trend_summary
  const recentTrend = (funnel.trend || []).slice(-6).reverse()
  const cards = [
    { label: 'Eligible Leads', value: formatCount(summary.eligible_leads), detail: `${formatCount(summary.unfiltered_eligible_leads)} workbook rows reviewed` },
    { label: 'Converted Exact Match', value: formatCount(summary.converted_leads), detail: formatPercentValue(summary.conversion_rate) },
    { label: 'Not Converted', value: formatCount(summary.not_converted_leads), detail: 'No exact Xcelerator driver match' },
    { label: 'Still Driving Evidence', value: formatCount(summary.still_driving_count), detail: formatPercentValue(summary.still_driving_rate) },
  ]

  return (
    <section className="rounded-xl border border-gray-800/70 bg-gray-900/45 p-5 light:border-gray-200 light:bg-white">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 items-start gap-2">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-300" />
          <div className="min-w-0">
            <h3 className="font-semibold text-white light:text-gray-900">Lead-to-Driver Conversion Funnel</h3>
            <p className="mt-1 text-xs text-gray-500 light:text-gray-600">
              {funnel.workbook_name || 'pending conversion workbook'} · exact Xcelerator match rule · PII suppressed
            </p>
          </div>
        </div>
        <span className="rounded-md border border-gray-700 bg-gray-950/40 px-2 py-1 text-xs text-gray-300 light:border-gray-200 light:bg-gray-50 light:text-gray-700">
          {funnel.source_status}
        </span>
      </div>

      {funnel.source_message && (
        <p className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100 light:text-amber-700">
          {funnel.source_message}
        </p>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(card => (
          <div key={card.label} className="rounded-lg border border-gray-800/70 bg-gray-950/40 p-3 light:border-gray-200 light:bg-gray-50">
            <p className="text-xs text-gray-500 light:text-gray-600">{card.label}</p>
            <p className="mt-1 text-xl font-semibold text-white light:text-gray-900">{card.value}</p>
            <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{card.detail}</p>
          </div>
        ))}
      </div>

      {trendSummary && (
        <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3">
          <div className="rounded-lg border border-gray-800/70 bg-gray-950/35 p-3 light:border-gray-200 light:bg-gray-50">
            <p className="text-xs text-gray-500 light:text-gray-600">Eligible Trend</p>
            <p className="mt-1 text-lg font-semibold text-white light:text-gray-900">{formatChange(trendSummary.eligible_change_pct)}</p>
            <p className="mt-1 text-xs text-gray-500 light:text-gray-600">Current {formatCount(trendSummary.current.eligible_leads)} | Prior {formatCount(trendSummary.previous.eligible_leads)}</p>
          </div>
          <div className="rounded-lg border border-gray-800/70 bg-gray-950/35 p-3 light:border-gray-200 light:bg-gray-50">
            <p className="text-xs text-gray-500 light:text-gray-600">Converted Trend</p>
            <p className="mt-1 text-lg font-semibold text-white light:text-gray-900">{formatChange(trendSummary.converted_change_pct)}</p>
            <p className="mt-1 text-xs text-gray-500 light:text-gray-600">Current {formatCount(trendSummary.current.converted_leads)} | Prior {formatCount(trendSummary.previous.converted_leads)}</p>
          </div>
          <div className="rounded-lg border border-gray-800/70 bg-gray-950/35 p-3 light:border-gray-200 light:bg-gray-50">
            <p className="text-xs text-gray-500 light:text-gray-600">Conversion Rate Trend</p>
            <p className="mt-1 text-lg font-semibold text-white light:text-gray-900">{formatPointChange(trendSummary.conversion_rate_change_points)}</p>
            <p className="mt-1 text-xs text-gray-500 light:text-gray-600">Current {formatPercentValue(trendSummary.current.conversion_rate)} | Prior {formatPercentValue(trendSummary.previous.conversion_rate)}</p>
          </div>
        </div>
      )}

      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-2">
        <ConversionGroupTable rows={funnel.by_source || []} labelKey="source_bucket" label="Source Bucket" />
        <ConversionGroupTable rows={funnel.by_sla || []} labelKey="sla_result" label="SLA Result" />
      </div>

      {!!recentTrend.length && (
        <div className="mt-5 overflow-x-auto rounded-xl border border-gray-800/70 light:border-gray-200">
          <table className="min-w-full divide-y divide-gray-800 text-sm light:divide-gray-200">
            <thead className="bg-gray-900/80 light:bg-gray-100">
              <tr className="text-left text-xs uppercase tracking-wide text-gray-500 light:text-gray-600">
                <th className="px-4 py-3 font-medium">Date</th>
                <th className="px-4 py-3 font-medium">Eligible</th>
                <th className="px-4 py-3 font-medium">Converted</th>
                <th className="px-4 py-3 font-medium">Not Converted</th>
                <th className="px-4 py-3 font-medium">Rate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/70 light:divide-gray-200">
              {recentTrend.map(row => (
                <tr key={row.date} className="bg-gray-900/35 light:bg-white">
                  <td className="px-4 py-3 text-gray-300 light:text-gray-700">{compactDate(row.date)}</td>
                  <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.eligible_leads)}</td>
                  <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.converted_leads)}</td>
                  <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.not_converted_leads)}</td>
                  <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatPercentValue(row.conversion_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-4 text-xs text-gray-500 light:text-gray-600">
        {funnel.source_authority} · {funnel.conversion_rule}
      </p>
    </section>
  )
}

function WorkbookExceptionQueue({ evidence }: { evidence: HrRecruitingWorkbookEvidence | undefined }) {
  if (!evidence) return null
  const rows = evidence.exception_queue || []
  const summary = evidence.exception_summary || []

  return (
    <section className="rounded-xl border border-gray-800/70 bg-gray-900/45 p-5 light:border-gray-200 light:bg-white">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 items-start gap-2">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" />
          <div className="min-w-0">
            <h3 className="font-semibold text-white light:text-gray-900">Workbook Exception Queue</h3>
            <p className="mt-1 text-xs text-gray-500 light:text-gray-600">
              {evidence.workbook_name || 'pending workbook'} · masked lead refs · contact data suppressed
            </p>
          </div>
        </div>
        {!!summary.length && (
          <div className="flex flex-wrap gap-2">
            {summary.map(item => (
              <span key={item.category} className="rounded-md border border-gray-700 bg-gray-950/40 px-2 py-1 text-xs text-gray-300 light:border-gray-200 light:bg-gray-50 light:text-gray-700">
                {item.category}: {formatCount(item.count)}
              </span>
            ))}
          </div>
        )}
      </div>

      {!rows.length ? (
        <EmptyPanel message="The approved HR KPI workbook has no exception-tab rows in the selected date range." />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-800/70 light:border-gray-200">
          <table className="min-w-full divide-y divide-gray-800 text-sm light:divide-gray-200">
            <thead className="bg-gray-900/80 light:bg-gray-100">
              <tr className="text-left text-xs text-gray-500 light:text-gray-600">
                <th className="px-4 py-3 font-medium">Lead Ref</th>
                <th className="px-4 py-3 font-medium">Exception</th>
                <th className="px-4 py-3 font-medium">Age</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">KPI Buckets</th>
                <th className="px-4 py-3 font-medium">Source</th>
                <th className="px-4 py-3 font-medium">Contact</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/70 light:divide-gray-200">
              {rows.map(row => (
                <tr key={row.exception_id} className="bg-gray-900/35 light:bg-white">
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-gray-200 light:text-gray-800">{row.lead_ref}</td>
                  <td className="min-w-[180px] px-4 py-3">
                    <span className={`inline-flex rounded-md border px-2 py-1 text-xs font-medium ${exceptionSeverityClasses(row.severity)}`}>
                      {row.category}
                    </span>
                    <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{row.reason}</p>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-gray-300 light:text-gray-700">{row.age_hours === null || row.age_hours === undefined ? '--' : formatHours(row.age_hours)}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-gray-300 light:text-gray-700">{compactOptionalDate(row.lead_created_date)}</td>
                  <td className="min-w-[130px] px-4 py-3 text-gray-300 light:text-gray-700">{row.status}</td>
                  <td className="min-w-[240px] px-4 py-3 text-xs text-gray-400 light:text-gray-600">
                    <p>Outreach: {row.first_outreach_bucket}</p>
                    <p className="mt-1">Discussion: {row.real_discussion_bucket}</p>
                  </td>
                  <td className="min-w-[190px] px-4 py-3 text-xs text-gray-400 light:text-gray-600">
                    <p>{row.source_system}</p>
                    <p className="mt-1">Tab: {row.source_sheet}</p>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-gray-500 light:text-gray-600">{row.masked_contact}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default function HrRecruitingWorklist() {
  const initialRange = useMemo(() => presetRange('last30', '', ''), [])
  const [datePreset, setDatePreset] = useState<DatePreset>('last30')
  const [customStartDate, setCustomStartDate] = useState(initialRange.startDate || '')
  const [customEndDate, setCustomEndDate] = useState(initialRange.endDate || '')
  const [selectedDepartment, setSelectedDepartment] = useState('HR')
  const dateRange = useMemo(
    () => presetRange(datePreset, customStartDate, customEndDate),
    [customEndDate, customStartDate, datePreset],
  )
  const { data, loading, error, refresh } = useHrRecruitingWorklist(dateRange)
  const byWorklist = data?.by_worklist || []
  const trend = data?.trend || []
  const statusCounts = data?.status_counts || []
  const daily = data?.daily || []
  const workbookSource = data?.source_profile === 'kpi_workbook'
  const hardTargets = useMemo(() => sourceBackedTargets(data?.hard_targets), [data?.hard_targets])
  const teamMembers = data?.team_members || []
  const sourceMessage = data?.source_message || (
    workbookSource
      ? 'Configure HR_RECRUITING_WORKBOOK_PATH with HR_Lead_KPI_Recheck_By_Phone.xlsx to populate this monitor.'
      : 'Import a sanitized Microsoft 365/SharePoint HR lead snapshot when HR_RECRUITING_WORKBOOK_PATH is unavailable.'
  )
  const empty = !loading && !error && data && data.row_counts.deduped_leads === 0

  if (loading && !data) {
    return <Skeleton />
  }

  return (
    <div className="space-y-6">
      <div className="flex min-w-0 flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <div className="rounded-xl bg-cyan-500/15 p-3">
            <Users className="h-6 w-6 text-cyan-300" />
          </div>
          <div className="min-w-0">
            <h2 className="text-xl font-bold text-white light:text-gray-900">HR Recruiting Worklist</h2>
            <p className="max-w-[calc(100vw-6rem)] text-sm text-gray-400 light:text-gray-600 xl:max-w-none">
              <span className="sm:hidden">{workbookSource ? 'Read-only workbook evidence' : 'Read-only M365 HR leads'}</span>
              <span className="hidden sm:inline">{workbookSource ? 'Read-only Grasshopper/SharePoint/Tenstreet workbook evidence · no applicant contact data exposed' : 'Read-only Microsoft 365 HR lead analytics · no applicant contact data exposed'}</span>
            </p>
          </div>
        </div>
        <div className="grid w-full min-w-0 grid-cols-1 gap-3 sm:flex sm:flex-wrap sm:items-center xl:w-auto">
          <span className="w-full min-w-0 truncate rounded-lg border border-gray-800 bg-gray-900/70 px-3 py-2 text-xs text-gray-400 light:border-gray-200 light:bg-white light:text-gray-600 sm:w-auto">
            {recruitingSourceLabel(data, workbookSource)}
          </span>
          <span className="w-full min-w-0 truncate rounded-lg border border-gray-800 bg-gray-900/70 px-3 py-2 text-xs text-gray-400 light:border-gray-200 light:bg-white light:text-gray-600 sm:w-auto">
            {data?.source_status || 'loading'}
          </span>
          <button
            onClick={refresh}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-blue-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      <DateRangeFilter
        preset={datePreset}
        onPresetChange={setDatePreset}
        startDate={dateRange.startDate || ''}
        endDate={dateRange.endDate || ''}
        onStartDateChange={value => {
          setDatePreset('custom')
          setCustomStartDate(value)
        }}
        onEndDateChange={value => {
          setDatePreset('custom')
          setCustomEndDate(value)
        }}
        department={selectedDepartment}
        onDepartmentChange={setSelectedDepartment}
      />

      <TrendComparisonStrip data={data} />

      {(error || data?.source_status === 'source_error') && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 text-amber-300" />
            <div>
              <p className="font-medium text-amber-100">HR recruiting source is unavailable</p>
              <p className="mt-1 text-sm text-amber-100/75">{error || data?.source_message || 'The dashboard is showing an empty read-only state.'}</p>
            </div>
          </div>
        </div>
      )}

      {!!hardTargets.length && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {hardTargets.map(target => {
            const presentation = targetPresentation(target)
            return (
              <KpiCard
                key={target.key}
                icon={presentation.icon}
                label={target.label}
                value={targetValue(target)}
                detail={`Target ${target.display_target}`}
                tone={presentation.tone}
                status={target.status}
              />
            )
          })}
        </div>
      )}

      <PeriodMetricCards data={data} />

      <TeamMembersPanel members={teamMembers} />

      {workbookSource && <WorkbookEvidencePanel evidence={data?.workbook_evidence} />}
      {workbookSource && <ConversionFunnelPanel funnel={data?.workbook_evidence?.conversion_funnel} />}
      {workbookSource && <WorkbookExceptionQueue evidence={data?.workbook_evidence} />}

      <DepartmentCallAnalysisPanel
        department={selectedDepartment}
        title={`${selectedDepartment} Call Analysis`}
        showDepartmentRollups
        dateRange={dateRange}
      />

      {empty && <EmptyPanel message={sourceMessage} />}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <section className="xl:col-span-2 rounded-xl border border-gray-800/70 bg-gray-900/45 p-5 light:border-gray-200 light:bg-white">
          <div className="mb-4 flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-cyan-300" />
            <h3 className="font-semibold text-white light:text-gray-900">{workbookSource ? 'First Outreach KPI Buckets' : 'Leads by Worklist'}</h3>
          </div>
          <WorklistTable rows={byWorklist} workbookSource={workbookSource} />
        </section>

        <section className="rounded-xl border border-gray-800/70 bg-gray-900/45 p-5 light:border-gray-200 light:bg-white">
          <div className="mb-4 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-300" />
            <h3 className="font-semibold text-white light:text-gray-900">{workbookSource ? 'Late or Missing Outreach' : 'Stale Leads'}</h3>
          </div>
          <StaleWorklistTable rows={byWorklist} workbookSource={workbookSource} />
        </section>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section className="rounded-xl border border-gray-800/70 bg-gray-900/45 p-5 light:border-gray-200 light:bg-white">
          <div className="mb-4 flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-emerald-300" />
            <h3 className="font-semibold text-white light:text-gray-900">Daily Trend</h3>
          </div>
          <DailyTrendChart rows={trend} />
        </section>

        <section className="rounded-xl border border-gray-800/70 bg-gray-900/45 p-5 light:border-gray-200 light:bg-white">
          <div className="mb-4 flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-violet-300" />
            <h3 className="font-semibold text-white light:text-gray-900">Status Counts</h3>
          </div>
          <StatusCountChart rows={statusCounts} />
        </section>
      </div>

      <section className="rounded-xl border border-gray-800/70 bg-gray-900/45 p-5 light:border-gray-200 light:bg-white">
        <div className="mb-4 flex items-center gap-2">
          <Database className="h-5 w-5 text-blue-300" />
          <h3 className="font-semibold text-white light:text-gray-900">Daily Worklist Rollup</h3>
        </div>
        <DailyVolumeTable rows={daily} workbookSource={workbookSource} />
        <p className="mt-4 text-xs text-gray-500 light:text-gray-600">
          Generated {data?.generated_at ? new Date(data.generated_at).toLocaleString() : 'pending'} · {data?.source_authority || 'Microsoft 365 Teams + SharePoint HR Driver Leads'} · PII suppressed
        </p>
      </section>
    </div>
  )
}
