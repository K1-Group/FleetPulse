import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { DollarSign, Gauge } from 'lucide-react'
import type { DashboardValidationItem } from '../types/fleet'
import ValidationBadge from './ValidationBadge'

interface K1OperatingCostSummary {
  added_p_and_l_ops: number
  cost_per_mile: number | null
  fleet_maintenance: number
  miles: number
  total_cost: number
}

interface K1OperatingCostSnapshot {
  as_of_date?: string | null
  entity: string
  error?: string
  projection_mode: 'read_only'
  source?: string
  status: 'configured' | 'configuration_error' | 'not_configured'
  summary: K1OperatingCostSummary | null
}

interface Props {
  className?: string
  compact?: boolean
  validation?: DashboardValidationItem | null
}

const endpoint = '/api/fuel/k1l-operating-kpi'

function formatCurrency(value: number | null | undefined, compact = true) {
  if (!Number.isFinite(Number(value))) return 'Pending'
  return new Intl.NumberFormat('en-US', {
    currency: 'USD',
    maximumFractionDigits: compact ? 1 : 0,
    notation: compact ? 'compact' : 'standard',
    style: 'currency',
  }).format(Number(value))
}

function formatMiles(value: number | null | undefined) {
  if (!Number.isFinite(Number(value))) return 'Pending'
  return Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })
}

function formatCpm(value: number | null | undefined) {
  if (!Number.isFinite(Number(value))) return 'Pending'
  return `$${Number(value).toFixed(3)}/mi`
}

async function fetchKpiSnapshot(): Promise<K1OperatingCostSnapshot | null> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 7000)
  try {
    const response = await fetch(endpoint, { signal: controller.signal })
    if (!response.ok) return null
    return await response.json() as K1OperatingCostSnapshot
  } catch {
    return null
  } finally {
    window.clearTimeout(timeout)
  }
}

export default function K1OperatingCostKpi({ className = '', compact = false, validation }: Props) {
  const [snapshot, setSnapshot] = useState<K1OperatingCostSnapshot | null>(null)
  const [loading, setLoading] = useState(true)

  const loadSnapshot = useCallback(async () => {
    const data = await fetchKpiSnapshot()
    setSnapshot(data)
    setLoading(false)
  }, [])

  useEffect(() => {
    void loadSnapshot()
    const id = window.setInterval(loadSnapshot, 60000)
    return () => window.clearInterval(id)
  }, [loadSnapshot])

  const configured = snapshot?.status === 'configured' && Boolean(snapshot.summary)
  const summary = snapshot?.summary
  const sourceLabel = snapshot?.source || 'QBO + Xcelerator + AtoB + Geotab'

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className={`rounded-xl border border-emerald-500/20 bg-gray-900/70 p-4 shadow-lg shadow-black/10 light:bg-white light:border-emerald-200 ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-xs font-semibold uppercase text-gray-400 light:text-gray-600">
            <Gauge className="h-4 w-4 text-emerald-300" />
            K1L Final CPM
          </p>
          <p className="mt-2 text-2xl font-bold text-white light:text-gray-900">
            {loading ? '...' : formatCpm(summary?.cost_per_mile)}
          </p>
        </div>
        <ValidationBadge
          compact
          item={validation}
          status={configured ? 'verified' : 'pending'}
        />
      </div>

      <div className={`mt-3 grid gap-2 text-xs text-gray-400 light:text-gray-600 ${compact ? 'grid-cols-1' : 'sm:grid-cols-2'}`}>
        <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2 light:bg-gray-50 light:border-gray-200">
          <div className="flex items-center gap-1 text-[10px] uppercase text-gray-500">
            <DollarSign className="h-3.5 w-3.5" />
            Total cost
          </div>
          <div className="mt-1 font-semibold text-white light:text-gray-900">{formatCurrency(summary?.total_cost)}</div>
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2 light:bg-gray-50 light:border-gray-200">
          <div className="text-[10px] uppercase text-gray-500">Miles</div>
          <div className="mt-1 font-semibold text-white light:text-gray-900">{formatMiles(summary?.miles)}</div>
        </div>
      </div>

      {!compact && (
        <div className="mt-3 text-xs text-gray-500 light:text-gray-600">
          <div className="truncate" title={sourceLabel}>{sourceLabel}</div>
          <div>Ops added {formatCurrency(summary?.added_p_and_l_ops)} · Fleet maintenance {formatCurrency(summary?.fleet_maintenance)}</div>
        </div>
      )}
    </motion.div>
  )
}
