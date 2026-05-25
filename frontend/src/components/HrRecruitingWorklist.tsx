import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import {
  AlertTriangle,
  BarChart3,
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
import DepartmentCallAnalysisPanel from './DepartmentCallAnalysisPanel'
import type {
  HrRecruitingDailyRow,
  HrRecruitingHardTarget,
  HrRecruitingStatusCount,
  HrRecruitingSummary,
  HrRecruitingTrendRow,
  HrRecruitingWorkbookEvidence,
  HrRecruitingWorkbookMemberKpi,
  HrRecruitingWorklistRow,
} from '../types/fleet'

const ZERO_SUMMARY: HrRecruitingSummary = {
  active_leads: 0,
  new_leads_today: 0,
  avg_process_age_hours: 0,
  stale_leads: 0,
  completed_today: 0,
  new_hires_7d: 0,
  active_qualified_pipeline: 0,
  first_touch_24h_pct: null,
  first_touch_eligible_count: 0,
  first_touch_within_24h_count: 0,
  stale_untouched_48h: 0,
  orientation_scheduled_count: 0,
  orientation_show_count: 0,
  orientation_show_rate: null,
}

const numberFormatter = new Intl.NumberFormat('en-US')

const FALLBACK_HARD_TARGETS: Record<string, HrRecruitingHardTarget> = {
  new_hires_7d: {
    key: 'new_hires_7d',
    label: 'New Hires',
    actual: 0,
    target: 5,
    operator: '>=',
    unit: 'hires',
    cadence: '7d',
    display_target: '>= 5/week',
    status: 'awaiting_feed',
  },
  active_qualified_pipeline: {
    key: 'active_qualified_pipeline',
    label: 'Active Qualified Pipeline',
    actual: 0,
    target: 10,
    operator: '>=',
    unit: 'applicants',
    cadence: 'current',
    display_target: '>= 10 applicants',
    status: 'awaiting_feed',
  },
  first_touch_24h_pct: {
    key: 'first_touch_24h_pct',
    label: 'First Touch Speed',
    actual: null,
    target: 0.95,
    operator: '>=',
    unit: 'pct',
    cadence: 'current',
    display_target: '>= 95% within 24h',
    status: 'awaiting_feed',
  },
  stale_untouched_48h: {
    key: 'stale_untouched_48h',
    label: 'Stale Applicants',
    actual: 0,
    target: 0,
    operator: '<=',
    unit: 'applicants',
    cadence: 'current',
    display_target: '0 untouched >48h',
    status: 'awaiting_feed',
  },
  orientation_show_rate: {
    key: 'orientation_show_rate',
    label: 'Orientation Show Rate',
    actual: null,
    target: 0.5,
    operator: '>=',
    unit: 'pct',
    cadence: 'current',
    display_target: '>= 50%',
    status: 'awaiting_feed',
  },
}

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

function formatMinutes(value: number | null | undefined) {
  return `${Number(value || 0).toFixed(0)}m`
}

function targetOrFallback(targets: Record<string, HrRecruitingHardTarget> | undefined, key: string, actual: number | null) {
  const target = targets?.[key] || FALLBACK_HARD_TARGETS[key]
  return { ...target, actual: target?.actual ?? actual }
}

function targetValue(target: HrRecruitingHardTarget) {
  if (target.unit === 'pct') return formatPercentValue(target.actual)
  if (target.actual === null || target.actual === undefined) return '--'
  return formatCount(target.actual)
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

function workbookMetric(evidence: HrRecruitingWorkbookEvidence | undefined, key: string) {
  const value = evidence?.kpi_summary?.[key]
  return typeof value === 'number' ? value : null
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
    return <EmptyPanel message={workbookSource ? 'The configured HR KPI workbook has no lead-level KPI rows after validation.' : 'The configured Zapier/Outlook snapshot has no active worklist leads after validation and dedupe.'} />
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

export default function HrRecruitingWorklist() {
  const { data, loading, error, refresh } = useHrRecruitingWorklist()
  const summary = data?.summary || ZERO_SUMMARY
  const byWorklist = data?.by_worklist || []
  const trend = data?.trend || []
  const statusCounts = data?.status_counts || []
  const daily = data?.daily || []
  const workbookSource = data?.source_profile === 'kpi_workbook'
  const hardTargets = [
    targetOrFallback(data?.hard_targets, 'new_hires_7d', summary.new_hires_7d),
    targetOrFallback(data?.hard_targets, 'active_qualified_pipeline', summary.active_qualified_pipeline),
    targetOrFallback(data?.hard_targets, 'first_touch_24h_pct', summary.first_touch_24h_pct),
    targetOrFallback(data?.hard_targets, 'stale_untouched_48h', summary.stale_untouched_48h),
    targetOrFallback(data?.hard_targets, 'orientation_show_rate', summary.orientation_show_rate),
  ]
  const sourceMessage = data?.source_message || (workbookSource ? 'Configure HR_RECRUITING_WORKBOOK_PATH with the approved HR KPI workbook to populate this monitor.' : 'Configure the approved Zapier/Outlook HR snapshot to populate this monitor.')
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
              <span className="sm:hidden">{workbookSource ? 'Read-only workbook evidence' : 'Read-only Zapier/Outlook analytics'}</span>
              <span className="hidden sm:inline">{workbookSource ? 'Read-only Grasshopper/SharePoint/Tenstreet workbook evidence · no applicant contact data exposed' : 'Read-only Zapier/Outlook analytics · no applicant contact data exposed'}</span>
            </p>
          </div>
        </div>
        <div className="grid w-full min-w-0 grid-cols-1 gap-3 sm:flex sm:flex-wrap sm:items-center xl:w-auto">
          <span className="w-full min-w-0 truncate rounded-lg border border-gray-800 bg-gray-900/70 px-3 py-2 text-xs text-gray-400 light:border-gray-200 light:bg-white light:text-gray-600 sm:w-auto">
            {workbookSource ? data?.source_artifact || 'Workbook pending' : `Table ${data?.table_id || '01KR00WV4YHCB6BMYDE1EG7HEM'}`}
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

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <KpiCard icon={<Users className="h-5 w-5 text-cyan-200" />} label={hardTargets[0].label} value={targetValue(hardTargets[0])} detail={`Target ${hardTargets[0].display_target}`} tone="bg-cyan-500/15" status={hardTargets[0].status} />
        <KpiCard icon={<TrendingUp className="h-5 w-5 text-emerald-200" />} label={hardTargets[1].label} value={targetValue(hardTargets[1])} detail={`Target ${hardTargets[1].display_target}`} tone="bg-emerald-500/15" status={hardTargets[1].status} />
        <KpiCard icon={<Clock className="h-5 w-5 text-blue-200" />} label={hardTargets[2].label} value={targetValue(hardTargets[2])} detail={`Target ${hardTargets[2].display_target}`} tone="bg-blue-500/15" status={hardTargets[2].status} />
        <KpiCard icon={<AlertTriangle className="h-5 w-5 text-amber-200" />} label={hardTargets[3].label} value={targetValue(hardTargets[3])} detail={`Target ${hardTargets[3].display_target}`} tone="bg-amber-500/15" status={hardTargets[3].status} />
        <KpiCard icon={<ShieldCheck className="h-5 w-5 text-violet-200" />} label={hardTargets[4].label} value={targetValue(hardTargets[4])} detail={`Target ${hardTargets[4].display_target}`} tone="bg-violet-500/15" status={hardTargets[4].status} />
      </div>

      {workbookSource && <WorkbookEvidencePanel evidence={data?.workbook_evidence} />}

      <DepartmentCallAnalysisPanel department="HR" title="HR Call Analysis" />

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
          Generated {data?.generated_at ? new Date(data.generated_at).toLocaleString() : 'pending'} · {data?.source_authority || 'Zapier Table + approved TenStreet Outlook emails'} · PII suppressed
        </p>
      </section>
    </div>
  )
}
