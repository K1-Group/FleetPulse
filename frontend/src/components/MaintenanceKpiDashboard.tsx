import { useMemo } from 'react'
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  Database,
  Gauge,
  HelpCircle,
  Info,
  ShieldAlert,
  TrendingUp,
  Truck,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { useMaintenanceIntelligence, useUrgentMaintenance } from '../hooks/useGeotab'

type Severity = 'critical' | 'high' | 'medium' | 'monitor' | 'neutral'

interface IntelligenceSummary {
  total_fault_rows?: number
  vehicles_with_faults?: number
  critical?: number
  high?: number
  medium?: number
  monitor?: number
}

interface IntelligenceDecision {
  vehicle_id: string
  vehicle_name: string
  urgency: 'critical' | 'high' | 'medium' | 'low'
  risk_score: number
  predicted_issue?: string
  recommended_action?: string
}

interface IntelligenceResponse {
  generated_at?: string
  period_days?: number
  source_authority?: string
  source_mode?: string
  feed_status?: string
  automation_mode?: string
  projection_mode?: string
  summary?: IntelligenceSummary
  decisions?: IntelligenceDecision[]
}

interface UrgentAlert {
  vehicle_id: string
  vehicle_name: string
  urgency: 'critical' | 'high' | 'medium' | 'low'
  active_fault_count?: number
  known_fault_count?: number
  unknown_fault_count?: number
  suppressed_fault_count?: number
}

const SEVERITY_LABEL: Record<Severity, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  monitor: 'Monitor',
  neutral: 'Neutral',
}

const SEVERITY_BADGE: Record<Severity, string> = {
  critical: 'border-red-400/40 bg-red-500/10 text-red-200',
  high: 'border-orange-400/40 bg-orange-500/10 text-orange-200',
  medium: 'border-amber-400/40 bg-amber-500/10 text-amber-200',
  monitor: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  neutral: 'border-gray-500/30 bg-gray-500/10 text-gray-200',
}

const urgencyToSeverity = (urgency: string | undefined): Severity => {
  switch (urgency) {
    case 'critical': return 'critical'
    case 'high': return 'high'
    case 'medium': return 'medium'
    case 'low': return 'monitor'
    default: return 'neutral'
  }
}

const formatCount = (value: number | undefined): string =>
  typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString() : '—'

const formatFeedStatus = (status?: string): { label: string; severity: Severity } => {
  const normalized = (status || '').toLowerCase()
  if (!normalized || normalized === 'ok' || normalized === 'healthy' || normalized === 'fresh') {
    return { label: 'Healthy', severity: 'monitor' }
  }
  if (normalized.includes('stale') || normalized.includes('degraded')) {
    return { label: status || 'Degraded', severity: 'medium' }
  }
  if (normalized.includes('error') || normalized.includes('down') || normalized.includes('fail')) {
    return { label: status || 'Error', severity: 'critical' }
  }
  return { label: status || 'Unknown', severity: 'neutral' }
}

const titleCase = (value: string): string =>
  value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (l) => l.toUpperCase())

interface KpiCardProps {
  label: string
  value: string
  description?: string
  icon: LucideIcon
  severity?: Severity
  hint?: string
}

