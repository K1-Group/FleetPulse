import { useMemo } from 'react'
import { motion } from 'framer-motion'
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  BadgeCheck,
  BarChart3,
  CheckCircle2,
  Circle,
  Clock3,
  DollarSign,
  Gauge,
  Hand,
  Map,
  MoveRight,
  PauseCircle,
  Route,
  Shield,
  Timer,
  Truck,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import type {
  DataConnectorSafetyResponse,
  DataConnectorVehicleKpiResponse,
  DashboardValidationItem,
  DashboardValidationResponse,
  DashboardValidationStatus,
  FleetOverview,
  VehicleSafetyScore,
} from '../types/fleet'

type KpiStatus = 'verified' | 'pending' | 'no-data' | 'stale' | 'error'
type KpiTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'
type KpiGroup = 'Fleet' | 'Operations' | 'Safety' | 'Service Levels' | 'Finance'
type KpiIcon =
  | 'activity'
  | 'alert-circle'
  | 'alert-triangle'
  | 'badge-check'
  | 'bar-chart-3'
  | 'check-circle'
  | 'circle'
  | 'clock-3'
  | 'dollar-sign'
  | 'gauge'
  | 'hand'
  | 'map'
  | 'move-right'
  | 'pause-circle'
  | 'route'
  | 'shield'
  | 'timer'
  | 'truck'
  | 'wrench'

type KpiCard = {
  id: string
  label: string
  value: string | number | null
  unit?: string
  status: KpiStatus
  stateLabel?: string
  tone?: KpiTone
  icon: KpiIcon
  source?: string
  updatedAt?: string
  delta?: string | number | null
  company?: 'K1L' | 'K1G' | null
  group: KpiGroup
  decimals?: number
}

interface Props {
  overview: FleetOverview | null
  loading: boolean
  safetyScores?: VehicleSafetyScore[] | null
  safetyLoading?: boolean
  safety7d?: DataConnectorSafetyResponse | null
  safety7dError?: string | null
  safety7dLoading?: boolean
  utilization7d?: DataConnectorVehicleKpiResponse | null
  utilization7dError?: string | null
  utilization7dLoading?: boolean
  validation?: DashboardValidationResponse | null
}

const KPI_GROUPS: KpiGroup[] = ['Fleet', 'Operations', 'Safety', 'Service Levels', 'Finance']

const iconMap: Record<KpiIcon, LucideIcon> = {
  activity: Activity,
  'alert-circle': AlertCircle,
  'alert-triangle': AlertTriangle,
  'badge-check': BadgeCheck,
  'bar-chart-3': BarChart3,
  'check-circle': CheckCircle2,
  circle: Circle,
  'clock-3': Clock3,
  'dollar-sign': DollarSign,
  gauge: Gauge,
  hand: Hand,
  map: Map,
  'move-right': MoveRight,
  'pause-circle': PauseCircle,
  route: Route,
  shield: Shield,
  timer: Timer,
  truck: Truck,
  wrench: Wrench,
}

const toneStyles: Record<KpiTone, string> = {
  neutral: 'text-slate-300 bg-slate-500/10 border-slate-400/15',
  info: 'text-sky-300 bg-sky-500/10 border-sky-400/20',
  success: 'text-emerald-300 bg-emerald-500/10 border-emerald-400/20',
  warning: 'text-amber-300 bg-amber-500/10 border-amber-400/20',
  danger: 'text-red-300 bg-red-500/10 border-red-400/20',
}

const accentStyles: Record<KpiTone, string> = {
  neutral: 'from-slate-400/60 to-slate-400/0',
  info: 'from-sky-400/80 to-sky-400/0',
  success: 'from-emerald-400/80 to-emerald-400/0',
  warning: 'from-amber-400/80 to-amber-400/0',
  danger: 'from-red-400/80 to-red-400/0',
}

const statusStyles: Record<KpiStatus, string> = {
  verified: 'border-emerald-400/25 bg-emerald-500/10 text-emerald-200 light:text-emerald-700',
  pending: 'border-amber-400/25 bg-amber-500/10 text-amber-200 light:text-amber-700',
  'no-data': 'border-slate-400/20 bg-slate-500/10 text-slate-300 light:text-slate-600',
  stale: 'border-amber-400/25 bg-amber-500/10 text-amber-200 light:text-amber-700',
  error: 'border-red-400/30 bg-red-500/10 text-red-200 light:text-red-700',
}

