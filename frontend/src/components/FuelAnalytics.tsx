import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  AlertTriangle,
  Building2,
  Database,
  DollarSign,
  FileCheck2,
  Fuel,
  Gauge,
  Loader2,
  ReceiptText,
  Target,
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
  power_automate_flow?: {
    flow_name: string
    environment: string
    flow_id: string
    connection: string
    trigger: string
    issue: string
    resolution: string
    fixed_at: string
    status: string
    failed_run_tracking_id: string
    failed_action_tracking_id: string
    next_step: string
  }
  loading_optimization_plan?: Array<{
    priority: number
    item: string
    detail: string
    status: string
  }>
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
  maintenance_cost?: number
  insurance_cost: number
  posted_insurance_cost?: number
  insurance_cost_per_mile?: number | null
  employee_cost?: number
  rental_trucks_trailers_cost?: number
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

interface EntityMarginSummary {
  miles: number
  drive_hours: number
  idle_hours: number
  operating_hours: number
  fuel_cost: number
  maintenance_cost?: number
  insurance_cost: number
  posted_insurance_cost?: number
  insurance_cost_per_mile?: number | null
  employee_cost?: number
  rental_trucks_trailers_cost?: number
  other_expense_cost: number
  k1l_orders: number
  k1l_grand_total: number
  k1l_driver_pay: number
  k1l_target_gross_margin: number
  k1l_actual_gross_margin_before_fuel: number
  k1l_actual_gross_margin_pct_before_fuel: number | null
  k1l_actual_gross_margin_after_fuel: number
  k1l_actual_gross_margin_pct_after_fuel: number | null
  k1l_revenue_per_mile: number | null
  k1l_revenue_per_drive_hour: number | null
  k1l_revenue_per_engine_hour: number | null
  k1l_driver_pay_cpm: number | null
  k1l_fuel_cpm: number | null
  k1l_fuel_plus_driver_cpm: number | null
  k1l_true_operating_cpm: number | null
  k1l_true_operating_cost: number | null
  k1l_true_operating_cost_per_drive_hour: number | null
  k1l_true_operating_cost_per_engine_hour: number | null
  k1l_profit: number | null
  k1l_profit_per_mile: number | null
  k1l_profit_per_drive_hour: number | null
  k1l_profit_per_engine_hour: number | null
  k1l_route_lh_orders?: number
  k1l_route_lh_candidate_orders?: number
  k1l_route_lh_revenue?: number
  k1l_route_lh_driver_pay?: number
  k1l_route_lh_hours?: number
  k1l_route_lh_revenue_per_hour?: number | null
  k1l_route_lh_driver_pay_per_hour?: number | null
  k1l_route_lh_direct_cost?: number | null
  k1l_route_lh_direct_cost_per_hour?: number | null
  k1l_route_lh_direct_profit?: number | null
  k1l_route_lh_direct_profit_per_hour?: number | null
  k1l_route_lh_true_operating_cost?: number | null
  k1l_route_lh_true_operating_cost_per_hour?: number | null
  k1l_route_lh_loaded_profit?: number | null
  k1l_route_lh_loaded_profit_per_hour?: number | null
  k1l_route_lh_profit?: number | null
  k1l_route_lh_profit_per_hour?: number | null
  k1l_route_lh_excluded_non_route_lh_orders?: number
  k1l_route_lh_excluded_low_revenue_orders?: number
  k1l_route_lh_excluded_short_duration_orders?: number
  k1l_route_lh_excluded_missing_duration_orders?: number
  k1l_route_lh_excluded_revenue?: number
  k1g_orders: number
  k1g_grand_total: number
  k1g_driver_pay: number
  k1g_target_gross_margin: number
  k1g_actual_gross_margin_before_overhead: number
  k1g_actual_gross_margin_pct_before_overhead: number | null
  qbo_expenses_available: boolean
}

interface WeeklyEntityMargin extends EntityMarginSummary {
  week_start: string
  week_end: string
  period_start: string
  period_end: string
}

interface EntityMarginSnapshot {
  period_start: string
  period_end: string
  generated_at: string
  source_authority: string
  projection_mode: string
  grain: string
  k1l_margin_target_pct: number
  k1g_margin_target_pct: number
  complete_k1l_cpm_available: boolean
  complete_k1l_true_cpm_available: boolean
  unresolved_sources: string[]
  true_cpm_unresolved_sources: string[]
  xcelerator_source_type: string
  sources: {
    telemetry: OperatingCostSource
    fuel: OperatingCostSource
    xcelerator_entity: OperatingCostSource
    qbo_expenses: OperatingCostSource
  }
  summary: EntityMarginSummary
  weekly: WeeklyEntityMargin[]
  excluded_delivery_centers: Record<string, number>
}

interface K1WeeklyEngineKpiSnapshot {
  period_start: string
  period_end: string
  generated_at: string
  source_authority: string
  projection_mode: string
  grain: string
  efficiency_basis?: string
  efficiency_rules?: {
    scope: string
    min_revenue: number
    min_lifecycle_hours: number
    hour_window: string
    cost_allocation?: string
    primary_cost_basis?: string
    loaded_cost_diagnostic?: string
  }
  complete_k1l_engine_kpi_available: boolean
  unresolved_sources: string[]
  xcelerator_source_type: string
  sources: {
    telemetry: OperatingCostSource
    xcelerator_entity: OperatingCostSource
    xcelerator_route_lh_efficiency?: OperatingCostSource
    operating_cost_stack: OperatingCostSource
  }
  summary: EntityMarginSummary
  weekly: WeeklyEntityMargin[]
  best_week: WeeklyEntityMargin | null
  weakest_week: WeeklyEntityMargin | null
  excluded_delivery_centers: Record<string, number>
}

interface K1OperatingCostMonth {
  added_p_and_l_ops: number
  cost_per_mile: number | null
  driver_pay: number
  fleet_maintenance: number
  fuel: number
  gross_profit: number | null
  miles: number
  month: string
  other_ops: number
  payroll: number
  profit_per_mile: number | null
  prior_cost: number
  revenue: number | null
  revenue_per_mile: number | null
  total_cost: number
}

interface K1OperatingCostKpiSnapshot {
  as_of_date?: string | null
  entity: string
  error?: string
  generated_at?: string
  method?: string
  monthly?: K1OperatingCostMonth[]
  projection_mode: 'read_only'
  revenue_source?: string
  revenue_source_status?: {
    message?: string
    row_count?: number | null
    status?: string
  }
  source?: string
  status: 'configured' | 'configuration_error' | 'not_configured'
  summary: {
    added_p_and_l_ops?: number
    cost_per_mile: number | null
    gross_profit?: number | null
    miles: number
    profit_per_mile?: number | null
    revenue?: number | null
    revenue_per_mile?: number | null
    total_cost: number
  } | null
}

