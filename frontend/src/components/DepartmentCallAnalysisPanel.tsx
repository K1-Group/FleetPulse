import { AlertTriangle, BarChart3, Clock, PhoneCall, ShieldCheck, TrendingUp, Users } from 'lucide-react'
import type { ReactNode } from 'react'
import { useDepartmentCallAnalysis } from '../hooks/useGeotab'
import type { DepartmentCallAnalysisRollup, HrCallCoachingFlag, HrCallEmployeeProductivity, HrCallAnalysisSummary } from '../types/fleet'

const ZERO_CALL_SUMMARY: HrCallAnalysisSummary = {
  total_call_legs: 0,
  total_minutes: 0,
  avg_call_seconds: 0,
  outbound_attempts: 0,
  connected_calls: 0,
  connect_rate_pct: null,
  voicemails: 0,
  hangups: 0,
  active_employee_count: 0,
  analysis_reports: 0,
  coaching_flags: 0,
  urgent_flags: 0,
  unresolved_calls: 0,
  human_error_reports: 0,
  first_call_eligible_leads: 0,
  first_call_within_24h: 0,
  first_call_24h_pct: null,
  stale_no_call_48h: 0,
}

function formatCount(value: number | null | undefined) {
  return Number(value || 0).toLocaleString()
}

function formatMinutes(value: number | null | undefined) {
  const minutes = Number(value || 0)
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60)
    const remainder = Math.round(minutes % 60)
    return `${hours.toLocaleString()}h ${remainder}m`
  }
  return `${Math.round(minutes)}m`
}

function formatPercentFromPct(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--'
  return `${Number(value).toFixed(1)}%`
}

function formatPercentValue(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--'
  return `${(Number(value) * 100).toFixed(1)}%`
}

function formatDateRange(start?: string | null, end?: string | null) {
  if (!start) return 'awaiting call-log state'
  const startText = new Date(start).toLocaleDateString()
  const endText = end ? new Date(end).toLocaleDateString() : 'now'
  return `${startText} - ${endText}`
}

function StatCard({
  icon,
  label,
  value,
  detail,
  tone = 'bg-blue-500/15',
}: {
  icon: ReactNode
  label: string
  value: string
  detail: string
  tone?: string
}) {
  return (
    <div className="rounded-xl border border-gray-800/70 bg-gray-950/35 p-4 light:border-gray-200 light:bg-gray-50">
      <div className="flex items-start justify-between gap-3">
        <div className={`rounded-lg p-2 ${tone}`}>{icon}</div>
      </div>
      <div className="mt-3 text-2xl font-semibold text-white light:text-gray-900" style={{ fontVariantNumeric: 'tabular-nums lining-nums' }}>
        {value}
      </div>
      <div className="mt-1 text-sm font-medium text-gray-300 light:text-gray-700">{label}</div>
      <div className="mt-2 text-xs text-gray-500 light:text-gray-600">{detail}</div>
    </div>
  )
}

function EmptyPanel({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-dashed border-gray-700/70 bg-gray-950/20 p-6 text-center light:border-gray-300 light:bg-gray-50">
      <p className="text-sm text-gray-500 light:text-gray-600">{message}</p>
    </div>
  )
}

