import { motion } from 'framer-motion'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts'
import type { Alert, FleetOverview, FuelTrend, LocationStats } from '../types/fleet'

interface Props {
  loading?: boolean
  overview?: FleetOverview | null
  locations?: LocationStats[] | null
  alerts?: Alert[] | null
  fuelTrends?: FuelTrend[] | null
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#f97316', '#6b7280']

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-gray-900 dark:bg-gray-900 light:bg-white border border-gray-700 dark:border-gray-700 light:border-gray-300 rounded-lg p-3 shadow-xl">
        <p className="text-gray-300 dark:text-gray-300 light:text-gray-700 text-sm mb-2">{label}</p>
        {payload.map((entry: any, index: number) => (
          <p key={index} className="text-sm" style={{ color: entry.color }}>
            {entry.name}: {entry.value}
            {entry.name === 'Efficiency' && ' MPG'}
            {entry.name === 'Score' && '%'}
            {entry.name === 'Vehicles' && ' vehicles'}
            {entry.name === 'Alerts' && ' alerts'}
          </p>
        ))}
      </div>
    )
  }
  return null
}

const chartVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { 
    opacity: 1, 
    y: 0,
    transition: {
      type: "spring" as const,
      stiffness: 300,
      damping: 30
    }
  }
}

function hubLabel(name: string) {
  return name
    .replace(/\s+(Yard|Terminal|Hub)$/i, '')
    .replace('Kansas City', 'KC')
    .replace('San Antonio', 'SA')
    .replace('Little Rock', 'LR')
    .replace('Fort Worth', 'FTW')
}