interface RevenueProductivitySnapshot {
  period_start: string
  period_end: string
  period_days: number
  projection_mode: 'read_only'
  source_authority: string
  targets: {
    revenue_per_driver_week: number
    revenue_per_truck_week: number
  }
  summary: {
    revenue: number | null
    truck_count: number | null
    driver_count: number | null
    driver_source: string | null
    revenue_per_truck: number | null
    revenue_per_driver: number | null
    truck_target_delta: number | null
    driver_target_delta: number | null
    truck_target_status: string
    driver_target_status: string
  }
  sources: {
    revenue: OperatingCostSource
    trucks: OperatingCostSource
    drivers: OperatingCostSource
  }
}

interface DeliveryCenterPerformanceRow {
  delivery_center: string
  entity: string
  orders: number
  pickup_orders: number
  pickup_measured_orders: number
  pickup_on_time_orders: number
  pickup_late_orders: number
  pickup_missing_orders: number
  pickup_missing_schedule_orders: number
  pickup_missing_actual_orders: number
  pickup_on_time_pct: number | null
  pickup_late_pct: number | null
  pickup_proof_coverage_pct: number | null
  pickup_avg_late_minutes: number | null
  pickup_max_late_minutes: number | null
  delivery_orders: number
  delivery_measured_orders: number
  delivery_on_time_orders: number
  delivery_late_orders: number
  delivery_missing_orders: number
  delivery_missing_schedule_orders: number
  delivery_missing_actual_orders: number
  delivery_on_time_pct: number | null
  delivery_late_pct: number | null
  delivery_proof_coverage_pct: number | null
  delivery_avg_late_minutes: number | null
  delivery_max_late_minutes: number | null
}

interface DeliveryCenterPerformanceSnapshot {
  period_start: string
  period_end: string
  generated_at: string
  source_authority: string
  projection_mode: 'read_only'
  grain: 'delivery_center'
  rules: {
    on_time_tolerance_minutes: number
    pickup_actual_basis?: string
    delivery_actual_basis?: string
    deadline_basis?: string
  }
  summary: DeliveryCenterPerformanceRow | null
  delivery_centers: DeliveryCenterPerformanceRow[]
  source: OperatingCostSource & {
    table?: string
    missing_column_families?: string[]
  }
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

const humanStatusLabel = (value?: string | null) => String(value || '').replace(/_/g, ' ')

const formatNumber = (value?: number | null, maximumFractionDigits = 0) => (
  value === null || value === undefined
    ? 'Pending'
    : value.toLocaleString(undefined, { maximumFractionDigits })
)

const formatRate = (value?: number | null, suffix = '/mi') => (
  value === null || value === undefined ? 'Pending' : `${formatCurrency(value, 2)}${suffix}`
)

const formatPercent = (value?: number | null) => (
  value === null || value === undefined ? 'Pending' : `${(value * 100).toFixed(1)}%`
)

const formatDeltaCurrency = (value?: number | null) => {
  if (value === null || value === undefined) return 'Pending'
  const sign = value > 0 ? '+' : ''
  return `${sign}${formatCurrency(value)}`
}

const rateDelta = (left?: number | null, right?: number | null) => (
  left === null || left === undefined || right === null || right === undefined
    ? null
    : Number((left - right).toFixed(3))
)

const finiteValue = (value?: number | null) => (
  value === null || value === undefined || !Number.isFinite(Number(value))
    ? null
    : Number(value)
)

const safeRatio = (numerator?: number | null, denominator?: number | null, digits = 4) => {
  const resolvedNumerator = finiteValue(numerator)
  const resolvedDenominator = finiteValue(denominator)
  if (resolvedNumerator === null || resolvedDenominator === null || resolvedDenominator <= 0) {
    return null
  }
  return Number((resolvedNumerator / resolvedDenominator).toFixed(digits))
}

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
  const [entityMargin, setEntityMargin] = useState<EntityMarginSnapshot | null>(null)
  const [k1OperatingKpi, setK1OperatingKpi] = useState<K1OperatingCostKpiSnapshot | null>(null)
  const [k1WeeklyEngineKpi, setK1WeeklyEngineKpi] = useState<K1WeeklyEngineKpiSnapshot | null>(null)
  const [revenueProductivity, setRevenueProductivity] = useState<RevenueProductivitySnapshot | null>(null)
  const [deliveryCenterPerformance, setDeliveryCenterPerformance] = useState<DeliveryCenterPerformanceSnapshot | null>(null)
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

      const [k1Kpi, weeklyEngineKpi, productivity, deliveryPerformance] = await Promise.all([
        fetchJson<K1OperatingCostKpiSnapshot | null>(
          '/api/fuel/k1l-operating-kpi',
          null,
          90000,
        ),
        fetchJson<K1WeeklyEngineKpiSnapshot | null>(
          `/api/fuel/k1l-weekly-engine-kpi?start=${ytdStart}`,
          null,
          90000,
        ),
        fetchJson<RevenueProductivitySnapshot | null>(
          '/api/fuel/revenue-productivity?days=7',
          null,
          90000,
        ),
        fetchJson<DeliveryCenterPerformanceSnapshot | null>(
          `/api/fuel/delivery-center-performance?start=${ytdStart}`,
          null,
          90000,
        ),
      ])
      setK1OperatingKpi(k1Kpi)
      setK1WeeklyEngineKpi(weeklyEngineKpi)
      setRevenueProductivity(productivity)
      setDeliveryCenterPerformance(deliveryPerformance)

