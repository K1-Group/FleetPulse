import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  AlertTriangle,
  Database,
  DollarSign,
  FileCheck2,
  Fuel,
  Gauge,
  Loader2,
  ReceiptText,
  TrendingDown,
  TrendingUp,
  Upload,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

type FuelCostSource = 'atob_manual_import' | 'geotab_distance_estimate' | 'unavailable'

interface FuelPeriod {
  total_miles: number
  total_gallons: number
  total_cost: number
  avg_mpg: number
  cost_per_mile: number
  actual_fuel_cost?: boolean
  fuel_cost_source?: FuelCostSource
  atob_transaction_count?: number
  atob_latest_transaction_date?: string | null
}

interface AtoBSummary {
  source_authority?: string
  projection_mode?: string
  period_days?: number
  transaction_count: number
  total_cost: number
  total_gallons: number
  avg_price_per_gallon: number | null
  vehicle_count: number
  latest_transaction_date: string | null
}

interface FuelSummary {
  period_30d: FuelPeriod
  period_7d: FuelPeriod
  waste: { harsh_events: number; wasted_gallons: number; wasted_cost: number }
  fleet_size: number
  cost_per_vehicle_30d: number
  fuel_price: number
  fuel_cost_source?: FuelCostSource
  atob_import?: AtoBSummary
}

interface FuelTrend {
  date: string
  miles: number
  gallons: number
  cost: number
  fuel_cost_source?: FuelCostSource
  transaction_count?: number
}

interface VehicleEfficiency {
  vehicle_id: string
  vehicle_name: string
  miles: number
  est_mpg: number
  est_gallons: number
  est_cost: number
  actual_cost?: number
  actual_gallons?: number
  fuel_cost_source?: FuelCostSource
  atob_transaction_count?: number
  harsh_events: number
  efficiency_grade: string
}

interface AtoBImportResult {
  status: string
  dry_run: boolean
  total_records: number
  imported_count: number
  duplicate_count: number
  invalid_count: number
  errors: string[]
  summary: AtoBSummary
}

interface AtoBSharePointStatus {
  enabled: boolean
  sync_ready: boolean
  folder_path: string
  source_file_url_count: number
  file_extensions: string[]
  file_limit: number
  api_key_required: boolean
  missing_config: string[]
  powerbi_connection?: {
    workspace_id?: string | null
    folder_id?: string | null
    ui_subfolder_id?: string | null
    report_id?: string | null
    semantic_model_id?: string | null
  }
}

interface AtoBSharePointSyncResult {
  status: string
  dry_run: boolean
  folder_path: string
  fetched_count: number
  imported_count: number
  duplicate_count: number
  invalid_count: number
  errors: string[]
}

interface QboExpenseSummary {
  source_authority?: string
  projection_mode?: string
  period_days?: number
  coverage_start?: string | null
  coverage_end?: string | null
  last_imported_at?: string | null
  row_count: number
  included_expense_count: number
  excluded_expense_count: number
  insurance_total: number
  other_expense_total: number
  included_expense_total: number
  date_min: string | null
  date_max: string | null
}

interface QboExpenseStatus {
  api_key_required: boolean
  state_path_configured: boolean
  state_exists: boolean
  missing_config: string[]
}

interface QboExpenseImportResult {
  status: string
  dry_run: boolean
  total_records: number
  imported_count: number
  duplicate_count: number
  invalid_count: number
  errors: string[]
  summary: QboExpenseSummary
}

interface OperatingCostSummary {
  miles: number
  drive_hours: number
  idle_hours: number
  operating_hours: number
  trips: number
  fuel_cost: number
  driver_pay: number
  insurance_cost: number
  other_expense_cost: number
  known_operating_cost: number
  true_operating_cost: number | null
  known_cost_per_mile: number | null
  true_cost_per_mile: number | null
  known_cost_per_drive_hour: number | null
  true_cost_per_drive_hour: number | null
  known_cost_per_operating_hour: number | null
  true_cost_per_operating_hour: number | null
}

interface WeeklyOperatingCost extends OperatingCostSummary {
  week_start: string
  week_end: string
  period_start: string
  period_end: string
}

