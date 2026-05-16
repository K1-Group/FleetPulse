import { ShieldCheck } from 'lucide-react'
import type { DashboardValidationResponse } from '../types/fleet'
import ValidationBadge from './ValidationBadge'

interface Props {
  loading?: boolean
  validation?: DashboardValidationResponse | null
}

const sectionOrder = [
  'k1l_final_cpm',
  'fleet_overview',
  'fleet_analytics',
  'fleet_map',
  'alerts',
  'agentic_monitor',
  'safety_scorecard',
  'driver_leaderboard',
  'vehicles',
  'locations',
  'data_connector',
  'operating_system',
]

export default function DashboardValidationSummary({ loading = false, validation }: Props) {
  const sections = validation?.sections || {}
  const summary = validation?.summary

  return (
    <div className="rounded-lg border border-gray-800/70 bg-gray-900/70 p-3 shadow-lg shadow-black/10 light:bg-white light:border-gray-200">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-emerald-300" />
          <h2 className="text-sm font-semibold text-white light:text-gray-900">Data Validation</h2>
        </div>
        <div className="flex flex-wrap gap-2 text-[11px] text-gray-400 light:text-gray-600">
          <span>{summary?.verified ?? 0} verified</span>
          <span>{summary?.pending ?? 0} pending</span>
          <span>{summary?.pending_no_data ?? 0} no data</span>
          <span>{summary?.pending_no_audit ?? 0} no audit</span>
          <span>{summary?.stale ?? 0} stale</span>
          <span>{summary?.failed ?? 0} failed</span>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {loading && !validation ? (
          <ValidationBadge compact label="Checking" status="pending" />
        ) : (
          sectionOrder.map(key => {
            const item = sections[key]
            if (!item) return null
            return (
              <span
                key={key}
                className="inline-flex min-h-7 max-w-full items-center gap-2 rounded-full border border-gray-800 bg-gray-950/40 px-2 py-1 text-xs text-gray-300 light:border-gray-200 light:bg-gray-50 light:text-gray-700"
              >
                <span className="truncate">{item.label}</span>
                <ValidationBadge compact item={item} />
              </span>
            )
          })
        )}
      </div>
    </div>
  )
}
