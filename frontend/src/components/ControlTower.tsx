import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock,
  Code2,
  DollarSign,
  MapPin,
  RadioTower,
  Truck,
} from 'lucide-react'
import {
  useControlTowerAgents,
  useControlTowerAttention,
  useControlTowerCodex,
  useControlTowerFinancial,
  useControlTowerOverview,
  useControlTowerTrailers,
} from '../hooks/useGeotab'
import type {
  ControlTowerFeedStatus,
  ControlTowerSectionSummary,
  ControlTowerStatus,
} from '../types/fleet'

type SectionKey = 'attention' | 'trailers' | 'financial' | 'agents' | 'codex'

const sections: Array<{ key: SectionKey; label: string; icon: typeof AlertTriangle }> = [
  { key: 'attention', label: 'Attention', icon: AlertTriangle },
  { key: 'trailers', label: 'Trailers', icon: Truck },
  { key: 'financial', label: 'Financial', icon: DollarSign },
  { key: 'agents', label: 'Agents', icon: Bot },
  { key: 'codex', label: 'Codex', icon: Code2 },
]

const statusStyles: Record<ControlTowerStatus, string> = {
  healthy: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  warning: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  critical: 'bg-red-500/15 text-red-300 border-red-500/30',
  awaiting_feed: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  unavailable: 'bg-gray-500/15 text-gray-300 border-gray-500/30',
}

const severityStyles = {
  critical: 'border-red-500/40 bg-red-500/10 text-red-200',
  high: 'border-orange-500/40 bg-orange-500/10 text-orange-200',
  medium: 'border-amber-500/40 bg-amber-500/10 text-amber-200',
  low: 'border-blue-500/40 bg-blue-500/10 text-blue-200',
}

function humanStatus(status: ControlTowerStatus) {
  return status.replace('_', ' ')
}

function formatTime(value: string | null | undefined) {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return parsed.toLocaleString()
}

function money(value: number | null | undefined) {
  if (value === null || value === undefined) return 'Awaiting feed'
  return value.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
}

function StatusPill({ status }: { status: ControlTowerStatus }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize ${statusStyles[status]}`}>
      {status === 'healthy' ? <CheckCircle2 className="h-3 w-3" /> : <Clock className="h-3 w-3" />}
      {humanStatus(status)}
    </span>
  )
}

function Panel({ children, className = '' }: { children?: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-gray-700/50 bg-gray-900/70 p-4 shadow-lg shadow-black/10 light:bg-white light:border-gray-200 ${className}`}>
      {children}
    </div>
  )
}