interface OperatingCostSource {
  status: string
  source_authority: string
  projection_mode: string
  message?: string
  row_count: number
}

interface OperatingCostSnapshot {
  period_start: string
  period_end: string
  generated_at: string
  source_authority: string
  projection_mode: string
  grain: string
  complete_cost_available: boolean
  unresolved_sources: string[]
  sources: {
    telemetry: OperatingCostSource
    fuel: OperatingCostSource
    driver_pay: OperatingCostSource
    qbo_expenses: OperatingCostSource
  }
  summary: OperatingCostSummary
  weekly: WeeklyOperatingCost[]
}

const formatCurrency = (value?: number | null, maximumFractionDigits = 0) => (
  value === null || value === undefined
    ? 'Pending'
    : value.toLocaleString(undefined, {
        style: 'currency',
        currency: 'USD',
        maximumFractionDigits,
      })
)

const formatRate = (value?: number | null, suffix = '/mi') => (
  value === null || value === undefined ? 'Pending' : `${formatCurrency(value, 2)}${suffix}`
)

async function fetchJson<T>(url: string, fallback: T, timeoutMs = 20000): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, { signal: controller.signal })
    if (!response.ok) {
      return fallback
    }
    return await response.json() as T
  } catch {
    return fallback
  } finally {
    window.clearTimeout(timeout)
  }
}

