import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bell,
  Fuel,
  MapPin,
  Truck,
  type LucideIcon,
} from 'lucide-react'
import {
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  ComposedChart,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts'
import type { Alert, FleetOverview, FuelTrend, LocationStats, Vehicle } from '../types/fleet'

interface Props {
  loading?: boolean
  overview?: FleetOverview | null
  locations?: LocationStats[] | null
  vehicles?: Vehicle[] | null
  alerts?: Alert[] | null
  fuelTrends?: FuelTrend[] | null
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#f97316', '#6b7280']

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const sourceRow = payload[0]?.payload || {}
    const truckNumbers = Array.isArray(sourceRow.truckNumbers) ? sourceRow.truckNumbers : []
    const activeTruckNumbers = Array.isArray(sourceRow.activeTruckNumbers) ? sourceRow.activeTruckNumbers : []
    const listUnavailable = sourceRow.truckListUnavailable && Number(sourceRow.vehicles || 0) > 0

    return (
      <div className="max-w-[320px] bg-gray-900 dark:bg-gray-900 light:bg-white border border-gray-700 dark:border-gray-700 light:border-gray-300 rounded-lg p-3 shadow-xl">
        <p className="text-gray-300 dark:text-gray-300 light:text-gray-700 text-sm mb-2">{label}</p>
        {payload.map((entry: any, index: number) => (
          <p key={index} className="text-sm" style={{ color: entry.color }}>
            {entry.name}: {entry.value}
            {entry.name === 'Efficiency' && ' MPG'}
            {entry.name === 'Score' && '%'}
            {entry.name === 'Vehicles' && ' vehicles'}
            {entry.name === 'Alerts' && ' alerts'}
          </p>
        ))}
        {truckNumbers.length > 0 && (
          <div className="mt-3 border-t border-gray-700 pt-2">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">Truck numbers</p>
            <div className="max-h-36 overflow-y-auto text-xs leading-5 text-gray-200 light:text-gray-700">
              {truckNumbers.join(', ')}
            </div>
          </div>
        )}
        {activeTruckNumbers.length > 0 && (
          <div className="mt-2">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-emerald-300">Active truck numbers</p>
            <div className="max-h-24 overflow-y-auto text-xs leading-5 text-gray-200 light:text-gray-700">
              {activeTruckNumbers.join(', ')}
            </div>
          </div>
        )}
        {listUnavailable && (
          <p className="mt-3 border-t border-gray-700 pt-2 text-xs text-amber-300">
            Truck list unavailable from the live Geotab vehicle feed.
          </p>
        )}
      </div>
    )
  }
  return null
}

const chartVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { 
    opacity: 1, 
    y: 0,
    transition: {
      type: "spring" as const,
      stiffness: 300,
      damping: 30
    }
  }
}

type PanelTone = 'emerald' | 'sky' | 'amber' | 'red'

const panelToneStyles: Record<PanelTone, {
  icon: string
  accent: string
  badge: string
  stat: string
}> = {
  emerald: {
    icon: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-200 light:text-emerald-700',
    accent: 'from-emerald-400/70 via-emerald-300/20 to-transparent',
    badge: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-200 light:text-emerald-700',
    stat: 'text-emerald-200 light:text-emerald-700',
  },
  sky: {
    icon: 'border-sky-400/25 bg-sky-400/10 text-sky-200 light:text-sky-700',
    accent: 'from-sky-400/70 via-sky-300/20 to-transparent',
    badge: 'border-sky-400/25 bg-sky-400/10 text-sky-200 light:text-sky-700',
    stat: 'text-sky-200 light:text-sky-700',
  },
  amber: {
    icon: 'border-amber-400/25 bg-amber-400/10 text-amber-200 light:text-amber-700',
    accent: 'from-amber-400/70 via-amber-300/20 to-transparent',
    badge: 'border-amber-400/25 bg-amber-400/10 text-amber-200 light:text-amber-700',
    stat: 'text-amber-200 light:text-amber-700',
  },
  red: {
    icon: 'border-red-400/25 bg-red-400/10 text-red-200 light:text-red-700',
    accent: 'from-red-400/70 via-red-300/20 to-transparent',
    badge: 'border-red-400/25 bg-red-400/10 text-red-200 light:text-red-700',
    stat: 'text-red-200 light:text-red-700',
  },
}

function hubLabel(name: string) {
  return name
    .replace(/\s+(Yard|Terminal|Hub)$/i, '')
    .replace('Kansas City', 'KC')
    .replace('San Antonio', 'SA')
    .replace('Little Rock', 'LR')
    .replace('Fort Worth', 'FTW')
}

