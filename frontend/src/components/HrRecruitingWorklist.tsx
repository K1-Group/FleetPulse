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
import type {
  HrRecruitingDailyRow,
  HrRecruitingStatusCount,
  HrRecruitingSummary,
  HrRecruitingTrendRow,
  HrRecruitingWorklistRow,
} from '../types/fleet'

const ZERO_SUMMARY: HrRecruitingSummary = {
  active_leads: 0,
  new_leads_today: 0,
  avg_process_age_hours: 0,
  stale_leads: 0,
  completed_today: 0,
}

const numberFormatter = new Intl.NumberFormat('en-US')

function formatCount(value: number | null | undefined) {
  return numberFormatter.format(Number(value || 0))
}

function formatHours(value: number | null | undefined) {
  return `${Number(value || 0).toFixed(1)}h`
}

function compactDate(value: string) {
  const parsed = new Date(`${value}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
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
}: {
  icon: ReactNode
  label: string
  value: string
  detail: string
  tone: string
}) {
  return (
    <motion.div
      className="rounded-xl border border-gray-800/70 bg-gray-900/65 p-4 shadow-lg light:border-gray-200 light:bg-white"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <div className="flex items-center justify-between gap-3">
        <div className={`rounded-lg p-2 ${tone}`}>{icon}</div>
        <p className="text-2xl font-bold text-white light:text-gray-900">{value}</p>
      </div>
      <p className="mt-3 text-sm font-medium text-gray-200 light:text-gray-800">{label}</p>
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

function WorklistTable({ rows }: { rows: HrRecruitingWorklistRow[] }) {
  if (!rows.length) {
    return <EmptyPanel message="The configured Zapier/Outlook snapshot has no active worklist leads after validation and dedupe." />
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800/70 light:border-gray-200">
      <table className="min-w-full divide-y divide-gray-800 text-sm light:divide-gray-200">
        <thead className="bg-gray-900/80 light:bg-gray-100">
          <tr className="text-left text-xs uppercase tracking-wide text-gray-500 light:text-gray-600">
            <th className="px-4 py-3 font-medium">Worklist</th>
            <th className="px-4 py-3 font-medium">Active</th>
            <th className="px-4 py-3 font-medium">New Today</th>
            <th className="px-4 py-3 font-medium">Avg Age</th>
            <th className="px-4 py-3 font-medium">Max Age</th>
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

function StaleWorklistTable({ rows }: { rows: HrRecruitingWorklistRow[] }) {
  const staleRows = rows
    .filter(row => row.stale_24h || row.stale_48h || row.stale_72h)
    .sort((a, b) => b.stale_72h - a.stale_72h || b.stale_48h - a.stale_48h || b.stale_24h - a.stale_24h)

  if (!staleRows.length) {
    return <EmptyPanel message="No active worklist leads are over the configured stale thresholds." />
  }

  return (
    <div className="space-y-3">
      {staleRows.map(row => (
        <div key={row.worklist} className="rounded-xl border border-gray-800/70 bg-gray-900/50 p-4 light:border-gray-200 light:bg-white">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-medium text-white light:text-gray-900">{row.worklist}</p>
              <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{formatCount(row.active_leads)} active leads · max age {formatHours(row.max_age_hours)}</p>
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

function DailyVolumeTable({ rows }: { rows: HrRecruitingDailyRow[] }) {
  const recent = rows.slice(-8).reverse()
  if (!recent.length) return null

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800/70 light:border-gray-200">
      <table className="min-w-full divide-y divide-gray-800 text-sm light:divide-gray-200">
        <thead className="bg-gray-900/80 light:bg-gray-100">
          <tr className="text-left text-xs uppercase tracking-wide text-gray-500 light:text-gray-600">
            <th className="px-4 py-3 font-medium">Date</th>
            <th className="px-4 py-3 font-medium">Worklist</th>
            <th className="px-4 py-3 font-medium">New</th>
            <th className="px-4 py-3 font-medium">Completed</th>
            <th className="px-4 py-3 font-medium">Active</th>
            <th className="px-4 py-3 font-medium">Avg Process</th>
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

export default function HrRecruitingWorklist() {
  const { data, loading, error, refresh } = useHrRecruitingWorklist()
  const summary = data?.summary || ZERO_SUMMARY
  const byWorklist = data?.by_worklist || []
  const trend = data?.trend || []
  const statusCounts = data?.status_counts || []
  const daily = data?.daily || []
  const sourceMessage = data?.source_message || 'Configure the approved Zapier/Outlook HR snapshot to populate this monitor.'
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
              <span className="sm:hidden">Read-only Zapier/Outlook analytics</span>
              <span className="hidden sm:inline">Read-only Zapier/Outlook analytics · no applicant contact data exposed</span>
            </p>
          </div>
        </div>
        <div className="grid w-full min-w-0 grid-cols-1 gap-3 sm:flex sm:flex-wrap sm:items-center xl:w-auto">
          <span className="w-full min-w-0 truncate rounded-lg border border-gray-800 bg-gray-900/70 px-3 py-2 text-xs text-gray-400 light:border-gray-200 light:bg-white light:text-gray-600 sm:w-auto">
            Table {data?.table_id || '01KR00WV4YHCB6BMYDE1EG7HEM'}
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
        <KpiCard icon={<Users className="h-5 w-5 text-cyan-200" />} label="Active Leads" value={formatCount(summary.active_leads)} detail="Currently open worklist items" tone="bg-cyan-500/15" />
        <KpiCard icon={<TrendingUp className="h-5 w-5 text-emerald-200" />} label="New Today" value={formatCount(summary.new_leads_today)} detail="First assignments today" tone="bg-emerald-500/15" />
        <KpiCard icon={<Clock className="h-5 w-5 text-blue-200" />} label="Avg Process Age" value={formatHours(summary.avg_process_age_hours)} detail="Open lead age from first assignment" tone="bg-blue-500/15" />
        <KpiCard icon={<AlertTriangle className="h-5 w-5 text-amber-200" />} label="Stale Leads" value={formatCount(summary.stale_leads)} detail="Open items over SLA threshold" tone="bg-amber-500/15" />
        <KpiCard icon={<ShieldCheck className="h-5 w-5 text-violet-200" />} label="Completed Today" value={formatCount(summary.completed_today)} detail="Completed with process time" tone="bg-violet-500/15" />
      </div>

      {empty && <EmptyPanel message={sourceMessage} />}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <section className="xl:col-span-2 rounded-xl border border-gray-800/70 bg-gray-900/45 p-5 light:border-gray-200 light:bg-white">
          <div className="mb-4 flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-cyan-300" />
            <h3 className="font-semibold text-white light:text-gray-900">Leads by Worklist</h3>
          </div>
          <WorklistTable rows={byWorklist} />
        </section>

        <section className="rounded-xl border border-gray-800/70 bg-gray-900/45 p-5 light:border-gray-200 light:bg-white">
          <div className="mb-4 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-300" />
            <h3 className="font-semibold text-white light:text-gray-900">Stale Leads</h3>
          </div>
          <StaleWorklistTable rows={byWorklist} />
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
        <DailyVolumeTable rows={daily} />
        <p className="mt-4 text-xs text-gray-500 light:text-gray-600">
          Generated {data?.generated_at ? new Date(data.generated_at).toLocaleString() : 'pending'} · {data?.source_authority || 'Zapier Table + approved TenStreet Outlook emails'} · PII suppressed
        </p>
      </section>
    </div>
  )
}
