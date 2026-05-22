import { useCallback, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { MessageCircle, Zap, BarChart3, Wrench, GraduationCap, Route, FileText, MapPin, Fuel, Shield, Database, Activity, Users, LineChart, DollarSign } from 'lucide-react'
import Dashboard from './components/Dashboard'
import FleetAnalytics from './components/FleetAnalytics'
import FleetChat from './components/FleetChat'
import FleetMap from './components/FleetMap'
import VehicleList from './components/VehicleList'
import SafetyScorecard from './components/SafetyScorecard'
import Leaderboard from './components/Leaderboard'
import AlertFeed from './components/AlertFeed'
import LocationCard from './components/LocationCard'
import AgenticMonitor from './components/AgenticMonitor'
import MaintenancePredictor from './components/MaintenancePredictor'
import ThemeToggle from './components/ThemeToggle'
import DriverCoaching from './components/DriverCoaching'
import RouteReplay from './components/RouteReplay'
import InstallPrompt from './components/InstallPrompt'
import OfflineIndicator from './components/OfflineIndicator'
import FleetReports from './components/FleetReports'
import GeofenceManager from './components/GeofenceManager'
import FuelAnalytics from './components/FuelAnalytics'
import ComplianceDashboard from './components/ComplianceDashboard'
import DataConnector from './components/DataConnector'
import ControlTower from './components/ControlTower'
import OperatingSystem from './components/OperatingSystem'
import HrRecruitingWorklist from './components/HrRecruitingWorklist'
import DashboardValidationSummary from './components/DashboardValidationSummary'
import StabilityDashboard from './components/StabilityDashboard'
import FinancialPerformanceDashboard from './components/FinancialPerformanceDashboard'
import DriverWorkforce from './components/DriverWorkforce'
import { useDashboardValidation, useFleetOverview, useVehicles, useSafetyScores, useLeaderboard, useAlerts, useLocations, useMonitorAlerts, useMonitorStatus, useControlTowerTrailerTracking, useDriverWorkforce, useDataConnectorVehicleKpis, useDataConnectorSafetyScores } from './hooks/useGeotab'

type AppTab = 'dashboard' | 'control-tower' | 'finance' | 'operating-system' | 'hr-recruiting' | 'maintenance' | 'coaching' | 'replay' | 'stability' | 'reports' | 'geofences' | 'fuel' | 'compliance' | 'data-connector'

const appTabs: AppTab[] = [
  'dashboard',
  'control-tower',
  'finance',
  'operating-system',
  'hr-recruiting',
  'maintenance',
  'coaching',
  'replay',
  'stability',
  'reports',
  'geofences',
  'fuel',
  'compliance',
  'data-connector',
]

function getInitialTab(): AppTab {
  const hash = window.location.hash.replace('#', '') as AppTab
  return appTabs.includes(hash) ? hash : 'dashboard'
}

export default function App() {
  const [chatOpen, setChatOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<AppTab>(getInitialTab)
  const [selectedVehicleId, setSelectedVehicleId] = useState<string | null>(null)
  
  const dashboardActive = activeTab === 'dashboard'
  const validationActive = dashboardActive || activeTab === 'operating-system'
  const overview = useFleetOverview(dashboardActive)
  const dashboardValidation = useDashboardValidation(validationActive)
  const vehicles = useVehicles(dashboardActive)
  const safety = useSafetyScores(dashboardActive)
  const leaderboard = useLeaderboard(dashboardActive)
  const alerts = useAlerts(dashboardActive)
  const locations = useLocations(dashboardActive)
  const monitorAlerts = useMonitorAlerts(dashboardActive)
  const monitorStatus = useMonitorStatus(dashboardActive)
  const trailerTracking = useControlTowerTrailerTracking(dashboardActive)
  const driverWorkforce = useDriverWorkforce(dashboardActive)
  const utilization7d = useDataConnectorVehicleKpis(7, dashboardActive)
  const safety7d = useDataConnectorSafetyScores(7, dashboardActive)

  const triggerCheck = useCallback(() => {
    fetch('/api/monitor/check', { method: 'POST' }).then(() => {
      monitorAlerts.refresh()
      monitorStatus.refresh()
    })
  }, [monitorAlerts, monitorStatus])

  const selectTab = useCallback((tab: AppTab) => {
    setActiveTab(tab)
    window.history.replaceState(null, '', `#${tab}`)
  }, [])

  const pageVariants = {
    initial: { opacity: 0, y: 20 },
    in: { opacity: 1, y: 0 },
    out: { opacity: 0, y: -20 }
  }

  const pageTransition = {
    type: 'tween' as const,
    ease: 'anticipate' as const,
    duration: 0.5
  }

  return (
    <div className="min-h-screen overflow-x-hidden bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950 light:from-gray-50 light:via-white light:to-gray-50 text-white dark:text-white light:text-gray-900">
      {/* Header */}
      <motion.header 
        className="border-b border-gray-800/50 dark:border-gray-800/50 light:border-gray-200/50 px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between gap-4 backdrop-blur-xl bg-gray-950/80 dark:bg-gray-950/80 light:bg-white/80"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
      >
        <div className="flex items-center gap-3">
          <motion.span 
            className="text-3xl"
            animate={{ rotate: [0, 10, 0] }}
            transition={{ duration: 2, repeat: Infinity, repeatDelay: 3 }}
          >
            🚗
          </motion.span>
          <div>
            <h1 className="text-xl sm:text-2xl font-bold bg-gradient-to-r from-blue-400 via-purple-400 to-emerald-400 bg-clip-text text-transparent">
              FleetPulse
            </h1>
            <p className="text-xs text-gray-500 dark:text-gray-500 light:text-gray-600 hidden sm:block">K1 Logistics · FTW · Justin · OKC · Kansas City · 4 Locations</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          {/* Navigation Tabs */}
          <nav className="flex flex-wrap gap-1 bg-gray-800/50 dark:bg-gray-800/50 light:bg-gray-200/50 rounded-lg p-1">
            <button
              onClick={() => selectTab('dashboard')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                activeTab === 'dashboard'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700/50 light:text-gray-600 light:hover:text-gray-900 light:hover:bg-white'
              }`}
            >
              <BarChart3 className="w-4 h-4" />
              <span className="hidden sm:inline">Dashboard</span>
            </button>
            <button
              onClick={() => selectTab('control-tower')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                activeTab === 'control-tower'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700/50 light:text-gray-600 light:hover:text-gray-900 light:hover:bg-white'
              }`}
            >
              <Activity className="w-4 h-4" />
              <span className="hidden sm:inline">Tower</span>
            </button>
            <button
              onClick={() => selectTab('finance')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                activeTab === 'finance'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700/50 light:text-gray-600 light:hover:text-gray-900 light:hover:bg-white'
              }`}
            >
              <DollarSign className="w-4 h-4" />
              <span className="hidden sm:inline">Finance</span>
            </button>
            <button
              onClick={() => selectTab('operating-system')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                activeTab === 'operating-system'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700/50 light:text-gray-600 light:hover:text-gray-900 light:hover:bg-white'
              }`}
            >
              <Users className="w-4 h-4" />
              <span className="hidden sm:inline">Org OS</span>
            </button>
            <button
              onClick={() => selectTab('hr-recruiting')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                activeTab === 'hr-recruiting'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700/50 light:text-gray-600 light:hover:text-gray-900 light:hover:bg-white'
              }`}
            >
              <Users className="w-4 h-4" />
              <span className="hidden sm:inline">HR</span>
            </button>
            <button
              onClick={() => selectTab('maintenance')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                activeTab === 'maintenance'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700/50 light:text-gray-600 light:hover:text-gray-900 light:hover:bg-white'
              }`}
            >
              <Wrench className="w-4 h-4" />
              <span className="hidden sm:inline">Maintenance</span>
            </button>
            <button
              onClick={() => selectTab('coaching')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                activeTab === 'coaching'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700/50 light:text-gray-600 light:hover:text-gray-900 light:hover:bg-white'
              }`}
            >
              <GraduationCap className="w-4 h-4" />
              <span className="hidden sm:inline">Coaching</span>
            </button>
            <button
              onClick={() => selectTab('replay')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                activeTab === 'replay'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700/50 light:text-gray-600 light:hover:text-gray-900 light:hover:bg-white'
              }`}
            >
              <Route className="w-4 h-4" />
              <span className="hidden sm:inline">Routes</span>
            </button>
            <button
              onClick={() => selectTab('stability')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                activeTab === 'stability'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700/50 light:text-gray-600 light:hover:text-gray-900 light:hover:bg-white'
              }`}
            >
              <LineChart className="w-4 h-4" />
              <span className="hidden sm:inline">Stability</span>
            </button>
            <button
              onClick={() => selectTab('fuel')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                activeTab === 'fuel'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700/50 light:text-gray-600 light:hover:text-gray-900 light:hover:bg-white'
              }`}
            >
              <Fuel className="w-4 h-4" />
              <span className="hidden sm:inline">Fuel</span>
            </button>
            <button
              onClick={() => selectTab('geofences')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                activeTab === 'geofences'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700/50 light:text-gray-600 light:hover:text-gray-900 light:hover:bg-white'
              }`}
            >
              <MapPin className="w-4 h-4" />
              <span className="hidden sm:inline">Zones</span>
            </button>
            <button
              onClick={() => selectTab('compliance')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                activeTab === 'compliance'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700/50 light:text-gray-600 light:hover:text-gray-900 light:hover:bg-white'
              }`}
            >
              <Shield className="w-4 h-4" />
              <span className="hidden sm:inline">ELD</span>
            </button>
            <button
              onClick={() => selectTab('reports')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                activeTab === 'reports'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700/50 light:text-gray-600 light:hover:text-gray-900 light:hover:bg-white'
              }`}
            >
              <FileText className="w-4 h-4" />
              <span className="hidden sm:inline">Reports</span>
            </button>
            <button
              onClick={() => selectTab('data-connector')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                activeTab === 'data-connector'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/50 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700/50 light:text-gray-600 light:hover:text-gray-900 light:hover:bg-white'
              }`}
            >
              <Database className="w-4 h-4" />
              <span className="hidden sm:inline">Connector</span>
            </button>
          </nav>
          
          <ThemeToggle />
          <div className="flex items-center gap-2 text-sm text-gray-400 dark:text-gray-400 light:text-gray-600">
            <motion.span 
              className="inline-block w-2 h-2 rounded-full bg-emerald-400"
              animate={{ opacity: [1, 0.3, 1] }}
              transition={{ duration: 2, repeat: Infinity }}
            />
            <span className="hidden sm:inline">Live</span>
          </div>
        </div>
      </motion.header>

      <motion.main 
        className="p-4 sm:p-6 space-y-6 max-w-[1800px] mx-auto"
        variants={pageVariants}
        initial="initial"
        animate="in"
        exit="out"
        transition={pageTransition}
      >
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
        {/* KPI Cards */}
        <section>
          <Dashboard
            overview={overview.data}
            loading={overview.loading}
            safetyScores={safety.data}
            safetyLoading={safety.loading}
            safety7d={safety7d.data}
            safety7dError={safety7d.error}
            safety7dLoading={safety7d.loading}
            utilization7d={utilization7d.data}
            utilization7dError={utilization7d.error}
            utilization7dLoading={utilization7d.loading}
            validation={dashboardValidation.data}
          />
        </section>

        <section>
          <DriverWorkforce
            data={driverWorkforce.data}
            loading={driverWorkforce.loading}
            onSelectVehicle={setSelectedVehicleId}
          />
        </section>

        <section>
          <DashboardValidationSummary validation={dashboardValidation.data} loading={dashboardValidation.loading} />
        </section>

        {/* Fleet Analytics */}
        <section>
          <FleetAnalytics loading={overview.loading} />
        </section>

        {/* Map + Alerts row */}
        <section className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.3, duration: 0.5 }}
            >
              <FleetMap
                vehicles={vehicles.data}
                locations={locations.data}
                trailers={trailerTracking.data?.trailers || null}
                selectedVehicleId={selectedVehicleId}
              />
            </motion.div>
          </div>
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.4, duration: 0.5 }}
          >
            <AlertFeed alerts={alerts.data} loading={alerts.loading} />
          </motion.div>
        </section>

        {/* Agentic Monitor */}
        <section>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5, duration: 0.5 }}
          >
            <AgenticMonitor
              alerts={monitorAlerts.data}
              status={monitorStatus.data}
              loading={monitorAlerts.loading}
              onTriggerCheck={triggerCheck}
              driverWorkforce={driverWorkforce.data}
            />
          </motion.div>
        </section>

        {/* Safety + Leaderboard row */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.6, duration: 0.5 }}
          >
            <SafetyScorecard scores={safety.data} loading={safety.loading} />
          </motion.div>
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.7, duration: 0.5 }}
          >
            <Leaderboard drivers={leaderboard.data} loading={leaderboard.loading} />
          </motion.div>
        </section>

        {/* Vehicles */}
        <section>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.8, duration: 0.5 }}
          >
            <VehicleList
              vehicles={vehicles.data}
              loading={vehicles.loading}
              selectedVehicleId={selectedVehicleId}
            />
          </motion.div>
        </section>

        {/* Location Cards */}
        <section>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.9, duration: 0.5 }}
          >
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              📍 Locations
              <span className="text-xs bg-gray-800 px-2 py-1 rounded-full text-gray-400">
                5 Active
              </span>
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {locations.data?.map((loc, index) => (
                <motion.div
                  key={loc.name}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 1.0 + index * 0.1, duration: 0.3 }}
                >
                  <LocationCard location={loc} />
                </motion.div>
              ))}
            </div>
          </motion.div>
        </section>
          </div>
        )}

        {activeTab === 'maintenance' && (
          <MaintenancePredictor />
        )}

        {activeTab === 'control-tower' && (
          <ControlTower />
        )}

        {activeTab === 'finance' && (
          <FinancialPerformanceDashboard />
        )}

        {activeTab === 'operating-system' && (
          <OperatingSystem validation={dashboardValidation.data} />
        )}

        {activeTab === 'hr-recruiting' && (
          <HrRecruitingWorklist />
        )}

        {activeTab === 'coaching' && (
          <DriverCoaching />
        )}

        {activeTab === 'replay' && (
          <RouteReplay onClose={() => selectTab('dashboard')} />
        )}

        {activeTab === 'stability' && <StabilityDashboard />}
        {activeTab === 'reports' && <FleetReports />}
        {activeTab === 'geofences' && <GeofenceManager />}
        {activeTab === 'fuel' && <FuelAnalytics />}
        {activeTab === 'compliance' && <ComplianceDashboard />}
        {activeTab === 'data-connector' && <DataConnector />}
      </motion.main>

      {/* PWA Components */}
      <InstallPrompt />
      <OfflineIndicator />

      {/* AI Chat Floating Action Button */}
      <motion.button
        onClick={() => setChatOpen(true)}
        className="fixed bottom-6 right-6 w-14 h-14 bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 rounded-full shadow-lg hover:shadow-xl flex items-center justify-center group z-40"
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.95 }}
        initial={{ opacity: 0, y: 100 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 2, type: "spring" as const, stiffness: 400, damping: 25 }}
      >
        <MessageCircle className="w-6 h-6 text-white" />
        <motion.div
          className="absolute -top-1 -right-1 w-4 h-4 bg-emerald-500 rounded-full flex items-center justify-center"
          animate={{ scale: [1, 1.2, 1], opacity: [1, 0.8, 1] }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          <Zap className="w-2 h-2 text-white" />
        </motion.div>
        
        {/* Tooltip */}
        <div className="absolute bottom-full right-0 mb-2 px-3 py-1 bg-gray-900 text-white text-sm rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none">
          Ask AI about your fleet
          <div className="absolute top-full right-4 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900" />
        </div>
      </motion.button>

      {/* AI Chat Interface */}
      <AnimatePresence>
        {chatOpen && <FleetChat isOpen={chatOpen} onClose={() => setChatOpen(false)} />}
      </AnimatePresence>
    </div>
  )
}
