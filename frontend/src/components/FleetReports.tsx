import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  AlertTriangle,
  BarChart3,
  Calendar,
  CheckCircle2,
  Clock,
  Download,
  FileJson,
  FileText,
  Gauge,
  Loader2,
  Mail,
  Printer,
  RefreshCw,
  Save,
  Send,
  Table2,
} from 'lucide-react'

type ReportPeriod = 'daily' | 'weekly' | 'monthly'
type ScheduleFrequency = 'daily' | 'weekly' | 'monthly'
type NoticeType = 'success' | 'warning' | 'error' | 'info'
type CostMode = 'weekly' | 'monthly'

type DateWindow = {
  end: string
  label: string
  start: string
}

type ReportSummary = {
  total_vehicles?: number
  total_trips?: number
  total_distance_mi?: number
  total_exceptions?: number
  trailers_tracked?: number
  trailer_custody_inferred?: number
  [key: string]: unknown
}

type ReportSchedule = {
  enabled: boolean
  period: ReportPeriod
  frequency: ScheduleFrequency
  recipients: string[]
  send_time: string
  timezone: string
  weekday?: number | null
  day_of_month?: number | null
}

type ReportResponse = {
  error?: string
  generated_at?: string | null
  html?: string
  period_end?: string | null
  period_start?: string | null
  summary?: ReportSummary
}

type ScheduleStatus = {
  schedule?: Partial<ReportSchedule>
  next_run_at?: string | null
  delivery_ready?: boolean
  required_config?: string[]
  persistent_storage?: boolean
}

type SourceStatus = {
  message?: string
  row_count?: number | null
  status?: string
}

type OperatingCostSummary = {
  drive_hours?: number | null
  driver_pay?: number | null
  fuel_cost?: number | null
  insurance_cost?: number | null
  known_cost_per_mile?: number | null
  known_operating_cost?: number | null
  maintenance_cost?: number | null
  miles?: number | null
  operating_hours?: number | null
  other_expense_cost?: number | null
  rental_trucks_trailers_cost?: number | null
  true_cost_per_mile?: number | null
  true_operating_cost?: number | null
}

type OperatingCostSnapshot = {
  complete_cost_available?: boolean
  generated_at?: string
  period_end?: string
  period_start?: string
  sources?: Record<string, SourceStatus>
  summary?: OperatingCostSummary | null
  unresolved_sources?: string[]
}

type EntityMarginSummary = {
  k1l_driver_pay?: number | null
  k1l_grand_total?: number | null
  k1l_profit?: number | null
  k1l_profit_per_mile?: number | null
  k1l_revenue_per_mile?: number | null
  k1l_true_operating_cost?: number | null
  k1l_true_operating_cpm?: number | null
}

type EntityMarginSnapshot = {
  generated_at?: string
  period_end?: string
  period_start?: string
  sources?: Record<string, SourceStatus>
  summary?: EntityMarginSummary | null
  unresolved_sources?: string[]
  xcelerator_source_type?: string | null
}

type CostSnapshot = {
  entity?: EntityMarginSnapshot | null
  operating?: OperatingCostSnapshot | null
}

const PERIODS: ReportPeriod[] = ['daily', 'weekly', 'monthly']
const FREQUENCIES: ScheduleFrequency[] = ['daily', 'weekly', 'monthly']
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

const buttonBase =
  'inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all disabled:cursor-not-allowed disabled:opacity-45'