function shortDate(value: string) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function normalizeAlertType(value: string) {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function vehicleUnitLabel(vehicle: Vehicle) {
  return vehicle.name || vehicle.id || 'Unknown'
}

function unitLabels(vehicles: Vehicle[]) {
  return vehicles
    .map(vehicleUnitLabel)
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
}

function compactNumber(value: number | null | undefined, suffix = '') {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${suffix}`
}

function average(values: number[]) {
  if (!values.length) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function TrendMetric({
  icon: Icon,
  label,
  value,
  hint,
  tone = 'sky',
}: {
  icon: LucideIcon
  label: string
  value: string
  hint: string
  tone?: PanelTone
}) {
  const styles = panelToneStyles[tone]
  return (
    <div className="min-h-[96px] rounded-lg border border-white/10 bg-white/[0.045] p-3.5 light:border-gray-200 light:bg-gray-50">
      <div className="flex items-center justify-between gap-3">
        <span className={`flex h-8 w-8 items-center justify-center rounded-lg border ${styles.icon}`}>
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
        <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-600 light:text-gray-500">
          {label}
        </span>
      </div>
      <div className={`mt-3 text-2xl font-semibold leading-none ${styles.stat}`} style={{ fontVariantNumeric: 'tabular-nums lining-nums' }}>
        {value}
      </div>
      <div className="mt-2 truncate text-[11px] text-gray-500 light:text-gray-500" title={hint}>
        {hint}
      </div>
    </div>
  )
}

function ChartPanel({
  icon: Icon,
  title,
  badge,
  metric,
  subtitle,
  tone,
  children,
}: {
  icon: LucideIcon
  title: string
  badge: string
  metric?: string
  subtitle?: string
  tone: PanelTone
  children: ReactNode
}) {
  const styles = panelToneStyles[tone]
  return (
    <motion.section
      variants={chartVariants}
      initial="hidden"
      animate="visible"
      className="relative overflow-hidden rounded-lg border border-white/10 bg-[linear-gradient(150deg,rgba(15,23,42,0.94),rgba(17,24,39,0.78))] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_18px_44px_rgba(2,6,23,0.22)] transition duration-200 hover:-translate-y-0.5 hover:border-white/20 light:border-gray-200 light:bg-white light:shadow-sm"
    >
      <div className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${styles.accent}`} />
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border ${styles.icon}`}>
            <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-semibold text-white light:text-gray-950">{title}</h3>
              <span className={`rounded-md border px-2 py-1 text-[10px] font-semibold leading-none ${styles.badge}`}>
                {badge}
              </span>
            </div>
            {subtitle && (
              <p className="mt-1 truncate text-xs text-gray-500 light:text-gray-500" title={subtitle}>
                {subtitle}
              </p>
            )}
          </div>
        </div>
        {metric && (
          <div className={`shrink-0 text-right text-2xl font-semibold ${styles.stat}`} style={{ fontVariantNumeric: 'tabular-nums lining-nums' }}>
            {metric}
          </div>
        )}
      </div>
      {children}
    </motion.section>
  )
}

function EmptyChartState({ message }: { message: string }) {
  return (
    <div className="flex h-[240px] items-center justify-center rounded-lg border border-dashed border-white/10 bg-white/[0.025] px-4 text-center text-sm text-gray-500 light:border-gray-200 light:bg-gray-50 light:text-gray-500">
      <span className="max-w-sm">{message}</span>
    </div>
  )
}

export default function FleetAnalytics({
  loading = false,
  overview = null,
  locations = null,
  vehicles = null,
  alerts = null,
  fuelTrends = null,
}: Props) {
  const liveVehicles = vehicles || []
  const hubAssetData = (locations || []).map(location => ({
    location: hubLabel(location.name),
    vehicles: location.vehicle_count,
    active: location.active,
    truckNumbers: unitLabels(liveVehicles.filter(vehicle => vehicle.location_name === location.name)),
    activeTruckNumbers: unitLabels(liveVehicles.filter(vehicle => vehicle.location_name === location.name && vehicle.status === 'active')),
    truckListUnavailable: !vehicles,
  }))
  const fuelEfficiencyData = (fuelTrends || [])
    .map(row => {
      const miles = Number(row.miles || 0)
      const gallons = Number(row.gallons || 0)
      if (!row.date || miles <= 0 || gallons <= 0) return null
      return {
        date: shortDate(row.date),
        efficiency: Number((miles / gallons).toFixed(1)),
      }
    })
    .filter((row): row is { date: string; efficiency: number } => Boolean(row))

  const fleetStateData = overview
    ? [
        { state: 'Active', vehicles: overview.active, truckNumbers: unitLabels(liveVehicles.filter(vehicle => vehicle.status === 'active')), truckListUnavailable: !vehicles },
        { state: 'Idle', vehicles: overview.idle, truckNumbers: unitLabels(liveVehicles.filter(vehicle => vehicle.status === 'idle')), truckListUnavailable: !vehicles },
        { state: 'Parked', vehicles: overview.parked, truckNumbers: unitLabels(liveVehicles.filter(vehicle => vehicle.status === 'parked')), truckListUnavailable: !vehicles },
        { state: 'Offline', vehicles: overview.offline, truckNumbers: unitLabels(liveVehicles.filter(vehicle => vehicle.status === 'offline')), truckListUnavailable: !vehicles },
      ]
    : []

  const alertDistribution = Object.entries(
    (alerts || []).reduce<Record<string, number>>((acc, alert) => {
      const key = alert.alert_type || 'fleet_alert'
      acc[key] = (acc[key] || 0) + 1
      return acc
    }, {}),
  ).map(([name, value], index) => ({
    name: normalizeAlertType(name),
    value,
    color: COLORS[index % COLORS.length],
  }))

  const averageMpg = average(fuelEfficiencyData.map(row => row.efficiency))
  const highestHub = hubAssetData.reduce<typeof hubAssetData[number] | null>(
    (best, row) => (!best || row.vehicles > best.vehicles ? row : best),
    null,
  )
  const fleetTotal = overview?.total_vehicles || 0
  const activeShare = fleetTotal > 0 ? Math.round(((overview?.active || 0) / fleetTotal) * 100) : null
  const alertTotal = alertDistribution.reduce((sum, item) => sum + item.value, 0)

  if (loading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-gray-900 dark:bg-gray-900 light:bg-white rounded-xl p-6 border border-gray-800 dark:border-gray-800 light:border-gray-200">
            <div className="animate-pulse">
              <div className="h-4 bg-gray-700 dark:bg-gray-700 light:bg-gray-200 rounded w-1/3 mb-4" />
              <div className="h-48 bg-gray-700 dark:bg-gray-700 light:bg-gray-200 rounded" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <motion.section
        className="relative overflow-hidden rounded-lg border border-white/10 bg-[linear-gradient(135deg,rgba(8,13,24,0.98),rgba(17,24,39,0.92)_52%,rgba(35,27,12,0.68))] p-5 shadow-[0_22px_60px_rgba(2,6,23,0.24)] light:border-gray-200 light:bg-white light:shadow-sm"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-sky-400/70 via-emerald-300/60 to-amber-300/60" />
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-2xl">
            <div className="flex flex-wrap items-center gap-3">
              <BarChart3 className="h-5 w-5 text-sky-300 light:text-sky-700" aria-hidden="true" />
              <h2 className="text-lg font-semibold text-white light:text-gray-950">Fleet Analytics</h2>
              <span className="rounded-md border border-sky-400/25 bg-sky-400/10 px-2 py-1 text-[11px] font-semibold text-sky-200 light:text-sky-700">
                Trend command center
              </span>
            </div>
            <p className="mt-2 text-sm leading-6 text-gray-400 light:text-gray-600">
              Source-backed trends for fleet utilization, fuel efficiency, hub coverage, and alert concentration. Hover charts to see the truck numbers behind each view.
            </p>
          </div>
          <div className="grid min-w-0 grid-cols-2 gap-3 sm:grid-cols-4 xl:min-w-[620px]">
            <TrendMetric
              icon={Fuel}
              label="Avg MPG"
              value={compactNumber(averageMpg, ' MPG')}
              hint={`${fuelEfficiencyData.length} fuel trend points`}
              tone="emerald"
            />
            <TrendMetric
              icon={MapPin}
              label="Top Hub"
              value={highestHub ? highestHub.location : '—'}
              hint={highestHub ? `${highestHub.vehicles} vehicles · ${highestHub.active} active` : 'No hub data returned'}
              tone="sky"
            />
            <TrendMetric
              icon={Activity}
              label="Active Share"
              value={activeShare === null ? '—' : `${activeShare}%`}
              hint={fleetTotal ? `${overview?.active || 0} of ${fleetTotal} assets active` : 'No Geotab overview returned'}
              tone="amber"
            />
            <TrendMetric
              icon={Bell}
              label="Alerts"
              value={compactNumber(alertTotal)}
              hint={`${alertDistribution.length} alert types`}
              tone={alertTotal > 0 ? 'red' : 'emerald'}
            />
          </div>
        </div>
      </motion.section>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <ChartPanel
          icon={Fuel}
          title="Fuel Efficiency Trend"
          badge="Geotab + AtoB"
          metric={compactNumber(averageMpg, ' MPG')}
          subtitle="Calculated from source mileage and gallons only"
          tone="emerald"
        >
          {fuelEfficiencyData.length ? (
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={fuelEfficiencyData} margin={{ top: 8, right: 18, bottom: 0, left: -16 }}>
                <defs>
                  <linearGradient id="fuelEfficiencyGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.36} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.32} />
                <XAxis dataKey="date" stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Area
                  type="monotone"
                  dataKey="efficiency"
                  name="Efficiency"
                  stroke="#10b981"
                  strokeWidth={3}
                  fill="url(#fuelEfficiencyGradient)"
                  dot={{ fill: '#10b981', strokeWidth: 2, r: 3 }}
                  activeDot={{ r: 5, stroke: '#d1fae5', strokeWidth: 2 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChartState message="No source-backed fuel gallons and mileage returned for the trend window." />
          )}
        </ChartPanel>

        <ChartPanel
          icon={MapPin}
          title="Assets by Hub"
          badge="Geotab"
          metric={highestHub ? `${highestHub.vehicles}` : undefined}
          subtitle={highestHub ? `${highestHub.location} has the highest current asset concentration` : 'Hub asset coverage'}
          tone="sky"
        >
          {hubAssetData.length ? (
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={hubAssetData} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.32} />
                <XAxis dataKey="location" stroke="#94a3b8" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis stroke="#94a3b8" fontSize={12} allowDecimals={false} tickLine={false} axisLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Legend iconType="circle" wrapperStyle={{ color: '#cbd5e1', fontSize: 12 }} />
                <Bar dataKey="vehicles" name="Vehicles" radius={[5, 5, 0, 0]} barSize={34}>
                  {hubAssetData.map((entry, index) => (
                    <Cell
                      key={`hub-cell-${index}`}
                      fill={entry.vehicles > 0 ? '#38bdf8' : '#475569'}
                    />
                  ))}
                </Bar>
                <Line
                  type="monotone"
                  dataKey="active"
                  name="Active"
                  stroke="#10b981"
                  strokeWidth={3}
                  dot={{ fill: '#10b981', r: 4 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChartState message="No hub asset rows returned from the live location feed." />
          )}
        </ChartPanel>

        <ChartPanel
          icon={Truck}
          title="Fleet Utilization"
          badge="Geotab Live"
          metric={activeShare === null ? undefined : `${activeShare}%`}
          subtitle="Active, idle, parked, and offline fleet posture"
          tone="amber"
        >
          {fleetStateData.length ? (
            <>
              <div className="mb-3 grid grid-cols-4 gap-2">
                {fleetStateData.map((item, index) => (
                  <div key={item.state} className="rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2 light:border-gray-200 light:bg-gray-50">
                    <div className="flex items-center gap-2">
                      <span
                        className="h-2 w-2 rounded-full"
                        style={{ backgroundColor: ['#10b981', '#f59e0b', '#64748b', '#ef4444'][index] }}
                      />
                      <span className="truncate text-[11px] text-gray-500 light:text-gray-500">{item.state}</span>
                    </div>
                    <div className="mt-1 text-lg font-semibold text-white light:text-gray-950" style={{ fontVariantNumeric: 'tabular-nums lining-nums' }}>
                      {item.vehicles}
                    </div>
                  </div>
                ))}
              </div>
              <ResponsiveContainer width="100%" height={205}>
                <BarChart data={fleetStateData} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.32} />
                  <XAxis dataKey="state" stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="#94a3b8" fontSize={12} allowDecimals={false} tickLine={false} axisLine={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="vehicles" name="Vehicles" radius={[5, 5, 0, 0]} barSize={42}>
                    {fleetStateData.map((entry, index) => (
                      <Cell
                        key={`fleet-state-${entry.state}`}
                        fill={['#10b981', '#f59e0b', '#64748b', '#ef4444'][index]}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </>
          ) : (
            <EmptyChartState message="No live fleet state returned from Geotab overview." />
          )}
        </ChartPanel>

        <ChartPanel
          icon={AlertTriangle}
          title="Alert Distribution"
          badge="Last 7 Days"
          metric={compactNumber(alertTotal)}
          subtitle="Recent safety and operations signals from the alert feed"
          tone="red"
        >
          {alertDistribution.length ? (
            <div className="grid items-center gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie
                    data={alertDistribution}
                    cx="50%"
                    cy="50%"
                    outerRadius={92}
                    innerRadius={48}
                    paddingAngle={3}
                    dataKey="value"
                    nameKey="name"
                  >
                    {alertDistribution.map((entry, index) => (
                      <Cell key={`alert-cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-2">
                {alertDistribution.map(item => (
                  <div key={item.name} className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2 light:border-gray-200 light:bg-gray-50">
                    <div
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: item.color }}
                    />
                    <span className="min-w-0 flex-1 truncate text-sm text-gray-300 light:text-gray-700">{item.name}</span>
                    <span className="text-xs font-semibold text-gray-500 light:text-gray-500" style={{ fontVariantNumeric: 'tabular-nums lining-nums' }}>{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyChartState message="No recent Geotab alert rows returned for this window." />
          )}
        </ChartPanel>
      </div>
    </div>
  )
}
