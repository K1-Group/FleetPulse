import { useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, Filter, ChevronDown, Activity, Clock, MapPin, Zap } from 'lucide-react'
import type { Vehicle } from '../types/fleet'
import { roundedMph } from '../utils/units'

interface Props {
  vehicles: Vehicle[] | null
  loading: boolean
  selectedVehicleId?: string | null
}

const statusBadge: Record<string, string> = {
  active: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  idle: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  parked: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30',
  offline: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
}

const statusIcon: Record<string, JSX.Element> = {
  active: <Activity className="w-3 h-3" />,
  idle: <Clock className="w-3 h-3" />,
  parked: <MapPin className="w-3 h-3" />,
  offline: <Zap className="w-3 h-3" />,
}

export default function VehicleList({ vehicles, loading, selectedVehicleId }: Props) {
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [locationFilter, setLocationFilter] = useState<string>('all')
  const [sortBy, setSortBy] = useState<'name' | 'status' | 'location' | 'speed'>('name')
  const [sortDesc, setSortDesc] = useState(false)

  const filteredAndSortedVehicles = useMemo(() => {
    if (!vehicles) return []

    let filtered = vehicles.filter(vehicle => {
      const matchesSearch = vehicle.name.toLowerCase().includes(searchTerm.toLowerCase())
      const matchesStatus = statusFilter === 'all' || vehicle.status === statusFilter
      const matchesLocation = locationFilter === 'all' || vehicle.location_name?.includes(locationFilter)
      
      return matchesSearch && matchesStatus && matchesLocation
    })

    // Sort vehicles
    filtered.sort((a, b) => {
      let aVal: any = (a as any)[sortBy] || ''
      let bVal: any = (b as any)[sortBy] || ''
      
      if (sortBy === 'speed') {
        aVal = a.position?.speed || 0
        bVal = b.position?.speed || 0
      } else if (sortBy === 'location') {
        aVal = a.location_name || ''
        bVal = b.location_name || ''
      }

      if (typeof aVal === 'string') {
        return sortDesc ? bVal.localeCompare(aVal) : aVal.localeCompare(bVal)
      }
      return sortDesc ? bVal - aVal : aVal - bVal
    })

    return filtered
  }, [vehicles, searchTerm, statusFilter, locationFilter, sortBy, sortDesc])

  const uniqueLocations = useMemo(() => {
    if (!vehicles) return []
    const locations = [...new Set(vehicles.map(v => v.location_name).filter(Boolean))]
    return locations.sort()
  }, [vehicles])

  const statusCounts = useMemo(() => {
    if (!vehicles) return {}
    return vehicles.reduce((acc, vehicle) => {
      acc[vehicle.status] = (acc[vehicle.status] || 0) + 1
      return acc
    }, {} as Record<string, number>)
  }, [vehicles])

  const handleSort = (column: 'name' | 'status' | 'location' | 'speed') => {
    if (sortBy === column) {
      setSortDesc(!sortDesc)
    } else {
      setSortBy(column)
      setSortDesc(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-gradient-to-br from-gray-900 to-gray-800 dark:from-gray-900 dark:to-gray-800 light:from-white light:to-gray-50 rounded-xl shadow-lg overflow-hidden border border-gray-800 dark:border-gray-800 light:border-gray-200"
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800/50 dark:border-gray-800/50 light:border-gray-200/50 bg-gradient-to-r from-gray-800 to-gray-700 dark:from-gray-800 dark:to-gray-700 light:from-gray-50 light:to-gray-100">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="font-semibold text-white dark:text-white light:text-gray-900 flex items-center gap-2">
              🚗 Fleet Vehicles
              <span className="text-xs bg-gray-700 dark:bg-gray-700 light:bg-gray-200 px-2 py-1 rounded-full text-gray-300 dark:text-gray-300 light:text-gray-700">
                {filteredAndSortedVehicles.length} of {vehicles?.length || 0}
              </span>
            </h2>
          </div>
          
          {/* Status Summary */}
          <div className="hidden sm:flex items-center gap-2">
            {Object.entries(statusCounts).map(([status, count]) => (
              <div key={status} className="flex items-center gap-1">
                {statusIcon[status]}
                <span className="text-xs text-gray-400 dark:text-gray-400 light:text-gray-600">{count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Filters */}
        <div className="mt-3 flex flex-col sm:flex-row gap-3">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-400 light:text-gray-500" />
            <input
              type="text"
              placeholder="Search vehicles..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-3 py-2 bg-gray-800 dark:bg-gray-800 light:bg-white border border-gray-700 dark:border-gray-700 light:border-gray-300 rounded-lg text-sm text-white dark:text-white light:text-gray-900 focus:outline-none focus:border-blue-500 transition-colors placeholder-gray-400 dark:placeholder-gray-400 light:placeholder-gray-500"
            />
          </div>

          {/* Status Filter */}
          <div className="relative">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="appearance-none bg-gray-800 dark:bg-gray-800 light:bg-white border border-gray-700 dark:border-gray-700 light:border-gray-300 rounded-lg px-3 py-2 pr-8 text-sm text-white dark:text-white light:text-gray-900 focus:outline-none focus:border-blue-500 transition-colors"
            >
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="idle">Idle</option>
              <option value="parked">Parked</option>
              <option value="offline">Offline</option>
            </select>
            <ChevronDown className="absolute right-2 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>

          {/* Location Filter */}
          <div className="relative">
            <select
              value={locationFilter}
              onChange={(e) => setLocationFilter(e.target.value)}
              className="appearance-none bg-gray-800 dark:bg-gray-800 light:bg-white border border-gray-700 dark:border-gray-700 light:border-gray-300 rounded-lg px-3 py-2 pr-8 text-sm text-white dark:text-white light:text-gray-900 focus:outline-none focus:border-blue-500 transition-colors"
            >
              <option value="all">All Locations</option>
              {uniqueLocations.map(location => (
                <option key={location} value={location || ''}>{location}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-800/50 dark:bg-gray-800/50 light:bg-gray-50 text-gray-400 dark:text-gray-400 light:text-gray-700">
            <tr>
              <th 
                className="px-4 py-3 text-left cursor-pointer hover:text-white transition-colors select-none"
                onClick={() => handleSort('name')}
              >
                <div className="flex items-center gap-2">
                  Vehicle Name
                  {sortBy === 'name' && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.5 }}
                      animate={{ opacity: 1, scale: 1 }}
                    >
                      {sortDesc ? '↓' : '↑'}
                    </motion.div>
                  )}
                </div>
              </th>
              <th 
                className="px-4 py-3 text-left cursor-pointer hover:text-white transition-colors select-none"
                onClick={() => handleSort('status')}
              >
                <div className="flex items-center gap-2">
                  Status
                  {sortBy === 'status' && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.5 }}
                      animate={{ opacity: 1, scale: 1 }}
                    >
                      {sortDesc ? '↓' : '↑'}
                    </motion.div>
                  )}
                </div>
              </th>
              <th 
                className="px-4 py-3 text-left cursor-pointer hover:text-white transition-colors select-none"
                onClick={() => handleSort('location')}
              >
                <div className="flex items-center gap-2">
                  Location
                  {sortBy === 'location' && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.5 }}
                      animate={{ opacity: 1, scale: 1 }}
                    >
                      {sortDesc ? '↓' : '↑'}
                    </motion.div>
                  )}
                </div>
              </th>
              <th 
                className="px-4 py-3 text-right cursor-pointer hover:text-white transition-colors select-none"
                onClick={() => handleSort('speed')}
              >
                <div className="flex items-center justify-end gap-2">
                  Speed
                  {sortBy === 'speed' && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.5 }}
                      animate={{ opacity: 1, scale: 1 }}
                    >
                      {sortDesc ? '↓' : '↑'}
                    </motion.div>
                  )}
                </div>
              </th>
              <th className="px-4 py-3 text-right">Last Contact</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {loading && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center">
                  <div className="flex items-center justify-center gap-2 text-gray-500">
                    <div className="animate-spin w-4 h-4 border-2 border-gray-600 border-t-gray-400 rounded-full"></div>
                    Loading vehicles...
                  </div>
                </td>
              </tr>
            )}
            
            <AnimatePresence>
              {filteredAndSortedVehicles.slice(0, 50).map((vehicle, index) => (
                <motion.tr
                  key={vehicle.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ delay: index * 0.02 }}
                  className={`hover:bg-gray-800/40 transition-colors group ${
                    selectedVehicleId === vehicle.id ? 'bg-yellow-500/10 ring-1 ring-yellow-400/40' : ''
                  }`}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-blue-600 rounded-lg flex items-center justify-center text-white text-xs font-bold">
                        {vehicle.name.charAt(0)}
                      </div>
                      <div>
                        <div className="font-medium text-white group-hover:text-blue-400 transition-colors">
                          {vehicle.name}
                        </div>
                        <div className="text-xs text-gray-500">
                          ID: {vehicle.id}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${statusBadge[vehicle.status]}`}>
                      {statusIcon[vehicle.status]}
                      <span className="capitalize">{vehicle.status}</span>
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 text-gray-300">
                      <MapPin className="w-4 h-4 text-gray-500" />
                      {vehicle.location_name || 'Unknown'}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <span className={`font-mono ${vehicle.position?.speed && vehicle.position.speed > 0 ? 'text-emerald-400' : 'text-gray-500'}`}>
                        {roundedMph(vehicle.position?.speed)}
                      </span>
                      <span className="text-xs text-gray-500">mph</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="text-xs text-gray-500 flex items-center justify-end gap-1">
                      <Clock className="w-3 h-3" />
                      {vehicle.last_contact ? new Date(vehicle.last_contact).toLocaleTimeString() : '—'}
                    </div>
                  </td>
                </motion.tr>
              ))}
            </AnimatePresence>

            {!loading && filteredAndSortedVehicles.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-500">
                  <div className="flex flex-col items-center gap-2">
                    <Search className="w-8 h-8 text-gray-600" />
                    <div>No vehicles found matching your filters</div>
                    <button 
                      onClick={() => {
                        setSearchTerm('')
                        setStatusFilter('all')
                        setLocationFilter('all')
                      }}
                      className="text-blue-400 hover:text-blue-300 text-sm transition-colors"
                    >
                      Clear filters
                    </button>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      {!loading && filteredAndSortedVehicles.length > 0 && (
        <div className="px-4 py-2 bg-gray-800/30 border-t border-gray-800/50 text-xs text-gray-500">
          Showing {Math.min(filteredAndSortedVehicles.length, 50)} of {filteredAndSortedVehicles.length} vehicles
          {filteredAndSortedVehicles.length > 50 && ' (limited to 50 for performance)'}
        </div>
      )}
    </motion.div>
  )
}
