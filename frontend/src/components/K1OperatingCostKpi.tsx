import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { DollarSign, Gauge } from 'lucide-react'
import type { DashboardValidationItem } from '../types/fleet'
import ValidationBadge from './ValidationBadge'

interface K1OperatingCostSummary {
  added_p_and_l_ops: number
  cost_per_mile: number | null
  driver_pay?: number | null
  employee?: number | null
  fleet_maintenance: number
  fuel?: number | null
  gross_profit?: number | null
  insurance?: number | null
  miles: number
  profit_per_mile?: number | null
  rental_trucks_trailers?: number | null
  revenue?: number | null
  revenue_per_mile?: number | null
  total_cost: number
}

interface K1OperatingCostSnapshot {
  as_of_date?: string | null
  entity: string
  error?: string
  projection_mode: 'read_only'
  revenue_source?: string
  revenue_source_status?: {
    message?: string
    row_count?: number | null
    status?: string
  }
  cost_source_status?: {
    message?: string
    row_count?: number | null
    status?: string
  }
  source?: string
  status: 'configured' | 'configuration_error' | 'not_configured'
  summary: K1OperatingCostSummary | null
}

interface Props {
  className?: string
  compact?: boolean
  validation?: DashboardValidationItem | null
}

interface OperatingCostApiSummary {
  driver_pay?: number | null
  employee_cost?: number | null
  fuel_cost?: number | null
  insurance_cost?: number | null
  known_cost_per_mile?: number | null
  known_operating_cost?: number | null
  maintenance_cost?: number | null
  miles?: number | null
  other_expense_cost?: number | null
  rental_trucks_trailers_cost?: number | null
  true_cost_per_mile?: number | null
  true_operating_cost?: number | null
}

interface OperatingCostApiSnapshot {
  complete_cost_available?: boolean
  period_end?: string
  period_start?: string
  row_counts?: Record<string, number>
  summary?: OperatingCostApiSummary | null
  unresolved_sources?: string[]
}

interface EntityMarginApiSnapshot {
  summary?: {
    k1l_grand_total?: number | null
  } | null
  sources?: Array<{
    row_count?: number | null
    status?: string
    table?: string
  }>
  xcelerator_source_type?: string
}

const legacyEndpoint = '/api/fuel/k1l-operating-kpi'
const ytdStart = `${new Date().getFullYear()}-01-01`
const operatingCostEndpoint = `/api/fuel/operating-cost?start=${ytdStart}`
const entityMarginEndpoint = `/api/fuel/entity-margin?start=${ytdStart}`

function formatCurrency(value: number | null | undefined, compact = true) {
  if (value === null || value === undefined) return 'Pending'
  if (!Number.isFinite(Number(value))) return 'Pending'
  return new Intl.NumberFormat('en-US', {
    currency: 'USD',
    maximumFractionDigits: compact ? 1 : 0,
    notation: compact ? 'compact' : 'standard',
    style: 'currency',
  }).format(Number(value))
}

function formatMiles(value: number | null | undefined) {
  if (value === null || value === undefined) return 'Pending'
  if (!Number.isFinite(Number(value))) return 'Pending'
  return Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })
}

function formatCpm(value: number | null | undefined) {
  if (value === null || value === undefined) return 'Pending'
  if (!Number.isFinite(Number(value))) return 'Pending'
  return `$${Number(value).toFixed(3)}/mi`
}

function round(value: number | null | undefined, digits = 3) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return null
  const factor = 10 ** digits
  return Math.round(Number(value) * factor) / factor
}

function sum(values: Array<number | null | undefined>): number {
  return values.reduce<number>((total, value) => total + (Number.isFinite(Number(value)) ? Number(value) : 0), 0)
}

async function fetchJson<T>(url: string, signal: AbortSignal): Promise<T | null> {
  const response = await fetch(url, { signal })
  if (!response.ok) return null
  return await response.json() as T
}