      void Promise.all([
        fetchJson<OperatingCostSnapshot | null>(
          `/api/fuel/operating-cost?start=${ytdStart}`,
          null,
          30000,
        ),
        fetchJson<EntityMarginSnapshot | null>(
          `/api/fuel/entity-margin?start=${ytdStart}`,
          null,
          30000,
        ),
      ]).then(([oc, em]) => {
        setOperatingCost(oc)
        setEntityMargin(em)
      })
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
  const atobFlow = sharePointStatus?.power_automate_flow
  const optimizationPlan = sharePointStatus?.loading_optimization_plan || []
  const operatingSummary = operatingCost?.summary
  const completeOperatingCost = Boolean(operatingCost?.complete_cost_available)
  const unresolvedCostSources = operatingCost?.unresolved_sources.join(', ') || ''
  const entitySummary = entityMargin?.summary
  const weeklyEngineSummary = k1WeeklyEngineKpi?.summary
  const marginSummary = entitySummary ?? weeklyEngineSummary
  const unresolvedEntitySources = entityMargin?.unresolved_sources.join(', ') || ''
  const monthlyK1CpmRows = (k1OperatingKpi?.monthly ?? []).filter((row) => row.cost_per_mile !== null)
  const k1OperatingSummary = k1OperatingKpi?.summary
  const k1lFinalCpm = k1OperatingSummary?.cost_per_mile ?? null
  const k1lRevenuePerMile = k1OperatingSummary?.revenue_per_mile ?? entitySummary?.k1l_revenue_per_mile ?? null
  const k1lProfitPerMile = k1OperatingSummary?.profit_per_mile ?? rateDelta(k1lRevenuePerMile, k1lFinalCpm)
  const completeEntityCpm = Boolean(entityMargin?.complete_k1l_cpm_available || k1lFinalCpm !== null)
  const completeEntityTrueCpm = Boolean(entityMargin?.complete_k1l_true_cpm_available || k1lFinalCpm !== null)
  const k1lProfitPerMileLabel = k1OperatingSummary?.profit_per_mile !== undefined && k1OperatingSummary?.profit_per_mile !== null
    ? 'Revenue/Mile - Final CPM'
    : 'Revenue/Mile - CPM'
  const k1lEngineHours = finiteValue(weeklyEngineSummary?.operating_hours ?? entitySummary?.operating_hours)
  const k1lTotalCost = finiteValue(k1OperatingSummary?.total_cost ?? entitySummary?.k1l_true_operating_cost)
  const k1lRevenue = finiteValue(k1OperatingSummary?.revenue ?? entitySummary?.k1l_grand_total)
  const k1lGrossProfit = finiteValue(k1OperatingSummary?.gross_profit) ?? (
    k1lRevenue !== null && k1lTotalCost !== null ? Number((k1lRevenue - k1lTotalCost).toFixed(2)) : null
  )
  const k1lSummaryRevenuePerEngineHour = safeRatio(k1lRevenue, k1lEngineHours) ?? entitySummary?.k1l_revenue_per_engine_hour ?? null
  const k1lSummaryCostPerEngineHour = safeRatio(k1lTotalCost, k1lEngineHours) ?? entitySummary?.k1l_true_operating_cost_per_engine_hour ?? null
  const k1lSummaryProfitPerEngineHour = safeRatio(k1lGrossProfit, k1lEngineHours) ?? entitySummary?.k1l_profit_per_engine_hour ?? null
  const useRouteLhEfficiency = k1WeeklyEngineKpi?.efficiency_basis === 'route_lh_qualified'
  const routeLhSummaryHours = finiteValue(weeklyEngineSummary?.k1l_route_lh_hours)
  const routeLhSummaryRph = finiteValue(weeklyEngineSummary?.k1l_route_lh_revenue_per_hour)
  const routeLhSummaryCostHr = finiteValue(
    weeklyEngineSummary?.k1l_route_lh_direct_cost_per_hour
      ?? weeklyEngineSummary?.k1l_route_lh_driver_pay_per_hour,
  )
  const routeLhSummaryProfitHr = finiteValue(
    weeklyEngineSummary?.k1l_route_lh_direct_profit_per_hour
      ?? weeklyEngineSummary?.k1l_route_lh_profit_per_hour,
  )
  const routeLhLoadedCostHr = finiteValue(weeklyEngineSummary?.k1l_route_lh_true_operating_cost_per_hour)
  const displayedSummaryHours = useRouteLhEfficiency ? routeLhSummaryHours : k1lEngineHours
  const displayedSummaryRph = useRouteLhEfficiency ? routeLhSummaryRph : k1lSummaryRevenuePerEngineHour
  const displayedSummaryCostHr = useRouteLhEfficiency ? routeLhSummaryCostHr : k1lSummaryCostPerEngineHour
  const displayedSummaryProfitHr = useRouteLhEfficiency ? routeLhSummaryProfitHr : k1lSummaryProfitPerEngineHour
  const routeLhExcludedOrders = useRouteLhEfficiency
    ? Number(weeklyEngineSummary?.k1l_route_lh_excluded_low_revenue_orders ?? 0)
      + Number(weeklyEngineSummary?.k1l_route_lh_excluded_short_duration_orders ?? 0)
      + Number(weeklyEngineSummary?.k1l_route_lh_excluded_missing_duration_orders ?? 0)
      + Number(weeklyEngineSummary?.k1l_route_lh_excluded_non_route_lh_orders ?? 0)
    : 0
  const entitySourceCards = (entityMargin?.sources ?? k1WeeklyEngineKpi?.sources ?? {}) as Record<string, OperatingCostSource>
  const entityTrendRows = (entityMargin?.weekly.length ?? 0) > 0
    ? entityMargin?.weekly ?? []
    : k1WeeklyEngineKpi?.weekly ?? []
  const weeklyK1lRows = (k1WeeklyEngineKpi?.weekly ?? entityMargin?.weekly ?? []).map((row) => {
    const routeHours = finiteValue(row.k1l_route_lh_hours)
    const routeOrders = Number(row.k1l_route_lh_orders ?? 0)
    const routeRevenue = finiteValue(row.k1l_route_lh_revenue)
    const routeCost = finiteValue(row.k1l_route_lh_direct_cost ?? row.k1l_route_lh_driver_pay)
    const routeCostHr = finiteValue(row.k1l_route_lh_direct_cost_per_hour ?? row.k1l_route_lh_driver_pay_per_hour)
    const routeProfit = finiteValue(row.k1l_route_lh_direct_profit ?? row.k1l_route_lh_profit)
    const routeProfitHr = finiteValue(row.k1l_route_lh_direct_profit_per_hour ?? row.k1l_route_lh_profit_per_hour)
    const routeRph = finiteValue(row.k1l_route_lh_revenue_per_hour)
    const useRouteRow = useRouteLhEfficiency && routeOrders > 0 && routeHours !== null && routeHours > 0
    const rowEngineHours = useRouteRow ? routeHours : finiteValue(row.operating_hours)
    const rowRevenue = useRouteRow ? routeRevenue : finiteValue(row.k1l_grand_total)
    const rowRevenuePerEngineHour = useRouteRow
      ? routeRph ?? safeRatio(rowRevenue, rowEngineHours)
      : safeRatio(rowRevenue, rowEngineHours) ?? row.k1l_revenue_per_engine_hour
    const rowCostPerEngineHour = useRouteRow
      ? routeCostHr ?? safeRatio(routeCost, rowEngineHours)
      : finiteValue(row.k1l_true_operating_cost_per_engine_hour) ?? k1lSummaryCostPerEngineHour
    const rowAllocatedCost = useRouteRow
      ? routeCost
      : rowCostPerEngineHour !== null && rowCostPerEngineHour !== undefined && rowEngineHours !== null
        ? Number((Number(rowCostPerEngineHour) * rowEngineHours).toFixed(2))
        : finiteValue(row.k1l_true_operating_cost)
    const rowProfit = rowRevenue !== null && rowAllocatedCost !== null
      ? Number((rowRevenue - rowAllocatedCost).toFixed(2))
      : useRouteRow
        ? routeProfit
        : finiteValue(row.k1l_profit)
    const rowProfitPerEngineHour = useRouteRow
      ? routeProfitHr ?? safeRatio(rowProfit, rowEngineHours)
      : safeRatio(rowProfit, rowEngineHours) ?? row.k1l_profit_per_engine_hour

    return {
      ...row,
      k1l_orders: useRouteRow ? routeOrders : row.k1l_orders,
      k1l_grand_total: rowRevenue ?? row.k1l_grand_total,
      operating_hours: rowEngineHours ?? row.operating_hours,
      k1l_revenue_per_engine_hour: rowRevenuePerEngineHour,
      k1l_true_operating_cost: rowAllocatedCost,
      k1l_true_operating_cost_per_engine_hour: rowCostPerEngineHour,
      k1l_profit: rowProfit,
      k1l_profit_per_engine_hour: rowProfitPerEngineHour,
      k1l_profit_per_mile: safeRatio(rowProfit, row.miles) ?? row.k1l_profit_per_mile,
    }
  }).filter((row) => Number(row.k1l_orders) > 0 && finiteValue(row.k1l_revenue_per_engine_hour) !== null)
  const rankedK1lWeeks = weeklyK1lRows.filter((row) => finiteValue(row.k1l_profit_per_engine_hour) !== null)
  const bestK1lWeek = rankedK1lWeeks.reduce<WeeklyEntityMargin | null>((best, row) => {
    if (!best) return row
    return Number(row.k1l_profit_per_engine_hour) > Number(best.k1l_profit_per_engine_hour) ? row : best
  }, null)
  const weakestK1lWeek = rankedK1lWeeks.reduce<WeeklyEntityMargin | null>((weakest, row) => {
    if (!weakest) return row
    return Number(row.k1l_profit_per_engine_hour) < Number(weakest.k1l_profit_per_engine_hour) ? row : weakest
  }, null)
  const k1OperatingRevenueSourceStatus = k1OperatingKpi?.revenue_source_status?.status || 'not_configured'
  const k1OperatingRevenueSourceLabel = k1OperatingKpi?.revenue_source === 'xcelerator_fabric_warehouse_sql'
    ? 'Xcelerator Fabric Warehouse SQL'
    : k1OperatingKpi?.revenue_source === 'xcelerator_ceo_powerbi'
      ? 'Xcelerator CEO Power BI'
      : 'Monthly JSON fallback'
  const k1OperatingRevenueSourceClass = k1OperatingRevenueSourceStatus === 'healthy'
    ? 'text-emerald-400'
    : k1OperatingRevenueSourceStatus === 'awaiting_feed'
      ? 'text-amber-400'
      : 'text-red-300'
  const productivitySummary = revenueProductivity?.summary
  const truckTarget = revenueProductivity?.targets.revenue_per_truck_week ?? 7000
  const driverTarget = revenueProductivity?.targets.revenue_per_driver_week ?? 5000
  const truckProductivityClass = productivitySummary?.truck_target_status === 'above_target'
    ? 'text-emerald-400'
    : productivitySummary?.truck_target_status === 'below_target'
      ? 'text-amber-300'
      : 'text-gray-400'
  const driverProductivityClass = productivitySummary?.driver_target_status === 'above_target'
    ? 'text-emerald-400'
    : productivitySummary?.driver_target_status === 'below_target'
      ? 'text-amber-300'
      : 'text-gray-400'
  const deliveryPerformanceRows = deliveryCenterPerformance?.delivery_centers ?? []
  const deliveryPerformanceSummary = deliveryCenterPerformance?.summary
  const deliveryPerformanceSource = deliveryCenterPerformance?.source
  const deliveryPerformanceChartRows = deliveryPerformanceRows.slice(0, 8)
  const deliveryPerformanceSourceClass = deliveryPerformanceSource?.status === 'healthy'
    ? 'text-emerald-400'
    : deliveryPerformanceSource?.status === 'partial' || deliveryPerformanceSource?.status === 'awaiting_feed'
      ? 'text-amber-300'
      : 'text-red-300'
  const missingPerformanceProof =
    Number(deliveryPerformanceSummary?.pickup_missing_orders ?? 0)
    + Number(deliveryPerformanceSummary?.delivery_missing_orders ?? 0)

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

