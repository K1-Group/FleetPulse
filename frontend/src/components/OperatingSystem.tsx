import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import {
  BarChart3,
  Building2,
  CheckCircle2,
  Network,
  ShieldCheck,
  Target,
  Users,
  Workflow,
} from 'lucide-react'
import {
  useOperatingSystemOrgChart,
  useOperatingSystemConfiguration,
  useOperatingSystemDepartmentScorecards,
  useOperatingSystemTaskKpiMatrix,
} from '../hooks/useGeotab'
import K1OperatingCostKpi from './K1OperatingCostKpi'
import ValidationBadge from './ValidationBadge'
import type {
  ControlTowerSeatKpiItem,
  ControlTowerStatus,
  DashboardValidationResponse,
  OperatingSystemConfigurationItem,
  OperatingSystemDepartmentScorecard,
  OperatingSystemSeatContract,
  OperatingSystemSourceBoundary,
} from '../types/fleet'

type ViewKey = 'chart' | 'scorecards' | 'matrix' | 'boundaries'

const views: Array<{ key: ViewKey; label: string; icon: typeof Network }> = [
  { key: 'chart', label: 'Org Chart', icon: Network },
  { key: 'scorecards', label: 'Scorecards', icon: BarChart3 },
  { key: 'matrix', label: 'Seat Matrix', icon: Target },
  { key: 'boundaries', label: 'Boundaries', icon: ShieldCheck },
]

const sectionStyles: Record<string, string> = {
  accountability: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-200',
  functional: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
}

const kpiStatusStyles: Record<ControlTowerStatus, string> = {
  healthy: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200 light:text-emerald-700',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-200 light:text-amber-700',
  critical: 'border-red-500/30 bg-red-500/10 text-red-200 light:text-red-700',
  awaiting_feed: 'border-gray-600/40 bg-gray-800/60 text-gray-300 light:border-gray-300 light:bg-gray-100 light:text-gray-700',
  unavailable: 'border-red-500/30 bg-red-500/10 text-red-200 light:text-red-700',
}

function Panel({ children, className = '' }: { children?: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-gray-700/50 bg-gray-900/70 p-4 shadow-lg shadow-black/10 light:bg-white light:border-gray-200 ${className}`}>
      {children}
    </div>
  )
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-dashed border-gray-700 p-5 text-center text-sm text-gray-400 light:border-gray-300 light:text-gray-600">
      {label}
    </div>
  )
}

function money(value: number | undefined) {
  if (value === undefined) return 'Awaiting contract'
  return value.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
}

function titleize(value: string) {
  return value.replace(/_/g, ' ')
}

function statusLabel(status: ControlTowerStatus) {
  if (status === 'healthy') return 'Live'
  if (status === 'warning') return 'Partial'
  if (status === 'critical') return 'Critical'
  if (status === 'unavailable') return 'Unavailable'
  return 'Awaiting feed'
}

function formatCoverage(value: number) {
  return `${Number(value || 0).toFixed(1)}%`
}

function SeatPill({ seat }: { seat: OperatingSystemSeatContract }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize ${sectionStyles[seat.seat_type]}`}>
      {seat.seat_type}
    </span>
  )
}

function MetricGrid({ targets }: { targets: Record<string, string> }) {
  const entries = Object.entries(targets)
  if (entries.length === 0) return <EmptyState label="No targets assigned." />
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
      {entries.map(([key, value]) => (
        <div key={key} className="rounded-lg border border-gray-700/40 bg-gray-950/40 p-3 light:bg-gray-50 light:border-gray-200">
          <p className="text-[11px] uppercase text-gray-500 light:text-gray-600">{titleize(key)}</p>
          <p className="mt-1 text-sm font-semibold text-white light:text-gray-900">{value}</p>
        </div>
      ))}
    </div>
  )
}