async function fetchKpiSnapshot(): Promise<K1OperatingCostSnapshot | null> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 60000)
  try {
    const [operatingCost, entityMargin] = await Promise.all([
      fetchJson<OperatingCostApiSnapshot>(operatingCostEndpoint, controller.signal),
      fetchJson<EntityMarginApiSnapshot>(entityMarginEndpoint, controller.signal),
    ])
    const operatingSummary = operatingCost?.summary
    if (!operatingSummary) {
      return await fetchJson<K1OperatingCostSnapshot>(legacyEndpoint, controller.signal)
    }

    const miles = Number(operatingSummary.miles || 0)
    const totalCost = (
      Number.isFinite(Number(operatingSummary.true_operating_cost))
        ? Number(operatingSummary.true_operating_cost)
        : Number(operatingSummary.known_operating_cost || 0)
    )
    const costPerMile = (
      Number.isFinite(Number(operatingSummary.true_cost_per_mile))
        ? Number(operatingSummary.true_cost_per_mile)
        : round(operatingSummary.known_cost_per_mile)
    )
    const revenue = entityMargin?.summary?.k1l_grand_total ?? null
    const revenuePerMile = revenue !== null && miles > 0 ? round(Number(revenue) / miles) : null
    const grossProfit = revenue !== null ? Number(revenue) - totalCost : null
    const profitPerMile = revenuePerMile !== null && costPerMile !== null ? round(revenuePerMile - costPerMile) : null
    const unresolved = operatingCost?.unresolved_sources ?? []
    const revenueSource = entityMargin?.xcelerator_source_type || 'fabric_warehouse_sql'
    const xceleratorRows = (entityMargin?.sources ?? []).find(source => source.table === 'dbo.xcelerator_review_orders')?.row_count

    return {
      as_of_date: operatingCost?.period_end,
      cost_source_status: {
        message: unresolved.length ? `Unresolved source: ${unresolved.join(', ')}` : 'Complete K1L operating cost stack.',
        row_count: operatingCost?.row_counts?.qbo_expenses ?? null,
        status: operatingCost?.complete_cost_available ? 'healthy' : 'pending',
      },
      entity: 'K1 Logistics Inc',
      projection_mode: 'read_only',
      revenue_source: revenueSource,
      revenue_source_status: {
        message: revenue !== null ? 'Xcelerator revenue is available.' : 'Xcelerator revenue is awaiting feed.',
        row_count: xceleratorRows ?? null,
        status: revenue !== null ? 'healthy' : 'awaiting_feed',
      },
      source: 'Xcelerator Warehouse SQL revenue/driver pay + QBO K1L expenses + Geotab miles/hours',
      status: 'configured',
      summary: {
        added_p_and_l_ops: sum([
          operatingSummary.insurance_cost,
          operatingSummary.employee_cost,
          operatingSummary.rental_trucks_trailers_cost,
          operatingSummary.other_expense_cost,
        ]),
        cost_per_mile: costPerMile,
        driver_pay: operatingSummary.driver_pay ?? null,
        employee: operatingSummary.employee_cost ?? null,
        fleet_maintenance: Number(operatingSummary.maintenance_cost || 0),
        fuel: operatingSummary.fuel_cost ?? null,
        gross_profit: grossProfit,
        insurance: operatingSummary.insurance_cost ?? null,
        miles,
        profit_per_mile: profitPerMile,
        rental_trucks_trailers: operatingSummary.rental_trucks_trailers_cost ?? null,
        revenue,
        revenue_per_mile: revenuePerMile,
        total_cost: totalCost,
      },
    }
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
  const revenueSourceStatus = snapshot?.revenue_source_status?.status || 'not_configured'
  const costSourceStatus = snapshot?.cost_source_status?.status || 'not_configured'
  const revenueSourceLabel = snapshot?.revenue_source === 'fabric_warehouse_sql'
    ? 'Xcelerator Warehouse SQL'
    : snapshot?.revenue_source === 'xcelerator_ceo_powerbi'
      ? 'Xcelerator CEO Power BI'
      : 'Monthly JSON fallback'
  const rpmVerified = (
    (snapshot?.revenue_source === 'fabric_warehouse_sql' || snapshot?.revenue_source === 'xcelerator_ceo_powerbi')
    && revenueSourceStatus === 'healthy'
    && Number.isFinite(Number(summary?.revenue_per_mile))
    && Number.isFinite(Number(summary?.profit_per_mile))
  )
  const fallbackVerified = Boolean(configured && rpmVerified && costSourceStatus === 'healthy' && Number.isFinite(Number(summary?.cost_per_mile)))

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
            K1L CPM + Revenue / Mile
          </p>
          <div className={`mt-2 grid gap-3 ${compact ? 'grid-cols-1' : 'grid-cols-2'}`}>
            <div>
              <div className="text-[10px] uppercase text-gray-500">CPM</div>
              <p className={`${compact ? 'text-xl' : 'text-2xl'} break-words font-bold text-white light:text-gray-900`}>
                {loading ? '...' : formatCpm(summary?.cost_per_mile)}
              </p>
            </div>
            <div>
              <div className="text-[10px] uppercase text-gray-500">Revenue / Mile</div>
              <p className={`${compact ? 'text-xl' : 'text-2xl'} break-words font-bold text-emerald-300 light:text-emerald-700`}>
                {loading ? '...' : formatCpm(summary?.revenue_per_mile)}
              </p>
            </div>
          </div>
        </div>
        <ValidationBadge
          compact
          item={validation}
          status={fallbackVerified ? 'verified' : 'pending'}
        />
      </div>

      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-500 light:text-gray-600">
        <span>CPM: Geotab miles + QBO K1L expenses + Xcelerator driver pay</span>
        <span>Revenue / Mile: {revenueSourceLabel} ({revenueSourceStatus.replace('_', ' ')})</span>
      </div>

      <div className={`mt-3 grid gap-2 text-xs text-gray-400 light:text-gray-600 ${compact ? 'grid-cols-1' : 'sm:grid-cols-3'}`}>
        <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2 light:bg-gray-50 light:border-gray-200">
          <div className="text-[10px] uppercase text-gray-500">Profit / mile</div>
          <div className="mt-1 font-semibold text-emerald-300 light:text-emerald-700">{formatCpm(summary?.profit_per_mile)}</div>
        </div>
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
          <div>Revenue {formatCurrency(summary?.revenue)} · Profit {formatCurrency(summary?.gross_profit)}</div>
          <div>Driver pay {formatCurrency(summary?.driver_pay)} · Fuel {formatCurrency(summary?.fuel)} · Maintenance {formatCurrency(summary?.fleet_maintenance)}</div>
          <div>Insurance {formatCurrency(summary?.insurance)} · Rental/lease {formatCurrency(summary?.rental_trucks_trailers)} · Ops added {formatCurrency(summary?.added_p_and_l_ops)}</div>
        </div>
      )}
    </motion.div>
  )
}