      {/* Entity Margin and CPM */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
      >
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-5">
          <div>
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Building2 className="w-5 h-5 text-emerald-400" />
              K1 Entity CPM & Margin
            </h3>
            <div className="mt-1 text-sm text-gray-400">
              {entityMargin?.period_start ?? k1WeeklyEngineKpi?.period_start ?? 'YTD'} to {entityMargin?.period_end ?? k1WeeklyEngineKpi?.period_end ?? k1OperatingKpi?.as_of_date ?? 'today'} · {completeEntityCpm ? 'K1L CPM ready' : `K1L CPM pending${unresolvedEntitySources ? ` · ${unresolvedEntitySources}` : ''}`}
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            {Object.entries(entitySourceCards).map(([key, source]) => (
              <div key={key} className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
                <div className="text-[10px] uppercase tracking-wide text-gray-500">{key.replace('_', ' ')}</div>
                <div className={source.status === 'healthy' ? 'text-emerald-400' : source.status === 'awaiting_feed' ? 'text-amber-400' : 'text-red-300'}>
                  {source.status.replace('_', ' ')}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 xl:grid-cols-5 gap-4 mb-6">
          <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-4">
            <div className="text-xs uppercase text-gray-500">K1L Final CPM</div>
            <div className="mt-1 text-2xl font-bold text-emerald-400">
              {formatRate(k1lFinalCpm ?? marginSummary?.k1l_true_operating_cpm)}
            </div>
            <div className="mt-1 text-xs text-gray-500">{formatCurrency(k1lTotalCost ?? marginSummary?.k1l_true_operating_cost)} total cost</div>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-4">
            <div className="text-xs uppercase text-gray-500">K1L Revenue / Mile</div>
            <div className="mt-1 text-2xl font-bold text-teal-300">
              {formatRate(k1lRevenuePerMile)}
            </div>
            <div className="mt-1 text-xs text-gray-500">Xcelerator revenue / Geotab miles</div>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-4">
            <div className="text-xs uppercase text-gray-500">K1L Profit / Mi</div>
            <div className="mt-1 text-2xl font-bold text-blue-400">
              {formatRate(completeEntityTrueCpm ? k1lProfitPerMile : null)}
            </div>
            <div className="mt-1 text-xs text-gray-500">{k1lProfitPerMileLabel}</div>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-4">
            <div className="flex items-center gap-1 text-xs uppercase text-gray-500">
              <Target className="h-3.5 w-3.5" /> K1L GM Target
            </div>
            <div className="mt-1 text-2xl font-bold text-white">{formatCurrency(marginSummary?.k1l_target_gross_margin)}</div>
            <div className="mt-1 text-xs text-gray-500">72% · actual {formatPercent(marginSummary?.k1l_actual_gross_margin_pct_before_fuel)}</div>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-4">
            <div className="flex items-center gap-1 text-xs uppercase text-gray-500">
              <Target className="h-3.5 w-3.5" /> K1G GM Target
            </div>
            <div className="mt-1 text-2xl font-bold text-purple-400">{formatCurrency(marginSummary?.k1g_target_gross_margin)}</div>
            <div className="mt-1 text-xs text-gray-500">20% · actual {formatPercent(marginSummary?.k1g_actual_gross_margin_pct_before_overhead)}</div>
          </div>
        </div>

        {entityTrendRows.length > 0 ? (
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={entityTrendRows}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="week_start" stroke="#6b7280" tick={{ fontSize: 11 }} tickFormatter={(v) => String(v).slice(5)} />
              <YAxis yAxisId="margin" stroke="#6b7280" tick={{ fontSize: 11 }} tickFormatter={(v) => `$${Number(v) / 1000}k`} />
              <YAxis yAxisId="rate" orientation="right" stroke="#6b7280" tick={{ fontSize: 11 }} tickFormatter={(v) => `$${Number(v).toFixed(2)}`} />
              <Tooltip
                contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                labelStyle={{ color: '#9ca3af' }}
                formatter={(value: number, name: string) => [
                  name.includes('CPM') || name.includes('Mile')
                    ? formatRate(value)
                    : formatCurrency(value),
                  name,
                ]}
              />
              <Legend />
              <Bar yAxisId="margin" dataKey="k1l_target_gross_margin" name="K1L 72% GM Target" fill="#10b981" />
              <Bar yAxisId="margin" dataKey="k1g_target_gross_margin" name="K1G 20% GM Target" fill="#a855f7" />
              <Line yAxisId="rate" type="monotone" dataKey="k1l_revenue_per_mile" name="K1L Revenue / Mile" stroke="#f8fafc" strokeWidth={2} dot={false} />
              <Line yAxisId="rate" type="monotone" dataKey="k1l_fuel_plus_driver_cpm" name="K1L Fuel+Driver CPM" stroke="#38bdf8" strokeWidth={2} dot={false} />
              <Line yAxisId="rate" type="monotone" dataKey="k1l_true_operating_cpm" name="K1L True CPM" stroke="#fb7185" strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-[260px] items-center justify-center rounded-lg border border-dashed border-gray-700 text-sm text-gray-500">
            Entity margin trend appears after Xcelerator delivery-center rows are available.
          </div>
        )}
      </motion.div>

      {/* K1L Weekly Engine-Hour Profitability */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.405 }}
        className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
      >
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-5">
          <div>
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Gauge className="w-5 h-5 text-cyan-300" />
              {useRouteLhEfficiency ? 'K1L Route/LH Revenue / Cost per Hr' : 'K1L Weekly Revenue / Cost per Engine Hr'}
            </h3>
            <div className="mt-1 text-sm text-gray-400">
              {useRouteLhEfficiency
                ? 'Qualified rows only: revenue >= $1,000 and start-to-finish >= 12 hrs · cost/hr uses Xcelerator driver pay per lifecycle hour'
                : 'Engine hrs = Geotab drive + idle hours · cost stack allocated by engine-hour share'}
            </div>
            {useRouteLhEfficiency && (
              <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-400">
                <span className="rounded border border-cyan-500/20 bg-cyan-950/20 px-2 py-1 text-cyan-200">
                  {formatNumber(weeklyEngineSummary?.k1l_route_lh_orders, 0)} qualified
                </span>
                <span className="rounded border border-amber-500/20 bg-amber-950/10 px-2 py-1 text-amber-200">
                  {formatNumber(routeLhExcludedOrders, 0)} excluded by rule
                </span>
                <span className="rounded border border-gray-700 bg-gray-950/40 px-2 py-1 text-gray-300">
                  Loaded stack diagnostic: {formatRate(routeLhLoadedCostHr, '/hr')}
                </span>
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-gray-500">RPH</div>
              <div className="text-cyan-300">{formatRate(displayedSummaryRph, '/hr')}</div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-gray-500">{useRouteLhEfficiency ? 'Driver Pay / Hr' : 'Cost / Hr'}</div>
              <div className="text-rose-300">{formatRate(displayedSummaryCostHr, '/hr')}</div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-gray-500">{useRouteLhEfficiency ? 'Gross Profit / Hr' : 'Profit / Hr'}</div>
              <div className="text-amber-300">{formatRate(displayedSummaryProfitHr, '/hr')}</div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-gray-500">{useRouteLhEfficiency ? 'Route/LH Hrs' : 'Engine Hrs'}</div>
              <div className="text-white">{formatNumber(displayedSummaryHours, 1)}</div>
            </div>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2 mb-5">
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-950/20 px-4 py-3">
            <div className="text-[10px] uppercase tracking-wide text-emerald-300">Best week</div>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-xl font-semibold text-white">{bestK1lWeek?.week_start ?? 'Pending'}</span>
              <span className="text-sm text-emerald-300">{formatRate(bestK1lWeek?.k1l_profit_per_engine_hour, '/hr')}</span>
              <span className="text-sm text-gray-400">{formatCurrency(bestK1lWeek?.k1l_profit)} {useRouteLhEfficiency ? 'gross profit' : 'profit'}</span>
            </div>
          </div>
          <div className="rounded-lg border border-amber-500/20 bg-amber-950/10 px-4 py-3">
            <div className="text-[10px] uppercase tracking-wide text-amber-300">Weakest week</div>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-xl font-semibold text-white">{weakestK1lWeek?.week_start ?? 'Pending'}</span>
              <span className="text-sm text-amber-300">{formatRate(weakestK1lWeek?.k1l_profit_per_engine_hour, '/hr')}</span>
              <span className="text-sm text-gray-400">{formatCurrency(weakestK1lWeek?.k1l_profit)} {useRouteLhEfficiency ? 'gross profit' : 'profit'}</span>
            </div>
          </div>
        </div>

        {weeklyK1lRows.length > 0 ? (
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_460px]">
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={weeklyK1lRows}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="week_start" stroke="#6b7280" tick={{ fontSize: 11 }} tickFormatter={(v) => String(v).slice(5)} />
                <YAxis yAxisId="dollars" stroke="#6b7280" tick={{ fontSize: 11 }} tickFormatter={(v) => `$${Number(v) / 1000}k`} />
                <YAxis yAxisId="rate" orientation="right" stroke="#6b7280" tick={{ fontSize: 11 }} tickFormatter={(v) => `$${Number(v).toFixed(0)}`} />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                  labelStyle={{ color: '#9ca3af' }}
                  formatter={(value: number, name: string) => {
                    if (name.includes('/Hr')) return [formatRate(value, '/hr'), name]
                    if (name === 'Engine Hrs') return [formatNumber(value, 1), name]
                    return [formatCurrency(value), name]
                  }}
                />
                <Legend />
                <Bar yAxisId="dollars" dataKey="k1l_grand_total" name={useRouteLhEfficiency ? 'Qualified Revenue' : 'Revenue'} fill="#06b6d4" radius={[4, 4, 0, 0]} />
                <Bar yAxisId="dollars" dataKey="k1l_true_operating_cost" name={useRouteLhEfficiency ? 'Driver Pay' : 'Cost (alloc)'} fill="#f43f5e" radius={[4, 4, 0, 0]} />
                <Line yAxisId="rate" type="monotone" dataKey="k1l_revenue_per_engine_hour" name="RPH /Hr" stroke="#67e8f9" strokeWidth={3} dot={{ r: 4 }} connectNulls />
                <Line yAxisId="rate" type="monotone" dataKey="k1l_true_operating_cost_per_engine_hour" name={useRouteLhEfficiency ? 'Pay /Hr' : 'Cost /Hr'} stroke="#fb7185" strokeWidth={3} dot={{ r: 4 }} connectNulls />
                <Line yAxisId="rate" type="monotone" dataKey="k1l_profit_per_engine_hour" name={useRouteLhEfficiency ? 'Gross Profit /Hr' : 'Profit /Hr'} stroke="#facc15" strokeWidth={2} dot={{ r: 3 }} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>

            <div className="overflow-x-auto overflow-y-hidden rounded-lg border border-gray-800 bg-gray-950/30">
              <div className="grid min-w-[620px] grid-cols-[64px_repeat(3,minmax(104px,1fr))_minmax(108px,1fr)_80px] gap-3 border-b border-gray-800 px-3 py-2 text-[11px] uppercase tracking-wide text-gray-500">
                <span className="whitespace-nowrap">Week</span>
                <span className="whitespace-nowrap text-right">RPH</span>
                <span className="whitespace-nowrap text-right">{useRouteLhEfficiency ? 'Pay/Hr' : 'Cost/Hr'}</span>
                <span className="whitespace-nowrap text-right">{useRouteLhEfficiency ? 'Gross/Hr' : 'Profit/Hr'}</span>
                <span className="whitespace-nowrap text-right">Profit</span>
                <span className="whitespace-nowrap text-right">{useRouteLhEfficiency ? 'Hours' : 'Eng Hrs'}</span>
              </div>
              <div className="max-h-[280px] divide-y divide-gray-800 overflow-y-auto text-sm">
                {weeklyK1lRows.map((row) => (
                  <div key={row.week_start} className="grid min-w-[620px] grid-cols-[64px_repeat(3,minmax(104px,1fr))_minmax(108px,1fr)_80px] gap-3 px-3 py-2">
                    <span className="whitespace-nowrap font-medium text-white">{row.week_start.slice(5)}</span>
                    <span className="whitespace-nowrap text-right font-semibold text-cyan-300">{formatRate(row.k1l_revenue_per_engine_hour, '/hr')}</span>
                    <span className="whitespace-nowrap text-right font-semibold text-rose-300">{formatRate(row.k1l_true_operating_cost_per_engine_hour, '/hr')}</span>
                    <span className="whitespace-nowrap text-right font-semibold text-amber-300">{formatRate(row.k1l_profit_per_engine_hour, '/hr')}</span>
                    <span className="whitespace-nowrap text-right text-gray-300">{formatCurrency(row.k1l_profit)}</span>
                    <span className="whitespace-nowrap text-right text-gray-400">{formatNumber(row.operating_hours, 1)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex h-[260px] items-center justify-center rounded-lg border border-dashed border-gray-700 text-sm text-gray-500">
            Weekly engine-hour profitability appears after Geotab hours, Xcelerator revenue, and operating costs are available.
          </div>
        )}
      </motion.div>

      {/* Delivery Center On-Time Performance */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.407 }}
        className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
      >
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-5">
          <div>
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Target className="w-5 h-5 text-emerald-300" />
              Delivery Center Pickup / Delivery On-Time
            </h3>
            <div className="mt-1 text-sm text-gray-400">
              {deliveryCenterPerformance?.period_start ?? 'YTD'} to {deliveryCenterPerformance?.period_end ?? 'today'} · Xcelerator ReviewOrders actuals vs target windows · {deliveryCenterPerformance?.rules.on_time_tolerance_minutes ?? 15} min tolerance
            </div>
            <div className="mt-1 text-xs text-gray-500">
              Source: {deliveryPerformanceSource?.table ?? 'ReviewOrders'} ·{' '}
              <span className={deliveryPerformanceSourceClass}>
                {(deliveryPerformanceSource?.status ?? 'pending').replace('_', ' ')}
              </span>
              {deliveryPerformanceSource?.message ? ` · ${deliveryPerformanceSource.message}` : ''}
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-gray-500">Centers</div>
              <div className="text-white">{formatNumber(deliveryPerformanceRows.length)}</div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-gray-500">Pickup OTD</div>
              <div className="text-emerald-300">{formatPercent(deliveryPerformanceSummary?.pickup_on_time_pct)}</div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-gray-500">Delivery OTD</div>
              <div className="text-cyan-300">{formatPercent(deliveryPerformanceSummary?.delivery_on_time_pct)}</div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-gray-500">Missing Proof</div>
              <div className="text-amber-300">{formatNumber(missingPerformanceProof)}</div>
            </div>
          </div>
        </div>

        {deliveryPerformanceRows.length > 0 ? (
          <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_760px]">
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={deliveryPerformanceChartRows}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="delivery_center" stroke="#6b7280" tick={{ fontSize: 11 }} interval={0} tickFormatter={(v) => String(v).replace('K1 ', '')} />
                <YAxis yAxisId="pct" domain={[0, 1]} stroke="#6b7280" tick={{ fontSize: 11 }} tickFormatter={(v) => `${(Number(v) * 100).toFixed(0)}%`} />
                <YAxis yAxisId="orders" orientation="right" stroke="#6b7280" tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                  labelStyle={{ color: '#9ca3af' }}
                  formatter={(value: number, name: string) => {
                    if (name.includes('OTD') || name.includes('Proof')) return [formatPercent(value), name]
                    return [formatNumber(value), name]
                  }}
                />
                <Legend />
                <Bar yAxisId="pct" dataKey="pickup_on_time_pct" name="Pickup OTD" fill="#34d399" radius={[4, 4, 0, 0]} />
                <Bar yAxisId="pct" dataKey="delivery_on_time_pct" name="Delivery OTD" fill="#22d3ee" radius={[4, 4, 0, 0]} />
                <Line yAxisId="orders" type="monotone" dataKey="orders" name="Orders" stroke="#facc15" strokeWidth={2} dot={{ r: 3 }} />
              </ComposedChart>
            </ResponsiveContainer>

            <div className="overflow-x-auto overflow-y-hidden rounded-lg border border-gray-800 bg-gray-950/30">
              <div className="grid min-w-[760px] grid-cols-[minmax(170px,1.4fr)_72px_repeat(3,minmax(92px,1fr))_repeat(3,minmax(92px,1fr))] gap-3 border-b border-gray-800 px-3 py-2 text-[11px] uppercase tracking-wide text-gray-500">
                <span>Delivery Center</span>
                <span className="text-right">Orders</span>
                <span className="text-right">Pickup OTD</span>
                <span className="text-right">P Late</span>
                <span className="text-right">P Missing</span>
                <span className="text-right">Delivery OTD</span>
                <span className="text-right">D Late</span>
                <span className="text-right">D Missing</span>
              </div>
              <div className="max-h-[260px] divide-y divide-gray-800 overflow-y-auto text-sm">
                {deliveryPerformanceRows.map((row) => (
                  <div key={row.delivery_center} className="grid min-w-[760px] grid-cols-[minmax(170px,1.4fr)_72px_repeat(3,minmax(92px,1fr))_repeat(3,minmax(92px,1fr))] gap-3 px-3 py-2">
                    <div className="min-w-0">
                      <div className="truncate font-medium text-white">{row.delivery_center}</div>
                      <div className="truncate text-[11px] text-gray-500">{row.entity}</div>
                    </div>
                    <span className="whitespace-nowrap text-right text-gray-300">{formatNumber(row.orders)}</span>
                    <span className="whitespace-nowrap text-right font-semibold text-emerald-300">{formatPercent(row.pickup_on_time_pct)}</span>
                    <span className="whitespace-nowrap text-right text-rose-300">{formatNumber(row.pickup_late_orders)}</span>
                    <span className="whitespace-nowrap text-right text-amber-300">{formatNumber(row.pickup_missing_orders)}</span>
                    <span className="whitespace-nowrap text-right font-semibold text-cyan-300">{formatPercent(row.delivery_on_time_pct)}</span>
                    <span className="whitespace-nowrap text-right text-rose-300">{formatNumber(row.delivery_late_orders)}</span>
                    <span className="whitespace-nowrap text-right text-amber-300">{formatNumber(row.delivery_missing_orders)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex h-[260px] items-center justify-center rounded-lg border border-dashed border-gray-700 px-6 text-center text-sm text-gray-500">
            {deliveryPerformanceSource?.message || 'Delivery-center on-time performance appears after Xcelerator ReviewOrders target and actual timestamps are available.'}
          </div>
        )}
      </motion.div>

      {/* K1L Monthly Final CPM Trend */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.41 }}
        className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
      >
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-5">
          <div>
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-emerald-400" />
              K1L Monthly Final CPM Trend
            </h3>
            <div className="mt-1 text-sm text-gray-400">
              {k1OperatingKpi?.as_of_date ? `Finalized through ${k1OperatingKpi.as_of_date}` : 'Finalized monthly snapshot'} · {k1OperatingKpi?.source || 'QBO + Xcelerator + AtoB + Geotab'}
            </div>
            <div className="mt-1 text-xs text-gray-500">
              CPM: Geotab miles + QBO/AtoB/Xcelerator cost stack · Revenue / Mile: {k1OperatingRevenueSourceLabel}{' '}
              <span className={k1OperatingRevenueSourceClass}>({k1OperatingRevenueSourceStatus.replace('_', ' ')})</span>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-sm">
            <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-gray-500">Final CPM</div>
              <div className="text-emerald-400">{formatRate(k1lFinalCpm)}</div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-gray-500">Revenue / Mile</div>
              <div className="text-teal-300">{formatRate(k1lRevenuePerMile)}</div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-gray-500">Profit / Mi</div>
              <div className="text-amber-300">{formatRate(k1lProfitPerMile)}</div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-gray-500">Total Cost</div>
              <div className="text-white">{formatCurrency(k1OperatingSummary?.total_cost)}</div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-gray-500">Miles</div>
              <div className="text-purple-300">{formatNumber(k1OperatingSummary?.miles)}</div>
            </div>
          </div>
        </div>

        {monthlyK1CpmRows.length > 0 ? (
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_440px]">
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={monthlyK1CpmRows}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="month" stroke="#6b7280" tick={{ fontSize: 11 }} tickFormatter={(v) => String(v).slice(5)} />
                <YAxis yAxisId="cost" stroke="#6b7280" tick={{ fontSize: 11 }} tickFormatter={(v) => `$${Number(v) / 1000}k`} />
                <YAxis yAxisId="rate" orientation="right" stroke="#6b7280" tick={{ fontSize: 11 }} tickFormatter={(v) => `$${Number(v).toFixed(2)}`} />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                  labelStyle={{ color: '#9ca3af' }}
                  formatter={(value: number, name: string) => {
                    if (name === 'Final CPM') return [formatRate(value), name]
                    if (name === 'Revenue / Mile') return [formatRate(value), name]
                    if (name === 'Profit/Mi') return [formatRate(value), name]
                    if (name === 'Miles') return [formatNumber(value), name]
                    return [formatCurrency(value), name]
                  }}
                />
                <Legend />
                <Bar yAxisId="cost" dataKey="total_cost" name="Total Cost" fill="#10b981" radius={[4, 4, 0, 0]} />
                <Line yAxisId="rate" type="monotone" dataKey="cost_per_mile" name="Final CPM" stroke="#f8fafc" strokeWidth={3} dot={{ r: 4 }} />
                <Line yAxisId="rate" type="monotone" dataKey="revenue_per_mile" name="Revenue / Mile" stroke="#34d399" strokeWidth={3} dot={{ r: 4 }} connectNulls />
                <Line yAxisId="rate" type="monotone" dataKey="profit_per_mile" name="Profit/Mi" stroke="#facc15" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                <Line yAxisId="rate" type="monotone" dataKey="miles" name="Miles" stroke="#a78bfa" strokeWidth={2} dot={false} hide />
              </ComposedChart>
            </ResponsiveContainer>

            <div className="overflow-hidden rounded-lg border border-gray-800 bg-gray-950/30">
              <div className="grid grid-cols-6 gap-2 border-b border-gray-800 px-3 py-2 text-[11px] uppercase tracking-wide text-gray-500">
                <span>Month</span>
                <span className="text-right">CPM</span>
                <span className="text-right">Revenue/Mi</span>
                <span className="text-right">Profit/Mi</span>
                <span className="text-right">Cost</span>
                <span className="text-right">Miles</span>
              </div>
              <div className="max-h-[280px] divide-y divide-gray-800 overflow-y-auto text-sm">
                {monthlyK1CpmRows.map((row) => (
                  <div key={row.month} className="grid grid-cols-6 gap-2 px-3 py-2">
                    <span className="font-medium text-white">{row.month}</span>
                    <span className="text-right font-semibold text-emerald-400">{formatRate(row.cost_per_mile)}</span>
                    <span className="text-right font-semibold text-teal-300">{formatRate(row.revenue_per_mile)}</span>
                    <span className="text-right font-semibold text-amber-300">{formatRate(row.profit_per_mile)}</span>
                    <span className="text-right text-gray-300">{formatCurrency(row.total_cost)}</span>
                    <span className="text-right text-gray-400">{formatNumber(row.miles)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex h-[260px] items-center justify-center rounded-lg border border-dashed border-gray-700 text-sm text-gray-500">
            Monthly K1L CPM trend appears after `K1L_OPERATING_COST_MONTHLY_JSON` is configured.
          </div>
        )}
      </motion.div>

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
              {operatingCost?.period_start ?? 'YTD'} to {operatingCost?.period_end ?? 'today'} · {completeOperatingCost ? 'Complete source stack' : `Known stack only${unresolvedCostSources ? ` · pending ${unresolvedCostSources}` : ''}`} · profit/mi uses {k1lProfitPerMileLabel}
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
              <Bar yAxisId="cost" dataKey="insurance_cost" name="Insurance / Mile" stackId="cost" fill="#a855f7" />
              <Bar yAxisId="cost" dataKey="maintenance_cost" name="Maintenance" stackId="cost" fill="#f59e0b" />
              <Bar yAxisId="cost" dataKey="employee_cost" name="Employee" stackId="cost" fill="#facc15" />
              <Bar yAxisId="cost" dataKey="rental_trucks_trailers_cost" name="Rental / Lease" stackId="cost" fill="#fb7185" />
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
            {atobFlow && (
              <div className="mt-4 rounded-xl border border-blue-500/25 bg-blue-500/10 p-4">
                <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                  <div>
                    <div className="text-xs uppercase tracking-wide text-blue-200/80">Power Automate Flow</div>
                    <div className="mt-1 text-sm font-semibold text-blue-100">{atobFlow.flow_name}</div>
                    <div className="mt-1 text-xs text-blue-100/70">
                      {atobFlow.environment} · {humanStatusLabel(atobFlow.status)}
                    </div>
                  </div>
                  <span className="rounded-full border border-amber-400/30 bg-amber-500/10 px-3 py-1 text-xs font-semibold text-amber-200">
                    Pending test validation
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-1 gap-3 text-xs text-blue-100/80 xl:grid-cols-2">
                  <div>
                    <span className="font-semibold text-blue-100">Root cause:</span> {atobFlow.issue}
                  </div>
                  <div>
                    <span className="font-semibold text-blue-100">Fix:</span> {atobFlow.resolution}
                  </div>
                  <div>
                    <span className="font-semibold text-blue-100">Flow ID:</span> {atobFlow.flow_id}
                  </div>
                  <div>
                    <span className="font-semibold text-blue-100">Next step:</span> {atobFlow.next_step}
                  </div>
                </div>
              </div>
            )}
            {optimizationPlan.length > 0 && (
              <div className="mt-3 rounded-xl border border-gray-700/70 bg-gray-950/35 p-4">
                <div className="mb-3 text-xs uppercase tracking-wide text-gray-500">Loading Optimization Plan</div>
                <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
                  {optimizationPlan.map(item => (
                    <div key={item.priority} className="rounded-lg border border-gray-800 bg-gray-900/50 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-medium text-gray-100">{item.item}</span>
                        <span className="rounded-full bg-gray-800 px-2 py-0.5 text-[11px] uppercase text-gray-400">{humanStatusLabel(item.status)}</span>
                      </div>
                      <p className="mt-1 text-xs text-gray-500">{item.detail}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
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
        <div className="mb-5 grid grid-cols-2 xl:grid-cols-4 gap-4">
          <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-4">
            <div className="text-xs uppercase text-gray-500">Revenue / Truck</div>
            <div className={`mt-1 text-2xl font-bold ${truckProductivityClass}`}>
              {formatCurrency(productivitySummary?.revenue_per_truck)}
            </div>
            <div className="mt-1 text-xs text-gray-500">
              Target {formatCurrency(truckTarget)} / wk · {formatDeltaCurrency(productivitySummary?.truck_target_delta)}
            </div>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-4">
            <div className="text-xs uppercase text-gray-500">Revenue / Driver</div>
            <div className={`mt-1 text-2xl font-bold ${driverProductivityClass}`}>
              {formatCurrency(productivitySummary?.revenue_per_driver)}
            </div>
            <div className="mt-1 text-xs text-gray-500">
              Target {formatCurrency(driverTarget)} / wk · {formatDeltaCurrency(productivitySummary?.driver_target_delta)}
            </div>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-4">
            <div className="text-xs uppercase text-gray-500">Active Trucks</div>
            <div className="mt-1 text-2xl font-bold text-blue-300">{formatNumber(productivitySummary?.truck_count)}</div>
            <div className="mt-1 text-xs text-gray-500">Geotab trucks with 10+ mi</div>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950/40 p-4">
            <div className="text-xs uppercase text-gray-500">Dispatch Drivers</div>
            <div className="mt-1 text-2xl font-bold text-purple-300">{formatNumber(productivitySummary?.driver_count)}</div>
            <div className="mt-1 text-xs text-gray-500">
              {productivitySummary?.driver_source === 'geotab_trip_driver_fallback' ? 'Geotab fallback' : 'Xcelerator drivers'}
            </div>
          </div>
        </div>
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