function FeedList({ feeds }: { feeds: ControlTowerFeedStatus[] }) {
  return (
    <div className="space-y-2">
      {feeds.map(feed => (
        <div key={feed.name} className="rounded-lg border border-gray-700/40 bg-gray-800/40 p-3 light:bg-gray-50 light:border-gray-200">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-white light:text-gray-900">{feed.name}</p>
              <p className="text-xs text-gray-400 light:text-gray-600">{feed.source_authority}</p>
            </div>
            <StatusPill status={feed.status} />
          </div>
          <p className="mt-2 text-sm text-gray-300 light:text-gray-700">{feed.message}</p>
          {feed.required_config.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {feed.required_config.map(item => (
                <span key={item} className="rounded bg-gray-950/60 px-2 py-1 font-mono text-[11px] text-gray-300 light:bg-gray-200 light:text-gray-700">
                  {item}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function SummaryCard({ section }: { section: ControlTowerSectionSummary }) {
  return (
    <Panel>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase text-gray-500 light:text-gray-600">{section.label}</p>
          <p className="mt-1 text-2xl font-bold text-white light:text-gray-900">{section.item_count}</p>
        </div>
        <StatusPill status={section.status} />
      </div>
      <p className="mt-3 text-sm text-gray-300 light:text-gray-700">{section.message}</p>
      <p className="mt-2 text-xs text-gray-500 light:text-gray-600">{section.source_authority}</p>
    </Panel>
  )
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-dashed border-gray-700 p-5 text-center text-sm text-gray-400 light:border-gray-300 light:text-gray-600">
      {label}
    </div>
  )
}

export default function ControlTower() {
  const [active, setActive] = useState<SectionKey>('trailers')
  const overview = useControlTowerOverview()
  const attention = useControlTowerAttention()
  const trailers = useControlTowerTrailers()
  const financial = useControlTowerFinancial()
  const agents = useControlTowerAgents()
  const codex = useControlTowerCodex()

  const summaryByKey = useMemo(() => {
    const map = new Map<SectionKey, ControlTowerSectionSummary>()
    overview.data?.sections.forEach(section => {
      map.set(section.key, section)
    })
    return map
  }, [overview.data])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <RadioTower className="h-6 w-6 text-cyan-300" />
          <div>
            <h2 className="text-xl font-bold text-white light:text-gray-900">Control Tower</h2>
            <p className="text-sm text-gray-400 light:text-gray-600">Read-only operating surfaces restored from the original Fleet Pulse build</p>
          </div>
        </div>
        <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-200 light:text-cyan-700">
          Projection mode: read-only
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {sections.map(({ key }) => {
          const section = summaryByKey.get(key)
          return section ? (
            <SummaryCard key={key} section={section} />
          ) : (
            <Panel key={key} className="h-32 animate-pulse" />
          )
        })}
      </div>

      <nav className="flex flex-wrap gap-2 rounded-lg border border-gray-700/50 bg-gray-900/70 p-2 light:bg-white light:border-gray-200">
        {sections.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActive(key)}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition ${
              active === key
                ? 'bg-cyan-500 text-white'
                : 'text-gray-400 hover:bg-gray-800 hover:text-white light:text-gray-600 light:hover:bg-gray-100 light:hover:text-gray-900'
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </nav>

      {active === 'attention' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Panel className="xl:col-span-2">
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Exception Queue</h3>
            {attention.loading ? (
              <EmptyState label="Loading attention queue..." />
            ) : attention.data?.items.length ? (
              <div className="space-y-2">
                {attention.data.items.map(item => (
                  <div key={item.id} className={`rounded-lg border p-3 ${severityStyles[item.severity]}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold">{item.category}</p>
                        <p className="mt-1 text-sm text-gray-200 light:text-gray-800">{item.message}</p>
                      </div>
                      <span className="rounded bg-black/20 px-2 py-1 text-xs">{item.action}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-400 light:text-gray-600">
                      <span>{item.source_authority}</span>
                      <span>{formatTime(item.timestamp)}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState label="No live exception items returned by configured feeds." />
            )}
          </Panel>
          <Panel>
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Feeds</h3>
            <FeedList feeds={attention.data?.feeds || []} />
          </Panel>
        </motion.div>
      )}

      {active === 'trailers' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Panel className="xl:col-span-2">
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Trailer Geofence Tracker</h3>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {[
                ['Total Trailers', trailers.data?.summary.total_trailers ?? 0],
                ['GPS Active', trailers.data?.summary.gps_active ?? 0],
                ['GPS Inactive', trailers.data?.summary.gps_inactive ?? 0],
                ['Events Today', trailers.data?.summary.geofence_events_today ?? 0],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border border-gray-700/50 bg-gray-800/50 p-3 light:bg-gray-50 light:border-gray-200">
                  <p className="text-xs text-gray-400 light:text-gray-600">{label}</p>
                  <p className="mt-1 text-2xl font-bold text-white light:text-gray-900">{value}</p>
                </div>
              ))}
            </div>
            <h4 className="mt-5 mb-2 text-sm font-semibold text-gray-200 light:text-gray-800">Yards</h4>
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {(trailers.data?.yard_locations || []).map(yard => (
                <div key={yard.name} className="flex items-center justify-between rounded-lg bg-gray-800/40 p-3 light:bg-gray-50">
                  <span className="flex items-center gap-2 text-sm text-gray-200 light:text-gray-800">
                    <MapPin className="h-4 w-4 text-cyan-300" />
                    {yard.name}
                  </span>
                  <span className="font-mono text-sm text-white light:text-gray-900">{yard.trailer_count}</span>
                </div>
              ))}
            </div>
          </Panel>
          <Panel>
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Feeds</h3>
            <FeedList feeds={trailers.data?.feeds || []} />
          </Panel>
        </motion.div>
      )}

      {active === 'financial' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Panel className="xl:col-span-2">
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Financial Ops</h3>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <div className="rounded-lg bg-gray-800/50 p-4 light:bg-gray-50">
                <p className="text-xs text-gray-400 light:text-gray-600">AP Pending</p>
                <p className="mt-1 text-xl font-bold text-white light:text-gray-900">{money(financial.data?.accounts_payable.pending_amount)}</p>
                <p className="mt-1 text-xs text-gray-500">{financial.data?.accounts_payable.pending_bills ?? 0} bills</p>
              </div>
              <div className="rounded-lg bg-gray-800/50 p-4 light:bg-gray-50">
                <p className="text-xs text-gray-400 light:text-gray-600">AP Overdue</p>
                <p className="mt-1 text-xl font-bold text-white light:text-gray-900">{money(financial.data?.accounts_payable.overdue_amount)}</p>
                <p className="mt-1 text-xs text-gray-500">{financial.data?.accounts_payable.overdue_count ?? 0} bills</p>
              </div>
              <div className="rounded-lg bg-gray-800/50 p-4 light:bg-gray-50">
                <p className="text-xs text-gray-400 light:text-gray-600">Net Weekly</p>
                <p className="mt-1 text-xl font-bold text-white light:text-gray-900">{money(financial.data?.cash_flow.net_weekly)}</p>
                <p className="mt-1 text-xs text-gray-500">{financial.data?.source_authority || 'K1 Group LLC'}</p>
              </div>
            </div>
            <h4 className="mt-5 mb-2 text-sm font-semibold text-gray-200 light:text-gray-800">AR Aging</h4>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              {(financial.data?.accounts_receivable || []).map(bucket => (
                <div key={bucket.bucket} className="rounded-lg border border-gray-700/40 p-3 light:border-gray-200">
                  <p className="text-xs text-gray-400 light:text-gray-600">{bucket.bucket}</p>
                  <p className="mt-1 font-semibold text-white light:text-gray-900">{money(bucket.amount)}</p>
                  <p className="text-xs text-gray-500">{bucket.count} rows</p>
                </div>
              ))}
            </div>
          </Panel>
          <Panel>
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Feeds</h3>
            <FeedList feeds={financial.data?.feeds || []} />
          </Panel>
        </motion.div>
      )}

      {active === 'agents' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {(agents.data?.systems || []).map(system => (
            <Panel key={system.name}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold text-white light:text-gray-900">{system.name}</h3>
                  {system.usage && <p className="text-xs text-gray-400">{system.usage}</p>}
                </div>
                <StatusPill status={system.status} />
              </div>
              <div className="mt-4 space-y-2">
                {system.flows.map(flow => (
                  <div key={flow.name} className="rounded-lg bg-gray-800/40 p-3 light:bg-gray-50">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium text-white light:text-gray-900">{flow.name}</p>
                      <StatusPill status={flow.status} />
                    </div>
                    <p className="mt-1 text-xs text-gray-400 light:text-gray-600">{flow.detail}</p>
                  </div>
                ))}
              </div>
            </Panel>
          ))}
        </motion.div>
      )}

      {active === 'codex' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Panel className="xl:col-span-2">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-white light:text-gray-900">Codex / GitHub Runtime</h3>
                <p className="mt-1 text-sm text-gray-400 light:text-gray-600">{codex.data?.message || 'Loading runtime metadata...'}</p>
              </div>
              <StatusPill status={codex.data?.overall_status || 'awaiting_feed'} />
            </div>
            <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-2">
              {[
                ['Repository', codex.data?.repository || 'Awaiting feed'],
                ['Branch', codex.data?.branch || 'Awaiting feed'],
                ['Commit', codex.data?.commit_sha || 'Awaiting feed'],
                ['Run ID', codex.data?.run_id || 'Awaiting feed'],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg bg-gray-800/40 p-3 light:bg-gray-50">
                  <p className="text-xs text-gray-400 light:text-gray-600">{label}</p>
                  <p className="mt-1 font-mono text-sm text-white light:text-gray-900">{value}</p>
                </div>
              ))}
            </div>
          </Panel>
          <Panel>
            <h3 className="mb-3 text-lg font-semibold text-white light:text-gray-900">Feeds</h3>
            <FeedList feeds={codex.data?.feeds || []} />
          </Panel>
        </motion.div>
      )}
    </div>
  )
}
