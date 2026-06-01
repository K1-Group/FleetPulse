import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Clock3, Mail, MapPin, Mic, Route, Search, Timer, Truck } from 'lucide-react'
import { useAddressBenchmarks } from '../hooks/useGeotab'
import type { AddressBenchmarkPair, AddressBenchmarkResponse } from '../types/fleet'

const DEFAULT_DAYS = 180

type ScanParams = {
  pickup: string
  delivery: string
  route: string
  days: number
}

type AddressBenchmarkScanViewProps = {
  data: AddressBenchmarkResponse | null
  days: number
  delivery: string
  error: string | null
  loading: boolean
  onDaysChange: (days: number) => void
  onDeliveryChange: (delivery: string) => void
  onPickupChange: (pickup: string) => void
  onRunScan: () => void
  onRouteChange?: (route: string) => void
  pickup: string
  route?: string
}

function hashScanParams(): ScanParams {
  if (typeof window === 'undefined') return { pickup: '', delivery: '', route: '', days: DEFAULT_DAYS }
  const hash = window.location.hash || ''
  const queryStart = hash.indexOf('?')
  const params = new URLSearchParams(queryStart >= 0 ? hash.slice(queryStart + 1) : '')
  const days = Math.min(730, Math.max(1, Number(params.get('days')) || DEFAULT_DAYS))
  return {
    pickup: params.get('pickup') || '',
    delivery: params.get('delivery') || '',
    route: params.get('route') || '',
    days,
  }
}

