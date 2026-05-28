import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Clock3, ExternalLink, Mail, MapPin, Mic, Route, Search, Timer, Truck } from 'lucide-react'
import type { AddressBenchmarkEvidenceBucket, AddressBenchmarkPair, AddressBenchmarkResponse } from '../types/fleet'

const DEFAULT_DAYS = 180

type ScanParams = {
  pickup: string
  delivery: string
  days: number
}

function buildQuery(params: ScanParams) {
  const query = new URLSearchParams({ days: String(params.days) })
  if (params.pickup.trim()) query.set('pickup', params.pickup.trim())
  if (params.delivery.trim()) query.set('delivery', params.delivery.trim())
  return query.toString()
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

function EvidenceList({
  icon,
  label,
  bucket,
}: {
  icon: 'voice' | 'email'
  label: string
  bucket: AddressBenchmarkEvidenceBucket
}) {
  const Icon = icon === 'voice' ? Mic : Mail
  const matches = bucket.matches.slice(0, 2)

  return (
    <div className="rounded-lg border border-white/10 bg-black/15 p-3 light:border-gray-200 light:bg-gray-50">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-white light:text-gray-950">
          <Icon className="h-4 w-4 shrink-0 text-emerald-300 light:text-emerald-700" aria-hidden="true" />
          <span className="truncate">{label}</span>
        </div>
        <span className={`rounded-md border px-2 py-1 text-[11px] font-semibold ${statusTone(bucket.status)}`}>
          {bucket.match_count}
        </span>
      </div>

      {matches.length ? (
        <div className="mt-3 space-y-2">
          {matches.map((match, index) => {
            const headline = match.subject || match.summary || match.source_system || `${label} ${index + 1}`
            return (
              <div key={`${match.source_uri || match.order_id || headline}-${index}`} className="rounded-md border border-white/10 bg-white/[0.035] p-2 text-xs light:border-gray-200 light:bg-white">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate font-semibold text-gray-200 light:text-gray-800" title={headline}>
                      {headline}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-gray-500">
                      {match.source_system && <span>{match.source_system}</span>}
                      {match.order_id && <span>Order {match.order_id}</span>}
                      {match.transcript_available && <span>Transcript available</span>}
                    </div>
                  </div>
                  {match.source_uri && (
                    <a
                      href={match.source_uri}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-white/10 text-gray-400 transition hover:border-sky-300/40 hover:text-sky-200 light:border-gray-200 light:text-gray-500 light:hover:text-sky-700"
                      title="Open evidence"
                      aria-label="Open evidence"
                    >
                      <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                    </a>
                  )}
                </div>
                {match.summary && match.subject && (
                  <div className="mt-2 line-clamp-2 text-gray-500 light:text-gray-600">{match.summary}</div>
                )}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="mt-3 text-xs leading-5 text-gray-500">{bucket.message}</div>
      )}
    </div>
  )
}

function DriverActionNotes({ pair }: { pair: AddressBenchmarkPair }) {
  const drivers = pair.driver_benchmarks
    .filter(driver => driver.coaching_direction)
    .slice(0, 4)

  if (!drivers.length) return null

  return (
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {drivers.map(driver => (
        <div key={`${driver.driver_id || driver.driver_name}-action`} className="rounded-lg border border-white/10 bg-white/[0.035] p-3 text-xs light:border-gray-200 light:bg-gray-50">
          <div className="flex items-center justify-between gap-3">
            <span className="truncate font-semibold text-gray-200 light:text-gray-800">{driver.driver_name}</span>
            <span className="shrink-0 text-gray-500">{formatNumber(driver.variance_vs_pair_average_minutes, 'm')} vs avg</span>
          </div>
          <div className="mt-2 leading-5 text-gray-500 light:text-gray-600">{driver.coaching_direction}</div>
        </div>
      ))}
    </div>
  )
}

function LongStopEvidence({ pair }: { pair: AddressBenchmarkPair }) {
  const stops = (pair.long_stop_evidence || []).slice(0, 3)
  if (!stops.length) return null

  return (
    <div className="mt-3 rounded-lg border border-amber-400/20 bg-amber-400/10 p-3 light:bg-amber-50">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.1em] text-amber-200 light:text-amber-800">
        <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
        Stop locations &gt;{pair.stop_threshold_minutes}m
      </div>
      <div className="mt-2 grid gap-2 lg:grid-cols-3">
        {stops.map(stop => {
          const place = stop.stop_geofence || stop.stop_address || 'Location not available'
          return (
            <div key={`${stop.order_id}-${stop.route_date}`} className="rounded-md border border-amber-300/20 bg-black/15 p-2 text-xs light:border-amber-200 light:bg-white">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-semibold text-gray-200 light:text-gray-800" title={place}>
                  {place}
                </span>
                <span className="shrink-0 text-amber-200 light:text-amber-800">
                  {formatNumber(stop.stop_minutes, 'm')}
                </span>
              </div>
              {stop.stop_geofence && stop.stop_address && (
                <div className="mt-1 truncate text-gray-500 light:text-gray-600" title={stop.stop_address}>
                  {stop.stop_address}
                </div>
              )}
              <div className="mt-1 flex items-center justify-between gap-2 text-[11px] text-gray-500">
                <span className="truncate">{stop.driver_name || stop.driver_id || 'Unassigned'}</span>
                <span className="shrink-0">{shortDate(stop.route_date)}</span>
              </div>
            </div>
          )
        })}
      </div>
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
            </div>
          ))}
        </div>
      </div>

      <LongStopEvidence pair={pair} />

      <DriverActionNotes pair={pair} />

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EvidenceList icon="voice" label="Voice evidence" bucket={voice} />
        <EvidenceList icon="email" label="Email evidence" bucket={emails} />
      </div>
    </article>
  )
}

export default function AddressBenchmarkScan() {
  const [pickup, setPickup] = useState('')
  const [delivery, setDelivery] = useState('')
  const [days, setDays] = useState(DEFAULT_DAYS)
  const [data, setData] = useState<AddressBenchmarkResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadScan = useCallback(async (params: ScanParams) => {
    setLoading(true)
    try {
      const response = await fetch(`/api/address-benchmarks?${buildQuery(params)}`)
      const contentType = response.headers.get('content-type') || ''
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      if (!contentType.includes('application/json')) throw new Error('Address benchmark API is not deployed')
      setData(await response.json())
      setError(null)
    } catch (scanError: any) {
      setData(null)
      setError(scanError.message || 'Address benchmark scan failed')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadScan({ pickup: '', delivery: '', days: DEFAULT_DAYS })
  }, [loadScan])

  const runScan = useCallback(() => {
    loadScan({ pickup: pickup.trim(), delivery: delivery.trim(), days })
  }, [days, delivery, loadScan, pickup])

  const topPair = data?.address_pairs?.[0]
  const xcelerator = data?.source_meta?.xcelerator || {}

  return (
    <section className="relative overflow-hidden rounded-lg border border-white/10 bg-[linear-gradient(135deg,rgba(8,13,24,0.98),rgba(17,24,39,0.92)_54%,rgba(31,30,18,0.72))] p-5 shadow-[0_22px_60px_rgba(2,6,23,0.24)] light:border-gray-200 light:bg-white light:shadow-sm">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-emerald-300/70 via-sky-300/60 to-amber-300/60" />
      <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div className="min-w-0 max-w-3xl">
          <div className="flex flex-wrap items-center gap-3">
            <MapPin className="h-5 w-5 text-emerald-300 light:text-emerald-700" aria-hidden="true" />
            <h2 className="text-lg font-semibold text-white light:text-gray-950">Pickup Delivery History</h2>
            <span className="rounded-md border border-emerald-400/25 bg-emerald-400/10 px-2 py-1 text-[11px] font-semibold text-emerald-200 light:text-emerald-700">
              Read-only scan
            </span>
            <span className={`rounded-md border px-2 py-1 text-[11px] font-semibold ${statusTone(xcelerator.status)}`}>
              Xcelerator {sourceStatusLabel(xcelerator.status)}
            </span>
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-500">Pickup</span>
              <input
                value={pickup}
                onChange={event => setPickup(event.target.value)}
                className="h-10 w-full rounded-lg border border-white/10 bg-black/20 px-3 text-sm text-white outline-none transition focus:border-sky-400 light:border-gray-200 light:bg-white light:text-gray-950"
                placeholder="Any pickup"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-500">Delivery</span>
              <input
                value={delivery}
                onChange={event => setDelivery(event.target.value)}
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
                  onChange={event => setDays(Math.min(730, Math.max(1, Number(event.target.value) || DEFAULT_DAYS)))}
                  className="h-10 min-w-0 flex-1 rounded-lg border border-white/10 bg-black/20 px-3 text-sm text-white outline-none transition focus:border-sky-400 light:border-gray-200 light:bg-white light:text-gray-950"
                />
                <button
                  type="button"
                  onClick={runScan}
                  className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-sky-500 text-white transition hover:bg-sky-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300"
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
          <ScanMetric label="Pairs" value={formatNumber(data?.summary.address_pairs, '', 0)} hint={`${formatNumber(data?.summary.measured_orders, '', 0)} measured orders`} />
          <ScanMetric label="Drivers" value={formatNumber(data?.summary.drivers_compared, '', 0)} hint="Compared on same lanes" />
          <ScanMetric label="Minutes" value={formatNumber(data?.summary.opportunity_minutes_vs_pair_average, 'm')} hint="Above pair average" />
          <ScanMetric label="Evidence" value={formatNumber(data?.summary.evidence_matches, '', 0)} hint={`${data?.evidence_sources.voice_recordings || 0} voice · ${data?.evidence_sources.emails || 0} email`} />
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
                &gt;{data.thresholds.stop_threshold_minutes}m stop rule
              </div>
              <div className="mt-1 text-xs text-gray-500">Configured stop/dwell evidence only</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-black/15 p-3 light:border-gray-200 light:bg-gray-50">
              <div className="flex items-center gap-2 text-sm font-semibold text-white light:text-gray-950">
                <Mic className="h-4 w-4 text-emerald-300 light:text-emerald-700" aria-hidden="true" />
                {sourceStatusLabel(data.evidence_sources.status)}
              </div>
              <div className="mt-1 flex items-center gap-3 text-xs text-gray-500">
                <span className="inline-flex items-center gap-1"><Mic className="h-3.5 w-3.5" />{data.evidence_sources.voice_recordings}</span>
                <span className="inline-flex items-center gap-1"><Mail className="h-3.5 w-3.5" />{data.evidence_sources.emails}</span>
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
              <span>No measured pickup/delivery pairs returned for this filter window.</span>
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