export default function FuelAnalytics() {
  const [summary, setSummary] = useState<FuelSummary | null>(null)
  const [atobSummary, setAtobSummary] = useState<AtoBSummary | null>(null)
  const [sharePointStatus, setSharePointStatus] = useState<AtoBSharePointStatus | null>(null)
  const [qboSummary, setQboSummary] = useState<QboExpenseSummary | null>(null)
  const [qboStatus, setQboStatus] = useState<QboExpenseStatus | null>(null)
  const [operatingCost, setOperatingCost] = useState<OperatingCostSnapshot | null>(null)
  const [trends, setTrends] = useState<FuelTrend[]>([])
  const [efficiency, setEfficiency] = useState<VehicleEfficiency[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [selectedQboFile, setSelectedQboFile] = useState<File | null>(null)
  const [qboApiKey, setQboApiKey] = useState('')
  const [importing, setImporting] = useState(false)
  const [importingQbo, setImportingQbo] = useState(false)
  const [syncingSharePoint, setSyncingSharePoint] = useState(false)
  const [importResult, setImportResult] = useState<AtoBImportResult | null>(null)
  const [qboImportResult, setQboImportResult] = useState<QboExpenseImportResult | null>(null)
  const [sharePointResult, setSharePointResult] = useState<AtoBSharePointSyncResult | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

  const loadFuelData = useCallback(async () => {
    setLoading(true)
    try {
      const ytdStart = `${new Date().getFullYear()}-01-01`
      const [s, t, e, a, sp, qbo, qboReady] = await Promise.all([
        fetchJson<FuelSummary | null>('/api/fuel/summary', null),
        fetchJson<FuelTrend[]>('/api/fuel/trends', []),
        fetchJson<VehicleEfficiency[]>('/api/fuel/efficiency', []),
        fetchJson<AtoBSummary | null>('/api/fuel/atob/summary?days=30', null),
        fetchJson<AtoBSharePointStatus | null>('/api/fuel/atob/sharepoint/status', null),
        fetchJson<QboExpenseSummary | null>('/api/fuel/qbo/expenses/summary?days=370', null),
        fetchJson<QboExpenseStatus | null>('/api/fuel/qbo/expenses/status', null),
      ])
      setSummary(s)
      setTrends(t)
      setEfficiency(e)
      setAtobSummary(a)
      setSharePointStatus(sp)
      setQboSummary(qbo)
      setQboStatus(qboReady)
      setLoading(false)

      const oc = await fetchJson<OperatingCostSnapshot | null>(
        `/api/fuel/operating-cost?start=${ytdStart}`,
        null,
        45000,
      )
      setOperatingCost(oc)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadFuelData()
  }, [loadFuelData])

  const handleAtoBImport = async (dryRun: boolean) => {
    if (!selectedFile) {
      setImportError('Select a downloaded AtoB CSV, TSV, or JSON report first.')
      return
    }
    setImporting(true)
    setImportError(null)
    try {
      const content = await selectedFile.text()
      const response = await fetch('/api/fuel/atob/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: selectedFile.name,
          content,
          dry_run: dryRun,
        }),
      })
      if (!response.ok) {
        throw new Error(`AtoB import failed with HTTP ${response.status}`)
      }
      const result = await response.json() as AtoBImportResult
      setImportResult(result)
      if (!dryRun) {
        await loadFuelData()
      }
    } catch (error) {
      setImportError(error instanceof Error ? error.message : 'AtoB import failed')
    } finally {
      setImporting(false)
    }
  }

  const handleSharePointSync = async (dryRun: boolean) => {
    setSyncingSharePoint(true)
    setImportError(null)
    setSharePointResult(null)
    try {
      const response = await fetch('/api/fuel/atob/sharepoint/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: dryRun }),
      })
      if (!response.ok) {
        throw new Error(`SharePoint sync failed with HTTP ${response.status}`)
      }
      const result = await response.json() as AtoBSharePointSyncResult
      setSharePointResult(result)
      if (!dryRun) {
        await loadFuelData()
      }
    } catch (error) {
      setImportError(error instanceof Error ? error.message : 'SharePoint sync failed')
    } finally {
      setSyncingSharePoint(false)
    }
  }

  const handleQboImport = async (dryRun: boolean) => {
    if (!selectedQboFile) {
      setImportError('Select a downloaded QBO CSV, TSV, or JSON expense report first.')
      return
    }
    setImportingQbo(true)
    setImportError(null)
    try {
      const content = await selectedQboFile.text()
      const now = new Date()
      const periodStart = `${now.getFullYear()}-01-01`
      const periodEnd = now.toISOString().slice(0, 10)
      const response = await fetch('/api/fuel/qbo/expenses/import', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(qboApiKey ? { 'X-FleetPulse-QBO-Key': qboApiKey } : {}),
        },
        body: JSON.stringify({
          filename: selectedQboFile.name,
          content,
          dry_run: dryRun,
          period_start: periodStart,
          period_end: periodEnd,
        }),
      })
      if (!response.ok) {
        throw new Error(`QBO import failed with HTTP ${response.status}`)
      }
      const result = await response.json() as QboExpenseImportResult
      setQboImportResult(result)
      if (!dryRun) {
        await loadFuelData()
      }
    } catch (error) {
      setImportError(error instanceof Error ? error.message : 'QBO import failed')
    } finally {
      setImportingQbo(false)
    }
  }

  const actualFuelCost = summary?.fuel_cost_source === 'atob_manual_import'
  const qboImportLocked = Boolean(qboStatus?.api_key_required && !qboApiKey)
  const sharePointReady = Boolean(sharePointStatus?.sync_ready)
  const operatingSummary = operatingCost?.summary
  const completeOperatingCost = Boolean(operatingCost?.complete_cost_available)
  const unresolvedCostSources = operatingCost?.unresolved_sources.join(', ') || ''

  const gradeColor = (grade: string) => {
    switch (grade) {
      case 'A': return 'text-emerald-400 bg-emerald-500/20'
      case 'B': return 'text-blue-400 bg-blue-500/20'
      case 'C': return 'text-amber-400 bg-amber-500/20'
      default: return 'text-red-400 bg-red-500/20'
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
          className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-5">
          <div className="flex items-center gap-2 text-gray-400 text-xs uppercase mb-2">
            <DollarSign className="w-4 h-4" /> 30-Day Fuel Cost
          </div>
          <div className="text-2xl font-bold text-emerald-400">${summary?.period_30d.total_cost.toLocaleString()}</div>
          <div className="text-xs text-gray-500 mt-1">
            {actualFuelCost ? 'AtoB actual import' : 'Geotab mileage estimate'}
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-5">
          <div className="flex items-center gap-2 text-gray-400 text-xs uppercase mb-2">
            <Gauge className="w-4 h-4" /> Fleet Avg MPG
          </div>
          <div className="text-2xl font-bold text-blue-400">{summary?.period_30d.avg_mpg}</div>
          <div className="text-xs text-gray-500 mt-1">{summary?.period_30d.total_gallons.toLocaleString()} gal recorded</div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
          className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-5">
          <div className="flex items-center gap-2 text-gray-400 text-xs uppercase mb-2">
            <TrendingUp className="w-4 h-4" /> Miles Driven (30d)
          </div>
          <div className="text-2xl font-bold text-purple-400">{summary?.period_30d.total_miles.toLocaleString()}</div>
          <div className="text-xs text-gray-500 mt-1">${summary?.period_30d.cost_per_mile}/mile</div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}
          className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-5">
          <div className="flex items-center gap-2 text-gray-400 text-xs uppercase mb-2">
            <AlertTriangle className="w-4 h-4" /> Fuel Waste
          </div>
          <div className="text-2xl font-bold text-amber-400">${summary?.waste.wasted_cost.toFixed(0)}</div>
          <div className="text-xs text-gray-500 mt-1">{summary?.waste.harsh_events} harsh events</div>
        </motion.div>
      </div>

      {/* True Operating Cost Stack */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.42 }}
        className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
      >
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-5">
          <div>
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <DollarSign className="w-5 h-5 text-blue-400" />
              Operating Cost Per Mile / Hour
            </h3>
            <div className="mt-1 text-sm text-gray-400">
              {operatingCost?.period_start ?? 'YTD'} to {operatingCost?.period_end ?? 'today'} · {completeOperatingCost ? 'Complete source stack' : `Known stack only${unresolvedCostSources ? ` · pending ${unresolvedCostSources}` : ''}`}
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            {Object.entries((operatingCost?.sources ?? {}) as Record<string, OperatingCostSource>).map(([key, source]) => (
              <div key={key} className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
                <div className="text-[10px] uppercase tracking-wide text-gray-500">{key.replace('_', ' ')}</div>
                <div className={source.status === 'healthy' ? 'text-emerald-400' : source.status === 'awaiting_feed' ? 'text-amber-400' : 'text-red-300'}>
                  {source.status.replace('_', ' ')}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-4">
            <div className="text-xs uppercase text-gray-500">{completeOperatingCost ? 'True CPM' : 'Known CPM'}</div>
            <div className="mt-1 text-2xl font-bold text-emerald-400">
              {formatRate(completeOperatingCost ? operatingSummary?.true_cost_per_mile : operatingSummary?.known_cost_per_mile)}
            </div>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-4">
            <div className="text-xs uppercase text-gray-500">{completeOperatingCost ? 'True Cost / Drive Hr' : 'Known Cost / Drive Hr'}</div>
            <div className="mt-1 text-2xl font-bold text-blue-400">
              {formatRate(completeOperatingCost ? operatingSummary?.true_cost_per_drive_hour : operatingSummary?.known_cost_per_drive_hour, '/hr')}
            </div>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-4">
            <div className="text-xs uppercase text-gray-500">Known Operating Cost</div>
            <div className="mt-1 text-2xl font-bold text-white">{formatCurrency(operatingSummary?.known_operating_cost)}</div>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-4">
            <div className="text-xs uppercase text-gray-500">Miles / Drive Hrs</div>
            <div className="mt-1 text-2xl font-bold text-purple-400">
              {(operatingSummary?.miles ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })} / {(operatingSummary?.drive_hours ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </div>
          </div>
        </div>

        {(operatingCost?.weekly.length ?? 0) > 0 ? (
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={operatingCost?.weekly ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="week_start" stroke="#6b7280" tick={{ fontSize: 11 }} tickFormatter={(v) => String(v).slice(5)} />
              <YAxis yAxisId="cost" stroke="#6b7280" tick={{ fontSize: 11 }} tickFormatter={(v) => `$${Number(v) / 1000}k`} />
              <YAxis yAxisId="rate" orientation="right" stroke="#6b7280" tick={{ fontSize: 11 }} tickFormatter={(v) => `$${Number(v).toFixed(2)}`} />
              <Tooltip
                contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                labelStyle={{ color: '#9ca3af' }}
                formatter={(value: number, name: string) => [
                  name.includes('Cost') || name.includes('Pay') || name.includes('Expense') || name.includes('Insurance')
                    ? formatCurrency(value)
                    : formatRate(value, name.includes('Hour') ? '/hr' : '/mi'),
                  name,
                ]}
              />
              <Legend />
              <Bar yAxisId="cost" dataKey="fuel_cost" name="Fuel Cost" stackId="cost" fill="#10b981" />
              <Bar yAxisId="cost" dataKey="driver_pay" name="Driver Pay" stackId="cost" fill="#3b82f6" />
              <Bar yAxisId="cost" dataKey="insurance_cost" name="Insurance" stackId="cost" fill="#a855f7" />
              <Bar yAxisId="cost" dataKey="other_expense_cost" name="Other Expense" stackId="cost" fill="#f59e0b" />
              <Line yAxisId="rate" type="monotone" dataKey="known_cost_per_mile" name="Known CPM" stroke="#f8fafc" strokeWidth={2} dot={false} />
              <Line yAxisId="rate" type="monotone" dataKey="known_cost_per_drive_hour" name="Known Cost/Hour" stroke="#fb7185" strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-[260px] items-center justify-center rounded-lg border border-dashed border-gray-700 text-sm text-gray-500">
            Weekly cost charts appear after Geotab miles and cost feeds are available.
          </div>
        )}
      </motion.div>

      {/* AtoB Manual Fuel Expense Intake */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.45 }}
        className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
      >
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-5">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Database className="w-5 h-5 text-emerald-400" />
              AtoB Fuel Expense Import
            </h3>
            <div className="mt-2 text-sm text-gray-400">
              SharePoint folder: {sharePointStatus?.folder_path || 'atob'} · {sharePointReady ? 'Ready' : 'Config needed'}
            </div>
            <div className="mt-1 text-xs text-gray-500">
              Power BI: {sharePointStatus?.powerbi_connection?.semantic_model_id ? 'AtoB model mapped' : 'Model mapping optional'} · Source files: {sharePointStatus?.source_file_url_count ?? 0}
            </div>
            <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
              <div>
                <div className="text-xs uppercase text-gray-500">Transactions</div>
                <div className="text-xl font-semibold text-white">{atobSummary?.transaction_count ?? 0}</div>
              </div>
              <div>
                <div className="text-xs uppercase text-gray-500">Actual Cost</div>
                <div className="text-xl font-semibold text-emerald-400">${(atobSummary?.total_cost ?? 0).toLocaleString()}</div>
              </div>
              <div>
                <div className="text-xs uppercase text-gray-500">Gallons</div>
                <div className="text-xl font-semibold text-blue-400">{(atobSummary?.total_gallons ?? 0).toLocaleString()}</div>
              </div>
              <div>
                <div className="text-xs uppercase text-gray-500">Latest</div>
                <div className="text-xl font-semibold text-gray-200">{atobSummary?.latest_transaction_date ?? 'None'}</div>
              </div>
            </div>
          </div>

          <div className="w-full lg:w-[460px] space-y-3">
            <label className="block">
              <span className="sr-only">AtoB fuel report</span>
              <input
                type="file"
                accept=".csv,.tsv,.txt,.json,.jsonl"
                onChange={(event) => {
                  setSelectedFile(event.target.files?.[0] ?? null)
                  setImportResult(null)
                  setImportError(null)
                }}
                className="block w-full text-sm text-gray-300 file:mr-4 file:rounded-lg file:border-0 file:bg-emerald-500 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-emerald-400"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={syncingSharePoint}
                onClick={() => void handleSharePointSync(true)}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-200 hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {syncingSharePoint ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileCheck2 className="w-4 h-4" />}
                Preview Folder
              </button>
              <button
                type="button"
                disabled={syncingSharePoint}
                onClick={() => void handleSharePointSync(false)}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {syncingSharePoint ? <Loader2 className="w-4 h-4 animate-spin" /> : <Database className="w-4 h-4" />}
                Sync SharePoint
              </button>
              <button
                type="button"
                disabled={importing}
                onClick={() => void handleAtoBImport(true)}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-200 hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileCheck2 className="w-4 h-4" />}
                Preview
              </button>
              <button
                type="button"
                disabled={importing}
                onClick={() => void handleAtoBImport(false)}
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                Import
              </button>
            </div>
            {selectedFile && (
              <div className="text-xs text-gray-500">Selected: {selectedFile.name}</div>
            )}
            {importError && (
              <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
                {importError}
              </div>
            )}
            {importResult && (
              <div className="rounded-lg border border-gray-700 bg-gray-950/50 px-3 py-2 text-sm text-gray-300">
                <span className="font-semibold text-white">{importResult.dry_run ? 'Preview' : 'Import'} complete:</span>{' '}
                {importResult.imported_count} new, {importResult.duplicate_count} duplicate, {importResult.invalid_count} invalid.
              </div>
            )}
            {sharePointResult && (
              <div className="rounded-lg border border-gray-700 bg-gray-950/50 px-3 py-2 text-sm text-gray-300">
                <span className="font-semibold text-white">{sharePointResult.dry_run ? 'Folder preview' : 'SharePoint sync'} complete:</span>{' '}
                {sharePointResult.fetched_count} files, {sharePointResult.imported_count} new, {sharePointResult.duplicate_count} duplicate, {sharePointResult.invalid_count} invalid.
              </div>
            )}
          </div>
        </div>
      </motion.div>

      {/* QBO Expense Intake */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.48 }}
        className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
      >
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-5">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <ReceiptText className="w-5 h-5 text-purple-400" />
              QBO Insurance & Operating Expense Import
            </h3>
            <div className="mt-2 text-sm text-gray-400">
              {qboStatus?.state_path_configured ? 'State path configured' : 'State path pending'} · {qboStatus?.api_key_required ? 'API key required' : 'Operator upload enabled'}
            </div>
            <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
              <div>
                <div className="text-xs uppercase text-gray-500">Rows</div>
                <div className="text-xl font-semibold text-white">{qboSummary?.row_count ?? 0}</div>
              </div>
              <div>
                <div className="text-xs uppercase text-gray-500">Insurance</div>
                <div className="text-xl font-semibold text-purple-400">{formatCurrency(qboSummary?.insurance_total ?? 0)}</div>
              </div>
              <div>
                <div className="text-xs uppercase text-gray-500">Other</div>
                <div className="text-xl font-semibold text-amber-400">{formatCurrency(qboSummary?.other_expense_total ?? 0)}</div>
              </div>
              <div>
                <div className="text-xs uppercase text-gray-500">Coverage</div>
                <div className="text-sm font-semibold text-gray-200">
                  {qboSummary?.coverage_start && qboSummary?.coverage_end
                    ? `${qboSummary.coverage_start.slice(5)}-${qboSummary.coverage_end.slice(5)}`
                    : qboSummary?.date_max ?? 'Pending'}
                </div>
              </div>
            </div>
          </div>

          <div className="w-full lg:w-[460px] space-y-3">
            <label className="block">
              <span className="sr-only">QBO expense report</span>
              <input
                type="file"
                accept=".csv,.tsv,.txt,.json,.jsonl"
                onChange={(event) => {
                  setSelectedQboFile(event.target.files?.[0] ?? null)
                  setQboImportResult(null)
                  setImportError(null)
                }}
                className="block w-full text-sm text-gray-300 file:mr-4 file:rounded-lg file:border-0 file:bg-purple-500 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-purple-400"
              />
            </label>
            {qboStatus?.api_key_required && (
              <input
                type="password"
                value={qboApiKey}
                onChange={(event) => setQboApiKey(event.target.value)}
                placeholder="QBO import key"
                className="w-full rounded-lg border border-gray-700 bg-gray-950/60 px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:border-purple-400 focus:outline-none"
              />
            )}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={importingQbo || qboImportLocked}
                onClick={() => void handleQboImport(true)}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-200 hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {importingQbo ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileCheck2 className="w-4 h-4" />}
                Preview
              </button>
              <button
                type="button"
                disabled={importingQbo || qboImportLocked}
                onClick={() => void handleQboImport(false)}
                className="inline-flex items-center gap-2 rounded-lg bg-purple-500 px-4 py-2 text-sm font-semibold text-white hover:bg-purple-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {importingQbo ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                Import
              </button>
            </div>
            {selectedQboFile && (
              <div className="text-xs text-gray-500">Selected: {selectedQboFile.name}</div>
            )}
            {qboImportResult && (
              <div className="rounded-lg border border-gray-700 bg-gray-950/50 px-3 py-2 text-sm text-gray-300">
                <span className="font-semibold text-white">{qboImportResult.dry_run ? 'Preview' : 'Import'} complete:</span>{' '}
                {qboImportResult.imported_count} new, {qboImportResult.duplicate_count} duplicate, {qboImportResult.invalid_count} invalid.
              </div>
            )}
          </div>
        </div>
      </motion.div>

      {/* Fuel Cost Trend Chart */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
        className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
      >
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <TrendingDown className="w-5 h-5 text-emerald-400" />
          Daily Fuel Cost Trend (30 Days)
        </h3>
        {trends.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={trends}>
              <defs>
                <linearGradient id="fuelGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" stroke="#6b7280" tick={{ fontSize: 11 }}
                tickFormatter={(v) => v.slice(5)} />
              <YAxis stroke="#6b7280" tick={{ fontSize: 11 }}
                tickFormatter={(v) => `$${v}`} />
              <Tooltip
                contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                labelStyle={{ color: '#9ca3af' }}
                formatter={(value: number) => [`$${value.toFixed(0)}`, 'Cost']}
              />
              <Area type="monotone" dataKey="cost" stroke="#10b981" fill="url(#fuelGradient)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-[300px] items-center justify-center rounded-lg border border-dashed border-gray-700 text-sm text-gray-500">
            Fuel cost trend appears after Geotab trips or AtoB expense imports are available.
          </div>
        )}
      </motion.div>

      {/* Vehicle Efficiency Table */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6 }}
        className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
      >
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Fuel className="w-5 h-5 text-blue-400" />
          Vehicle Fuel Efficiency (7 Days)
        </h3>
        {efficiency.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-500 uppercase border-b border-gray-800">
                  <th className="text-left py-3 px-2">Vehicle</th>
                  <th className="text-right py-3 px-2">Miles</th>
                  <th className="text-right py-3 px-2">Est. MPG</th>
                  <th className="text-right py-3 px-2">Gallons</th>
                  <th className="text-right py-3 px-2">Cost</th>
                  <th className="text-center py-3 px-2">Grade</th>
                </tr>
              </thead>
              <tbody>
                {efficiency.slice(0, 15).map((v, i) => (
                  <motion.tr
                    key={v.vehicle_id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.7 + i * 0.03 }}
                    className="border-b border-gray-800/50 hover:bg-gray-800/20"
                  >
                    <td className="py-3 px-2 font-medium">{v.vehicle_name}</td>
                    <td className="py-3 px-2 text-right text-gray-300">{v.miles.toLocaleString()}</td>
                    <td className="py-3 px-2 text-right text-gray-300">{v.est_mpg}</td>
                    <td className="py-3 px-2 text-right text-gray-300">{v.est_gallons}</td>
                    <td className="py-3 px-2 text-right text-gray-300">
                      ${((v.actual_cost ?? v.est_cost)).toLocaleString()}
                      <div className="text-[10px] uppercase tracking-wide text-gray-500">
                        {v.actual_cost === undefined ? 'Est.' : 'AtoB'}
                      </div>
                    </td>
                    <td className="py-3 px-2 text-center">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-bold ${gradeColor(v.efficiency_grade)}`}>
                        {v.efficiency_grade}
                      </span>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-center text-gray-500 py-8">No efficiency data available yet</p>
        )}
      </motion.div>
    </div>
  )
}