const statusLabels: Record<KpiStatus, string> = {
  verified: 'Verified',
  pending: 'Pending',
  'no-data': 'No Data',
  stale: 'Stale',
  error: 'Error',
}

const statusIcons: Record<KpiStatus, LucideIcon> = {
  verified: CheckCircle2,
  pending: Clock3,
  'no-data': Circle,
  stale: AlertTriangle,
  error: AlertCircle,
}

const metricValidationKeys: Record<string, string> = {
  active: 'active',
  avgDistance: 'avg_trip_distance_miles',
  avgDriverHrs: 'avg_trip_duration_hours',
  idle: 'idle',
  mileage24h: 'total_distance_miles',
  parked: 'parked',
  routes24h: 'total_trips_today',
  stops5m: 'total_stops_today',
  totalFleet: 'total_vehicles',
  trips12h: 'trips_meeting_target',
  under12h: 'trips_under_target',
}

const validationStateLabels: Partial<Record<DashboardValidationStatus, string>> = {
  failed: 'Error',
  pending_no_audit: 'No Audit',
  pending_no_data: 'No Data',
}

function validationItem(validation: DashboardValidationResponse | null | undefined, metricKey?: string) {
  if (!metricKey) return null
  return validation?.metrics?.[metricKey] || validation?.sections?.fleet_overview || null
}

function mapValidationStatus(
  item: DashboardValidationItem | null,
  hasValue: boolean,
  loading: boolean,
): KpiStatus {
  if (loading) return 'pending'
  if (!item) return hasValue ? 'verified' : 'no-data'
  if (item.status === 'verified') return hasValue ? 'verified' : 'no-data'
  if (item.status === 'failed') return 'error'
  if (item.status === 'stale') return hasValue ? 'stale' : 'no-data'
  if (item.status === 'pending_no_data' || item.status === 'pending_no_audit') return 'no-data'
  return hasValue ? 'pending' : 'pending'
}

function relativeTime(value?: string | null) {
  if (!value) return null
  const parsed = new Date(value).getTime()
  if (!Number.isFinite(parsed)) return null
  const diffSeconds = Math.max(0, Math.round((Date.now() - parsed) / 1000))
  if (diffSeconds < 60) return 'Updated now'
  const diffMinutes = Math.round(diffSeconds / 60)
  if (diffMinutes < 60) return `Updated ${diffMinutes}m ago`
  const diffHours = Math.round(diffMinutes / 60)
  if (diffHours < 24) return `Updated ${diffHours}h ago`
  const diffDays = Math.round(diffHours / 24)
  return `Updated ${diffDays}d ago`
}

function formatNumber(value: string | number | null, decimals = 0) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value
  if (!Number.isFinite(value)) return '—'
  return value.toLocaleString('en-US', {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  })
}

function formattedValue(card: KpiCard) {
  if (card.status === 'pending' && card.value === null) return 'Pending'
  if (card.status === 'error') return 'Error'
  if (card.status === 'no-data' && card.value === null) return '—'
  return formatNumber(card.value, card.decimals)
}

function footerText(card: KpiCard) {
  const source = card.source || 'Source pending'
  if (card.status === 'pending') return `${source} · Pending`
  if (card.status === 'no-data') return `${source} · ${card.stateLabel || 'No data'}`
  if (card.status === 'error') return `${source} · Diagnostic needed`
  if (card.delta !== null && card.delta !== undefined) return `${source} · ${card.delta}`
  return `${source} · ${relativeTime(card.updatedAt) || 'Updated'}`
}

function asNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : null
}

function overviewKpi(
  validation: DashboardValidationResponse | null | undefined,
  loading: boolean,
  overview: FleetOverview | null,
  config: Omit<KpiCard, 'status' | 'value' | 'updatedAt'> & {
    key: keyof FleetOverview
    metricId: keyof typeof metricValidationKeys
  },
): KpiCard {
  const item = validationItem(validation, metricValidationKeys[config.metricId])
  const value = asNumber(overview?.[config.key])
  const status = mapValidationStatus(item, value !== null, loading)
  return {
    ...config,
    value,
    status,
    stateLabel: item?.status ? validationStateLabels[item.status] : undefined,
    source: item?.source_authority || config.source,
    updatedAt: item?.checked_at || validation?.generated_at,
  }
}

function placeholderKpi(card: Omit<KpiCard, 'value'> & { value?: null }): KpiCard {
  return { value: null, ...card }
}