function ProductivityTable({ rows }: { rows: HrCallEmployeeProductivity[] }) {
  if (!rows.length) {
    return <EmptyPanel message="Call productivity appears after department call-detail rows are imported." />
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800/70 light:border-gray-200">
      <table className="min-w-full divide-y divide-gray-800 text-sm light:divide-gray-200">
        <thead className="bg-gray-900/80 light:bg-gray-100">
          <tr className="text-left text-xs uppercase tracking-wide text-gray-500 light:text-gray-600">
            <th className="px-4 py-3 font-medium">Employee</th>
            <th className="px-4 py-3 font-medium">Score</th>
            <th className="px-4 py-3 font-medium">Calls</th>
            <th className="px-4 py-3 font-medium">Outbound</th>
            <th className="px-4 py-3 font-medium">Connected</th>
            <th className="px-4 py-3 font-medium">Minutes</th>
            <th className="px-4 py-3 font-medium">Voicemail</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/70 light:divide-gray-200">
          {rows.map(row => (
            <tr key={`${row.department || 'department'}-${row.extension_id}-${row.employee_name}`} className="bg-gray-900/35 light:bg-white">
              <td className="px-4 py-3 font-medium text-gray-100 light:text-gray-900">{row.employee_name}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{Number(row.productivity_score_0_100).toFixed(1)}%</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.call_legs)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatCount(row.outbound_legs)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatPercentFromPct(row.connected_rate_pct)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatMinutes(row.total_minutes)}</td>
              <td className="px-4 py-3 text-gray-300 light:text-gray-700">{formatPercentFromPct(row.voicemail_rate_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CoachingFlags({ rows }: { rows: HrCallCoachingFlag[] }) {
  const recent = rows.slice(0, 6)
  if (!recent.length) {
    return <EmptyPanel message="No coaching flags were found in imported call-analysis reports." />
  }

  return (
    <div className="space-y-3">
      {recent.map(row => (
        <div key={row.analysis_file_key} className="rounded-xl border border-gray-800/70 bg-gray-900/50 p-4 light:border-gray-200 light:bg-white">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-medium text-white light:text-gray-900">{row.agent_name || 'Unknown agent'}</p>
              <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{row.call_date || 'No date'} | {row.category || 'Unclassified'}</p>
            </div>
            <span className="rounded-md bg-amber-500/15 px-2 py-1 text-xs font-medium text-amber-200 light:text-amber-700">
              {row.flag_reasons}
            </span>
          </div>
          <p className="mt-3 text-sm text-gray-300 light:text-gray-700">
            Sentiment {row.sentiment || '--'} | resolution {row.resolution_quality || '--'} | actions {formatCount(row.action_items_count)}
          </p>
        </div>
      ))}
    </div>
  )
}

function DepartmentRollups({ rows }: { rows: DepartmentCallAnalysisRollup[] }) {
  if (!rows.length) return null

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {rows.map(row => (
        <div key={row.department_key} className="rounded-xl border border-gray-800/70 bg-gray-950/25 p-4 light:border-gray-200 light:bg-gray-50">
          <div className="flex items-center justify-between gap-3">
            <p className="font-medium text-white light:text-gray-900">{row.department}</p>
            <span className="rounded-full border border-gray-700 px-2 py-0.5 text-xs text-gray-400 light:border-gray-300 light:text-gray-600">
              {row.source_status}
            </span>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-gray-400 light:text-gray-600">
            <span>{formatCount(row.summary.total_call_legs)} calls</span>
            <span>{formatPercentFromPct(row.summary.connect_rate_pct)} connect</span>
            <span>{formatCount(row.summary.coaching_flags)} flags</span>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function DepartmentCallAnalysisPanel({
  department,
  title,
  showDepartmentRollups = false,
}: {
  department: string
  title?: string
  showDepartmentRollups?: boolean
}) {
  const callAnalysis = useDepartmentCallAnalysis(department)
  const summary = callAnalysis.data?.summary || ZERO_CALL_SUMMARY
  const employees = callAnalysis.data?.employee_productivity || []
  const coachingFlags = callAnalysis.data?.coaching_flags || []
  const panelTitle = title || `${callAnalysis.data?.department || department} Call Analysis`

  return (
    <section className="rounded-xl border border-gray-800/70 bg-gray-900/45 p-5 light:border-gray-200 light:bg-white">
      <div className="mb-4 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex items-center gap-2">
          <PhoneCall className="h-5 w-5 text-emerald-300" />
          <h3 className="font-semibold text-white light:text-gray-900">{panelTitle}</h3>
        </div>
        <span className="text-xs text-gray-500 light:text-gray-600">
          {callAnalysis.data?.source_status || 'loading'} | {formatDateRange(callAnalysis.data?.coverage?.start, callAnalysis.data?.coverage?.end)}
        </span>
      </div>

      {callAnalysis.error && (
        <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
          Department call-analysis source unavailable: {callAnalysis.error}
        </div>
      )}

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard icon={<PhoneCall className="h-5 w-5 text-emerald-200" />} label="Call Legs" value={formatCount(summary.total_call_legs)} detail={`${formatMinutes(summary.total_minutes)} total talk time`} tone="bg-emerald-500/15" />
        <StatCard icon={<TrendingUp className="h-5 w-5 text-blue-200" />} label="Connect Rate" value={formatPercentFromPct(summary.connect_rate_pct)} detail={`${formatCount(summary.connected_calls)} connected of ${formatCount(summary.outbound_attempts)} outbound`} tone="bg-blue-500/15" />
        <StatCard icon={<Clock className="h-5 w-5 text-cyan-200" />} label="First Call 24h" value={formatPercentValue(summary.first_call_24h_pct)} detail={`${formatCount(summary.first_call_within_24h)} of ${formatCount(summary.first_call_eligible_leads)} matched leads`} tone="bg-cyan-500/15" />
        <StatCard icon={<AlertTriangle className="h-5 w-5 text-amber-200" />} label="Coaching Flags" value={formatCount(summary.coaching_flags)} detail={`${formatCount(summary.urgent_flags)} urgent | ${formatCount(summary.unresolved_calls)} unresolved`} tone="bg-amber-500/15" />
        <StatCard icon={<Users className="h-5 w-5 text-violet-200" />} label="Employees" value={formatCount(summary.active_employee_count)} detail={`${department} extensions scored`} tone="bg-violet-500/15" />
      </div>

      {showDepartmentRollups && (
        <div className="mb-6">
          <div className="mb-3 flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-cyan-300" />
            <h4 className="font-semibold text-white light:text-gray-900">Department Rollup</h4>
          </div>
          <DepartmentRollups rows={callAnalysis.data?.department_rollups || []} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <div className="mb-3 flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-emerald-300" />
            <h4 className="font-semibold text-white light:text-gray-900">Employee Productivity</h4>
          </div>
          <ProductivityTable rows={employees} />
        </div>
        <div>
          <div className="mb-3 flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-amber-300" />
            <h4 className="font-semibold text-white light:text-gray-900">Coaching Flags</h4>
          </div>
          <CoachingFlags rows={coachingFlags} />
        </div>
      </div>
    </section>
  )
}
