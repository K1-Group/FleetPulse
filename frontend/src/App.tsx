import { useCallback, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { MessageCircle, Zap, BarChart3, Wrench, GraduationCap, Route, FileText, MapPin, Fuel, Shield, Database, Activity, Users, LineChart, DollarSign, Truck, type LucideIcon } from 'lucide-react'
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
import UserLoginStatus from './components/UserLoginStatus'
import { useAuthSession, useDashboardValidation, useFleetOverview, useVehicles, useSafetyScores, useLeaderboard, useAlerts, useLocations, useMonitorAlerts, useMonitorStatus, useControlTowerTrailerTracking, useDriverWorkforce, useFuelTrends, useDataConnectorVehicleKpis, useDataConnectorSafetyScores, useEntityMarginYtd, useDeliveryCenterPerformanceYtd, useLaneStabilityWindow } from './hooks/useGeotab'

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

type NavItem = {
  tab: AppTab
  label: string
  shortLabel: string
  Icon: LucideIcon
}

const navigationItems: NavItem[] = [
  { tab: 'dashboard', label: 'Dashboard', shortLabel: 'Dash', Icon: BarChart3 },
  { tab: 'control-tower', label: 'Control Tower', shortLabel: 'Tower', Icon: Activity },
  { tab: 'finance', label: 'Finance', shortLabel: 'Fin', Icon: DollarSign },
  { tab: 'operating-system', label: 'Org OS', shortLabel: 'Org', Icon: Users },
  { tab: 'hr-recruiting', label: 'HR Recruiting', shortLabel: 'HR', Icon: Users },
  { tab: 'maintenance', label: 'Maintenance', shortLabel: 'Maint', Icon: Wrench },
  { tab: 'coaching', label: 'Coaching', shortLabel: 'Coach', Icon: GraduationCap },
  { tab: 'replay', label: 'Routes', shortLabel: 'Routes', Icon: Route },
  { tab: 'stability', label: 'Stability', shortLabel: 'Stable', Icon: LineChart },
  { tab: 'fuel', label: 'Fuel', shortLabel: 'Fuel', Icon: Fuel },
  { tab: 'geofences', label: 'Zones', shortLabel: 'Zones', Icon: MapPin },
  { tab: 'compliance', label: 'ELD', shortLabel: 'ELD', Icon: Shield },
  { tab: 'reports', label: 'Reports', shortLabel: 'Reports', Icon: FileText },
  { tab: 'data-connector', label: 'Connector', shortLabel: 'Data', Icon: Database },
]

function getInitialTab(): AppTab {
  const hash = window.location.hash.replace('#', '') as AppTab
  return appTabs.includes(hash) ? hash : 'dashboard'
}

function FleetNav({
  activeTab,
  onSelect,
  variant,
}: {
  activeTab: AppTab
  onSelect: (tab: AppTab) => void
  variant: 'sidebar' | 'mobile'
}) {
  const sidebar = variant === 'sidebar'

  return (
    <nav
      aria-label="FleetPulse sections"
      className={sidebar ? 'space-y-1.5' : 'flex min-w-max gap-1.5'}
    >
      {navigationItems.map(({ tab, label, shortLabel, Icon }) => {
        const active = activeTab === tab
        return (
          <button
            key={tab}
            aria-current={active ? 'page' : undefined}
            aria-label={label}
            onClick={() => onSelect(tab)}
            className={
              sidebar
                ? `group flex h-10 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium transition ${
                    active
                      ? 'bg-white text-gray-950 shadow-sm light:bg-gray-950 light:text-white'
                      : 'text-gray-400 hover:bg-gray-900 hover:text-white light:text-gray-600 light:hover:bg-gray-100 light:hover:text-gray-950'
                  } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950`
                : `flex h-11 min-w-11 items-center justify-center gap-2 rounded-lg px-3 text-sm font-medium transition ${
                    active
                      ? 'bg-sky-500 text-white shadow-sm'
                      : 'text-gray-400 hover:bg-gray-900 hover:text-white light:text-gray-600 light:hover:bg-gray-100 light:hover:text-gray-950'
                  } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950`
            }
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className={sidebar ? 'truncate' : 'hidden sm:inline'}>{sidebar ? label : shortLabel}</span>
          </button>
        )
      })}
    </nav>
  )
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
  const fuelTrends = useFuelTrends(dashboardActive)
  const utilization7d = useDataConnectorVehicleKpis(7, dashboardActive)
  const safety7d = useDataConnectorSafetyScores(7, dashboardActive)
  const entityMargin = useEntityMarginYtd(dashboardActive)
  const deliveryPerformance = useDeliveryCenterPerformanceYtd(dashboardActive)
  const laneStability = useLaneStabilityWindow(364, dashboardActive)
  const authSession = useAuthSession(true)

  const activeLocationCount = locations.data?.length ?? null
  const headerSubtitle = activeLocationCount !== null
    ? `K1 Logistics · ${activeLocationCount.toLocaleString()} active location${activeLocationCount === 1 ? '' : 's'}`
    : 'K1 Logistics · location roster pending'
  const liveStatus = overview.error || dashboardValidation.error
    ? 'Degraded'
    : overview.loading || dashboardValidation.loading
    ? 'Syncing'
    : 'Live'
  const liveStatusClass = liveStatus === 'Degraded'
    ? 'bg-amber-400'
    : liveStatus === 'Syncing'
    ? 'bg-sky-400'
    : 'bg-emerald-400'

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
        className="sticky top-0 z-40 border-b border-gray-800/50 bg-gray-950/95 px-4 py-3 backdrop-blur-xl light:border-gray-200/70 light:bg-white/95 sm:px-6"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
      >
        <div className="mx-auto flex max-w-[1800px] flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3.5">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-sky-400/25 bg-sky-500/10 text-sky-300 light:text-sky-700">
                <Truck className="h-5 w-5" aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <h1 className="text-xl font-semibold tracking-normal text-white light:text-gray-950 sm:text-2xl">
                  FleetPulse
                </h1>
                <p className="hidden truncate text-xs text-gray-500 dark:text-gray-500 light:text-gray-600 sm:block">
                  {headerSubtitle}
                </p>
              </div>
            </div>
            <div className="flex items-center md:hidden">
              <span className={`inline-block h-2 w-2 rounded-full ${liveStatusClass}`} />
            </div>
          </div>

          <div className="flex w-full min-w-0 items-center gap-2 overflow-x-auto sm:justify-end sm:gap-3 lg:w-auto lg:overflow-visible">
            <div className="hidden items-center gap-2 rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-2 text-sm text-gray-400 light:border-gray-200 light:bg-gray-50 light:text-gray-600 md:flex">
              <motion.span
                className={`inline-block h-2 w-2 rounded-full ${liveStatusClass}`}
                animate={{ opacity: [1, 0.3, 1] }}
                transition={{ duration: 2, repeat: Infinity }}
              />
              <span>{liveStatus}</span>
            </div>
            <ThemeToggle />
            <UserLoginStatus session={authSession.data} loading={authSession.loading} error={authSession.error} />
          </div>

          <div className="-mx-4 mt-3 overflow-x-auto border-t border-gray-900 px-4 pt-3 light:border-gray-200 sm:-mx-6 sm:px-6 lg:hidden">
            <FleetNav activeTab={activeTab} onSelect={selectTab} variant="mobile" />
          </div>
        </div>
      </motion.header>

      <div className="mx-auto flex max-w-[1800px]">
        <aside className="sticky top-[73px] hidden h-[calc(100vh-73px)] w-64 shrink-0 border-r border-gray-900/80 px-4 py-5 light:border-gray-200 lg:block">
          <FleetNav activeTab={activeTab} onSelect={selectTab} variant="sidebar" />
          <div className="mt-6 rounded-lg border border-gray-800 bg-gray-900/40 p-3 light:border-gray-200 light:bg-white">
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-gray-500">Source Status</p>
            <div className="mt-3 space-y-2 text-xs text-gray-400 light:text-gray-600">
              <div className="flex items-center justify-between gap-3">
                <span>Locations</span>
                <span className="font-semibold text-gray-200 light:text-gray-900">
                  {activeLocationCount === null ? 'Pending' : activeLocationCount.toLocaleString()}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span>Session</span>
                <span className="font-semibold text-gray-200 light:text-gray-900">
                  {authSession.data?.auth_mode || 'Pending'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span>Seat</span>
                <span className="truncate text-right font-semibold text-gray-200 light:text-gray-900">
                  {authSession.data?.seat_access.primary_seat?.display_name || (authSession.data?.authenticated ? 'Unassigned' : 'Public')}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span>API</span>
                <span className="inline-flex items-center gap-1.5 font-semibold text-gray-200 light:text-gray-900">
                  <span className={`inline-block h-1.5 w-1.5 rounded-full ${liveStatusClass}`} />
                  {liveStatus}
                </span>
              </div>
            </div>
          </div>
        </aside>

        <motion.main
        className="min-w-0 flex-1 space-y-6 p-4 sm:p-6"
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
            entityMargin={entityMargin.data}
            entityMarginError={entityMargin.error}
            entityMarginLoading={entityMargin.loading}
            deliveryPerformance={deliveryPerformance.data}
            deliveryPerformanceError={deliveryPerformance.error}
            deliveryPerformanceLoading={deliveryPerformance.loading}
            laneStability={laneStability.data}
            laneStabilityError={laneStability.error}
            laneStabilityLoading={laneStability.loading}
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
          <FleetAnalytics
            loading={overview.loading || fuelTrends.loading || alerts.loading || vehicles.loading}
            overview={overview.data}
            locations={locations.data}
            vehicles={vehicles.data}
            alerts={alerts.data}
            fuelTrends={fuelTrends.data}
          />
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
                {locations.loading
                  ? 'Loading'
                  : `${(locations.data?.length ?? 0).toLocaleString()} Active`}
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
      </div>

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