function utilizationStatus(
  data: DataConnectorVehicleKpiResponse | null | undefined,
  loading: boolean,
  error?: string | null,
): KpiStatus {
  if (loading) return 'pending'
  if (error) return 'error'
  if (!data) return 'no-data'
  if (data.feed_status === 'degraded' || data.feed_status === 'table_unavailable') return 'error'
  if (data.feed_status === 'empty') return 'no-data'
  return asNumber(data.summary?.utilization_pct) !== null ? 'verified' : 'no-data'
}

function dataConnectorSafetyStatus(
  data: DataConnectorSafetyResponse | null | undefined,
  loading: boolean,
  error?: string | null,
): KpiStatus {
  if (loading) return 'pending'
  if (error) return 'error'
  if (!data) return 'no-data'
  if (data.feed_status === 'degraded' || data.feed_status === 'table_unavailable') return 'error'
  if (data.feed_status === 'empty') return 'no-data'
  return asNumber(data.summary?.safety_rank_pct) !== null ? 'verified' : 'no-data'
}

function safetyTone(value: number | null): KpiTone {
  if (value === null) return 'neutral'
  if (value < 50) return 'danger'
  if (value < 75) return 'warning'
  return 'success'
}

function buildCards(
  overview: FleetOverview | null,
  loading: boolean,
  validation: DashboardValidationResponse | null | undefined,
  safety7d: DataConnectorSafetyResponse | null | undefined,
  safety7dLoading: boolean,
  safety7dError: string | null | undefined,
  utilization7d: DataConnectorVehicleKpiResponse | null | undefined,
  utilization7dLoading: boolean,
  utilization7dError?: string | null,
): KpiCard[] {
  const safetyValue = asNumber(safety7d?.summary?.safety_rank_pct)
  const safetyStatus = dataConnectorSafetyStatus(safety7d, safety7dLoading, safety7dError)
  const safetyPeriod = safety7d?.period_days || 7
  const safetyLatestDate = safety7d?.summary?.latest_date
  const utilization7dValue = asNumber(utilization7d?.summary?.utilization_pct)
  const utilization7dPeriod = utilization7d?.period_days || 7
  const utilization7dStatus = utilizationStatus(utilization7d, utilization7dLoading, utilization7dError)

  return [
    overviewKpi(validation, loading, overview, {
      group: 'Fleet',
      icon: 'truck',
      id: 'total-fleet',
      key: 'total_vehicles',
      label: 'Total Fleet',
      metricId: 'totalFleet',
      source: 'Geotab',
      tone: 'info',
    }),
    overviewKpi(validation, loading, overview, {
      group: 'Fleet',
      icon: 'activity',
      id: 'active',
      key: 'active',
      label: 'Active',
      metricId: 'active',
      source: 'Geotab',
      tone: 'success',
    }),
    overviewKpi(validation, loading, overview, {
      group: 'Fleet',
      icon: 'circle',
      id: 'parked',
      key: 'parked',
      label: 'Parked',
      metricId: 'parked',
      source: 'Geotab',
      tone: 'neutral',
    }),
    overviewKpi(validation, loading, overview, {
      group: 'Fleet',
      icon: 'pause-circle',
      id: 'idle',
      key: 'idle',
      label: 'Idle',
      metricId: 'idle',
      source: 'Geotab',
      tone: 'warning',
    }),
    placeholderKpi({
      group: 'Fleet',
      icon: 'alert-triangle',
      id: 'oos-vehicles',
      label: 'OOS Vehicles',
      source: 'Geotab diagnostics',
      stateLabel: 'No Data',
      status: 'no-data',
      tone: 'danger',
    }),
    placeholderKpi({
      group: 'Fleet',
      icon: 'wrench',
      id: 'downtime',
      label: 'Downtime',
      source: 'Maintenance feed',
      stateLabel: 'No Data',
      status: 'no-data',
      tone: 'warning',
    }),
    {
      group: 'Fleet',
      icon: 'gauge',
      id: 'utilization',
      label: 'Utilization 7d',
      source: utilization7d?.source_authority || 'Geotab Data Connector',
      stateLabel: utilization7dStatus === 'no-data' ? 'No Data' : undefined,
      status: utilization7dStatus,
      tone: 'info',
      unit: '%',
      value: utilization7dValue,
      decimals: 1,
      delta: `Previous ${utilization7dPeriod} days`,
    },
    overviewKpi(validation, loading, overview, {
      decimals: 1,
      group: 'Operations',
      icon: 'route',
      id: 'mileage-24h',
      key: 'total_distance_miles',
      label: 'Mileage 24h',
      metricId: 'mileage24h',
      source: 'Geotab trips',
      tone: 'info',
      unit: 'mi',
    }),
    overviewKpi(validation, loading, overview, {
      group: 'Operations',
      icon: 'map',
      id: 'routes-24h',
      key: 'total_trips_today',
      label: 'Routes 24h',
      metricId: 'routes24h',
      source: 'Geotab trips proxy',
      tone: 'info',
    }),
    overviewKpi(validation, loading, overview, {
      decimals: 1,
      group: 'Operations',
      icon: 'timer',
      id: 'avg-driver-hrs',
      key: 'avg_trip_duration_hours',
      label: 'Avg Driver Hrs',
      metricId: 'avgDriverHrs',
      source: 'Geotab trips',
      tone: 'info',
      unit: 'hrs',
    }),
    overviewKpi(validation, loading, overview, {
      decimals: 1,
      group: 'Operations',
      icon: 'move-right',
      id: 'avg-distance',
      key: 'avg_trip_distance_miles',
      label: 'Avg Distance',
      metricId: 'avgDistance',
      source: 'Geotab trips',
      tone: 'info',
      unit: 'mi',
    }),
    overviewKpi(validation, loading, overview, {
      group: 'Operations',
      icon: 'hand',
      id: 'stops-5m',
      key: 'total_stops_today',
      label: 'Stops >5m',
      metricId: 'stops5m',
      source: 'Geotab trips',
      tone: 'warning',
    }),
    overviewKpi(validation, loading, overview, {
      group: 'Operations',
      icon: 'check-circle',
      id: 'trips-12h',
      key: 'trips_meeting_target',
      label: 'Trips 12h+',
      metricId: 'trips12h',
      source: 'Geotab trips',
      tone: 'success',
    }),
    overviewKpi(validation, loading, overview, {
      group: 'Operations',
      icon: 'alert-circle',
      id: 'under-12h',
      key: 'trips_under_target',
      label: 'Under 12h',
      metricId: 'under12h',
      source: 'Geotab trips',
      tone: 'warning',
    }),
    {
      group: 'Safety',
      icon: 'shield',
      id: 'safety-percent',
      label: 'Safety %',
      source: safety7d?.source_authority || 'Geotab Data Connector',
      status: safetyStatus,
      stateLabel: safetyStatus === 'no-data' ? 'No Data' : undefined,
      tone: safetyTone(safetyValue),
      unit: '%',
      updatedAt: safetyLatestDate || validation?.generated_at,
      value: safetyValue,
      decimals: 1,
      delta: safetyLatestDate
        ? `Latest ${safetyLatestDate} · previous ${safetyPeriod} days`
        : safety7d?.message || `Previous ${safetyPeriod} days`,
    },
    placeholderKpi({
      group: 'Safety',
      icon: 'bar-chart-3',
      id: 'stability',
      label: 'Stability',
      source: 'Xcelerator/Fabric',
      status: 'pending',
      tone: 'neutral',
    }),
    placeholderKpi({
      group: 'Service Levels',
      icon: 'badge-check',
      id: 'maintenance-done-wtd',
      label: 'Maint. Done WTD',
      source: 'Geotab + SharePoint',
      status: 'pending',
      tone: 'success',
    }),
    placeholderKpi({
      company: 'K1L',
      group: 'Service Levels',
      icon: 'clock-3',
      id: 'otp-k1l',
      label: 'OTP K1L',
      source: 'Xcelerator',
      status: 'pending',
      tone: 'neutral',
      unit: '%',
    }),
    placeholderKpi({
      company: 'K1G',
      group: 'Service Levels',
      icon: 'clock-3',
      id: 'otp-k1g',
      label: 'OTP K1G',
      source: 'Xcelerator',
      status: 'pending',
      tone: 'neutral',
      unit: '%',
    }),
    placeholderKpi({
      company: 'K1L',
      group: 'Service Levels',
      icon: 'clock-3',
      id: 'otd-k1l',
      label: 'OTD K1L',
      source: 'Xcelerator',
      status: 'pending',
      tone: 'neutral',
      unit: '%',
    }),
    placeholderKpi({
      company: 'K1G',
      group: 'Service Levels',
      icon: 'clock-3',
      id: 'otd-k1g',
      label: 'OTD K1G',
      source: 'Xcelerator',
      status: 'pending',
      tone: 'neutral',
      unit: '%',
    }),
    placeholderKpi({
      company: 'K1L',
      group: 'Finance',
      icon: 'dollar-sign',
      id: 'gm-k1l',
      label: 'GM% K1L',
      source: 'QBO + Xcelerator',
      status: 'pending',
      tone: 'neutral',
      unit: '%',
    }),
    placeholderKpi({
      company: 'K1G',
      group: 'Finance',
      icon: 'dollar-sign',
      id: 'gm-k1g',
      label: 'GM% K1G',
      source: 'QBO + Xcelerator',
      status: 'pending',
      tone: 'neutral',
      unit: '%',
    }),
  ]
}

