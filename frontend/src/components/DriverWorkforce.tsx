import { useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { AlertTriangle, CheckCircle2, ChevronDown, Clock, Route, Search, Timer, Truck, Users } from 'lucide-react'
import type { DriverWorkforceResponse, DriverWorkforceStatus, DriverWorkforceWorkday } from '../types/fleet'
import ValidationBadge from './ValidationBadge'

interface Props {
  data: DriverWorkforceResponse | null
  loading: boolean
  onSelectVehicle?: (vehicleId: string | null) => void
}

const statusClass: Record<string, string> = {
  scheduled: 'border-blue-500/30 bg-blue-500/10 text-blue-300',
  working: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  near_limit: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  overdue: 'border-red-500/30 bg-red-500/10 text-red-300',
  late_start: 'border-orange-500/30 bg-orange-500/10 text-orange-300',
  complete: 'border-emerald-500/20 bg-emerald-500/5 text-emerald-200',
  active_without_ticket: 'border-purple-500/30 bg-purple-500/10 text-purple-300',
  ticket_no_activity: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  unmatched: 'border-gray-500/30 bg-gray-500/10 text-gray-300',
}

const statusOptions: Array<{ value: 'all' | DriverWorkforceStatus; label: string }> = [
  { value: 'all', label: 'All statuses' },
  { value: 'working', label: 'Working' },
  { value: 'near_limit', label: 'Near Limit' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'late_start', label: 'Late Start' },
  { value: 'scheduled', label: 'Scheduled' },
  { value: 'complete', label: 'Complete' },
  { value: 'active_without_ticket', label: 'Active Without Ticket' },
  { value: 'ticket_no_activity', label: 'Ticket No Activity' },
]

const kpiCards = [
  { key: 'scheduled_today', label: 'Scheduled Today', icon: Users, color: 'text-blue-300' },
  { key: 'working_now', label: 'Working Now', icon: Truck, color: 'text-emerald-300' },
  { key: 'late_start', label: 'Late Start', icon: AlertTriangle, color: 'text-orange-300' },
  { key: 'near_limit', label: 'Near Limit', icon: Timer, color: 'text-amber-300' },
  { key: 'overdue', label: 'Overdue', icon: AlertTriangle, color: 'text-red-300' },
  { key: 'avg_time_worked_minutes', label: 'Avg Time Worked', icon: Clock, color: 'text-cyan-300' },
  { key: 'active_without_ticket', label: 'Active No Ticket', icon: Route, color: 'text-purple-300' },
] as const

function formatMinutes(minutes: number | null | undefined) {
  if (minutes === null || minutes === undefined) return '--'
  const negative = minutes < 0
  const abs = Math.abs(Math.round(minutes))
  const hours = Math.floor(abs / 60)
  const mins = abs % 60
  const value = hours ? `${hours}h ${mins.toString().padStart(2, '0')}m` : `${mins}m`
  return negative ? `Overdue ${value}` : value
}

function formatTime(value: string | null | undefined) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--'
  return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

function routeWindow(row: DriverWorkforceWorkday) {
  return `${formatTime(row.planned_start)}-${formatTime(row.planned_finish)}`
}

function statusLabel(status: string) {
  return status
    .split('_')
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export default function DriverWorkforce({ data, loading, onSelectVehicle }: Props) {
  const [statusFilter, setStatusFilter] = useState<'all' | DriverWorkforceStatus>('all')
  const [locationFilter, setLocationFilter] = useState('all')
  const [searchTerm, setSearchTerm] = useState('')

  const locations = useMemo(() => {
    const values = new Set<string>()
    for (const row of data?.workdays || []) {
      if (row.pickup_location) values.add(row.pickup_location)
      if (row.delivery_location) values.add(row.delivery_location)
    }
    return [...values].sort()
  }, [data?.workdays])

  const rows = useMemo(() => {
    const term = searchTerm.trim().toLowerCase()
    return (data?.workdays || []).filter(row => {
      const matchesStatus = statusFilter === 'all' || row.status === statusFilter
      const matchesLocation =
        locationFilter === 'all' ||
        row.pickup_location === locationFilter ||
        row.delivery_location === locationFilter
      const text = [
        row.driver_name,
        row.vehicle_name,
        row.ticket_id,
        row.pickup_location,
        row.delivery_location,
      ].join(' ').toLowerCase()
      return matchesStatus && matchesLocation && (!term || text.includes(term))
    })
  }, [data?.workdays, locationFilter, searchTerm, statusFilter])

  const validationItem = data?.validation
    ? {
        blocked_by: data.validation.state || null,
        checked_at: data.generated_at,
        contract: {},
        key: 'driver_workforce',
        label: 'Driver Workforce Route Windows',
        message: data.validation.message,
        metrics: [],
        next_check: null,
        projection_mode: 'read_only' as const,
        required_config: [],
        row_count: data.validation.row_count,
        source_authority: data.source_authority,
        status: data.validation.status,
        verified: data.validation.status === 'verified',
      }
    : null

  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-gray-800 bg-gradient-to-br from-gray-900 to-gray-800 shadow-lg light:border-gray-200 light:from-white light:to-gray-50"
    >
      <div className="border-b border-gray-800/60 px-4 py-4 light:border-gray-200">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Route className="h-5 w-5 text-blue-300" />
              <h2 className="text-lg font-semibold text-white light:text-gray-900">
                Driver Workforce - Xcelerator Route Windows
              </h2>
              {validationItem && <ValidationBadge compact item={validationItem} />}
            </div>
            <p className="mt-1 text-sm text-gray-400 light:text-gray-600">
              Planned route windows from Xcelerator, actual driver activity from Geotab.
            </p>
          </div>
          <div className="text-xs text-gray-500 light:text-gray-600">
            Xcelerator tickets: {data?.source_freshness.xcelerator_tickets ? formatTime(data.source_freshness.xcelerator_tickets) : '--'} | Geotab: {data?.source_freshness.geotab ? formatTime(data.source_freshness.geotab) : '--'}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          {kpiCards.map(card => {
            const Icon = card.icon
            const raw = data?.kpis?.[card.key]
            const value = card.key === 'avg_time_worked_minutes' ? formatMinutes(raw as number | null) : String(raw ?? 0)
            return (
              <div
                key={card.key}
                className="min-h-24 rounded-lg border border-gray-800 bg-gray-950/40 p-3 light:border-gray-200 light:bg-white"
              >
                <div className="flex items-center justify-between">
                  <Icon className={`h-4 w-4 ${card.color}`} />
                  {loading && <span className="h-2 w-2 animate-pulse rounded-full bg-gray-500" />}
                </div>
                <div className="mt-3 font-mono text-2xl font-semibold tabular-nums text-white light:text-gray-900">
                  {loading ? '--' : value}
                </div>
                <div className="mt-1 text-xs text-gray-400 light:text-gray-600">{card.label}</div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="px-4 py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <h3 className="font-semibold text-white light:text-gray-900">Drivers Working Against Route Tickets</h3>
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
              <input
                value={searchTerm}
                onChange={event => setSearchTerm(event.target.value)}
                placeholder="Search driver, vehicle, ticket"
                className="w-full rounded-lg border border-gray-700 bg-gray-900 py-2 pl-9 pr-3 text-sm text-white outline-none transition-colors focus:border-blue-500 light:border-gray-300 light:bg-white light:text-gray-900"
              />
            </div>
            <div className="relative">
              <select
                value={statusFilter}
                onChange={event => setStatusFilter(event.target.value as 'all' | DriverWorkforceStatus)}
                className="w-full appearance-none rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 pr-8 text-sm text-white outline-none focus:border-blue-500 light:border-gray-300 light:bg-white light:text-gray-900"
              >
                {statusOptions.map(option => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
            </div>
            <div className="relative">
              <select
                value={locationFilter}
                onChange={event => setLocationFilter(event.target.value)}
                className="w-full appearance-none rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 pr-8 text-sm text-white outline-none focus:border-blue-500 light:border-gray-300 light:bg-white light:text-gray-900"
              >
                <option value="all">All locations</option>
                {locations.map(location => (
                  <option key={location} value={location}>{location}</option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
            </div>
          </div>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[1080px] text-sm">
            <thead className="bg-gray-950/50 text-xs uppercase tracking-wide text-gray-500 light:bg-gray-50 light:text-gray-600">
              <tr>
                <th className="px-3 py-3 text-left">Driver</th>
                <th className="px-3 py-3 text-left">Vehicle</th>
                <th className="px-3 py-3 text-left">Ticket</th>
                <th className="px-3 py-3 text-left">Route Window</th>
                <th className="px-3 py-3 text-right">Planned</th>
                <th className="px-3 py-3 text-left">Actual Start</th>
                <th className="px-3 py-3 text-right">Worked</th>
                <th className="px-3 py-3 text-right">Remaining</th>
                <th className="px-3 py-3 text-left">Last Activity</th>
                <th className="px-3 py-3 text-left">Pickup</th>
                <th className="px-3 py-3 text-left">Delivery</th>
                <th className="px-3 py-3 text-left">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60 light:divide-gray-200">
              {loading && (
                <tr>
                  <td colSpan={12} className="px-3 py-8 text-center text-gray-500">
                    Loading route-window workforce status...
                  </td>
                </tr>
              )}
              {!loading && rows.length === 0 && (
                <tr>
                  <td colSpan={12} className="px-3 py-8 text-center text-gray-500">
                    No driver route-window rows match the current filters.
                  </td>
                </tr>
              )}
              {!loading && rows.map(row => (
                <tr
                  key={`${row.ticket_id || row.vehicle_id}-${row.status}`}
                  onClick={() => onSelectVehicle?.(row.vehicle_id || null)}
                  className="cursor-pointer hover:bg-gray-800/40 light:hover:bg-gray-50"
                >
                  <td className="px-3 py-3 font-medium text-white light:text-gray-900">{row.driver_name || '--'}</td>
                  <td className="px-3 py-3 text-gray-300 light:text-gray-700">{row.vehicle_name || '--'}</td>
                  <td className="px-3 py-3 font-mono text-gray-300 light:text-gray-700">{row.ticket_id || '--'}</td>
                  <td className="px-3 py-3 font-mono tabular-nums text-gray-300 light:text-gray-700">{routeWindow(row)}</td>
                  <td className="px-3 py-3 text-right font-mono tabular-nums text-gray-300 light:text-gray-700">{row.planned_hours}h</td>
                  <td className="px-3 py-3 font-mono tabular-nums text-gray-300 light:text-gray-700">{formatTime(row.actual_start_time)}</td>
                  <td className="px-3 py-3 text-right font-mono tabular-nums text-gray-300 light:text-gray-700">{row.time_worked_display}</td>
                  <td className="px-3 py-3 text-right font-mono tabular-nums text-gray-300 light:text-gray-700">{row.remaining_display}</td>
                  <td className="px-3 py-3 font-mono tabular-nums text-gray-300 light:text-gray-700">{formatTime(row.actual_last_seen)}</td>
                  <td className="max-w-[180px] truncate px-3 py-3 text-gray-300 light:text-gray-700">{row.pickup_location || '--'}</td>
                  <td className="max-w-[180px] truncate px-3 py-3 text-gray-300 light:text-gray-700">{row.delivery_location || '--'}</td>
                  <td className="px-3 py-3">
                    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs ${statusClass[row.status] || statusClass.unmatched}`}>
                      {row.status === 'complete' ? <CheckCircle2 className="h-3 w-3" /> : <Clock className="h-3 w-3" />}
                      {row.status_label || statusLabel(row.status)}
                    </span>
                    {row.overlap_issue && (
                      <span className="ml-2 rounded-full bg-red-500/10 px-2 py-1 text-xs text-red-300">
                        Overlap
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {data?.insights?.length ? (
          <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {data.insights.slice(0, 6).map(insight => (
              <div key={insight} className="rounded-lg border border-purple-500/20 bg-purple-500/5 p-3 text-sm text-gray-300 light:text-gray-700">
                {insight}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </motion.div>
  )
}