const KpiCard = ({ label, value, description, icon: Icon, severity = 'neutral', hint }: KpiCardProps) => (
  <div className="flex h-full flex-col justify-between rounded-lg border border-gray-700/60 bg-gray-900/40 p-4">
    <div className="flex items-start justify-between gap-3">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-gray-400">
        <Icon className="h-4 w-4 text-gray-300" aria-hidden="true" />
        <span>{label}</span>
      </div>
      {severity !== 'neutral' && (
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${SEVERITY_BADGE[severity]}`}
        >
          {SEVERITY_LABEL[severity]}
        </span>
      )}
    </div>
    <p
      className="mt-3 text-2xl font-semibold text-white"
      style={{ fontVariantNumeric: 'tabular-nums lining-nums' }}
    >
      {value}
    </p>
    {description && <p className="mt-1 text-xs text-gray-400">{description}</p>}
    {hint && (
      <p className="mt-2 flex items-start gap-1 text-[11px] text-gray-500">
        <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
        <span>{hint}</span>
      </p>
    )}
  </div>
)

const SkeletonCard = () => (
  <div className="h-32 animate-pulse rounded-lg border border-gray-700/60 bg-gray-900/40" />
)

const ErrorBanner = ({ message }: { message: string }) => (
  <div className="flex items-start gap-2 rounded-lg border border-red-500/40 bg-red-950/20 p-3 text-sm text-red-200">
    <AlertOctagon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
    <span>{message}</span>
  </div>
)

const EmptyState = ({ message }: { message: string }) => (
  <div className="rounded-lg border border-dashed border-gray-700/60 bg-gray-900/30 p-4 text-sm text-gray-400">
    {message}
  </div>
)

export default function MaintenanceKpiDashboard() {
  const intelligence = useMaintenanceIntelligence()
  const urgent = useUrgentMaintenance()

  const data = intelligence.data as IntelligenceResponse | null
  const summary = data?.summary || {}
  const decisions = (data?.decisions || []) as IntelligenceDecision[]
  const urgentAlerts = (urgent.data || []) as UrgentAlert[]

  const feedStatus = useMemo(() => formatFeedStatus(data?.feed_status), [data?.feed_status])

  const topHighRiskUnits = useMemo(() => {
    return [...decisions]
      .filter((d) => d.urgency === 'critical' || d.urgency === 'high')
      .sort((a, b) => (b.risk_score ?? 0) - (a.risk_score ?? 0))
      .slice(0, 5)
  }, [decisions])

  const unmappedUnits = useMemo(
    () => urgentAlerts.filter((a) => (a.unknown_fault_count || 0) > 0),
    [urgentAlerts],
  )

  const unmappedDiagnosticCount = useMemo(
    () => unmappedUnits.reduce((sum, a) => sum + (a.unknown_fault_count || 0), 0),
    [unmappedUnits],
  )

  const urgentCount = urgentAlerts.length
  const loading = intelligence.loading || urgent.loading
  const generatedAt = data?.generated_at ? new Date(data.generated_at) : null

  const sourceAuthority = data?.source_authority ? titleCase(data.source_authority) : 'Geotab'
  const automationMode = data?.automation_mode || 'ai_recommends_human_executes'
  const projectionMode = data?.projection_mode || 'read_only_decision_support'
  const periodLabel = data?.period_days ? `Last ${data.period_days} days` : 'Configured window'

  const criticalCount = summary.critical ?? 0
  const highCount = summary.high ?? 0
  const mediumCount = summary.medium ?? 0
  const monitorCount = summary.monitor ?? 0

  const severityForOverall: Severity =
    criticalCount > 0 ? 'critical' : highCount > 0 ? 'high' : mediumCount > 0 ? 'medium' : 'monitor'

  return (
    <section
      aria-label="Maintenance KPI overview"
      className="rounded-xl border border-gray-700/60 bg-gray-900/30 p-5"
    >
      <header className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Wrench className="h-5 w-5 text-blue-300" aria-hidden="true" />
            <h2 className="text-lg font-semibold text-white">Maintenance KPI Overview</h2>
          </div>
          <p className="mt-1 max-w-3xl text-sm text-gray-400">
            Executive view of fleet maintenance risk. Counts and recommendations are derived from{' '}
            {sourceAuthority} fault telemetry; no writes are made back to source systems.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${SEVERITY_BADGE[feedStatus.severity]}`}>
            Feed: {feedStatus.label}
          </span>
          <span className="rounded-full border border-gray-600/40 bg-gray-800/60 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-gray-300">
            {periodLabel}
          </span>
          {generatedAt && (
            <span className="text-[11px] text-gray-500">
              Updated {generatedAt.toLocaleString()}
            </span>
          )}
        </div>
      </header>

      {intelligence.error && (
        <div className="mb-4">
          <ErrorBanner message={`Maintenance intelligence unavailable: ${intelligence.error}`} />
        </div>
      )}
      {urgent.error && !intelligence.error && (
        <div className="mb-4">
          <ErrorBanner message={`Urgent maintenance unavailable: ${urgent.error}`} />
        </div>
      )}

      {loading && !data ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard
            label="Feed Source"
            value={sourceAuthority}
            description={data?.source_mode ? titleCase(data.source_mode) : 'Source mode pending'}
            icon={Database}
            severity={feedStatus.severity}
            hint={`Status: ${feedStatus.label}`}
          />
          <KpiCard
            label="Fault Rows"
            value={formatCount(summary.total_fault_rows)}
            description="Diagnostic events scored in window"
            icon={Activity}
          />
          <KpiCard
            label="Vehicles With Faults"
            value={formatCount(summary.vehicles_with_faults)}
            description="Unique assets with at least one fault"
            icon={Truck}
          />
          <KpiCard
            label="Critical"
            value={formatCount(criticalCount)}
            description="Assets at execution priority"
            icon={AlertOctagon}
            severity={criticalCount > 0 ? 'critical' : 'neutral'}
          />
          <KpiCard
            label="High"
            value={formatCount(highCount)}
            description="Assets needing prompt review"
            icon={AlertTriangle}
            severity={highCount > 0 ? 'high' : 'neutral'}
          />
          <KpiCard
            label="Medium"
            value={formatCount(mediumCount)}
            description="Assets in scheduled-watch queue"
            icon={Gauge}
            severity={mediumCount > 0 ? 'medium' : 'neutral'}
          />
          <KpiCard
            label="Monitor"
            value={formatCount(monitorCount)}
            description="Assets within normal range"
            icon={CheckCircle2}
            severity={monitorCount > 0 ? 'monitor' : 'neutral'}
          />
          <KpiCard
            label="Urgent Units"
            value={formatCount(urgentCount)}
            description="On triage queue right now"
            icon={ShieldAlert}
            severity={urgentCount > 0 ? severityForOverall : 'neutral'}
          />
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 rounded-lg border border-gray-700/60 bg-gray-900/40 p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
              <TrendingUp className="h-4 w-4 text-blue-300" aria-hidden="true" />
              Top High-Risk Units
            </h3>
            <span className="text-[11px] text-gray-500">
              By scored risk · top {Math.min(5, topHighRiskUnits.length) || 0}
            </span>
          </div>
          {topHighRiskUnits.length === 0 ? (
            <EmptyState message="No critical or high-risk units in the current window." />
          ) : (
            <ol className="divide-y divide-gray-700/60">
              {topHighRiskUnits.map((unit, idx) => {
                const severity = urgencyToSeverity(unit.urgency)
                return (
                  <li
                    key={unit.vehicle_id}
                    className="flex flex-col gap-1 py-2 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="flex items-start gap-3">
                      <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-gray-600/50 bg-gray-800/70 text-[11px] font-semibold text-gray-300">
                        {idx + 1}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-white">{unit.vehicle_name}</p>
                        {unit.predicted_issue && (
                          <p className="truncate text-xs text-gray-400">{unit.predicted_issue}</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 sm:shrink-0">
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${SEVERITY_BADGE[severity]}`}
                      >
                        {SEVERITY_LABEL[severity]}
                      </span>
                      <span className="rounded border border-gray-700/70 bg-gray-800/70 px-2 py-0.5 text-[11px] font-mono text-gray-200">
                        Risk {unit.risk_score}
                      </span>
                    </div>
                  </li>
                )
              })}
            </ol>
          )}
        </div>

        <div className="space-y-4">
          <div className="rounded-lg border border-gray-700/60 bg-gray-900/40 p-4">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
                <HelpCircle className="h-4 w-4 text-amber-300" aria-hidden="true" />
                Unmapped Diagnostics
              </h3>
              {unmappedDiagnosticCount > 0 && (
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${SEVERITY_BADGE.medium}`}>
                  Mapping Needed
                </span>
              )}
            </div>
            {unmappedDiagnosticCount === 0 ? (
              <EmptyState message="All active diagnostics map to a known component." />
            ) : (
              <>
                <p className="text-sm text-gray-300">
                  <span
                    className="text-2xl font-semibold text-white"
                    style={{ fontVariantNumeric: 'tabular-nums lining-nums' }}
                  >
                    {formatCount(unmappedDiagnosticCount)}
                  </span>{' '}
                  unmapped diagnostic{unmappedDiagnosticCount === 1 ? '' : 's'} across{' '}
                  {unmappedUnits.length} unit{unmappedUnits.length === 1 ? '' : 's'}.
                </p>
                <p className="mt-1 text-xs text-gray-500">
                  Review and add component mappings to improve triage accuracy.
                </p>
              </>
            )}
          </div>

          <div className="rounded-lg border border-gray-700/60 bg-gray-900/40 p-4">
            <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-white">
              <Info className="h-4 w-4 text-cyan-300" aria-hidden="true" />
              Decision Mode
            </h3>
            <dl className="space-y-2 text-xs">
              <div>
                <dt className="uppercase tracking-wide text-gray-500">Automation</dt>
                <dd className="text-sm text-gray-200">{titleCase(automationMode)}</dd>
              </div>
              <div>
                <dt className="uppercase tracking-wide text-gray-500">Projection</dt>
                <dd className="text-sm text-gray-200">{titleCase(projectionMode)}</dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </section>
  )
}
