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
  DeliveryCenterPerformanceSnapshot,
  EntityMarginSnapshot,
  FleetOverview,
  LaneStabilityPayload,
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
  entityMargin?: EntityMarginSnapshot | null
  entityMarginLoading?: boolean
  entityMarginError?: string | null
  deliveryPerformance?: DeliveryCenterPerformanceSnapshot | null
  deliveryPerformanceLoading?: boolean
  deliveryPerformanceError?: string | null
  laneStability?: LaneStabilityPayload | null
  laneStabilityLoading?: boolean
  laneStabilityError?: string | null
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
  stops60m: 'total_stops_today',
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

function asDisplayPercent(value: unknown): number | null {
  const numeric = asNumber(value)
  if (numeric === null) return null
  return Math.abs(numeric) <= 1 ? Number((numeric * 100).toFixed(1)) : Number(numeric.toFixed(1))
}

type SourceStatus = {
  status?: string
  source_authority?: string
  message?: string
  row_count?: number | null
}

function readableSourceStatus(status?: string | null) {
  if (!status) return null
  return status
    .split('_')
    .filter(Boolean)
    .map(part => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(' ')
}

function sourceStateLabel(source?: SourceStatus | null) {
  const label = readableSourceStatus(source?.status)
  if (!label) return undefined
  if (source?.status === 'healthy') return undefined
  if (source?.status === 'partial') return 'Partial'
  return label
}

function sourceKpiStatus(
  source: SourceStatus | null | undefined,
  hasValue: boolean,
  loading: boolean,
  error?: string | null,
): KpiStatus {
  if (loading) return 'pending'
  if (error) return 'error'
  if (!source) return hasValue ? 'verified' : 'no-data'
  if (source.status === 'unavailable') return 'error'
  if (source.status === 'partial') return hasValue ? 'stale' : 'no-data'
  if (source.status === 'healthy') return hasValue ? 'verified' : 'no-data'
  if (source.status === 'awaiting_feed' || source.status === 'not_configured') return 'no-data'
  return hasValue ? 'verified' : 'no-data'
}

function percentTone(value: number | null, target = 80): KpiTone {
  if (value === null) return 'neutral'
  if (value >= target) return 'success'
  if (value >= target - 10) return 'warning'
  return 'danger'
}

function sourceWithPeriod(source: string | undefined, start?: string, end?: string) {
  const label = source || 'Source pending'
  if (!start || !end) return label
  return `${label} · ${start} to ${end}`
}

function rowCountText(count: number | null | undefined, unit: string) {
  if (count === null || count === undefined) return null
  return `${Number(count).toLocaleString()} ${unit}`
}

function isK1Entity(rowEntity: string | null | undefined, entity: 'K1L' | 'K1G') {
  const normalized = String(rowEntity || '').toLowerCase()
  if (entity === 'K1L') return normalized.includes('k1 logistics')
  return normalized.includes('k1 group')
}

function ratio(numerator: number, denominator: number) {
  return denominator > 0 ? numerator / denominator : null
}

function aggregateDeliveryPerformance(
  snapshot: DeliveryCenterPerformanceSnapshot | null | undefined,
  entity: 'K1L' | 'K1G',
) {
  const rows = snapshot?.delivery_centers?.filter(row => isK1Entity(row.entity, entity)) || []
  const totals = rows.reduce(
    (acc, row) => {
      acc.orders += asNumber(row.orders) || 0
      acc.pickupMeasured += asNumber(row.pickup_measured_orders) || 0
      acc.pickupOnTime += asNumber(row.pickup_on_time_orders) || 0
      acc.pickupMissing += asNumber(row.pickup_missing_orders) || 0
      acc.deliveryMeasured += asNumber(row.delivery_measured_orders) || 0
      acc.deliveryOnTime += asNumber(row.delivery_on_time_orders) || 0
      acc.deliveryMissing += asNumber(row.delivery_missing_orders) || 0
      return acc
    },
    {
      orders: 0,
      pickupMeasured: 0,
      pickupOnTime: 0,
      pickupMissing: 0,
      deliveryMeasured: 0,
      deliveryOnTime: 0,
      deliveryMissing: 0,
    },
  )
  return {
    ...totals,
    centerCount: rows.length,
    pickupOnTimePct: asDisplayPercent(ratio(totals.pickupOnTime, totals.pickupMeasured)),
    deliveryOnTimePct: asDisplayPercent(ratio(totals.deliveryOnTime, totals.deliveryMeasured)),
  }
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
  entityMargin?: EntityMarginSnapshot | null,
  entityMarginLoading = false,
  entityMarginError?: string | null,
  deliveryPerformance?: DeliveryCenterPerformanceSnapshot | null,
  deliveryPerformanceLoading = false,
  deliveryPerformanceError?: string | null,
  laneStability?: LaneStabilityPayload | null,
  laneStabilityLoading = false,
  laneStabilityError?: string | null,
): KpiCard[] {
  const safetyValue = asNumber(safety7d?.summary?.safety_rank_pct)
  const safetyStatus = dataConnectorSafetyStatus(safety7d, safety7dLoading, safety7dError)
  const safetyPeriod = safety7d?.period_days || 7
  const safetyLatestDate = safety7d?.summary?.latest_date
  const safetyPeriodStart = safety7d?.summary?.period_start_date
  const safetyPeriodEnd = safety7d?.summary?.period_end_date
  const utilization7dValue = asNumber(utilization7d?.summary?.utilization_pct)
  const utilization7dPeriod = utilization7d?.period_days || 7
  const utilization7dStatus = utilizationStatus(utilization7d, utilization7dLoading, utilization7dError)
  const laneStabilityValue = asDisplayPercent(laneStability?.summary?.today_stable_cov_pct)
  const laneStabilityStatus: KpiStatus = laneStabilityLoading
    ? 'pending'
    : laneStabilityError
    ? 'error'
    : laneStabilityValue !== null && (laneStability?.rows?.length || 0) > 0
    ? 'verified'
    : 'no-data'
  const laneStabilityDelta = laneStability?.summary
    ? `${Number(laneStability.summary.critical_today || 0).toLocaleString()} critical lanes · ${asDisplayPercent(laneStability.summary.wow_delta_pp)?.toFixed(1) ?? '0.0'} pp WoW`
    : null
  const entitySource = entityMargin?.sources?.xcelerator_entity
  const fuelSource = entityMargin?.sources?.fuel
  const fuelHealthy = fuelSource?.status === 'healthy'
  const k1lMarginRaw = fuelHealthy
    ? entityMargin?.summary?.k1l_actual_gross_margin_pct_after_fuel
    : entityMargin?.summary?.k1l_actual_gross_margin_pct_before_fuel
  const k1lMarginValue = asDisplayPercent(k1lMarginRaw)
  const k1gMarginValue = asDisplayPercent(entityMargin?.summary?.k1g_actual_gross_margin_pct_before_overhead)
  const k1lMarginStatus = sourceKpiStatus(entitySource, k1lMarginValue !== null, entityMarginLoading, entityMarginError)
  const k1gMarginStatus = sourceKpiStatus(entitySource, k1gMarginValue !== null, entityMarginLoading, entityMarginError)
  const k1lMarginBasis = fuelHealthy ? 'after fuel' : 'before fuel'
  const k1lMarginDelta = rowCountText(entityMargin?.summary?.k1l_orders, 'orders')
  const k1gMarginDelta = rowCountText(entityMargin?.summary?.k1g_orders, 'orders')
  const k1lPerformance = aggregateDeliveryPerformance(deliveryPerformance, 'K1L')
  const k1gPerformance = aggregateDeliveryPerformance(deliveryPerformance, 'K1G')
  const deliverySource = deliveryPerformance?.source
  const deliveryStatus = (value: number | null) => sourceKpiStatus(
    deliverySource,
    value !== null,
    deliveryPerformanceLoading,
    deliveryPerformanceError,
  )
  const serviceDelta = (measured: number, missing: number) => (
    measured > 0
      ? `${measured.toLocaleString()} measured · ${missing.toLocaleString()} missing proof`
      : null
  )

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
      id: 'stops-60m',
      key: 'total_stops_today',
      label: 'Stops >60m',
      metricId: 'stops60m',
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
      delta: safetyPeriodStart && safetyPeriodEnd
        ? `Fleet daily avg ${safetyPeriodStart} to ${safetyPeriodEnd}`
        : safetyLatestDate
        ? `Fleet daily avg · latest ${safetyLatestDate} · previous ${safetyPeriod} days`
        : safety7d?.message || `Previous ${safetyPeriod} days`,
    },
    {
      group: 'Safety',
      icon: 'bar-chart-3',
      id: 'stability',
      label: 'Stability',
      source: laneStability?.source_authority || 'K1 Group LLC / Fabric lakehouse lane_stability_daily_kpi',
      status: laneStabilityStatus,
      stateLabel: laneStabilityStatus === 'no-data' ? 'No Data' : undefined,
      tone: percentTone(laneStabilityValue, 80),
      unit: '%',
      value: laneStabilityValue,
      decimals: 1,
      delta: laneStabilityDelta,
      updatedAt: laneStability?.generated_at,
    },
    placeholderKpi({
      group: 'Service Levels',
      icon: 'badge-check',
      id: 'maintenance-done-wtd',
      label: 'Maint. Done WTD',
      source: 'Geotab + SharePoint',
      status: 'pending',
      tone: 'success',
    }),
    {
      company: 'K1L',
      group: 'Service Levels',
      icon: 'clock-3',
      id: 'otp-k1l',
      label: 'OTP K1L',
      source: sourceWithPeriod(deliverySource?.source_authority || deliveryPerformance?.source_authority, deliveryPerformance?.period_start, deliveryPerformance?.period_end),
      status: deliveryStatus(k1lPerformance.pickupOnTimePct),
      stateLabel: sourceStateLabel(deliverySource),
      tone: percentTone(k1lPerformance.pickupOnTimePct, 95),
      unit: '%',
      value: k1lPerformance.pickupOnTimePct,
      decimals: 1,
      delta: serviceDelta(k1lPerformance.pickupMeasured, k1lPerformance.pickupMissing),
      updatedAt: deliveryPerformance?.generated_at,
    },
    {
      company: 'K1G',
      group: 'Service Levels',
      icon: 'clock-3',
      id: 'otp-k1g',
      label: 'OTP K1G',
      source: sourceWithPeriod(deliverySource?.source_authority || deliveryPerformance?.source_authority, deliveryPerformance?.period_start, deliveryPerformance?.period_end),
      status: deliveryStatus(k1gPerformance.pickupOnTimePct),
      stateLabel: sourceStateLabel(deliverySource),
      tone: percentTone(k1gPerformance.pickupOnTimePct, 95),
      unit: '%',
      value: k1gPerformance.pickupOnTimePct,
      decimals: 1,
      delta: serviceDelta(k1gPerformance.pickupMeasured, k1gPerformance.pickupMissing),
      updatedAt: deliveryPerformance?.generated_at,
    },
    {
      company: 'K1L',
      group: 'Service Levels',
      icon: 'clock-3',
      id: 'otd-k1l',
      label: 'OTD K1L',
      source: sourceWithPeriod(deliverySource?.source_authority || deliveryPerformance?.source_authority, deliveryPerformance?.period_start, deliveryPerformance?.period_end),
      status: deliveryStatus(k1lPerformance.deliveryOnTimePct),
      stateLabel: sourceStateLabel(deliverySource),
      tone: percentTone(k1lPerformance.deliveryOnTimePct, 95),
      unit: '%',
      value: k1lPerformance.deliveryOnTimePct,
      decimals: 1,
      delta: serviceDelta(k1lPerformance.deliveryMeasured, k1lPerformance.deliveryMissing),
      updatedAt: deliveryPerformance?.generated_at,
    },
    {
      company: 'K1G',
      group: 'Service Levels',
      icon: 'clock-3',
      id: 'otd-k1g',
      label: 'OTD K1G',
      source: sourceWithPeriod(deliverySource?.source_authority || deliveryPerformance?.source_authority, deliveryPerformance?.period_start, deliveryPerformance?.period_end),
      status: deliveryStatus(k1gPerformance.deliveryOnTimePct),
      stateLabel: sourceStateLabel(deliverySource),
      tone: percentTone(k1gPerformance.deliveryOnTimePct, 95),
      unit: '%',
      value: k1gPerformance.deliveryOnTimePct,
      decimals: 1,
      delta: serviceDelta(k1gPerformance.deliveryMeasured, k1gPerformance.deliveryMissing),
      updatedAt: deliveryPerformance?.generated_at,
    },
    {
      company: 'K1L',
      group: 'Finance',
      icon: 'dollar-sign',
      id: 'gm-k1l',
      label: 'GM% K1L',
      source: sourceWithPeriod(entitySource?.source_authority || entityMargin?.source_authority, entityMargin?.period_start, entityMargin?.period_end),
      status: k1lMarginStatus,
      stateLabel: sourceStateLabel(entitySource),
      tone: percentTone(k1lMarginValue, asDisplayPercent(entityMargin?.k1l_margin_target_pct) || 72),
      unit: '%',
      value: k1lMarginValue,
      decimals: 1,
      delta: k1lMarginDelta ? `${k1lMarginDelta} · ${k1lMarginBasis}` : k1lMarginBasis,
      updatedAt: entityMargin?.generated_at,
    },
    {
      company: 'K1G',
      group: 'Finance',
      icon: 'dollar-sign',
      id: 'gm-k1g',
      label: 'GM% K1G',
      source: sourceWithPeriod(entitySource?.source_authority || entityMargin?.source_authority, entityMargin?.period_start, entityMargin?.period_end),
      status: k1gMarginStatus,
      stateLabel: sourceStateLabel(entitySource),
      tone: percentTone(k1gMarginValue, asDisplayPercent(entityMargin?.k1g_margin_target_pct) || 20),
      unit: '%',
      value: k1gMarginValue,
      decimals: 1,
      delta: k1gMarginDelta ? `${k1gMarginDelta} · before overhead` : 'before overhead',
      updatedAt: entityMargin?.generated_at,
    },
  ]
}

