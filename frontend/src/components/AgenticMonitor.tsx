import { useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Brain, AlertTriangle, Lightbulb, Clock } from 'lucide-react'
import type { Alert, DriverWorkforceResponse } from '../types/fleet'

interface MonitorStatus {
  running: boolean
  total_alerts: number
  patterns: {
    last_check?: string
    total_vehicles?: number
    active_vehicles?: number
    alerts_generated?: number
    checks_run?: number
    location_vehicle_counts?: Record<string, number>
  }
}

interface Props {
  alerts: Alert[] | null
  status: MonitorStatus | null
  loading: boolean
  onTriggerCheck: () => void
  driverWorkforce?: DriverWorkforceResponse | null
}

const groupStyle: Record<string, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-amber-500',
  low: 'bg-blue-500',
}

export default function AgenticMonitor({ alerts, status, loading, onTriggerCheck, driverWorkforce }: Props) {
  const [expanded, setExpanded] = useState(true)
  const [activeTab, setActiveTab] = useState<'alerts' | 'insights' | 'recommendations'>('insights')
  const patterns = status?.patterns || {}
  const checksRun = Number(patterns.checks_run || 0)
  const monitoredVehicles = Number(patterns.total_vehicles || 0)
  const activeVehicles = Number(patterns.active_vehicles || 0)
  const alertsGenerated = Number(patterns.alerts_generated || 0)
  const lastCheck = typeof patterns.last_check === 'string' ? patterns.last_check : null

  const liveInsights = useMemo(() => {
    const alertInsights = (alerts || []).slice(0, 5).map(alert => ({
      id: alert.id,
      icon: <AlertTriangle className="w-4 h-4" />,
      title: alert.alert_type || 'Fleet alert',
      message: alert.message,
      action: alert.acknowledged ? 'Acknowledged' : 'Review',
      priority: alert.severity,
    }))
    const workforceInsights = (driverWorkforce?.insights || []).slice(0, 5).map((message, index) => ({
      id: `driver-workforce-${index}`,
      icon: <Clock className="w-4 h-4" />,
      title: 'Driver Workforce',
      message,
      action: 'Review',
      priority: driverWorkforce?.kpis.overdue ? 'critical' : driverWorkforce?.kpis.near_limit ? 'medium' : 'low',
    }))
    return [...workforceInsights, ...alertInsights].slice(0, 8)
  }, [alerts, driverWorkforce?.insights, driverWorkforce?.kpis.near_limit, driverWorkforce?.kpis.overdue])

  const recommendations = useMemo(() => {
    const activeAlerts = alerts || []
    const urgent = activeAlerts.filter(alert => alert.severity === 'critical' || alert.severity === 'high')
    if (urgent.length > 0) {
      return urgent.slice(0, 5).map(alert => ({
        title: `${alert.vehicle_name} ${alert.alert_type}`,
        description: alert.message,
        impact: alert.severity === 'critical' ? 'Critical review' : 'High-priority review',
        type: alert.severity,
      }))
    }
    if ((driverWorkforce?.kpis.overdue || 0) > 0) {
      return [{
        title: 'Overdue route tickets',
        description: `${driverWorkforce?.kpis.overdue} Xcelerator route ticket(s) are past planned finish and still open.`,
        impact: 'Dispatch review required',
        type: 'critical',
      }]
    }
    if (!status?.running) {
      return [{
        title: 'Monitor disabled',
        description: 'No background monitor cycle is running for FleetPulse.',
        impact: 'Enable monitor for live anomaly checks',
        type: 'medium',
      }]
    }
    return []
  }, [alerts, driverWorkforce?.kpis.overdue, status?.running])

  const groupedAlerts = useMemo(() => {
    const activeAlerts = alerts || []
    return (['critical', 'high', 'medium', 'low'] as const)
      .map(severity => {
        const matches = activeAlerts.filter(alert => alert.severity === severity)
        return {
          category: `${severity.charAt(0).toUpperCase()}${severity.slice(1)} Alerts`,
          count: matches.length,
          color: groupStyle[severity],
          alerts: matches.map(alert => `${alert.vehicle_name}: ${alert.message}`),
        }
      })
      .filter(group => group.count > 0)
  }, [alerts])

  const tabs = [
    { id: 'insights', label: 'AI Insights', icon: <Brain className="w-4 h-4" />, count: liveInsights.length },
    { id: 'alerts', label: 'Grouped Alerts', icon: <AlertTriangle className="w-4 h-4" />, count: alerts?.length || 0 },
    { id: 'recommendations', label: 'Recommendations', icon: <Lightbulb className="w-4 h-4" />, count: recommendations.length }
  ]

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-gradient-to-br from-gray-900 via-purple-900/20 to-blue-900/20 dark:from-gray-900 dark:via-purple-900/20 dark:to-blue-900/20 light:from-white light:via-purple-50 light:to-blue-50 rounded-xl shadow-lg overflow-hidden border border-purple-500/30 dark:border-purple-500/30 light:border-purple-200 backdrop-blur-sm"
    >
      <div className="px-4 py-3 border-b border-gray-800/50 dark:border-gray-800/50 light:border-purple-200/50 flex items-center justify-between bg-gradient-to-r from-purple-900/40 to-blue-900/40 dark:from-purple-900/40 dark:to-blue-900/40 light:from-purple-100/40 light:to-blue-100/40">
        <div className="flex items-center gap-3">
          <motion.div
            animate={{ rotate: [0, 360] }}
            transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
            className="p-2 bg-gradient-to-r from-purple-500 to-blue-500 rounded-lg"
          >
            <Brain className="w-5 h-5 text-white" />
          </motion.div>
          <div>
            <h2 className="font-semibold text-white dark:text-white light:text-gray-900">Agentic Intelligence Hub</h2>
            <p className="text-xs text-gray-400 dark:text-gray-400 light:text-gray-600">Real-time fleet analysis & recommendations</p>
          </div>
          {status?.running && (
            <motion.span
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex items-center gap-1 text-xs text-emerald-400 bg-emerald-500/20 px-2 py-1 rounded-full"
            >
              <motion.span 
                className="inline-block w-2 h-2 rounded-full bg-emerald-400"
                animate={{ opacity: [1, 0.3, 1] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              />
              Monitoring Active
            </motion.span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={onTriggerCheck}
            className="text-xs bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 text-white px-3 py-1.5 rounded-lg transition-colors flex items-center gap-2"
          >
            <Brain className="w-3 h-3" />
            Deep Scan
          </motion.button>
          <button onClick={() => setExpanded(!expanded)} className="text-gray-400 text-xs hover:text-white transition-colors">
            {expanded ? '▼' : '▶'}
          </button>
        </div>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            {/* KPI Summary */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 border-b border-gray-800/50">
              <motion.div className="text-center" whileHover={{ scale: 1.05 }}>
                <div className="text-2xl font-bold text-purple-400">
                  {checksRun}
                </div>
                <div className="text-xs text-gray-500">AI Checks</div>
              </motion.div>
              <motion.div className="text-center" whileHover={{ scale: 1.05 }}>
                <div className="text-2xl font-bold text-blue-400">
                  {monitoredVehicles}
                </div>
                <div className="text-xs text-gray-500">Monitored</div>
              </motion.div>
              <motion.div className="text-center" whileHover={{ scale: 1.05 }}>
                <div className="text-2xl font-bold text-emerald-400">
                  {activeVehicles}
                </div>
                <div className="text-xs text-gray-500">Active</div>
              </motion.div>
              <motion.div className="text-center" whileHover={{ scale: 1.05 }}>
                <div className="text-2xl font-bold text-amber-400">
                  {alertsGenerated}
                </div>
                <div className="text-xs text-gray-500">Generated</div>
              </motion.div>
            </div>

            {/* Tab Navigation */}
            <div className="border-b border-gray-800/50">
              <div className="flex">
                {tabs.map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id as any)}
                    className={`flex-1 px-4 py-3 text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                      activeTab === tab.id
                        ? 'bg-purple-600/30 text-white border-b-2 border-purple-500'
                        : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
                    }`}
                  >
                    {tab.icon}
                    <span className="hidden sm:inline">{tab.label}</span>
                    <span className="bg-gray-700 text-xs px-1.5 py-0.5 rounded-full">{tab.count}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Tab Content */}
            <div className="max-h-[400px] overflow-y-auto">
              <AnimatePresence mode="wait">
                {activeTab === 'insights' && (
                  <motion.div
                    key="insights"
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 20 }}
                    className="p-4 space-y-3"
                  >
                    {liveInsights.length === 0 && (
                      <div className="rounded-lg border border-gray-700/50 bg-gray-800/30 p-4 text-sm text-gray-400">
                        No monitor insights returned by live alert feeds.
                      </div>
                    )}
                    {liveInsights.map((insight, index) => (
                      <motion.div
                        key={insight.id}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.1 }}
                        className={`p-3 rounded-lg border-l-4 ${
                          insight.priority === 'critical' || insight.priority === 'high' ? 'border-red-500 bg-red-500/5' :
                          insight.priority === 'medium' ? 'border-amber-500 bg-amber-500/5' :
                          'border-blue-500 bg-blue-500/5'
                        } backdrop-blur-sm`}
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex items-start gap-3">
                            <div className={`p-1.5 rounded-lg ${
                              insight.priority === 'critical' || insight.priority === 'high' ? 'bg-red-500/20 text-red-400' :
                              insight.priority === 'medium' ? 'bg-amber-500/20 text-amber-400' :
                              'bg-blue-500/20 text-blue-400'
                            }`}>
                              {insight.icon}
                            </div>
                            <div className="flex-1">
                              <h4 className="font-medium text-white mb-1">{insight.title}</h4>
                              <p className="text-sm text-gray-300">{insight.message}</p>
                            </div>
                          </div>
                          <motion.button
                            whileHover={{ scale: 1.05 }}
                            whileTap={{ scale: 0.95 }}
                            className="text-xs bg-purple-600/20 hover:bg-purple-600/30 text-purple-400 px-2 py-1 rounded-lg transition-colors"
                          >
                            {insight.action}
                          </motion.button>
                        </div>
                      </motion.div>
                    ))}
                  </motion.div>
                )}

                {activeTab === 'alerts' && (
                  <motion.div
                    key="alerts"
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 20 }}
                    className="p-4 space-y-3"
                  >
                    {groupedAlerts.length === 0 && (
                      <div className="rounded-lg border border-gray-700/50 bg-gray-800/30 p-4 text-sm text-gray-400">
                        No grouped alerts returned by live alert feeds.
                      </div>
                    )}
                    {groupedAlerts.map((group, index) => (
                      <motion.div
                        key={group.category}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.1 }}
                        className="border border-gray-700/50 rounded-lg overflow-hidden backdrop-blur-sm"
                      >
                        <div className="p-3 bg-gray-800/30 flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className={`w-3 h-3 rounded-full ${group.color}`} />
                            <span className="font-medium text-white">{group.category}</span>
                            <span className="bg-gray-700 text-xs px-2 py-0.5 rounded-full">{group.count}</span>
                          </div>
                          <Clock className="w-4 h-4 text-gray-400" />
                        </div>
                        <div className="p-3 space-y-2">
                          {group.alerts.map((alert, alertIndex) => (
                            <div key={alertIndex} className="text-sm text-gray-300 flex items-center gap-2">
                              <span className="text-gray-500">•</span>
                              {alert}
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    ))}
                  </motion.div>
                )}

                {activeTab === 'recommendations' && (
                  <motion.div
                    key="recommendations"
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 20 }}
                    className="p-4 space-y-3"
                  >
                    {recommendations.length === 0 && (
                      <div className="rounded-lg border border-gray-700/50 bg-gray-800/30 p-4 text-sm text-gray-400">
                        No recommendations returned by the active monitor state.
                      </div>
                    )}
                    {recommendations.map((rec, index) => (
                      <motion.div
                        key={rec.title}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.1 }}
                        className="p-4 border border-emerald-500/20 rounded-lg bg-emerald-500/5 backdrop-blur-sm"
                      >
                        <div className="flex items-start justify-between mb-2">
                          <h4 className="font-medium text-white">{rec.title}</h4>
                          <span className={`text-xs px-2 py-1 rounded-full ${
                            rec.type === 'revenue' ? 'bg-emerald-500/20 text-emerald-400' :
                            rec.type === 'efficiency' ? 'bg-blue-500/20 text-blue-400' :
                            'bg-amber-500/20 text-amber-400'
                          }`}>
                            {rec.type}
                          </span>
                        </div>
                        <p className="text-sm text-gray-300 mb-2">{rec.description}</p>
                        <p className="text-sm font-medium text-emerald-400">{rec.impact}</p>
                      </motion.div>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Status Footer */}
            <div className="px-4 py-2 text-xs text-gray-600 border-t border-gray-800/50 flex items-center justify-between">
              <span>Last analysis: {lastCheck ? new Date(lastCheck).toLocaleTimeString() : 'Awaiting monitor check'}</span>
              <span className="flex items-center gap-1 text-emerald-400">
                <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
                {status?.running ? 'Live monitoring' : 'Monitor paused'}
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
