import { AlertTriangle, CalendarClock, CheckCircle2, ClipboardCheck, FileWarning, Shield } from 'lucide-react'
import type { DriverComplianceDocumentStatus, DriverComplianceResponse } from '../types/fleet'

interface Props {
  data: DriverComplianceResponse | null
  loading: boolean
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '--'
  return value.toLocaleString()
}

function formatDate(value: string | null | undefined) {
  if (!value) return '--'
  const parsed = new Date(`${value}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function statusTone(status: DriverComplianceDocumentStatus | undefined) {
  if (status === 'valid') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
  if (status === 'warning') return 'border-amber-500/30 bg-amber-500/10 text-amber-300'
  if (status === 'expired') return 'border-red-500/30 bg-red-500/10 text-red-300'
  return 'border-gray-500/30 bg-gray-500/10 text-gray-300'
}

function statusLabel(status: string | undefined) {
  return (status || 'pending').replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

export default function DriverCompliance({ data, loading }: Props) {
  const requiredConfig = data?.validation.required_config || data?.source_status.required_config || []
  const drivers = data?.drivers || []

  return (
    <section className="rounded-lg border border-gray-800 bg-gradient-to-br from-gray-900 to-gray-800 shadow-lg light:border-gray-200 light:from-white light:to-gray-50">
      <div className="border-b border-gray-800/60 px-4 py-4 light:border-gray-200">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Shield className="h-5 w-5 text-emerald-300" aria-hidden="true" />
              <h2 className="text-lg font-semibold text-white light:text-gray-900">Driver Compliance</h2>
              <span className={`rounded-full border px-2 py-1 text-[11px] font-semibold ${statusTone(data?.source_status.status)}`}>
                {statusLabel(data?.source_status.status)}
              </span>
              <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-1 text-[11px] font-semibold text-emerald-300">
                Read-only
              </span>
            </div>
            <p className="mt-1 text-sm text-gray-400 light:text-gray-600">
              {data?.source_status.message || 'Driver qualification source status pending.'}
            </p>
          </div>
          <div className="text-xs text-gray-500 light:text-gray-600">
            Warning window: {data?.config.warning_days || 45} days
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          <Metric icon={ClipboardCheck} label="Drivers" value={loading ? '--' : formatNumber(data?.summary.drivers)} />
          <Metric icon={CheckCircle2} label="Valid" value={loading ? '--' : formatNumber(data?.summary.valid)} />
          <Metric icon={AlertTriangle} label="Warning" value={loading ? '--' : formatNumber(data?.summary.warning)} />
          <Metric icon={FileWarning} label="Expired" value={loading ? '--' : formatNumber(data?.summary.expired)} />
          <Metric icon={CalendarClock} label="Medical Due" value={loading ? '--' : formatNumber(data?.summary.medical_card_expiring)} />
          <Metric icon={CalendarClock} label="Drug Test Due" value={loading ? '--' : formatNumber(data?.summary.drug_test_expiring)} />
          <Metric icon={CalendarClock} label="MVR Due" value={loading ? '--' : formatNumber(data?.summary.mvr_expiring)} />
        </div>
      </div>

      <div className="px-4 py-4">
        {requiredConfig.length > 0 && !drivers.length && (
          <div className="mb-4 rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 text-sm text-amber-100 light:text-amber-800">
            <div className="font-semibold">Required config</div>
            <div className="mt-1 text-xs leading-5">{requiredConfig.join(' | ')}</div>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] text-sm">
            <thead className="bg-gray-950/50 text-xs uppercase tracking-wide text-gray-500 light:bg-gray-50 light:text-gray-600">
              <tr>
                <th className="px-3 py-3 text-left">Driver</th>
                <th className="px-3 py-3 text-left">Terminal</th>
                <th className="px-3 py-3 text-left">Medical Card</th>
                <th className="px-3 py-3 text-left">Drug Test</th>
                <th className="px-3 py-3 text-left">MVR</th>
                <th className="px-3 py-3 text-left">Next Expiration</th>
                <th className="px-3 py-3 text-left">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60 light:divide-gray-200">
              {loading && (
                <tr>
                  <td colSpan={7} className="px-3 py-8 text-center text-gray-500">Loading driver compliance foundation...</td>
                </tr>
              )}
              {!loading && drivers.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-3 py-8 text-center text-gray-500">No source-backed driver compliance rows returned.</td>
                </tr>
              )}
              {!loading && drivers.map(driver => (
                <tr key={driver.driver_id} className="hover:bg-gray-800/40 light:hover:bg-gray-50">
                  <td className="px-3 py-3">
                    <div className="font-medium text-white light:text-gray-900">{driver.driver_name}</div>
                    <div className="text-xs text-gray-500">{driver.driver_id}</div>
                  </td>
                  <td className="px-3 py-3 text-gray-300 light:text-gray-700">{driver.terminal || '--'}</td>
                  <td className="px-3 py-3"><DocBadge status={driver.documents.medical_card.status} date={driver.documents.medical_card.expires_on} /></td>
                  <td className="px-3 py-3"><DocBadge status={driver.documents.drug_test.status} date={driver.documents.drug_test.expires_on} /></td>
                  <td className="px-3 py-3"><DocBadge status={driver.documents.mvr.status} date={driver.documents.mvr.expires_on} /></td>
                  <td className="px-3 py-3 text-gray-300 light:text-gray-700">{formatDate(driver.next_expiration_date)}</td>
                  <td className="px-3 py-3">
                    <span className={`inline-flex rounded-full border px-2 py-1 text-xs font-semibold ${statusTone(driver.overall_status)}`}>
                      {statusLabel(driver.overall_status)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

function DocBadge({ status, date }: { status: DriverComplianceDocumentStatus; date: string | null }) {
  return (
    <span className={`inline-flex min-w-[150px] items-center justify-between gap-2 rounded-full border px-2 py-1 text-xs ${statusTone(status)}`}>
      <span className="font-semibold">{statusLabel(status)}</span>
      <span>{formatDate(date)}</span>
    </span>
  )
}

function Metric({ icon: Icon, label, value }: { icon: typeof Shield; label: string; value: string }) {
  return (
    <div className="min-h-24 rounded-lg border border-gray-800 bg-gray-950/40 p-3 light:border-gray-200 light:bg-white">
      <Icon className="h-4 w-4 text-emerald-300" aria-hidden="true" />
      <div className="mt-3 font-mono text-2xl font-semibold tabular-nums text-white light:text-gray-900">{value}</div>
      <div className="mt-1 text-xs text-gray-400 light:text-gray-600">{label}</div>
    </div>
  )
}