function ExecutiveKpiCard({ card, index }: { card: KpiCard; index: number }) {
  const Icon = iconMap[card.icon]
  const StatusIcon = statusIcons[card.status]
  const tone = card.tone || 'neutral'

  return (
    <motion.article
      aria-label={`${card.label}: ${formattedValue(card)} ${card.unit || ''}. ${card.stateLabel || statusLabels[card.status]}`}
      className="group relative min-h-[124px] overflow-hidden rounded-lg border border-white/10 bg-[linear-gradient(145deg,rgba(15,23,42,0.94),rgba(17,24,39,0.74))] p-3.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_14px_34px_rgba(2,6,23,0.22)] backdrop-blur-sm transition duration-200 hover:-translate-y-0.5 hover:border-white/20 light:border-gray-200 light:bg-white light:shadow-sm light:hover:border-gray-300"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.015, duration: 0.25 }}
    >
      <div className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${accentStyles[tone]}`} />
      <div className="absolute right-[-42px] top-[-42px] h-24 w-24 rounded-full bg-white/[0.035] blur-2xl light:bg-gray-200/50" />
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

function numericCardValue(card: KpiCard | undefined): number | null {
  if (!card || typeof card.value !== 'number' || !Number.isFinite(card.value)) return null
  return card.value
}

function displayCardValue(card: KpiCard | undefined) {
  if (!card) return '—'
  const unit = card.unit && card.status !== 'pending' && card.status !== 'error' ? card.unit : ''
  return `${formattedValue(card)}${unit}`
}

function DashboardCommandSummary({ cards }: { cards: KpiCard[] }) {
  const totalFleet = cards.find(card => card.id === 'total-fleet')
  const active = cards.find(card => card.id === 'active')
  const idle = cards.find(card => card.id === 'idle')
  const parked = cards.find(card => card.id === 'parked')
  const utilization = cards.find(card => card.id === 'utilization')
  const safety = cards.find(card => card.id === 'safety-percent')
  const verifiedCount = cards.filter(card => card.status === 'verified').length
  const attentionCount = cards.filter(card => card.status === 'error' || card.status === 'stale' || card.status === 'pending').length
  const fleetTotal = numericCardValue(totalFleet) || 0
  const activeCount = numericCardValue(active) || 0
  const activePct = fleetTotal > 0 ? Math.round((activeCount / fleetTotal) * 100) : null
  const stateBars = [
    { label: 'Active', card: active, color: 'bg-emerald-400' },
    { label: 'Idle', card: idle, color: 'bg-amber-400' },
    { label: 'Parked', card: parked, color: 'bg-slate-400' },
  ].map(item => {
    const value = numericCardValue(item.card) || 0
    return {
      ...item,
      value,
      width: fleetTotal > 0 ? Math.max(4, Math.round((value / fleetTotal) * 100)) : 0,
    }
  })

  return (
    <motion.section
      aria-label="Fleet command summary"
      className="relative overflow-hidden rounded-lg border border-white/10 bg-[linear-gradient(135deg,rgba(8,13,24,0.98),rgba(17,24,39,0.92)_46%,rgba(12,38,45,0.76))] p-5 shadow-[0_22px_60px_rgba(2,6,23,0.28)] light:border-gray-200 light:bg-white light:shadow-sm"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
    >
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-sky-400/70 via-emerald-300/60 to-amber-300/60" />
      <div className="grid gap-5 xl:grid-cols-[1.15fr_1fr]">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-lg font-semibold text-white light:text-gray-950">Fleet Command View</h2>
            <span className="rounded-md border border-emerald-400/25 bg-emerald-400/10 px-2 py-1 text-[11px] font-semibold text-emerald-200 light:text-emerald-700">
              Read-only projection
            </span>
          </div>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-400 light:text-gray-600">
            Live operational posture from Geotab, Xcelerator-linked service metrics, and approved finance feeds. FleetPulse displays the consolidated view without becoming the source of truth.
          </p>

          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: 'Fleet assets', value: displayCardValue(totalFleet), hint: totalFleet?.stateLabel || statusLabels[totalFleet?.status || 'no-data'] },
              { label: 'Active share', value: activePct === null ? '—' : `${activePct}%`, hint: `${displayCardValue(active)} active` },
              { label: 'Utilization', value: displayCardValue(utilization), hint: utilization?.delta || utilization?.stateLabel || 'Previous 7 days' },
              { label: 'Safety', value: displayCardValue(safety), hint: safety?.delta || safety?.stateLabel || 'Geotab score' },
            ].map(item => (
              <div key={item.label} className="min-h-[88px] rounded-lg border border-white/10 bg-white/[0.045] p-3 light:border-gray-200 light:bg-gray-50">
                <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-gray-500 light:text-gray-500">{item.label}</div>
                <div className="mt-2 text-2xl font-semibold text-white light:text-gray-950" style={{ fontVariantNumeric: 'tabular-nums lining-nums' }}>{item.value}</div>
                <div className="mt-1 truncate text-[11px] text-gray-500 light:text-gray-500" title={String(item.hint)}>{item.hint}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-white/10 bg-black/20 p-4 light:border-gray-200 light:bg-white">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-white light:text-gray-950">Operational Mix</div>
              <div className="mt-1 text-xs text-gray-500 light:text-gray-500">{verifiedCount}/{cards.length} metrics verified · {attentionCount} need attention</div>
            </div>
            <div className="text-right text-2xl font-semibold text-white light:text-gray-950" style={{ fontVariantNumeric: 'tabular-nums lining-nums' }}>
              {fleetTotal || '—'}
            </div>
          </div>

          <div className="mt-5 space-y-3">
            {stateBars.map(item => (
              <div key={item.label}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="text-gray-400 light:text-gray-600">{item.label}</span>
                  <span className="font-medium text-gray-200 light:text-gray-700">{item.value.toLocaleString()}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-white/10 light:bg-gray-100">
                  <div className={`h-full rounded-full ${item.color}`} style={{ width: `${item.width}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </motion.section>
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
  entityMargin,
  entityMarginLoading = false,
  entityMarginError,
  deliveryPerformance,
  deliveryPerformanceLoading = false,
  deliveryPerformanceError,
  laneStability,
  laneStabilityLoading = false,
  laneStabilityError,
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
      entityMargin,
      entityMarginLoading,
      entityMarginError,
      deliveryPerformance,
      deliveryPerformanceLoading,
      deliveryPerformanceError,
      laneStability,
      laneStabilityLoading,
      laneStabilityError,
    ),
    [
      deliveryPerformance,
      deliveryPerformanceError,
      deliveryPerformanceLoading,
      entityMargin,
      entityMarginError,
      entityMarginLoading,
      laneStability,
      laneStabilityError,
      laneStabilityLoading,
      loading,
      overview,
      safety7d,
      safety7dError,
      safety7dLoading,
      utilization7d,
      utilization7dError,
      utilization7dLoading,
      validation,
    ],
  )

  return (
    <div className="space-y-5">
      <DashboardCommandSummary cards={cards} />

      {KPI_GROUPS.map(group => {
        const groupCards = cards.filter(card => card.group === group)
        const verifiedCount = groupCards.filter(card => card.status === 'verified').length
        const completion = groupCards.length ? Math.round((verifiedCount / groupCards.length) * 100) : 0

        return (
          <section key={group} aria-label={`${group} KPI group`} className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <span className="h-2 w-2 rounded-full bg-sky-400" />
                <h2 className="truncate text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500 light:text-gray-500">
                  {group}
                </h2>
              </div>
              <div className="flex min-w-[150px] items-center justify-end gap-2">
                <div className="hidden h-1.5 w-20 overflow-hidden rounded-full bg-white/10 light:bg-gray-100 sm:block">
                  <div className="h-full rounded-full bg-emerald-400" style={{ width: `${completion}%` }} />
                </div>
                <span className="text-[11px] text-gray-600 light:text-gray-500" style={{ fontVariantNumeric: 'tabular-nums lining-nums' }}>
                  {verifiedCount}/{groupCards.length} verified
                </span>
              </div>
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
