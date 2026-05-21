import { motion } from 'framer-motion'
import { useState } from 'react'
import { Calendar, Clock, DollarSign, AlertTriangle, CheckCircle, XCircle, Wrench, TrendingUp, BrainCircuit, ClipboardCheck, ShieldCheck, Gauge } from 'lucide-react'
import { useMaintenancePredictions, useMaintenanceCosts, useUrgentMaintenance, useMaintenanceIntelligence } from '../hooks/useGeotab'

interface MaintenanceService {
  service_type: string
  due_date: string
  is_overdue: boolean
  urgency: 'low' | 'medium' | 'high' | 'critical'
  estimated_cost: number
}

interface MaintenancePrediction {
  vehicle_id: string
  vehicle_name: string
  current_odometer: number
  engine_hours: number
  upcoming_services: MaintenanceService[]
  has_active_fault_codes: boolean
  active_fault_count: number
  ai_health_score?: number
  ai_decision?: MaintenanceDecision | null
}

interface MaintenanceDecision {
  vehicle_id: string
  vehicle_name: string
  decision: string
  urgency: 'low' | 'medium' | 'high' | 'critical'
  risk_score: number
  health_score: number
  confidence: number
  predicted_issue: string
  recommended_action: string
  execution_plan: string[]
  evidence: string[]
  fault_insights: Array<{
    code: string
    description: string
    count: number
    severity: string
    component?: string
  }>
  source_authority: string
  automation_mode: string
}

interface UrgentAlert {
  vehicle_id: string
  vehicle_name: string
  urgency: 'low' | 'medium' | 'high' | 'critical'
  active_fault_codes: Array<{code: string, description: string}>
  overdue_services: Array<{service_type: string, days_overdue: number}>
  urgent_services: Array<{service_type: string, days_until_due: number}>
  estimated_repair_cost: number
}

const getUrgencyColor = (urgency: string) => {
  switch (urgency) {
    case 'critical': return 'from-red-500 to-red-700'
    case 'high': return 'from-orange-500 to-orange-700'
    case 'medium': return 'from-yellow-500 to-yellow-700'
    default: return 'from-green-500 to-green-700'
  }
}

const getUrgencyIcon = (urgency: string) => {
  switch (urgency) {
    case 'critical': return <XCircle className="w-5 h-5 text-red-400" />
    case 'high': return <AlertTriangle className="w-5 h-5 text-orange-400" />
    case 'medium': return <Clock className="w-5 h-5 text-yellow-400" />
    default: return <CheckCircle className="w-5 h-5 text-green-400" />
  }
}

const formatServiceType = (type: string) => {
  return type.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())
}