function formatNumber(value: number | null | undefined, suffix = '', maximumFractionDigits = 1) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${value.toLocaleString(undefined, { maximumFractionDigits })}${suffix}`
}

function formatMoney(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
}

function shortDate(value: string | null | undefined) {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function sourceStatusLabel(status: string | undefined) {
  if (!status) return 'Pending'
  return status.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

function statusTone(status: string | undefined) {
  if (status === 'healthy' || status === 'matched') return 'border-emerald-400/25 bg-emerald-400/10 text-emerald-200 light:text-emerald-700'
  if (status === 'pending_config' || status === 'no_matching_evidence') return 'border-amber-400/25 bg-amber-400/10 text-amber-200 light:text-amber-700'
  return 'border-slate-400/20 bg-slate-500/10 text-slate-300 light:text-slate-600'
}

function bestDriver(pair: AddressBenchmarkPair) {
  return [...pair.driver_benchmarks]
    .filter(driver => typeof driver.avg_route_minutes === 'number')
    .sort((a, b) => Number(a.avg_route_minutes) - Number(b.avg_route_minutes))[0]
}

function ScanMetric({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint: string
}) {
  return (
    <div className="min-h-[86px] rounded-lg border border-white/10 bg-white/[0.045] p-3 light:border-gray-200 light:bg-gray-50">
      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 light:text-gray-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-white light:text-gray-950" style={{ fontVariantNumeric: 'tabular-nums lining-nums' }}>
        {value}
      </div>
      <div className="mt-1 truncate text-[11px] text-gray-500 light:text-gray-500" title={hint}>{hint}</div>
    </div>
  )
}

function PairRow({ pair }: { pair: AddressBenchmarkPair }) {
  const fastest = bestDriver(pair)
  const voice = pair.evidence.voice_recordings
  const emails = pair.evidence.emails

  return (
    <article className="rounded-lg border border-white/10 bg-white/[0.035] p-4 light:border-gray-200 light:bg-white">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Route className="h-4 w-4 text-sky-300 light:text-sky-700" aria-hidden="true" />
            <h3 className="truncate text-sm font-semibold text-white light:text-gray-950">
              {pair.pickup_address} to {pair.delivery_address}
            </h3>
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
            <span className="rounded-md border border-sky-400/20 bg-sky-400/10 px-2 py-1 text-sky-200 light:text-sky-700">
              {pair.measured_orders}/{pair.orders} measured
            </span>
            <span className="rounded-md border border-amber-400/20 bg-amber-400/10 px-2 py-1 text-amber-200 light:text-amber-700">
              {pair.stop_events_over_threshold} stops &gt;{pair.stop_threshold_minutes}m
            </span>
            {(pair.routes || []).slice(0, 3).map(route => (
              <span key={`${pair.address_pair_key}-${route}`} className="rounded-md border border-cyan-400/20 bg-cyan-400/10 px-2 py-1 text-cyan-200 light:text-cyan-700">
                {route}
              </span>
            ))}
            <span className={`rounded-md border px-2 py-1 ${statusTone(voice.status)}`}>
              {voice.match_count} voice
            </span>
            <span className={`rounded-md border px-2 py-1 ${statusTone(emails.status)}`}>
              {emails.match_count} email
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:w-[520px]">
          <ScanMetric label="Avg" value={formatNumber(pair.avg_route_minutes, 'm')} hint="Pickup to delivery" />
          <ScanMetric label="Best" value={formatNumber(pair.best_route_minutes, 'm')} hint={fastest?.driver_name || 'No driver proof'} />
          <ScanMetric label="Opportunity" value={formatNumber(pair.opportunity_minutes_vs_pair_average, 'm')} hint="Above lane average" />
          <ScanMetric label="Cost" value={formatMoney(pair.estimated_opportunity_cost_vs_pair_average)} hint="Configured hourly rate" />
        </div>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.25fr)_minmax(260px,0.75fr)]">
        <div className="overflow-hidden rounded-lg border border-white/10 light:border-gray-200">
          <div className="grid grid-cols-[minmax(90px,1fr)_92px_92px_92px] bg-white/[0.045] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-gray-500 light:bg-gray-50">
            <span>Driver</span>
            <span className="text-right">Avg</span>
            <span className="text-right">Var</span>
            <span className="text-right">Stops</span>
          </div>
          {pair.driver_benchmarks.slice(0, 4).map(driver => (
            <div key={`${driver.driver_id || driver.driver_name}-${driver.avg_route_minutes}`} className="grid grid-cols-[minmax(90px,1fr)_92px_92px_92px] border-t border-white/10 px-3 py-2 text-sm light:border-gray-200">
              <span className="truncate text-gray-200 light:text-gray-800" title={driver.coaching_direction}>{driver.driver_name}</span>
              <span className="text-right text-gray-300 light:text-gray-700">{formatNumber(driver.avg_route_minutes, 'm')}</span>
              <span className="text-right text-gray-300 light:text-gray-700">{formatNumber(driver.variance_vs_pair_average_minutes, 'm')}</span>
              <span className="text-right text-gray-300 light:text-gray-700">{driver.stop_events_over_threshold}</span>
            </div>
          ))}
        </div>

        <div className="space-y-2">
          {pair.recent_orders.slice(0, 3).map(order => (
            <div key={order.order_id} className="rounded-lg border border-white/10 bg-black/15 px-3 py-2 text-xs light:border-gray-200 light:bg-gray-50">
              <div className="flex items-center justify-between gap-3">
                <span className="truncate font-semibold text-gray-200 light:text-gray-800">{order.order_id}</span>
                <span className="text-gray-500">{shortDate(order.route_date)}</span>
              </div>
              <div className="mt-1 flex items-center justify-between gap-3 text-gray-500">
                <span className="truncate">{order.driver_name || order.driver_id || 'Unassigned'}</span>
                <span>{formatNumber(order.route_minutes, 'm')}</span>
              </div>
              {order.route && <div className="mt-1 truncate text-[11px] text-gray-500">Route {order.route}</div>}
            </div>
          ))}
        </div>
      </div>
    </article>
  )
}

export default function AddressBenchmarkScan() {
  const [pickup, setPickup] = useState(() => hashScanParams().pickup)
  const [delivery, setDelivery] = useState(() => hashScanParams().delivery)
  const [route, setRoute] = useState(() => hashScanParams().route)
  const [days, setDays] = useState(() => hashScanParams().days)
  const [filters, setFilters] = useState<ScanParams>(() => hashScanParams())
  const { data, loading, error, refresh } = useAddressBenchmarks(filters)

  const runScan = useCallback(() => {
    const nextFilters = { pickup: pickup.trim(), delivery: delivery.trim(), route: route.trim(), days }
    if (
      nextFilters.pickup === filters.pickup &&
      nextFilters.delivery === filters.delivery &&
      nextFilters.route === filters.route &&
      nextFilters.days === filters.days
    ) {
      refresh()
      return
    }
    setFilters(nextFilters)
  }, [days, delivery, filters.days, filters.delivery, filters.pickup, filters.route, pickup, refresh, route])

  useEffect(() => {
    const syncFromHash = () => {
      if (!window.location.hash.startsWith('#address-benchmarks')) return
      const nextFilters = hashScanParams()
      setPickup(nextFilters.pickup)
      setDelivery(nextFilters.delivery)
      setRoute(nextFilters.route)
      setDays(nextFilters.days)
      setFilters(nextFilters)
    }
    window.addEventListener('hashchange', syncFromHash)
    return () => window.removeEventListener('hashchange', syncFromHash)
  }, [])

  return (
    <AddressBenchmarkScanView
      data={data}
      days={days}
      delivery={delivery}
      error={error}
      loading={loading}
      onDaysChange={setDays}
      onDeliveryChange={setDelivery}
      onPickupChange={setPickup}
      onRunScan={runScan}
      onRouteChange={setRoute}
      pickup={pickup}
      route={route}
    />
  )
}

export function AddressBenchmarkScanView({
  data,
  days,
  delivery,
  error,
  loading,
  onDaysChange,
  onDeliveryChange,
  onPickupChange,
  onRunScan,
  onRouteChange = () => undefined,
  pickup,
  route = '',
}: AddressBenchmarkScanViewProps) {
  const topPair = data?.address_pairs?.[0]
  const xcelerator = data?.source_meta?.xcelerator || {}
  const evidenceSources = data?.evidence_sources
  const summary = data?.summary
  const thresholds = data?.thresholds
  const routeFilter = data?.filters?.route || route.trim()
  const authorityLabel = xcelerator.source_authority || data?.source_authority
  const durationBasis = xcelerator.duration_basis

  return (
    <section aria-busy={loading} className="relative overflow-hidden rounded-lg border border-white/10 bg-[linear-gradient(135deg,rgba(8,13,24,0.98),rgba(17,24,39,0.92)_54%,rgba(31,30,18,0.72))] p-5 shadow-[0_22px_60px_rgba(2,6,23,0.24)] light:border-gray-200 light:bg-white light:shadow-sm">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-emerald-300/70 via-sky-300/60 to-amber-300/60" />
      <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div className="min-w-0 max-w-3xl">
          <div className="flex flex-wrap items-center gap-3">
            <MapPin className="h-5 w-5 text-emerald-300 light:text-emerald-700" aria-hidden="true" />
            <h2 className="text-lg font-semibold text-white light:text-gray-950">
              {routeFilter ? 'Pickup Delivery Gap Watchlist' : 'Pickup Delivery History'}
            </h2>
            <span className="rounded-md border border-emerald-400/25 bg-emerald-400/10 px-2 py-1 text-[11px] font-semibold text-emerald-200 light:text-emerald-700">
              Read-only scan
            </span>
            {routeFilter && (
              <span className="rounded-md border border-cyan-400/25 bg-cyan-400/10 px-2 py-1 text-[11px] font-semibold text-cyan-200 light:text-cyan-700">
                Route {routeFilter}
              </span>
            )}
            <span className={`rounded-md border px-2 py-1 text-[11px] font-semibold ${statusTone(xcelerator.status)}`}>
              Xcelerator {sourceStatusLabel(xcelerator.status)}
            </span>
          </div>
          <p className="mt-2 text-xs leading-5 text-gray-500 light:text-gray-600">
            Xcelerator remains the authority for pickup, delivery, route, lifecycle timestamps, revenue, and driver pay; FleetPulse only renders this watchlist.
          </p>
          {(authorityLabel || durationBasis || xcelerator.message) && (
            <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-400 light:text-gray-600">
              {authorityLabel && (
                <span className="rounded-md border border-white/10 bg-black/15 px-2 py-1 light:border-gray-200 light:bg-gray-50">
                  {authorityLabel}
                </span>
              )}
              {durationBasis && (
                <span className="rounded-md border border-sky-400/20 bg-sky-400/10 px-2 py-1 text-sky-200 light:text-sky-700">
                  {durationBasis}
                </span>
              )}
              {xcelerator.message && (
                <span className="rounded-md border border-amber-400/20 bg-amber-400/10 px-2 py-1 text-amber-200 light:text-amber-700">
                  {xcelerator.message}
                </span>
              )}
            </div>
          )}
          <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-500">Route</span>
              <input
                value={route}
                onChange={event => onRouteChange(event.target.value)}
                className="h-10 w-full rounded-lg border border-white/10 bg-black/20 px-3 text-sm text-white outline-none transition focus:border-sky-400 light:border-gray-200 light:bg-white light:text-gray-950"
                placeholder="Any route"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-500">Pickup</span>
              <input
                value={pickup}
                onChange={event => onPickupChange(event.target.value)}
                className="h-10 w-full rounded-lg border border-white/10 bg-black/20 px-3 text-sm text-white outline-none transition focus:border-sky-400 light:border-gray-200 light:bg-white light:text-gray-950"
                placeholder="Any pickup"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-500">Delivery</span>
              <input
                value={delivery}
                onChange={event => onDeliveryChange(event.target.value)}
                className="h-10 w-full rounded-lg border border-white/10 bg-black/20 px-3 text-sm text-white outline-none transition focus:border-sky-400 light:border-gray-200 light:bg-white light:text-gray-950"
                placeholder="Any delivery"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-500">Days</span>
              <div className="flex gap-2">
                <input
                  type="number"
                  min={1}
                  max={730}
                  value={days}
                  onChange={event => onDaysChange(Math.min(730, Math.max(1, Number(event.target.value) || DEFAULT_DAYS)))}
                  className="h-10 min-w-0 flex-1 rounded-lg border border-white/10 bg-black/20 px-3 text-sm text-white outline-none transition focus:border-sky-400 light:border-gray-200 light:bg-white light:text-gray-950"
                />
                <button
                  type="button"
                  disabled={loading}
                  onClick={onRunScan}
                  className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-sky-500 text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-gray-600 disabled:text-gray-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300"
                  title="Run scan"
                  aria-label="Run scan"
                >
                  <Search className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </label>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:min-w-[640px]">
          <ScanMetric label="Pairs" value={formatNumber(summary?.address_pairs, '', 0)} hint={`${formatNumber(summary?.measured_orders, '', 0)} measured orders`} />
          <ScanMetric label="Drivers" value={formatNumber(summary?.drivers_compared, '', 0)} hint="Compared on same lanes" />
          <ScanMetric label="Minutes" value={formatNumber(summary?.opportunity_minutes_vs_pair_average, 'm')} hint="Above pair average" />
          <ScanMetric label="Evidence" value={formatNumber(summary?.evidence_matches, '', 0)} hint={`${evidenceSources?.voice_recordings || 0} voice · ${evidenceSources?.emails || 0} email`} />
        </div>
      </div>

      {error && (
        <div className="mt-5 flex items-start gap-3 rounded-lg border border-amber-400/25 bg-amber-400/10 p-3 text-sm text-amber-100 light:text-amber-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {!error && loading && (
        <div className="mt-5 grid gap-3 lg:grid-cols-2">
          {[0, 1].map(index => (
            <div key={index} className="h-44 animate-pulse rounded-lg border border-white/10 bg-white/[0.04] light:border-gray-200 light:bg-gray-50" />
          ))}
        </div>
      )}

      {!error && !loading && data && (
        <div className="mt-5 space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-lg border border-white/10 bg-black/15 p-3 light:border-gray-200 light:bg-gray-50">
              <div className="flex items-center gap-2 text-sm font-semibold text-white light:text-gray-950">
                <Timer className="h-4 w-4 text-sky-300 light:text-sky-700" aria-hidden="true" />
                {formatNumber(topPair?.avg_route_minutes, 'm')} top lane avg
              </div>
              <div className="mt-1 truncate text-xs text-gray-500" title={topPair ? `${topPair.pickup_address} to ${topPair.delivery_address}` : 'No measured pair'}>
                {topPair ? `${topPair.pickup_address} to ${topPair.delivery_address}` : 'No measured pair'}
              </div>
            </div>
            <div className="rounded-lg border border-white/10 bg-black/15 p-3 light:border-gray-200 light:bg-gray-50">
              <div className="flex items-center gap-2 text-sm font-semibold text-white light:text-gray-950">
                <Clock3 className="h-4 w-4 text-amber-300 light:text-amber-700" aria-hidden="true" />
                &gt;{thresholds?.stop_threshold_minutes ?? 60}m stop rule
              </div>
              <div className="mt-1 text-xs text-gray-500">Configured stop/dwell evidence only</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-black/15 p-3 light:border-gray-200 light:bg-gray-50">
              <div className="flex items-center gap-2 text-sm font-semibold text-white light:text-gray-950">
                <Mic className="h-4 w-4 text-emerald-300 light:text-emerald-700" aria-hidden="true" />
                {sourceStatusLabel(evidenceSources?.status)}
              </div>
              <div className="mt-1 flex items-center gap-3 text-xs text-gray-500">
                <span className="inline-flex items-center gap-1"><Mic className="h-3.5 w-3.5" />{evidenceSources?.voice_recordings ?? 0}</span>
                <span className="inline-flex items-center gap-1"><Mail className="h-3.5 w-3.5" />{evidenceSources?.emails ?? 0}</span>
              </div>
            </div>
          </div>

          {data.address_pairs.length ? (
            <div className="space-y-3">
              {data.address_pairs.slice(0, 5).map(pair => (
                <PairRow key={pair.address_pair_key} pair={pair} />
              ))}
            </div>
          ) : (
            <div className="flex min-h-[160px] items-center justify-center rounded-lg border border-dashed border-white/10 bg-white/[0.025] px-4 text-center text-sm text-gray-500 light:border-gray-200 light:bg-gray-50">
              <span>
                No measured Xcelerator pickup/delivery pairs returned for this filter window{routeFilter ? ` on route ${routeFilter}` : ''}.
              </span>
            </div>
          )}

          {data.recommendations.length > 0 && (
            <div className="grid gap-2 md:grid-cols-2">
              {data.recommendations.slice(0, 4).map(recommendation => (
                <div key={recommendation} className="flex items-start gap-2 rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs leading-5 text-gray-400 light:border-gray-200 light:bg-gray-50 light:text-gray-600">
                  <Truck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-300 light:text-sky-700" aria-hidden="true" />
                  <span>{recommendation}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