function KpiContractRow({ item }: { item: ControlTowerSeatKpiItem }) {
  return (
    <div className="rounded-lg border border-gray-700/40 bg-gray-950/35 p-3 light:border-gray-200 light:bg-gray-50">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-white light:text-gray-900">{item.label}</p>
          <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{item.target}</p>
        </div>
        <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium ${kpiStatusStyles[item.status]}`}>
          {statusLabel(item.status)}
        </span>
      </div>
      <p className="mt-2 text-xs text-gray-400 light:text-gray-600">{item.source_authority}</p>
      {item.blocker && (
        <p className="mt-1 text-xs text-amber-200 light:text-amber-700">{titleize(item.blocker)}</p>
      )}
      <p className="mt-2 text-xs text-gray-300 light:text-gray-700">{item.owner_action}</p>
    </div>
  )
}

function scorecardStatus(scorecard: OperatingSystemDepartmentScorecard): ControlTowerStatus {
  if (scorecard.kpis.some(item => item.status === 'critical')) return 'critical'
  return scorecard.kpi_summary.awaiting_feed || scorecard.kpi_summary.unavailable ? 'warning' : 'healthy'
}

function scorecardTopIssue(scorecard: OperatingSystemDepartmentScorecard) {
  return (
    scorecard.kpis.find(item => item.status === 'awaiting_feed' || item.status === 'unavailable')
    || scorecard.kpis.find(item => item.status === 'warning' || item.status === 'critical')
    || scorecard.kpis[0]
    || null
  )
}

function DepartmentScorecardCard({
  scorecard,
  selected,
  onSelect,
}: {
  scorecard: OperatingSystemDepartmentScorecard
  selected: boolean
  onSelect: () => void
}) {
  const covered = scorecard.kpi_summary.healthy + scorecard.kpi_summary.warning
  const missing = scorecard.kpi_summary.awaiting_feed + scorecard.kpi_summary.unavailable
  const status = scorecardStatus(scorecard)
  const topIssue = scorecardTopIssue(scorecard)

  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={`min-h-[236px] rounded-lg border p-4 text-left shadow-lg shadow-black/10 transition hover:-translate-y-0.5 hover:border-emerald-500/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950 light:shadow-sm ${
        selected
          ? 'border-emerald-500/50 bg-emerald-500/10 light:bg-emerald-50'
          : 'border-gray-700/50 bg-gray-900/70 light:border-gray-200 light:bg-white'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold text-white light:text-gray-900">{scorecard.department_label}</p>
          <p className="mt-1 line-clamp-2 text-xs text-gray-400 light:text-gray-600">{scorecard.manager_label}</p>
        </div>
        <span className={`shrink-0 rounded-full border px-3 py-1 text-xs font-medium ${kpiStatusStyles[status]}`}>
          {formatCoverage(scorecard.kpi_summary.coverage_pct)}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {scorecard.source_authorities.map(authority => (
          <span key={authority} className="rounded border border-gray-700/50 px-2 py-1 text-[10px] font-medium text-gray-300 light:border-gray-200 light:text-gray-700">
            {authority}
          </span>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3 border-y border-gray-800 py-3 light:border-gray-200">
        <div>
          <p className="text-[10px] uppercase text-gray-500 light:text-gray-600">Live</p>
          <p className="mt-1 text-xl font-bold text-emerald-200 light:text-emerald-700">{scorecard.kpi_summary.healthy}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase text-gray-500 light:text-gray-600">Partial</p>
          <p className="mt-1 text-xl font-bold text-amber-200 light:text-amber-700">{scorecard.kpi_summary.warning}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase text-gray-500 light:text-gray-600">Missing</p>
          <p className="mt-1 text-xl font-bold text-white light:text-gray-900">{missing}</p>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3 text-xs text-gray-400 light:text-gray-600">
        <span>{covered}/{scorecard.kpi_summary.total} KPI contracts covered</span>
        <span>{scorecard.managed_seats.length} seats</span>
      </div>

      <div className="mt-4">
        <p className="text-[10px] uppercase text-gray-500 light:text-gray-600">Top blocker / action</p>
        <p className="mt-1 line-clamp-3 text-xs leading-5 text-gray-300 light:text-gray-700">
          {topIssue?.blocker ? titleize(topIssue.blocker) : topIssue?.owner_action || 'All registered KPI contracts have source coverage.'}
        </p>
      </div>
    </button>
  )
}

function ScorecardDetailPanel({
  scorecard,
  onSelectSeat,
}: {
  scorecard: OperatingSystemDepartmentScorecard
  onSelectSeat: (seatId: string) => void
}) {
  const weights = Object.entries(scorecard.scorecard_weights)
  const status = scorecardStatus(scorecard)

  return (
    <Panel className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold text-white light:text-gray-900">{scorecard.department_label} Seat KPI Detail</h3>
            <span className={`rounded-full border px-3 py-1 text-xs font-medium ${kpiStatusStyles[status]}`}>
              {statusLabel(status)}
            </span>
          </div>
          <p className="mt-1 text-sm text-gray-400 light:text-gray-600">{scorecard.source_message}</p>
        </div>
        <span className="rounded-full border border-gray-700 px-3 py-1 text-xs text-gray-300 light:border-gray-300 light:text-gray-700">
          {scorecard.entity_scope}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1.2fr_0.8fr]">
        <div>
          <p className="mb-2 text-xs uppercase text-gray-500 light:text-gray-600">KPI Contracts</p>
          <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
            {scorecard.kpis.length ? (
              scorecard.kpis.map(item => <KpiContractRow key={`${scorecard.department_id}-${item.key}`} item={item} />)
            ) : (
              <EmptyState label="No KPI contracts are registered for this department yet." />
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <p className="mb-2 text-xs uppercase text-gray-500 light:text-gray-600">Managed Seats</p>
            <div className="flex flex-wrap gap-2">
              {scorecard.managed_seats.map(seat => (
                <button
                  key={seat.seat_id}
                  onClick={() => onSelectSeat(seat.seat_id)}
                  className="rounded-lg border border-gray-700/60 bg-gray-800/60 px-3 py-2 text-left text-xs text-gray-300 transition hover:border-emerald-500/50 hover:text-white light:border-gray-200 light:bg-gray-50 light:text-gray-700 light:hover:text-gray-900"
                >
                  {seat.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-xs uppercase text-gray-500 light:text-gray-600">Source Authorities</p>
            <div className="flex flex-wrap gap-2">
              {scorecard.source_authorities.map(authority => (
                <span key={authority} className="rounded-lg border border-gray-700/50 bg-gray-800/60 px-3 py-1 text-xs text-gray-300 light:bg-gray-50 light:border-gray-200 light:text-gray-700">
                  {authority}
                </span>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-xs uppercase text-gray-500 light:text-gray-600">Scorecard Weights</p>
            <div className="grid grid-cols-3 gap-2">
              {weights.map(([key, value]) => (
                <div key={key} className="rounded-lg border border-gray-700/40 bg-gray-950/35 p-2 light:border-gray-200 light:bg-gray-50">
                  <p className="text-[10px] uppercase text-gray-500 light:text-gray-600">{titleize(key)}</p>
                  <p className="mt-1 text-lg font-bold text-white light:text-gray-900">{value}%</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </Panel>
  )
}

function SeatDetail({ seat }: { seat: OperatingSystemSeatContract }) {
  return (
    <Panel className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold text-white light:text-gray-900">{seat.label}</h3>
            <SeatPill seat={seat} />
          </div>
          <p className="mt-1 text-sm text-gray-400 light:text-gray-600">{seat.primary_score}</p>
        </div>
        <span className="rounded-full border border-gray-700 px-3 py-1 text-xs text-gray-300 light:border-gray-300 light:text-gray-700">
          {seat.entity_scope}
        </span>
      </div>

      <MetricGrid targets={seat.targets} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-xs uppercase text-gray-500 light:text-gray-600">Daily Work</p>
          <div className="space-y-2">
            {seat.daily_work.map(item => (
              <div key={item} className="flex gap-2 text-sm text-gray-300 light:text-gray-700">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs uppercase text-gray-500 light:text-gray-600">Source Authorities</p>
          <div className="flex flex-wrap gap-2">
            {seat.source_authorities.map(authority => (
              <span key={authority} className="rounded-lg border border-gray-700/50 bg-gray-800/60 px-3 py-1 text-xs text-gray-300 light:bg-gray-50 light:border-gray-200 light:text-gray-700">
                {authority}
              </span>
            ))}
          </div>
          <p className="mb-2 mt-4 text-xs uppercase text-gray-500 light:text-gray-600">Access Bundle</p>
          <div className="flex flex-wrap gap-2">
            {seat.access_bundle.map(item => (
              <span key={item} className="rounded-lg border border-blue-500/25 bg-blue-500/10 px-3 py-1 text-xs text-blue-200 light:text-blue-700">
                {item}
              </span>
            ))}
          </div>
        </div>
      </div>
    </Panel>
  )
}

function BoundaryCard({ boundary }: { boundary: OperatingSystemSourceBoundary }) {
  return (
    <Panel>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-base font-semibold text-white light:text-gray-900">{boundary.system}</p>
          <p className="text-xs text-gray-500 light:text-gray-600">{boundary.entity}</p>
        </div>
        <ShieldCheck className="h-5 w-5 text-cyan-300" />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {boundary.authority.map(item => (
          <span key={item} className="rounded bg-gray-950/60 px-2 py-1 font-mono text-[11px] text-gray-300 light:bg-gray-100 light:text-gray-700">
            {item}
          </span>
        ))}
      </div>
      <p className="mt-3 text-sm text-gray-300 light:text-gray-700">{boundary.portal_rule}</p>
    </Panel>
  )
}

function ConfigCard({ item }: { item: OperatingSystemConfigurationItem }) {
  return (
    <div className="rounded-lg border border-gray-700/40 bg-gray-950/40 p-3 light:bg-gray-50 light:border-gray-200">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-white light:text-gray-900">{item.name}</p>
          <p className="text-xs text-gray-500 light:text-gray-600">{item.system}</p>
        </div>
        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
          item.configured
            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200 light:text-emerald-700'
            : 'border-amber-500/30 bg-amber-500/10 text-amber-200 light:text-amber-700'
        }`}>
          {item.configured ? 'Configured' : 'Missing'}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <span className="rounded bg-gray-900 px-2 py-1 font-mono text-[11px] text-gray-300 light:bg-gray-200 light:text-gray-700">
          {item.env_var}
        </span>
        {item.fallback_env_var && (
          <span className="rounded bg-gray-900 px-2 py-1 font-mono text-[11px] text-gray-300 light:bg-gray-200 light:text-gray-700">
            {item.fallback_env_var}
          </span>
        )}
      </div>
      <p className="mt-3 text-sm text-gray-300 light:text-gray-700">{item.purpose}</p>
    </div>
  )
}

interface Props {
  validation?: DashboardValidationResponse | null
}

export default function OperatingSystem({ validation }: Props) {
  const [active, setActive] = useState<ViewKey>('scorecards')
  const [selectedSeatId, setSelectedSeatId] = useState('executive_command')
  const [selectedScorecardId, setSelectedScorecardId] = useState('revenue_manager')
  const org = useOperatingSystemOrgChart()
  const matrix = useOperatingSystemTaskKpiMatrix()
  const scorecards = useOperatingSystemDepartmentScorecards()
  const config = useOperatingSystemConfiguration()

  const seatMap = useMemo(() => {
    const map = new Map<string, OperatingSystemSeatContract>()
    matrix.data?.seats.forEach(seat => map.set(seat.seat_id, seat))
    return map
  }, [matrix.data])

  const selectedSeat = seatMap.get(selectedSeatId) || matrix.data?.seats[0] || null
  const selectedScorecard = useMemo(
    () => (
      scorecards.data?.departments.find(scorecard => scorecard.department_id === selectedScorecardId)
      || scorecards.data?.departments[0]
      || null
    ),
    [scorecards.data, selectedScorecardId],
  )
  const managerSeats = matrix.data?.seats.filter(seat => seat.seat_type === 'accountability') || []
  const functionalSeats = matrix.data?.seats.filter(seat => seat.seat_type === 'functional') || []
  const operatingValidation = validation?.sections?.operating_system

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Workflow className="h-6 w-6 text-emerald-300" />
          <div>
            <h2 className="text-xl font-bold text-white light:text-gray-900">K1 Seat-Based Operating System</h2>
            <p className="text-sm text-gray-400 light:text-gray-600">Fixed-seat org contract, task matrix, and source-boundary controls</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-200 light:text-emerald-700">
            Projection mode: read-only
          </span>
          <ValidationBadge item={operatingValidation} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <K1OperatingCostKpi compact validation={validation?.sections?.k1l_final_cpm} />
        <Panel>
          <p className="text-xs uppercase text-gray-500 light:text-gray-600">Annual Target</p>
          <p className="mt-1 text-2xl font-bold text-white light:text-gray-900">{money(org.data?.targets.annual_target)}</p>
          <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{money(org.data?.targets.monthly_target)} monthly run rate</p>
        </Panel>
        <Panel>
          <p className="text-xs uppercase text-gray-500 light:text-gray-600">Fixed Seats</p>
          <p className="mt-1 text-2xl font-bold text-white light:text-gray-900">{org.data?.total_seats ?? '...'}</p>
          <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{org.data?.accountability_seats ?? 0} accountability, {org.data?.functional_seats ?? 0} functional</p>
        </Panel>
        <Panel>
          <p className="text-xs uppercase text-gray-500 light:text-gray-600">Gross Margin Target</p>
          <p className="mt-1 text-2xl font-bold text-white light:text-gray-900">{org.data?.targets.gross_margin_target_percent ?? 0}%</p>
          <p className="mt-1 text-xs text-gray-500 light:text-gray-600">Managed through Xcelerator finance controls</p>
        </Panel>
        <Panel>
          <p className="text-xs uppercase text-gray-500 light:text-gray-600">Source Deck</p>
          <p className="mt-1 truncate text-sm font-semibold text-white light:text-gray-900">{org.data?.source_document.name || 'Loading...'}</p>
          <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{org.data?.source_document.last_modified || 'Awaiting source'}</p>
        </Panel>
      </div>

      <nav className="flex flex-wrap gap-2 rounded-lg border border-gray-700/50 bg-gray-900/70 p-2 light:bg-white light:border-gray-200">
        {views.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActive(key)}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition ${
              active === key
                ? 'bg-emerald-500 text-white'
                : 'text-gray-400 hover:bg-gray-800 hover:text-white light:text-gray-600 light:hover:bg-gray-100 light:hover:text-gray-900'
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </nav>

      {active === 'chart' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          {org.loading ? (
            <EmptyState label="Loading seat org chart..." />
          ) : (
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
              {org.data?.management_tree.map(node => (
                <Panel key={node.manager_seat_id} className={node.manager_seat_id === 'executive_command' ? 'xl:col-span-3' : ''}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-base font-semibold text-white light:text-gray-900">{node.manager_label}</p>
                      <p className="text-xs text-gray-500 light:text-gray-600">{node.functional_seat_ids.length} managed seats</p>
                    </div>
                    <Users className="h-5 w-5 text-cyan-300" />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {node.functional_seats.map(seat => (
                      <button
                        key={seat.seat_id}
                        onClick={() => {
                          setSelectedSeatId(seat.seat_id)
                          setActive('matrix')
                        }}
                        className="rounded-lg border border-gray-700/60 bg-gray-800/60 px-3 py-2 text-left text-xs text-gray-300 transition hover:border-emerald-500/50 hover:text-white light:bg-gray-50 light:border-gray-200 light:text-gray-700 light:hover:text-gray-900"
                      >
                        {seat.label}
                      </button>
                    ))}
                  </div>
                </Panel>
              ))}
            </div>
          )}
        </motion.div>
      )}

      {active === 'scorecards' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          {scorecards.loading ? (
            <EmptyState label="Loading department scorecards..." />
          ) : scorecards.error ? (
            <EmptyState label={`Department scorecards unavailable: ${scorecards.error}`} />
          ) : (
            <>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
                {scorecards.data?.departments.map(scorecard => (
                  <DepartmentScorecardCard
                    key={scorecard.department_id}
                    scorecard={scorecard}
                    selected={selectedScorecard?.department_id === scorecard.department_id}
                    onSelect={() => setSelectedScorecardId(scorecard.department_id)}
                  />
                ))}
              </div>
              {selectedScorecard ? (
                <ScorecardDetailPanel
                  scorecard={selectedScorecard}
                  onSelectSeat={seatId => {
                    setSelectedSeatId(seatId)
                    setActive('matrix')
                  }}
                />
              ) : (
                <EmptyState label="No manager-seat KPI scorecards returned yet." />
              )}
            </>
          )}
        </motion.div>
      )}

      {active === 'matrix' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 gap-4 lg:grid-cols-4">
          <Panel className="lg:col-span-1">
            <div className="flex items-center gap-2">
              <Building2 className="h-5 w-5 text-emerald-300" />
              <h3 className="text-lg font-semibold text-white light:text-gray-900">Seats</h3>
            </div>
            <p className="mt-1 text-xs text-gray-500 light:text-gray-600">{managerSeats.length} accountability, {functionalSeats.length} functional</p>
            <div className="mt-4 max-h-[560px] space-y-1 overflow-y-auto pr-1">
              {matrix.loading ? (
                <EmptyState label="Loading seat matrix..." />
              ) : (
                matrix.data?.seats.map(seat => (
                  <button
                    key={seat.seat_id}
                    onClick={() => setSelectedSeatId(seat.seat_id)}
                    className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${
                      selectedSeat?.seat_id === seat.seat_id
                        ? 'bg-emerald-500 text-white'
                        : 'text-gray-400 hover:bg-gray-800 hover:text-white light:text-gray-600 light:hover:bg-gray-100 light:hover:text-gray-900'
                    }`}
                  >
                    <span className="block truncate font-medium">{seat.label}</span>
                    <span className="block truncate text-[11px] opacity-75">{seat.primary_score}</span>
                  </button>
                ))
              )}
            </div>
          </Panel>

          <div className="space-y-4 lg:col-span-3">
            {selectedSeat ? <SeatDetail seat={selectedSeat} /> : <EmptyState label="Select a seat to view its contract." />}
            <Panel>
              <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Scorecard Weights</h3>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                {Object.entries(matrix.data?.scorecard_weights || {}).map(([key, value]) => (
                  <div key={key} className="rounded-lg border border-gray-700/40 bg-gray-950/40 p-3 light:bg-gray-50 light:border-gray-200">
                    <p className="text-[11px] uppercase text-gray-500 light:text-gray-600">{titleize(key)}</p>
                    <p className="mt-1 text-2xl font-bold text-white light:text-gray-900">{value}%</p>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        </motion.div>
      )}

      {active === 'boundaries' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
            {org.data?.source_boundaries.map(boundary => (
              <BoundaryCard key={boundary.system} boundary={boundary} />
            ))}
          </div>

          <Panel>
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Employee Portal Build Contract</h3>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
              {org.data?.portal_workflow.map(step => (
                <div key={step.step} className="rounded-lg border border-gray-700/40 bg-gray-950/40 p-3 light:bg-gray-50 light:border-gray-200">
                  <p className="text-xs text-gray-500 light:text-gray-600">Step {step.step}</p>
                  <p className="mt-1 text-sm font-semibold text-white light:text-gray-900">{step.name}</p>
                  <p className="mt-2 text-xs text-gray-400 light:text-gray-600">{step.contract}</p>
                </div>
              ))}
            </div>
          </Panel>

          <Panel>
            <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <h3 className="text-lg font-semibold text-white light:text-gray-900">Runtime Configuration</h3>
              <span className="rounded-full border border-gray-700 px-3 py-1 text-xs text-gray-300 light:border-gray-300 light:text-gray-700">
                API key required: {config.data?.api_key_required ? 'yes' : 'no'}
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
              {config.data?.items.map(item => (
                <ConfigCard key={item.env_var} item={item} />
              ))}
            </div>
            <p className="mt-3 text-xs text-gray-500 light:text-gray-600">
              Secret values are never returned by this endpoint; only configured or missing state is shown.
            </p>
          </Panel>
        </motion.div>
      )}
    </div>
  )
}