const formatDate = (dateStr: string) => {
  const date = new Date(dateStr)
  const now = new Date()
  const diffDays = Math.ceil((date.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
  
  if (diffDays < 0) {
    return `${Math.abs(diffDays)} days overdue`
  } else if (diffDays === 0) {
    return 'Due today'
  } else if (diffDays <= 7) {
    return `Due in ${diffDays} days`
  } else {
    return date.toLocaleDateString()
  }
}

const formatDecision = (decision: string) => {
  return decision.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

const getRiskColor = (urgency?: string) => {
  switch (urgency) {
    case 'critical': return 'text-red-300 bg-red-500/10 border-red-400/25'
    case 'high': return 'text-orange-300 bg-orange-500/10 border-orange-400/25'
    case 'medium': return 'text-amber-300 bg-amber-500/10 border-amber-400/25'
    default: return 'text-emerald-300 bg-emerald-500/10 border-emerald-400/25'
  }
}

const getDecisionTone = (urgency: string) => {
  switch (urgency) {
    case 'critical': return 'border-red-500/35 bg-red-950/20'
    case 'high': return 'border-orange-500/35 bg-orange-950/20'
    case 'medium': return 'border-amber-500/30 bg-amber-950/15'
    default: return 'border-emerald-500/20 bg-emerald-950/10'
  }
}

const formatDayWindow = (days?: number | null) => {
  return Number.isFinite(days) && days ? `${days} days` : 'configured window'
}

export default function MaintenancePredictor() {
  const [selectedVehicle, setSelectedVehicle] = useState<string | null>(null)
  const predictions = useMaintenancePredictions()
  const intelligence = useMaintenanceIntelligence()
  const costs = useMaintenanceCosts()
  const urgentAlerts = useUrgentMaintenance()
  const decisions = (intelligence.data?.decisions || []) as MaintenanceDecision[]
  const intelligenceSummary = intelligence.data?.summary || {}
  const primaryForecastDays = costs.data?.forecast_primary_days as number | undefined
  const secondaryForecastDays = costs.data?.forecast_secondary_days as number | undefined

  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1
      }
    }
  }

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 }
  }

  if (predictions.loading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-700 rounded w-64 mb-6"></div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3, 4, 5, 6].map(i => (
              <div key={i} className="h-64 bg-gray-700 rounded-xl"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <motion.div 
      className="space-y-6"
      variants={containerVariants}
      initial="hidden"
      animate="show"
    >
      {/* Header */}
      <motion.div variants={itemVariants} className="flex items-center gap-3">
        <Wrench className="w-8 h-8 text-blue-400" />
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 via-purple-400 to-emerald-400 bg-clip-text text-transparent">
            Predictive Maintenance
          </h1>
          <p className="text-gray-400">AI-powered fleet maintenance forecasting</p>
        </div>
      </motion.div>

      {/* AI Decision Layer */}
      <motion.div variants={itemVariants} className="rounded-xl border border-cyan-500/20 bg-cyan-950/10 p-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-cyan-400/25 bg-cyan-500/10">
              <BrainCircuit className="h-5 w-5 text-cyan-200" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">AI Diagnostic Decision Layer</h2>
              <p className="mt-1 max-w-3xl text-sm text-gray-400">
                Geotab fault codes are scored into a maintenance execution queue. FleetPulse recommends; the maintenance team executes and confirms outcomes.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="rounded-full border border-emerald-400/20 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-200">
              {intelligence.data?.automation_mode || 'ai_recommends_human_executes'}
            </span>
            <span className="rounded-full border border-cyan-400/20 bg-cyan-500/10 px-3 py-1 text-xs font-semibold text-cyan-200">
              Previous {formatDayWindow(intelligence.data?.period_days)}
            </span>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            {
              label: 'Codes Read',
              value: intelligence.loading ? 'Pending' : (intelligenceSummary.total_fault_rows ?? 0).toLocaleString(),
              icon: Gauge,
              color: 'text-cyan-300',
            },
            {
              label: 'Assets Scored',
              value: intelligence.loading ? 'Pending' : (intelligenceSummary.vehicles_with_faults ?? 0).toLocaleString(),
              icon: BrainCircuit,
              color: 'text-blue-300',
            },
            {
              label: 'Critical / High',
              value: intelligence.loading ? 'Pending' : `${intelligenceSummary.critical ?? 0} / ${intelligenceSummary.high ?? 0}`,
              icon: AlertTriangle,
              color: 'text-red-300',
            },
            {
              label: 'Execution Queue',
              value: intelligence.loading ? 'Pending' : decisions.length.toLocaleString(),
              icon: ClipboardCheck,
              color: 'text-emerald-300',
            },
          ].map(({ label, value, icon: Icon, color }) => (
            <div key={label} className="rounded-lg border border-white/10 bg-gray-900/50 p-4">
              <div className="mb-2 flex items-center gap-2 text-xs text-gray-400">
                <Icon className={`h-4 w-4 ${color}`} />
                {label}
              </div>
              <p className="text-2xl font-semibold text-white" style={{ fontVariantNumeric: 'tabular-nums lining-nums' }}>
                {value}
              </p>
            </div>
          ))}
        </div>

        {decisions.length > 0 && (
          <div className="mt-5 grid grid-cols-1 gap-3 xl:grid-cols-2">
            {decisions.slice(0, 6).map(decision => (
              <div
                key={`${decision.vehicle_id}-${decision.decision}`}
                className={`rounded-xl border p-4 ${getDecisionTone(decision.urgency)}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-base font-semibold text-white">{decision.vehicle_name}</h3>
                      <span className={`rounded-full border px-2 py-1 text-[10px] font-semibold uppercase ${getRiskColor(decision.urgency)}`}>
                        Risk {decision.risk_score}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-gray-300">{decision.predicted_issue}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs uppercase tracking-wide text-gray-500">Confidence</p>
                    <p className="text-sm font-semibold text-white">{Math.round(decision.confidence * 100)}%</p>
                  </div>
                </div>

                <div className="mt-3 rounded-lg border border-white/10 bg-black/15 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{formatDecision(decision.decision)}</p>
                  <p className="mt-1 text-sm text-gray-200">{decision.recommended_action}</p>
                </div>

                <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Human Plan</p>
                    <ul className="space-y-1 text-xs text-gray-300">
                      {decision.execution_plan.slice(0, 3).map(step => (
                        <li key={step} className="flex gap-2">
                          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-300" />
                          <span>{step}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Evidence</p>
                    <div className="space-y-1 text-xs text-gray-400">
                      {decision.fault_insights.slice(0, 3).map(fault => (
                        <div key={`${decision.vehicle_id}-${fault.code}`} className="flex items-center justify-between gap-2">
                          <span className="truncate font-mono text-gray-200">{fault.code}</span>
                          <span className="shrink-0 text-gray-500">x{fault.count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </motion.div>

      {/* Cost Forecast Cards */}
      <motion.div variants={itemVariants} className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-gradient-to-br from-gray-800/50 to-gray-900/50 backdrop-blur-sm rounded-xl p-6 border border-gray-700/50">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-400 text-sm">Next {formatDayWindow(primaryForecastDays)}</p>
              <p className="text-2xl font-bold text-white">
                ${costs.data?.total_cost_next_month?.toLocaleString() || '0'}
              </p>
            </div>
            <DollarSign className="w-8 h-8 text-yellow-400" />
          </div>
        </div>

        <div className="bg-gradient-to-br from-gray-800/50 to-gray-900/50 backdrop-blur-sm rounded-xl p-6 border border-gray-700/50">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-400 text-sm">Next {formatDayWindow(secondaryForecastDays)}</p>
              <p className="text-2xl font-bold text-white">
                ${costs.data?.total_cost_next_3_months?.toLocaleString() || '0'}
              </p>
            </div>
            <TrendingUp className="w-8 h-8 text-blue-400" />
          </div>
        </div>

        <div className="bg-gradient-to-br from-gray-800/50 to-gray-900/50 backdrop-blur-sm rounded-xl p-6 border border-gray-700/50">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-400 text-sm">Monthly Average</p>
              <p className="text-2xl font-bold text-white">
                ${Math.round(costs.data?.average_monthly_cost || 0).toLocaleString()}
              </p>
            </div>
            <Calendar className="w-8 h-8 text-purple-400" />
          </div>
        </div>
      </motion.div>

      {/* Urgent Alerts */}
      {urgentAlerts.data && urgentAlerts.data.length > 0 && (
        <motion.div variants={itemVariants}>
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            Urgent Maintenance Required
            <span className="text-xs bg-red-500 px-2 py-1 rounded-full">
              {urgentAlerts.data.length}
            </span>
          </h2>
          <div className="grid gap-4">
            {urgentAlerts.data.map((alert: UrgentAlert, index: number) => (
              <motion.div
                key={alert.vehicle_id}
                variants={itemVariants}
                className="bg-gradient-to-r from-red-900/20 to-red-800/20 border border-red-700/50 rounded-lg p-4"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold text-red-200">{alert.vehicle_name}</h3>
                    <div className="space-y-1 mt-2">
                      {alert.active_fault_codes.map((fault, i) => (
                        <div key={i} className="text-sm text-red-300">
                          <span className="font-mono bg-red-900/30 px-2 py-1 rounded">
                            {fault.code}
                          </span>
                          <span className="ml-2">{fault.description}</span>
                        </div>
                      ))}
                      {alert.overdue_services.map((service, i) => (
                        <div key={i} className="text-sm text-red-300">
                          <strong>{formatServiceType(service.service_type)}</strong> - {service.days_overdue} days overdue
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-red-200 font-semibold">
                      ${alert.estimated_repair_cost.toLocaleString()}
                    </p>
                    <p className="text-xs text-red-400">{alert.urgency.toUpperCase()}</p>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Vehicle Maintenance Cards */}
      <motion.div variants={itemVariants}>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Wrench className="w-5 h-5 text-blue-400" />
          Vehicle Maintenance Status
          <span className="text-xs bg-gray-700 px-2 py-1 rounded-full">
            {predictions.data?.length || 0} Vehicles
          </span>
        </h2>

        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
          {predictions.data?.map((prediction: MaintenancePrediction, index: number) => {
            const mostUrgentService = prediction.upcoming_services.reduce((prev, current) => {
              const urgencyOrder = { critical: 4, high: 3, medium: 2, low: 1 }
              return urgencyOrder[current.urgency as keyof typeof urgencyOrder] > urgencyOrder[prev.urgency as keyof typeof urgencyOrder] ? current : prev
            })
            const aiRiskScore = prediction.ai_decision?.risk_score ?? Math.max(0, 100 - (prediction.ai_health_score ?? 100))

            return (
              <motion.div
                key={prediction.vehicle_id}
                variants={itemVariants}
                className="bg-gradient-to-br from-gray-800/50 to-gray-900/50 backdrop-blur-sm rounded-xl p-6 border border-gray-700/50 hover:border-gray-600/50 transition-all duration-300"
                whileHover={{ scale: 1.02 }}
              >
                {/* Vehicle Header */}
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-lg font-semibold text-white">{prediction.vehicle_name}</h3>
                    <p className="text-sm text-gray-400">
                      {Math.round(prediction.current_odometer).toLocaleString()} mi • {Math.round(prediction.engine_hours)}h
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {prediction.ai_decision && (
                      <span className={`rounded-full border px-2 py-1 text-[10px] font-semibold ${getRiskColor(prediction.ai_decision.urgency)}`}>
                        AI {aiRiskScore}
                      </span>
                    )}
                    {getUrgencyIcon(mostUrgentService.urgency)}
                    {prediction.has_active_fault_codes && (
                      <div className="flex items-center gap-1 text-red-400 text-xs">
                        <AlertTriangle className="w-3 h-3" />
                        {prediction.active_fault_count}
                      </div>
                    )}
                  </div>
                </div>

                {/* Status Bar */}
                <div className={`w-full h-2 rounded-full mb-4 bg-gradient-to-r ${getUrgencyColor(mostUrgentService.urgency)}`}>
                </div>

                {prediction.ai_decision && (
                  <div className="mb-4 rounded-lg border border-cyan-400/15 bg-cyan-950/10 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-cyan-200">
                      {formatDecision(prediction.ai_decision.decision)}
                    </p>
                    <p className="mt-1 text-sm text-gray-300">{prediction.ai_decision.predicted_issue}</p>
                    <p className="mt-1 text-xs text-gray-500">{prediction.ai_decision.recommended_action}</p>
                  </div>
                )}

                {/* Upcoming Services */}
                <div className="space-y-3">
                  <h4 className="text-sm font-medium text-gray-300">Next Services</h4>
                  {prediction.upcoming_services.slice(0, 3).map((service, i) => (
                    <div key={i} className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-white">
                          {formatServiceType(service.service_type)}
                        </p>
                        <p className="text-xs text-gray-400">
                          {formatDate(service.due_date)}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-medium text-white">
                          ${service.estimated_cost}
                        </p>
                        <div className="flex items-center gap-1">
                          {getUrgencyIcon(service.urgency)}
                          <span className="text-xs text-gray-400 capitalize">
                            {service.urgency}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Total Cost */}
                <div className="mt-4 pt-4 border-t border-gray-700">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-400">Est. Total Cost</span>
                    <span className="text-lg font-bold text-white">
                      ${prediction.upcoming_services.reduce((sum, s) => sum + s.estimated_cost, 0).toLocaleString()}
                    </span>
                  </div>
                </div>
              </motion.div>
            )
          })}
        </div>
      </motion.div>

      {/* Cost Breakdown Chart */}
      {costs.data?.cost_breakdown && (
        <motion.div variants={itemVariants} className="bg-gradient-to-br from-gray-800/50 to-gray-900/50 backdrop-blur-sm rounded-xl p-6 border border-gray-700/50">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-purple-400" />
            Cost Breakdown by Service Type
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Object.entries(costs.data.cost_breakdown).map(([serviceType, data]) => (
              <div key={serviceType} className="text-center">
                <div className="bg-gray-700/50 rounded-lg p-4">
                  <p className="text-sm font-medium text-gray-300 mb-1">
                    {formatServiceType(serviceType)}
                  </p>
                  <p className="text-lg font-bold text-white">
                    ${(data as any).total_cost?.toLocaleString()}
                  </p>
                  <p className="text-xs text-gray-400">
                    {(data as any).count} vehicles
                  </p>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </motion.div>
  )
}
