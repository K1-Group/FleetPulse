import { Activity, AlertTriangle, Clock3, Users } from 'lucide-react'
import type { EmployeeWorkforceResponse } from '../types/fleet'

interface Props {
  data: EmployeeWorkforceResponse | null
  loading: boolean
}

function formatNumber(value: number | null | undefined, suffix = '', maximumFractionDigits = 1) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '--'
  return `${value.toLocaleString(undefined, { maximumFractionDigits })}${suffix}`
}

function shortDate(value: string | null | undefined) {
  if (!value) return '--'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function sourceTone(status: string | undefined) {
  if (status === 'healthy') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
  if (status === 'unavailable') return 'border-red-500/30 bg-red-500/10 text-red-300'
  return 'border-amber-500/30 bg-amber-500/10 text-amber-300'
}

function sourceLabel(status: string | undefined) {
  return (status || 'pending').replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

export default function EmployeeWorkforce({ data, loading }: Props) {
  const requiredConfig = data?.validation.required_config || data?.source_status.required_config || []
  const employees = data?.employees || []

  return (
    <section className="rounded-lg border border-gray-800 bg-gradient-to-br from-gray-900 to-gray-800 shadow-lg light:border-gray-200 light:from-white light:to-gray-50">
      <div className="border-b border-gray-800/60 px-4 py-4 light:border-gray-200">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Users className="h-5 w-5 text-sky-300" aria-hidden="true" />
              <h2 className="text-lg font-semibold text-white light:text-gray-900">Employee Workforce - Time Doctor</h2>
              <span className={`rounded-full border px-2 py-1 text-[11px] font-semibold ${sourceTone(data?.source_status.status)}`}>
                {sourceLabel(data?.source_status.status)}
              </span>
              <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-1 text-[11px] font-semibold text-emerald-300">
                Read-only
              </span>
            </div>
            <p className="mt-1 text-sm text-gray-400 light:text-gray-600">
              {data?.source_status.message || 'Time Doctor source status pending.'}
            </p>
          </div>
          <div className="text-xs text-gray-500 light:text-gray-600">
            Window: {data?.period.start || '--'} to {data?.period.end || '--'}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
          <Metric icon={Users} label="Employees" value={loading ? '--' : formatNumber(data?.summary.employees, '', 0)} />
          <Metric icon={Activity} label="Active Today" value={loading ? '--' : formatNumber(data?.summary.active_today, '', 0)} />
          <Metric icon={Clock3} label="Worked" value={loading ? '--' : formatNumber(data?.summary.worked_hours, 'h')} />
          <Metric icon={Clock3} label="Idle" value={loading ? '--' : formatNumber(data?.summary.idle_hours, 'h')} />
          <Metric icon={Activity} label="Productivity" value={loading ? '--' : formatNumber(data?.summary.avg_productivity_pct, '%')} />
          <Metric icon={AlertTriangle} label="Missing Today" value={loading ? '--' : formatNumber(data?.summary.missing_timesheet_count, '', 0)} />
        </div>
      </div>

      <div className="px-4 py-4">
        {requiredConfig.length > 0 && !employees.length && (
          <div className="mb-4 rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 text-sm text-amber-100 light:text-amber-800">
            <div className="font-semibold">Required config</div>
            <div className="mt-1 text-xs leading-5">{requiredConfig.join(' | ')}</div>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead className="bg-gray-950/50 text-xs uppercase tracking-wide text-gray-500 light:bg-gray-50 light:text-gray-600">
              <tr>
                <th className="px-3 py-3 text-left">Employee</th>
                <th className="px-3 py-3 text-left">Department</th>
                <th className="px-3 py-3 text-right">Worked</th>
                <th className="px-3 py-3 text-right">Productivity</th>
                <th className="px-3 py-3 text-right">Idle</th>
                <th className="px-3 py-3 text-right">Days</th>
                <th className="px-3 py-3 text-left">Latest</th>
                <th className="px-3 py-3 text-left">Projects</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60 light:divide-gray-200">
              {loading && (
                <tr>
                  <td colSpan={8} className="px-3 py-8 text-center text-gray-500">Loading employee workforce status...</td>
                </tr>
              )}
              {!loading && employees.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-3 py-8 text-center text-gray-500">No source-backed Time Doctor rows returned.</td>
                </tr>
              )}
              {!loading && employees.map(employee => (
                <tr key={employee.employee_id} className="hover:bg-gray-800/40 light:hover:bg-gray-50">
                  <td className="px-3 py-3">
                    <div className="font-medium text-white light:text-gray-900">{employee.employee_name}</div>
                    <div className="text-xs text-gray-500">{employee.email || employee.employee_id}</div>
                  </td>
                  <td className="px-3 py-3 text-gray-300 light:text-gray-700">{employee.department || '--'}</td>
                  <td className="px-3 py-3 text-right font-mono tabular-nums text-gray-300 light:text-gray-700">{formatNumber(employee.worked_hours, 'h')}</td>
                  <td className="px-3 py-3 text-right font-mono tabular-nums text-gray-300 light:text-gray-700">{formatNumber(employee.productivity_pct, '%')}</td>
                  <td className="px-3 py-3 text-right font-mono tabular-nums text-gray-300 light:text-gray-700">{formatNumber(employee.idle_hours, 'h')}</td>
                  <td className="px-3 py-3 text-right font-mono tabular-nums text-gray-300 light:text-gray-700">{employee.days_reported}</td>
                  <td className="px-3 py-3 text-gray-300 light:text-gray-700">{shortDate(employee.latest_activity_date)}</td>
                  <td className="max-w-[260px] truncate px-3 py-3 text-gray-300 light:text-gray-700">{employee.top_projects.join(', ') || '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

function Metric({ icon: Icon, label, value }: { icon: typeof Users; label: string; value: string }) {
  return (
    <div className="min-h-24 rounded-lg border border-gray-800 bg-gray-950/40 p-3 light:border-gray-200 light:bg-white">
      <Icon className="h-4 w-4 text-sky-300" aria-hidden="true" />
      <div className="mt-3 font-mono text-2xl font-semibold tabular-nums text-white light:text-gray-900">{value}</div>
      <div className="mt-1 text-xs text-gray-400 light:text-gray-600">{label}</div>
    </div>
  )
}
