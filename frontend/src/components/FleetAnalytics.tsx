import { motion } from 'framer-motion'
import {
  LineChart,
  Line,
  AreaChart,
  Area,
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
import type { LocationStats } from '../types/fleet'

interface Props {
  loading?: boolean
  locations?: LocationStats[] | null
}

const fuelEfficiencyData = [
  { date: 'Mon', efficiency: 8.2, trend: 8.5 },
  { date: 'Tue', efficiency: 7.8, trend: 8.3 },
  { date: 'Wed', efficiency: 8.5, trend: 8.1 },
  { date: 'Thu', efficiency: 8.1, trend: 7.9 },
  { date: 'Fri', efficiency: 7.9, trend: 8.0 },
  { date: 'Sat', efficiency: 8.3, trend: 8.2 },
  { date: 'Sun', efficiency: 8.6, trend: 8.4 },
]

const utilizationData = [
  { hour: '6AM', active: 12, idle: 8, maintenance: 2 },
  { hour: '8AM', active: 28, idle: 15, maintenance: 2 },
  { hour: '10AM', active: 35, idle: 8, maintenance: 2 },
  { hour: '12PM', active: 42, idle: 5, maintenance: 2 },
  { hour: '2PM', active: 38, idle: 9, maintenance: 2 },
  { hour: '4PM', active: 45, idle: 3, maintenance: 2 },
  { hour: '6PM', active: 32, idle: 12, maintenance: 2 },
  { hour: '8PM', active: 18, idle: 25, maintenance: 2 },
  { hour: '10PM', active: 8, idle: 35, maintenance: 2 },
]

// NOTE: Mock data for demo visualization
// Matches the safety score distribution in backend/services/safety_service.py
// Total of 100 alerts distributed across categories
// Production version would fetch from /api/alerts/distribution endpoint
const alertDistribution = [
  { name: 'Speeding', value: 35, color: '#ef4444' },
  { name: 'Idle Time', value: 28, color: '#f59e0b' },
  { name: 'Harsh Braking', value: 15, color: '#f97316' },
  { name: 'Route Deviation', value: 12, color: '#06b6d4' },
  { name: 'Maintenance', value: 10, color: '#8b5cf6' },
]

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

export default function FleetAnalytics({ loading = false, locations = null }: Props) {
  const hubAssetData = (locations || []).map(location => ({
    location: hubLabel(location.name),
    vehicles: location.vehicle_count,
    active: location.active,
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
              This Week
            </span>
          </h3>
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
              <Line 
                type="monotone" 
                dataKey="trend" 
                stroke="#6b7280" 
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
                name="Target"
              />
            </LineChart>
          </ResponsiveContainer>
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

        {/* Fleet Utilization Over Time */}
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
              24h Pattern
            </span>
          </h3>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={utilizationData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis dataKey="hour" stroke="#9ca3af" fontSize={12} />
              <YAxis stroke="#9ca3af" fontSize={12} />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="active"
                stackId="1"
                stroke="#10b981"
                fill="#10b981"
                fillOpacity={0.8}
                name="Active"
              />
              <Area
                type="monotone"
                dataKey="idle"
                stackId="1"
                stroke="#f59e0b"
                fill="#f59e0b"
                fillOpacity={0.8}
                name="Idle"
              />
              <Area
                type="monotone"
                dataKey="maintenance"
                stackId="1"
                stroke="#ef4444"
                fill="#ef4444"
                fillOpacity={0.8}
                name="Maintenance"
              />
            </AreaChart>
          </ResponsiveContainer>
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
                >
                  {alertDistribution.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
              </PieChart>
            </ResponsiveContainer>
            <div className="w-40% space-y-2">
              {alertDistribution.map((item, index) => (
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
        </motion.div>
      </div>
    </div>
  )
}