function ExecutiveKpiCard({ card, index }: { card: KpiCard; index: number }) {
  const Icon = iconMap[card.icon]
  const StatusIcon = statusIcons[card.status]
  const tone = card.tone || 'neutral'

  return (
    <motion.article
      aria-label={`${card.label}: ${formattedValue(card)} ${card.unit || ''}. ${card.stateLabel || statusLabels[card.status]}`}
      className="group relative min-h-[116px] overflow-hidden rounded-[18px] border border-white/10 bg-gray-900/70 p-3.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] backdrop-blur-sm transition duration-200 hover:-translate-y-0.5 hover:border-white/20 hover:bg-gray-900/80 light:border-gray-200 light:bg-white light:shadow-sm light:hover:border-gray-300"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.015, duration: 0.25 }}
    >
      <div className={`absolute inset-x-0 top-0 h-px bg-gradient-to-r ${accentStyles[tone]}`} />
      <div className="flex items-start justify-between gap-3">
        <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border ${toneStyles[tone]}`}>
          <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
        </div>
        <span className={`inline-flex max-w-[7.5rem] shrink-0 items-center gap-1 rounded-full border px-2 py-1 text-[10px] font-semibold leading-none ${statusStyles[card.status]}`}>
          <StatusIcon className="h-3 w-3" aria-hidden="true" />
          <span className="truncate">{card.stateLabel || statusLabels[card.status]}</span>
        </span>
      </div>

      <div className="mt-3 flex items-baseline gap-1.5" style={{ fontVariantNumeric: 'tabular-nums lining-nums' }}>
        <span className="min-w-0 truncate text-[1.62rem] font-semibold leading-none tracking-normal text-white light:text-gray-950">
          {formattedValue(card)}
        </span>
        {card.unit && card.status !== 'pending' && card.status !== 'error' && (
          <span className="text-xs font-medium text-gray-400 light:text-gray-500">{card.unit}</span>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between gap-2">
        <p className="truncate text-[12px] font-semibold leading-none text-gray-300 light:text-gray-700">
          {card.label}
        </p>
        {card.company && (
          <span className="rounded-md border border-white/10 px-1.5 py-0.5 text-[9px] font-bold text-gray-400 light:border-gray-200 light:text-gray-500">
            {card.company}
          </span>
        )}
      </div>

      <div className="mt-3 truncate border-t border-white/5 pt-2 text-[10.5px] text-gray-500 light:border-gray-100 light:text-gray-500" title={footerText(card)}>
        {footerText(card)}
      </div>
    </motion.article>
  )
}

export default function Dashboard({
  overview,
  loading,
  safetyScores,
  safetyLoading = false,
  safety7d,
  safety7dError,
  safety7dLoading = false,
  utilization7d,
  utilization7dError,
  utilization7dLoading = false,
  validation,
}: Props) {
  const cards = useMemo(
    () => buildCards(
      overview,
      loading,
      validation,
      safety7d,
      safety7dLoading,
      safety7dError,
      utilization7d,
      utilization7dLoading,
      utilization7dError,
    ),
    [loading, overview, safety7d, safety7dError, safety7dLoading, utilization7d, utilization7dError, utilization7dLoading, validation],
  )

  return (
    <div className="space-y-5">
      {KPI_GROUPS.map(group => {
        const groupCards = cards.filter(card => card.group === group)
        const verifiedCount = groupCards.filter(card => card.status === 'verified').length

        return (
          <section key={group} aria-label={`${group} KPI group`} className="space-y-2.5">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500 light:text-gray-500">
                {group}
              </h2>
              <span className="text-[11px] text-gray-600 light:text-gray-500" style={{ fontVariantNumeric: 'tabular-nums lining-nums' }}>
                {verifiedCount}/{groupCards.length} verified
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3 min-[520px]:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6">
              {groupCards.map((card, index) => (
                <ExecutiveKpiCard key={card.id} card={card} index={index} />
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