function parseRecipients(value: string): string[] {
  return value
    .split(/[,;\n]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function downloadBlob(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function csvValue(value: unknown): string {
  const text = value == null ? '' : String(value)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function formatDateTime(value?: string | null): string {
  if (!value) return 'Not scheduled'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Not scheduled'
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function fileDate(value?: string | null): string {
  if (!value) return new Date().toISOString().slice(0, 10)
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? new Date().toISOString().slice(0, 10) : parsed.toISOString().slice(0, 10)
}

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function toDateInputValue(value: Date): string {
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
}

function toMonthInputValue(value: Date): string {
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}`
}

function parseDateInput(value: string): Date {
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return new Date()
  return new Date(year, month - 1, day)
}

function addDays(value: Date, days: number): Date {
  const next = new Date(value)
  next.setDate(next.getDate() + days)
  return next
}

function startOfWeekMonday(value: Date): Date {
  const start = new Date(value.getFullYear(), value.getMonth(), value.getDate())
  const day = start.getDay()
  const diff = day === 0 ? -6 : 1 - day
  start.setDate(start.getDate() + diff)
  return start
}

function lastDayOfMonth(year: number, monthIndex: number): Date {
  return new Date(year, monthIndex + 1, 0)
}

function formatWindowLabel(start?: string | null, end?: string | null): string {
  if (!start || !end) return 'Window pending'
  const startDate = new Date(`${start.slice(0, 10)}T12:00:00`)
  const endDate = new Date(`${end.slice(0, 10)}T12:00:00`)
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return 'Window pending'
  const sameYear = startDate.getFullYear() === endDate.getFullYear()
  const sameMonth = sameYear && startDate.getMonth() === endDate.getMonth()
  const startMonthDay = startDate.toLocaleDateString([], { month: 'short', day: 'numeric' })
  const endMonthDay = endDate.toLocaleDateString([], { month: 'short', day: 'numeric' })
  if (sameMonth) return `${startMonthDay}-${endDate.getDate()}, ${endDate.getFullYear()}`
  if (sameYear) return `${startMonthDay}-${endMonthDay}, ${endDate.getFullYear()}`
  return `${startDate.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}-${endDate.toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })}`
}

function calculateCostWindow(mode: CostMode, weekDate: string, monthValue: string): DateWindow {
  if (mode === 'monthly') {
    const [yearRaw, monthRaw] = monthValue.split('-').map(Number)
    const today = new Date()
    const year = yearRaw || today.getFullYear()
    const monthIndex = (monthRaw || today.getMonth() + 1) - 1
    const start = new Date(year, monthIndex, 1)
    const end = lastDayOfMonth(year, monthIndex)
    return {
      start: toDateInputValue(start),
      end: toDateInputValue(end),
      label: formatWindowLabel(toDateInputValue(start), toDateInputValue(end)),
    }
  }

  const weekStart = startOfWeekMonday(parseDateInput(weekDate))
  const weekEnd = addDays(weekStart, 6)
  return {
    start: toDateInputValue(weekStart),
    end: toDateInputValue(weekEnd),
    label: formatWindowLabel(toDateInputValue(weekStart), toDateInputValue(weekEnd)),
  }
}

function reportWindowFromResponse(data: ReportResponse, fallbackPeriod: ReportPeriod): DateWindow | null {
  if (data.period_start && data.period_end) {
    return {
      start: data.period_start.slice(0, 10),
      end: data.period_end.slice(0, 10),
      label: formatWindowLabel(data.period_start, data.period_end),
    }
  }

  const generated = data.generated_at ? new Date(data.generated_at) : new Date()
  if (Number.isNaN(generated.getTime())) return null
  const days = fallbackPeriod === 'daily' ? 1 : fallbackPeriod === 'monthly' ? 30 : 7
  const start = addDays(generated, -days)
  return {
    start: toDateInputValue(start),
    end: toDateInputValue(generated),
    label: formatWindowLabel(toDateInputValue(start), toDateInputValue(generated)),
  }
}

function formatCurrency(value: number | null | undefined, options: Intl.NumberFormatOptions = {}) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Pending'
  return new Intl.NumberFormat('en-US', {
    currency: 'USD',
    maximumFractionDigits: 0,
    style: 'currency',
    ...options,
  }).format(Number(value))
}

function formatNumber(value: number | null | undefined, maximumFractionDigits = 0) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Pending'
  return Number(value).toLocaleString('en-US', { maximumFractionDigits })
}

function formatCpm(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Pending'
  return `$${Number(value).toFixed(2)}/mi`
}

function sourceStatusLabel(source?: SourceStatus): string {
  if (!source?.status) return 'not configured'
  return source.status.replace(/_/g, ' ')
}

function CostMetricCard({
  accent = 'text-white',
  label,
  subtext,
  value,
  windowLabel,
}: {
  accent?: string
  label: string
  subtext?: string
  value: string
  windowLabel: string
}) {
  return (
    <div className="rounded-lg border border-gray-800/70 bg-gray-950/30 p-4 light:border-gray-200 light:bg-gray-50">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`mt-2 break-words text-2xl font-bold ${accent}`}>{value}</div>
      {subtext && <div className="mt-1 text-xs text-gray-400 light:text-gray-600">{subtext}</div>}
      <div className="mt-3 border-t border-gray-800/70 pt-2 text-[11px] text-gray-500 light:border-gray-200 light:text-gray-600">
        Window: {windowLabel}
      </div>
    </div>
  )
}

export default function FleetReports() {
  const [period, setPeriod] = useState<ReportPeriod>('weekly')
  const [loading, setLoading] = useState(false)
  const [reportHtml, setReportHtml] = useState<string | null>(null)
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)
  const [reportWindow, setReportWindow] = useState<DateWindow | null>(null)
  const [summary, setSummary] = useState<ReportSummary | null>(null)
  const [notice, setNotice] = useState<{ type: NoticeType; message: string } | null>(null)
  const [emailRecipients, setEmailRecipients] = useState('')
  const [emailSending, setEmailSending] = useState(false)
  const [costMode, setCostMode] = useState<CostMode>('weekly')
  const [costWeekDate, setCostWeekDate] = useState(() => toDateInputValue(addDays(startOfWeekMonday(new Date()), -7)))
  const [costMonth, setCostMonth] = useState(() => toMonthInputValue(new Date()))
  const [costSnapshot, setCostSnapshot] = useState<CostSnapshot | null>(null)
  const [costLoading, setCostLoading] = useState(false)
  const [costError, setCostError] = useState<string | null>(null)
  const [scheduleEnabled, setScheduleEnabled] = useState(false)
  const [scheduleFrequency, setScheduleFrequency] = useState<ScheduleFrequency>('weekly')
  const [schedulePeriod, setSchedulePeriod] = useState<ReportPeriod>('weekly')
  const [scheduleRecipients, setScheduleRecipients] = useState('')
  const [scheduleTime, setScheduleTime] = useState('07:00')
  const [scheduleWeekday, setScheduleWeekday] = useState(0)
  const [scheduleDayOfMonth, setScheduleDayOfMonth] = useState(1)
  const [scheduleSaving, setScheduleSaving] = useState(false)
  const [scheduleStatus, setScheduleStatus] = useState<ScheduleStatus | null>(null)

  const reportFileBase = `fleetpulse-report-${period}-${fileDate(generatedAt)}`
  const reportWindowLabel = reportWindow?.label || 'Window pending'
  const costWindow = useMemo(
    () => calculateCostWindow(costMode, costWeekDate, costMonth),
    [costMode, costMonth, costWeekDate]
  )
  const operatingSummary = costSnapshot?.operating?.summary
  const entitySummary = costSnapshot?.entity?.summary
  const xceleratorReady = !(costSnapshot?.entity?.unresolved_sources || []).length && Number.isFinite(Number(entitySummary?.k1l_true_operating_cost))
  const knownCost = operatingSummary?.known_operating_cost ?? null
  const knownCpm = operatingSummary?.known_cost_per_mile ?? null
  const allInCost = xceleratorReady ? entitySummary?.k1l_true_operating_cost : operatingSummary?.true_operating_cost
  const allInCpm = xceleratorReady ? entitySummary?.k1l_true_operating_cpm : operatingSummary?.true_cost_per_mile
  const costSources = costSnapshot?.operating?.sources || {}
  const entitySources = costSnapshot?.entity?.sources || {}
  const unresolvedCostSources = [
    ...(costSnapshot?.operating?.unresolved_sources || []),
    ...(costSnapshot?.entity?.unresolved_sources || []),
  ].filter((value, index, array) => value && array.indexOf(value) === index)
  const allInUnresolvedSources = xceleratorReady ? [] : unresolvedCostSources

  const summaryRows = useMemo(
    () => [
      ['Vehicles', summary?.total_vehicles ?? 0],
      ['Trips', summary?.total_trips ?? 0],
      ['Miles', Number(summary?.total_distance_mi ?? 0).toFixed(0)],
      ['Exceptions', summary?.total_exceptions ?? 0],
      ['Trailer Custody', summary?.trailer_custody_inferred ?? 0],
    ],
    [summary]
  )

  useEffect(() => {
    const loadSchedule = async () => {
      try {
        const res = await fetch('/api/reports/schedule')
        if (!res.ok) return
        const data: ScheduleStatus = await res.json()
        const schedule = data.schedule
        setScheduleStatus(data)
        if (!schedule) return
        setScheduleEnabled(Boolean(schedule.enabled))
        setScheduleFrequency((schedule.frequency as ScheduleFrequency) || 'weekly')
        setSchedulePeriod((schedule.period as ReportPeriod) || 'weekly')
        setScheduleRecipients((schedule.recipients || []).join(', '))
        setScheduleTime(schedule.send_time || '07:00')
        setScheduleWeekday(Number(schedule.weekday ?? 0))
        setScheduleDayOfMonth(Number(schedule.day_of_month ?? 1))
      } catch (e) {
        console.error('Failed to load report schedule:', e)
      }
    }
    loadSchedule()
  }, [])

  const loadOperatingCost = useCallback(async () => {
    setCostLoading(true)
    setCostError(null)
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 60000)

    const fetchCostJson = async <T,>(path: string): Promise<T> => {
      const res = await fetch(path, { signal: controller.signal })
      if (!res.ok) throw new Error(`${path} returned ${res.status}`)
      return await res.json() as T
    }

    try {
      const query = `start=${encodeURIComponent(costWindow.start)}&end=${encodeURIComponent(costWindow.end)}`
      const [operatingResult, entityResult] = await Promise.allSettled([
        fetchCostJson<OperatingCostSnapshot>(`/api/fuel/operating-cost?${query}`),
        fetchCostJson<EntityMarginSnapshot>(`/api/fuel/entity-margin?${query}`),
      ])
      if (operatingResult.status === 'rejected' && entityResult.status === 'rejected') {
        throw operatingResult.reason instanceof Error ? operatingResult.reason : new Error('Cost APIs unavailable')
      }
      setCostSnapshot({
        operating: operatingResult.status === 'fulfilled' ? operatingResult.value : null,
        entity: entityResult.status === 'fulfilled' ? entityResult.value : null,
      })
      if (operatingResult.status === 'rejected' || entityResult.status === 'rejected') {
        setCostError('One cost source did not respond; showing the available read-only projection.')
      }
    } catch (e) {
      console.error('Failed to load operating cost window:', e)
      setCostSnapshot(null)
      setCostError(e instanceof Error ? e.message : 'Operating cost window failed to load.')
    } finally {
      window.clearTimeout(timeout)
      setCostLoading(false)
    }
  }, [costWindow.end, costWindow.start])

  useEffect(() => {
    void loadOperatingCost()
  }, [loadOperatingCost])

  const generateReport = async () => {
    setLoading(true)
    setNotice(null)
    try {
      const res = await fetch(`/api/reports/generate?period=${period}`)
      if (!res.ok) throw new Error(`Report API returned ${res.status}`)
      const data: ReportResponse = await res.json()
      setReportHtml(data.html || null)
      setSummary(data.summary || null)
      setGeneratedAt(data.generated_at || new Date().toISOString())
      setReportWindow(reportWindowFromResponse(data, period))
      if (data.error) {
        setNotice({ type: 'warning', message: `Report generated with a source warning: ${data.error}` })
      }
    } catch (e) {
      console.error('Failed to generate report:', e)
      setNotice({ type: 'error', message: 'Report generation failed. Check Geotab/API connectivity and retry.' })
    } finally {
      setLoading(false)
    }
  }

  const printReport = () => {
    if (!reportHtml) return
    const w = window.open('', '_blank')
    if (w) {
      w.document.write(reportHtml)
      w.document.close()
      setTimeout(() => w.print(), 500)
    }
  }

  const downloadReport = () => {
    if (!reportHtml) return
    downloadBlob(`${reportFileBase}.html`, reportHtml, 'text/html')
    setNotice({ type: 'success', message: 'HTML report exported.' })
  }

  const downloadJsonReport = () => {
    if (!reportHtml || !summary) return
    downloadBlob(
      `${reportFileBase}.json`,
      JSON.stringify({
        period,
        period_start: reportWindow?.start,
        period_end: reportWindow?.end,
        generated_at: generatedAt,
        summary,
        html: reportHtml,
      }, null, 2),
      'application/json'
    )
    setNotice({ type: 'success', message: 'JSON report package exported.' })
  }

  const downloadCsvReport = () => {
    if (!summary) return
    const rows = [['Metric', 'Value', 'Window'], ...summaryRows.map(([label, value]) => [label, value, reportWindowLabel])]
    const csv = rows.map((row) => row.map(csvValue).join(',')).join('\n')
    downloadBlob(`${reportFileBase}-summary.csv`, csv, 'text/csv')
    setNotice({ type: 'success', message: 'CSV summary exported.' })
  }

  const openEmailDraft = (recipients: string[]) => {
    const subject = `FleetPulse ${period.charAt(0).toUpperCase() + period.slice(1)} Report`
    const body = [
      `FleetPulse ${period} report generated ${formatDateTime(generatedAt)}.`,
      `Window: ${reportWindowLabel}.`,
      '',
      ...summaryRows.map(([label, value]) => `${label}: ${value}`),
      '',
      'The full report is available from FleetPulse report export.',
    ].join('\n')
    window.location.href = `mailto:${recipients.join(',')}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
  }

  const emailReport = async () => {
    if (!reportHtml) return
    const recipients = parseRecipients(emailRecipients)
    if (!recipients.length) {
      setNotice({ type: 'error', message: 'Add at least one email recipient.' })
      return
    }

    setEmailSending(true)
    setNotice(null)
    try {
      const res = await fetch('/api/reports/email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recipients,
          period,
          period_start: reportWindow?.start,
          period_end: reportWindow?.end,
          subject: `FleetPulse ${period.charAt(0).toUpperCase() + period.slice(1)} Report`,
          html: reportHtml,
          summary: summary || {},
          generated_at: generatedAt,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || `Email API returned ${res.status}`)
      if (data.status === 'sent') {
        setNotice({ type: 'success', message: data.message || 'Report email submitted.' })
        return
      }
      openEmailDraft(recipients)
      setNotice({
        type: 'warning',
        message: data.message || 'Server-side email is not configured; opened an email draft instead.',
      })
    } catch (e) {
      console.error('Failed to email report:', e)
      openEmailDraft(recipients)
      setNotice({ type: 'warning', message: 'Email delivery failed; opened an email draft fallback.' })
    } finally {
      setEmailSending(false)
    }
  }

  const saveSchedule = async () => {
    const recipients = parseRecipients(scheduleRecipients)
    if (scheduleEnabled && !recipients.length) {
      setNotice({ type: 'error', message: 'Add at least one recipient before enabling scheduled reports.' })
      return
    }

    setScheduleSaving(true)
    setNotice(null)
    try {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Chicago'
      const res = await fetch('/api/reports/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled: scheduleEnabled,
          frequency: scheduleFrequency,
          period: schedulePeriod,
          recipients,
          send_time: scheduleTime,
          timezone,
          weekday: scheduleWeekday,
          day_of_month: scheduleDayOfMonth,
        }),
      })
      const data: ScheduleStatus & { detail?: string } = await res.json()
      if (!res.ok) throw new Error(data.detail || `Schedule API returned ${res.status}`)
      setScheduleStatus(data)
      setNotice({
        type: data.delivery_ready ? 'success' : 'warning',
        message: data.delivery_ready
          ? 'Report schedule saved.'
          : `Schedule saved, but email delivery still needs ${data.required_config?.join(', ') || 'delivery config'}.`,
      })
    } catch (e) {
      console.error('Failed to save report schedule:', e)
      setNotice({ type: 'error', message: e instanceof Error ? e.message : 'Report schedule save failed.' })
    } finally {
      setScheduleSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gray-900/50 dark:bg-gray-900/50 light:bg-white border border-gray-800/50 dark:border-gray-800/50 light:border-gray-200 rounded-xl p-6"
      >
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between mb-6">
          <div className="flex items-center gap-3">
            <FileText className="w-6 h-6 text-blue-400" />
            <div>
              <h2 className="text-xl font-bold">Fleet Reports</h2>
              <p className="text-sm text-gray-400">Generate, export, email, and schedule fleet analytics reports</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="inline-flex items-center gap-1 rounded-full border border-gray-700 bg-gray-800/40 px-3 py-1 text-gray-300 light:border-gray-200 light:bg-gray-50 light:text-gray-600">
              <Clock className="h-3.5 w-3.5" />
              Next: {formatDateTime(scheduleStatus?.next_run_at)}
            </span>
            <span
              className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 ${
                scheduleStatus?.delivery_ready
                  ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                  : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
              }`}
            >
              {scheduleStatus?.delivery_ready ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
              {scheduleStatus?.delivery_ready ? 'Email ready' : 'Email config needed'}
            </span>
          </div>
        </div>

        {notice && (
          <div
            className={`mb-6 flex items-start gap-2 rounded-lg border px-4 py-3 text-sm ${
              notice.type === 'success'
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                : notice.type === 'error'
                  ? 'border-red-500/30 bg-red-500/10 text-red-200'
                  : notice.type === 'warning'
                    ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                    : 'border-blue-500/30 bg-blue-500/10 text-blue-200'
            }`}
          >
            {notice.type === 'success' ? <CheckCircle2 className="mt-0.5 h-4 w-4" /> : <AlertTriangle className="mt-0.5 h-4 w-4" />}
            <span>{notice.message}</span>
          </div>
        )}

        <div className="mb-6 rounded-xl border border-gray-800/70 bg-gray-950/25 p-4 light:border-gray-200 light:bg-gray-50">
          <div className="mb-4 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex min-w-0 items-start gap-3">
              <Gauge className="mt-1 h-5 w-5 shrink-0 text-emerald-300" />
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-gray-100 light:text-gray-900">Operating Cost Window</h3>
                <p className="mt-1 text-sm text-gray-400 light:text-gray-600">
                  {costWindow.label} · Geotab miles, AtoB fuel, QBO expenses, Entra-protected read-only projection
                </p>
              </div>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="flex rounded-lg border border-gray-700 bg-gray-900/70 p-1 light:border-gray-300 light:bg-white">
                {(['weekly', 'monthly'] as CostMode[]).map((item) => (
                  <button
                    key={item}
                    onClick={() => setCostMode(item)}
                    className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                      costMode === item
                        ? 'bg-emerald-500 text-gray-950'
                        : 'text-gray-400 hover:bg-gray-800 hover:text-white light:hover:bg-gray-100 light:hover:text-gray-900'
                    }`}
                  >
                    {item.charAt(0).toUpperCase() + item.slice(1)}
                  </button>
                ))}
              </div>
              {costMode === 'weekly' ? (
                <label className="flex flex-col gap-1 text-xs text-gray-400">
                  Week of
                  <input
                    type="date"
                    value={costWeekDate}
                    onChange={(event) => setCostWeekDate(toDateInputValue(startOfWeekMonday(parseDateInput(event.target.value))))}
                    className="rounded-lg border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white light:border-gray-300 light:bg-white light:text-gray-900"
                  />
                </label>
              ) : (
                <label className="flex flex-col gap-1 text-xs text-gray-400">
                  Month
                  <input
                    type="month"
                    value={costMonth}
                    onChange={(event) => setCostMonth(event.target.value)}
                    className="rounded-lg border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white light:border-gray-300 light:bg-white light:text-gray-900"
                  />
                </label>
              )}
              <button
                onClick={loadOperatingCost}
                disabled={costLoading}
                className={`${buttonBase} bg-emerald-600 text-white hover:bg-emerald-500`}
              >
                {costLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                Refresh
              </button>
            </div>
          </div>

          {costError && (
            <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
              {costError}
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <CostMetricCard
              accent="text-emerald-300 light:text-emerald-700"
              label="Known operating cost"
              value={costLoading ? 'Loading...' : formatCurrency(knownCost)}
              subtext="Fuel + QBO expense buckets + insurance allocation"
              windowLabel={costWindow.label}
            />
            <CostMetricCard
              accent="text-blue-300 light:text-blue-700"
              label="Known CPM"
              value={costLoading ? 'Loading...' : formatCpm(knownCpm)}
              subtext={`${formatNumber(operatingSummary?.miles)} miles`}
              windowLabel={costWindow.label}
            />
            <CostMetricCard
              accent="text-purple-300 light:text-purple-700"
              label="All-in K1L cost"
              value={costLoading ? 'Loading...' : formatCurrency(allInCost)}
              subtext={xceleratorReady ? 'Includes Xcelerator driver pay' : 'Driver pay pending in this window'}
              windowLabel={costWindow.label}
            />
            <CostMetricCard
              accent="text-amber-300 light:text-amber-700"
              label="All-in CPM"
              value={costLoading ? 'Loading...' : formatCpm(allInCpm)}
              subtext={allInUnresolvedSources.length ? `Pending: ${allInUnresolvedSources.join(', ')}` : 'All required cost sources resolved'}
              windowLabel={costWindow.label}
            />
            <CostMetricCard
              label="Fuel"
              value={costLoading ? 'Loading...' : formatCurrency(operatingSummary?.fuel_cost)}
              subtext={sourceStatusLabel(costSources.fuel)}
              windowLabel={costWindow.label}
            />
            <CostMetricCard
              label="Insurance"
              value={costLoading ? 'Loading...' : formatCurrency(operatingSummary?.insurance_cost)}
              subtext="$0.27/mi allocation when configured"
              windowLabel={costWindow.label}
            />
            <CostMetricCard
              label="Maintenance"
              value={costLoading ? 'Loading...' : formatCurrency(operatingSummary?.maintenance_cost)}
              subtext="QBO maintenance bucket"
              windowLabel={costWindow.label}
            />
            <CostMetricCard
              label="Rental / lease"
              value={costLoading ? 'Loading...' : formatCurrency(operatingSummary?.rental_trucks_trailers_cost)}
              subtext="QBO rental-truck/trailer bucket"
              windowLabel={costWindow.label}
            />
          </div>

          <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-gray-400 light:text-gray-600">
            <span className="rounded-full border border-gray-800 bg-gray-900/60 px-3 py-1 light:border-gray-200 light:bg-white">
              QBO: {sourceStatusLabel(costSources.qbo_expenses)}
            </span>
            <span className="rounded-full border border-gray-800 bg-gray-900/60 px-3 py-1 light:border-gray-200 light:bg-white">
              Fuel: {sourceStatusLabel(costSources.fuel)}
            </span>
            <span className="rounded-full border border-gray-800 bg-gray-900/60 px-3 py-1 light:border-gray-200 light:bg-white">
              Xcelerator: {sourceStatusLabel(entitySources.xcelerator_entity)}
            </span>
            <span className="rounded-full border border-gray-800 bg-gray-900/60 px-3 py-1 light:border-gray-200 light:bg-white">
              Period: {costWindow.start} to {costWindow.end}
            </span>
          </div>
        </div>

        {/* Period Selector */}
        <div className="flex flex-wrap gap-4 items-center mb-6">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-gray-400" />
            <span className="text-sm text-gray-400">Report Period:</span>
          </div>
          <div className="flex gap-2">
            {PERIODS.map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  period === p
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-800/50 text-gray-400 hover:bg-gray-700/50 hover:text-white'
                }`}
              >
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </button>
            ))}
          </div>
          <button
            onClick={generateReport}
            disabled={loading}
            className="ml-auto flex items-center gap-2 px-6 py-2 bg-gradient-to-r from-blue-500 to-purple-500 text-white rounded-lg font-medium hover:from-blue-600 hover:to-purple-600 disabled:opacity-50 transition-all"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <BarChart3 className="w-4 h-4" />}
            {loading ? 'Generating...' : 'Generate Report'}
          </button>
        </div>

        {/* Summary Cards */}
        {summary && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6"
          >
            <div className="bg-gray-800/30 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-blue-400">{summary.total_vehicles || 0}</div>
              <div className="text-xs text-gray-500 uppercase">Vehicles</div>
              <div className="mt-2 text-[11px] text-gray-500">Window: {reportWindowLabel}</div>
            </div>
            <div className="bg-gray-800/30 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-emerald-400">{summary.total_trips || 0}</div>
              <div className="text-xs text-gray-500 uppercase">Trips</div>
              <div className="mt-2 text-[11px] text-gray-500">Window: {reportWindowLabel}</div>
            </div>
            <div className="bg-gray-800/30 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-purple-400">{(summary.total_distance_mi || 0).toLocaleString(undefined, {maximumFractionDigits: 0})}</div>
              <div className="text-xs text-gray-500 uppercase">Miles</div>
              <div className="mt-2 text-[11px] text-gray-500">Window: {reportWindowLabel}</div>
            </div>
            <div className="bg-gray-800/30 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-amber-400">{summary.total_exceptions || 0}</div>
              <div className="text-xs text-gray-500 uppercase">Exceptions</div>
              <div className="mt-2 text-[11px] text-gray-500">Window: {reportWindowLabel}</div>
            </div>
            <div className="bg-gray-800/30 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-cyan-400">{summary.trailer_custody_inferred || 0}</div>
              <div className="text-xs text-gray-500 uppercase">Trailer Custody</div>
              <div className="mt-2 text-[11px] text-gray-500">Window: {reportWindowLabel}</div>
            </div>
          </motion.div>
        )}

        {/* Action Buttons */}
        {reportHtml && (
          <div className="grid gap-4 mb-6 xl:grid-cols-[1.1fr_1fr]">
            <div className="rounded-xl border border-gray-800/70 bg-gray-950/25 p-4 light:border-gray-200 light:bg-gray-50">
              <div className="mb-3 flex items-center gap-2">
                <Download className="h-4 w-4 text-blue-300" />
                <h3 className="text-sm font-semibold text-gray-100 light:text-gray-900">Export Report</h3>
              </div>
              <div className="flex flex-wrap gap-3">
                <button onClick={printReport} className={`${buttonBase} bg-gray-800/60 text-white hover:bg-gray-700/70`}>
                  <Printer className="w-4 h-4" />
                  PDF
                </button>
                <button onClick={downloadReport} className={`${buttonBase} bg-gray-800/60 text-white hover:bg-gray-700/70`}>
                  <Download className="w-4 h-4" />
                  HTML
                </button>
                <button onClick={downloadCsvReport} className={`${buttonBase} bg-gray-800/60 text-white hover:bg-gray-700/70`}>
                  <Table2 className="w-4 h-4" />
                  CSV
                </button>
                <button onClick={downloadJsonReport} className={`${buttonBase} bg-gray-800/60 text-white hover:bg-gray-700/70`}>
                  <FileJson className="w-4 h-4" />
                  JSON
                </button>
              </div>
            </div>

            <div className="rounded-xl border border-gray-800/70 bg-gray-950/25 p-4 light:border-gray-200 light:bg-gray-50">
              <div className="mb-3 flex items-center gap-2">
                <Mail className="h-4 w-4 text-cyan-300" />
                <h3 className="text-sm font-semibold text-gray-100 light:text-gray-900">Email Report</h3>
              </div>
              <div className="flex flex-col gap-3 sm:flex-row">
                <input
                  value={emailRecipients}
                  onChange={(event) => setEmailRecipients(event.target.value)}
                  placeholder="ops@company.com, finance@company.com"
                  className="min-w-0 flex-1 rounded-lg border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:border-blue-400 focus:outline-none light:border-gray-300 light:bg-white light:text-gray-900"
                />
                <button
                  onClick={emailReport}
                  disabled={emailSending}
                  className={`${buttonBase} bg-cyan-600 text-white hover:bg-cyan-500`}
                >
                  {emailSending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  Send
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="mb-6 rounded-xl border border-gray-800/70 bg-gray-950/25 p-4 light:border-gray-200 light:bg-gray-50">
          <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-purple-300" />
              <h3 className="text-sm font-semibold text-gray-100 light:text-gray-900">Scheduled Report</h3>
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-300 light:text-gray-700">
              <input
                type="checkbox"
                checked={scheduleEnabled}
                onChange={(event) => setScheduleEnabled(event.target.checked)}
                className="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500"
              />
              Enabled
            </label>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
            <label className="flex flex-col gap-1 text-xs text-gray-400">
              Frequency
              <select
                value={scheduleFrequency}
                onChange={(event) => setScheduleFrequency(event.target.value as ScheduleFrequency)}
                className="rounded-lg border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white light:border-gray-300 light:bg-white light:text-gray-900"
              >
                {FREQUENCIES.map((item) => (
                  <option key={item} value={item}>
                    {item.charAt(0).toUpperCase() + item.slice(1)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-gray-400">
              Report
              <select
                value={schedulePeriod}
                onChange={(event) => setSchedulePeriod(event.target.value as ReportPeriod)}
                className="rounded-lg border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white light:border-gray-300 light:bg-white light:text-gray-900"
              >
                {PERIODS.map((item) => (
                  <option key={item} value={item}>
                    {item.charAt(0).toUpperCase() + item.slice(1)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-gray-400">
              Time
              <input
                type="time"
                value={scheduleTime}
                onChange={(event) => setScheduleTime(event.target.value)}
                className="rounded-lg border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white light:border-gray-300 light:bg-white light:text-gray-900"
              />
            </label>
            {scheduleFrequency === 'weekly' && (
              <label className="flex flex-col gap-1 text-xs text-gray-400">
                Day
                <select
                  value={scheduleWeekday}
                  onChange={(event) => setScheduleWeekday(Number(event.target.value))}
                  className="rounded-lg border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white light:border-gray-300 light:bg-white light:text-gray-900"
                >
                  {WEEKDAYS.map((item, index) => (
                    <option key={item} value={index}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {scheduleFrequency === 'monthly' && (
              <label className="flex flex-col gap-1 text-xs text-gray-400">
                Day
                <input
                  type="number"
                  min={1}
                  max={31}
                  value={scheduleDayOfMonth}
                  onChange={(event) => setScheduleDayOfMonth(Number(event.target.value))}
                  className="rounded-lg border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white light:border-gray-300 light:bg-white light:text-gray-900"
                />
              </label>
            )}
            <label className="flex flex-col gap-1 text-xs text-gray-400 md:col-span-2 xl:col-span-2">
              Recipients
              <input
                value={scheduleRecipients}
                onChange={(event) => setScheduleRecipients(event.target.value)}
                placeholder="ops@company.com, finance@company.com"
                className="rounded-lg border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white placeholder:text-gray-500 light:border-gray-300 light:bg-white light:text-gray-900"
              />
            </label>
            <button
              onClick={saveSchedule}
              disabled={scheduleSaving}
              className={`${buttonBase} self-end bg-purple-600 text-white hover:bg-purple-500 xl:col-start-6`}
            >
              {scheduleSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save
            </button>
          </div>
        </div>

        {/* Report Preview */}
        {reportHtml && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white rounded-xl overflow-hidden shadow-2xl"
          >
            <iframe
              srcDoc={reportHtml}
              className="w-full border-0"
              style={{ height: '800px' }}
              title="Fleet Report Preview"
            />
          </motion.div>
        )}

        {!reportHtml && !loading && (
          <div className="text-center py-20 text-gray-500">
            <FileText className="w-16 h-16 mx-auto mb-4 opacity-30" />
            <p className="text-lg">Select a period and generate your fleet report</p>
            <p className="text-sm mt-2">Reports include trip data, safety exceptions, and fleet utilization metrics</p>
          </div>
        )}
      </motion.div>
    </div>
  )
}