function shortDate(value: string) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function normalizeAlertType(value: string) {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function EmptyChartState({ message }: { message: string }) {
  return (
    <div className="flex h-[200px] items-center justify-center rounded-lg border border-dashed border-gray-800 px-4 text-center text-sm text-gray-500 light:border-gray-200 light:text-gray-500">
      {message}
    </div>
  )
}

export default function FleetAnalytics({
  loading = false,
  overview = null,
  locations = null,
  alerts = null,
  fuelTrends = null,
}: Props) {
  const hubAssetData = (locations || []).map(location => ({
    location: hubLabel(location.name),
    vehicles: location.vehicle_count,
    active: location.active,
  }))
  const fuelEfficiencyData = (fuelTrends || [])
    .map(row => {
      const miles = Number(row.miles || 0)
      const gallons = Number(row.gallons || 0)
      if (!row.date || miles <= 0 || gallons <= 0) return null
      return {
        date: shortDate(row.date),
        efficiency: Number((miles / gallons).toFixed(1)),
      }
    })
    .filter((row): row is { date: string; efficiency: number } => Boolean(row))

  const fleetStateData = overview
    ? [
        { state: 'Active', vehicles: overview.active },
        { state: 'Idle', vehicles: overview.idle },
        { state: 'Parked', vehicles: overview.parked },
        { state: 'Offline', vehicles: overview.offline },
      ]
    : []

  const alertDistribution = Object.entries(
    (alerts || []).reduce<Record<string, number>>((acc, alert) => {
      const key = alert.alert_type || 'fleet_alert'
      acc[key] = (acc[key] || 0) + 1
      return acc
    }, {}),
  ).map(([name, value], index) => ({
    name: normalizeAlertType(name),
    value,
    color: COLORS[index % COLORS.length],
  }))

  if (loading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-gray-900 dark:bg-gray-900 light:bg-white rounded-xl p-6 border border-gray-800 dark:border-gray-800 light:border-gray-200">
            <div className="animate-pulse">
              <div className="h-4 bg-gray-700 dark:bg-gray-700 light:bg-gray-200 rounded w-1/3 mb-4" />
              <div className="h-48 bg-gray-700 dark:bg-gray-700 light:bg-gray-200 rounded" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <motion.h2 
        className="text-xl font-semibold text-white dark:text-white light:text-gray-900 mb-4 flex items-center gap-2"
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.2 }}
      >
        📊 Fleet Analytics
      </motion.h2>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Fuel Efficiency Trends */}
        <motion.div
          variants={chartVariants}
          initial="hidden"
          animate="visible"
          className="bg-gray-900/70 dark:bg-gray-900/70 light:bg-white/90 backdrop-blur-sm rounded-xl p-6 border border-gray-800 dark:border-gray-800 light:border-gray-200 hover:border-gray-700 dark:hover:border-gray-700 light:hover:border-gray-300 transition-colors duration-300"
        >
          <h3 className="text-lg font-medium text-white dark:text-white light:text-gray-900 mb-4 flex items-center gap-2">
            ⛽ Fuel Efficiency Trends
            <span className="text-xs bg-emerald-500/20 text-emerald-400 px-2 py-1 rounded-full">
              Geotab + AtoB
            </span>
          </h3>
          {fuelEfficiencyData.length ? (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={fuelEfficiencyData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                <XAxis dataKey="date" stroke="#9ca3af" fontSize={12} />
                <YAxis stroke="#9ca3af" fontSize={12} />
                <Tooltip content={<CustomTooltip />} />
                <Line
                  type="monotone"
                  dataKey="efficiency"
                  stroke="#10b981"
                  strokeWidth={3}
                  dot={{ fill: '#10b981', strokeWidth: 2, r: 4 }}
                  name="Efficiency"
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChartState message="No source-backed fuel gallons and mileage returned for the trend window." />
          )}
        </motion.div>

        {/* Hub Asset Coverage */}
        <motion.div
          variants={chartVariants}
          initial="hidden"
          animate="visible"
          transition={{ delay: 0.1 }}
          className="bg-gray-900/70 backdrop-blur-sm rounded-xl p-6 border border-gray-800 hover:border-gray-700 transition-colors duration-300"
        >
          <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
            📍 Assets by Hub
            <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-1 rounded-full">
              Geotab
            </span>
          </h3>
          {hubAssetData.length ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={hubAssetData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                <XAxis dataKey="location" stroke="#9ca3af" fontSize={10} angle={-45} textAnchor="end" height={60} />
                <YAxis stroke="#9ca3af" fontSize={12} allowDecimals={false} />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Bar dataKey="vehicles" name="Vehicles" radius={[4, 4, 0, 0]}>
                  {hubAssetData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.vehicles > 0 ? '#38bdf8' : '#475569'}
                    />
                  ))}
                </Bar>
                <Bar dataKey="active" name="Active" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-[200px] items-center justify-center rounded-lg border border-dashed border-gray-800 text-sm text-gray-500">
              No hub data returned
            </div>
          )}
        </motion.div>

        {/* Fleet Utilization */}
        <motion.div
          variants={chartVariants}
          initial="hidden"
          animate="visible"
          transition={{ delay: 0.2 }}
          className="bg-gray-900/70 backdrop-blur-sm rounded-xl p-6 border border-gray-800 hover:border-gray-700 transition-colors duration-300"
        >
          <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
            📈 Fleet Utilization
            <span className="text-xs bg-purple-500/20 text-purple-400 px-2 py-1 rounded-full">
              Geotab Live
            </span>
          </h3>
          {fleetStateData.length ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={fleetStateData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                <XAxis dataKey="state" stroke="#9ca3af" fontSize={12} />
                <YAxis stroke="#9ca3af" fontSize={12} allowDecimals={false} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="vehicles" name="Vehicles" radius={[4, 4, 0, 0]}>
                  {fleetStateData.map((entry, index) => (
                    <Cell
                      key={`fleet-state-${entry.state}`}
                      fill={['#10b981', '#f59e0b', '#64748b', '#ef4444'][index]}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChartState message="No live fleet state returned from Geotab overview." />
          )}
        </motion.div>

        {/* Alert Type Distribution */}
        <motion.div
          variants={chartVariants}
          initial="hidden"
          animate="visible"
          transition={{ delay: 0.3 }}
          className="bg-gray-900/70 backdrop-blur-sm rounded-xl p-6 border border-gray-800 hover:border-gray-700 transition-colors duration-300"
        >
          <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
            🚨 Alert Distribution
            <span className="text-xs bg-red-500/20 text-red-400 px-2 py-1 rounded-full">
              Last 7 Days
            </span>
          </h3>
          {alertDistribution.length ? (
            <div className="flex items-center">
              <ResponsiveContainer width="60%" height={200}>
                <PieChart>
                  <Pie
                    data={alertDistribution}
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    innerRadius={30}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                  >
                    {alertDistribution.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="w-40% space-y-2">
                {alertDistribution.map(item => (
                  <div key={item.name} className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: item.color }}
                    />
                    <span className="text-sm text-gray-300">{item.name}</span>
                    <span className="text-xs text-gray-500 ml-auto">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyChartState message="No recent Geotab alert rows returned for this window." />
          )}
        </motion.div>
      </div>
    </div>
  )
}
