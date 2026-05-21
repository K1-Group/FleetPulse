import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { MapContainer, TileLayer, Marker, Popup, Tooltip, Circle, Polyline, useMap } from 'react-leaflet'
import { Eye, EyeOff, Activity, MapPin, Navigation, Layers, Truck } from 'lucide-react'
import L from 'leaflet'
import type { Vehicle, LocationStats, ControlTowerTrailerLiveAsset } from '../types/fleet'
import { formatMph } from '../utils/units'

interface Props {
  vehicles: Vehicle[] | null
  locations: LocationStats[] | null
  trailers?: ControlTowerTrailerLiveAsset[] | null
  selectedVehicleId?: string | null
}

interface RouteTrail {
  vehicleId: string
  vehicleName: string
  points: [number, number][]
  color: string
  totalPoints: number
}

const statusColor: Record<string, string> = {
  active: '#10b981',
  idle: '#f59e0b', 
  parked: '#6366f1',
  offline: '#6b7280',
}

const statusEmoji: Record<string, string> = {
  active: '🟢',
  idle: '🟡',
  parked: '🔵', 
  offline: '⚫'
}

function vehicleIcon(status: string, isMoving: boolean = false, isSelected: boolean = false) {
  const color = statusColor[status] || '#6b7280'
  const size = isSelected ? 24 : isMoving ? 16 : 14
  const animation = isMoving ? 'animation: pulse 1.5s infinite;' : ''
  const border = isSelected ? '3px solid #facc15' : '2px solid white'
  
  return L.divIcon({
    className: '',
    html: `
      <div style="
        width:${size}px;
        height:${size}px;
        border-radius:50%;
        background:${color};
        border:${border};
        box-shadow:0 0 8px rgba(0,0,0,.6);
        ${animation}
        transform: translate(-50%, -50%);
      "></div>
      <style>
        @keyframes pulse {
          0%, 100% { box-shadow: 0 0 8px rgba(0,0,0,.6), 0 0 0 0 ${color}; }
          50% { box-shadow: 0 0 8px rgba(0,0,0,.6), 0 0 0 6px rgba(16, 185, 129, 0.2); }
        }
      </style>
    `,
    iconSize: [size, size],
    iconAnchor: [size/2, size/2],
  })
}

function trailerIcon(trailer: ControlTowerTrailerLiveAsset) {
  const hasCustody = Boolean(trailer.custody.vehicle_id)
  const color = hasCustody ? '#06b6d4' : trailer.position ? '#f59e0b' : '#6b7280'

  return L.divIcon({
    className: '',
    html: `
      <div style="
        width:18px;
        height:18px;
        border-radius:4px;
        background:${color};
        border:2px solid white;
        box-shadow:0 0 8px rgba(0,0,0,.6);
        transform: translate(-50%, -50%) rotate(45deg);
      "></div>
    `,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  })
}

function locationIcon(locationStats: LocationStats) {
  const color = locationStats.safety_score >= 90 ? '#10b981' : locationStats.safety_score >= 85 ? '#f59e0b' : '#ef4444'
  return L.divIcon({
    className: '',
    html: `
      <div style="
        width: 24px;
        height: 24px;
        background: ${color};
        border: 3px solid white;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 10px;
        font-weight: bold;
        color: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.4);
      ">${locationStats.vehicle_count}</div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  })
}

function MapAutoFit({ positions }: { positions: [number, number][] }) {
  const map = useMap()

  useEffect(() => {
    if (positions.length === 0) return

    if (positions.length === 1) {
      map.setView(positions[0], Math.max(map.getZoom(), 10), { animate: true })
      return
    }

    map.fitBounds(L.latLngBounds(positions), {
      animate: true,
      maxZoom: 12,
      padding: [32, 32]
    })
  }, [map, positions])

  return null
}

const formatLastUpdated = (value: string | null): string => {
  if (!value) return 'No live contact yet'

  const timestamp = new Date(value)
  if (Number.isNaN(timestamp.getTime())) return 'Unknown'

  return timestamp.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  })
}

const assetLabel = (vehicle: Vehicle): string => vehicle.name || vehicle.id || 'Unknown asset'

export default function FleetMap({ vehicles, locations, trailers, selectedVehicleId }: Props) {
  const [showVehicles, setShowVehicles] = useState(true)
  const [showTrailers, setShowTrailers] = useState(true)
  const [showLocations, setShowLocations] = useState(true)
  const [showRoutes, setShowRoutes] = useState(false)
  const [showCustodyLinks, setShowCustodyLinks] = useState(true)
  const [showOffline, setShowOffline] = useState(false)
  const [selectedLocation, setSelectedLocation] = useState<string | null>(null)
  const [routeTrails, setRouteTrails] = useState<RouteTrail[]>([])
  const [routesLoading, setRoutesLoading] = useState(false)
  const [routesError, setRoutesError] = useState<string | null>(null)

  // DFW center
  const center: [number, number] = [32.82, -97.00]

  // Filter vehicles by selected location
  const filteredVehicles = useMemo(() => {
    if (!vehicles) return []
    return vehicles.filter(v => {
      if (!showOffline && v.status === 'offline') return false
      if (!selectedLocation) return true
      return v.location_name === selectedLocation
    })
  }, [vehicles, selectedLocation, showOffline])

  const filteredTrailers = useMemo(() => {
    if (!trailers) return []
    return trailers.filter(trailer => {
      if (!showOffline && !trailer.position) return false
      if (!selectedLocation) return true
      return trailer.location_name === selectedLocation
    })
  }, [trailers, selectedLocation, showOffline])

  const routeVehicles = useMemo(
    () => filteredVehicles.filter(v => v.status === 'active' && v.position).slice(0, 5),
    [filteredVehicles]
  )

  useEffect(() => {
    if (!showRoutes || routeVehicles.length === 0) {
      setRouteTrails([])
      setRoutesLoading(false)
      setRoutesError(null)
      return
    }

    let cancelled = false
    const controller = new AbortController()

    const fetchRoutes = async () => {
      setRoutesLoading(true)
      setRoutesError(null)

      try {
        const trails = await Promise.all(
          routeVehicles.map(async vehicle => {
            const toDate = vehicle.last_contact ? new Date(vehicle.last_contact) : new Date()
            if (Number.isNaN(toDate.getTime())) return null

            const fromDate = new Date(toDate.getTime() - 60 * 60 * 1000)
            const url = `/api/trips/vehicle/${encodeURIComponent(vehicle.id)}/route?from=${encodeURIComponent(fromDate.toISOString())}&to=${encodeURIComponent(toDate.toISOString())}`
            const response = await fetch(url, { signal: controller.signal })
            if (!response.ok) return null

            const payload = await response.json()
            const points = (payload.points || [])
              .filter((point: any) => Number.isFinite(point.latitude) && Number.isFinite(point.longitude))
              .slice(-200)
              .map((point: any) => [point.latitude, point.longitude] as [number, number])

            if (points.length < 2) return null

            return {
              vehicleId: vehicle.id,
              vehicleName: vehicle.name,
              points,
              color: statusColor[vehicle.status] || '#10b981',
              totalPoints: payload.total_points || points.length
            }
          })
        )

        if (!cancelled) {
          setRouteTrails(trails.filter((trail): trail is RouteTrail => trail !== null))
        }
      } catch (error: any) {
        if (!cancelled && error.name !== 'AbortError') {
          setRouteTrails([])
          setRoutesError('Route history unavailable')
        }
      } finally {
        if (!cancelled) setRoutesLoading(false)
      }
    }

    fetchRoutes()

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [routeVehicles, showRoutes])

  const visiblePositions = useMemo(() => {
    const vehiclePositions = showVehicles
      ? filteredVehicles
          .filter(v => v.position)
          .map(v => [v.position!.latitude, v.position!.longitude] as [number, number])
      : []

    const locationPositions = showLocations && vehiclePositions.length === 0
      ? (locations || []).map(loc => [loc.latitude, loc.longitude] as [number, number])
      : []

    const trailerPositions = showTrailers
      ? filteredTrailers
          .filter(trailer => trailer.position)
          .map(trailer => [trailer.position!.latitude, trailer.position!.longitude] as [number, number])
      : []

    return [...vehiclePositions, ...trailerPositions, ...locationPositions]
  }, [filteredVehicles, filteredTrailers, locations, showLocations, showTrailers, showVehicles])

  const lastUpdated = useMemo(() => {
    const timestamps = (vehicles || [])
      .map(v => v.last_contact ? new Date(v.last_contact).getTime() : NaN)
      .filter(Number.isFinite)

    if (timestamps.length === 0) return null
    return new Date(Math.max(...timestamps)).toISOString()
  }, [vehicles])

  const trailerLastUpdated = useMemo(() => {
    const timestamps = (trailers || [])
      .map(trailer => {
        const value = trailer.geotab_last_contact || trailer.xtra_last_event?.timestamp
        return value ? new Date(value).getTime() : NaN
      })
      .filter(Number.isFinite)

    if (timestamps.length === 0) return null
    return new Date(Math.max(...timestamps)).toISOString()
  }, [trailers])

  // Status summary
  const statusSummary = useMemo(() => {
    if (!vehicles) return {}
    return vehicles.reduce((acc, v) => {
      acc[v.status] = (acc[v.status] || 0) + 1
      return acc
    }, {} as Record<string, number>)
  }, [vehicles])

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="bg-gradient-to-br from-gray-900 to-gray-800 dark:from-gray-900 dark:to-gray-800 light:from-white light:to-gray-50 rounded-xl overflow-hidden shadow-lg border border-gray-800 dark:border-gray-800 light:border-gray-200"
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800/50 bg-gradient-to-r from-gray-800 to-gray-700">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-semibold text-white flex items-center gap-2">
            <MapPin className="w-5 h-5 text-blue-400" />
            Live Fleet Map
            <span className="text-xs bg-emerald-500/20 text-emerald-400 px-2 py-1 rounded-full">
              Geotab live
            </span>
          </h2>
          
          {/* Map Controls */}
          <div className="flex items-center gap-2">
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setShowVehicles(!showVehicles)}
              className={`p-2 rounded-lg transition-colors flex items-center gap-1 ${
                showVehicles ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400'
              }`}
            >
              {showVehicles ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
              <span className="hidden sm:inline text-xs">Vehicles</span>
            </motion.button>

            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setShowOffline(!showOffline)}
              className={`p-2 rounded-lg transition-colors flex items-center gap-1 ${
                showOffline ? 'bg-gray-500 text-white' : 'bg-gray-700 text-gray-400'
              }`}
            >
              {showOffline ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
              <span className="hidden sm:inline text-xs">Offline</span>
            </motion.button>

            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setShowTrailers(!showTrailers)}
              className={`p-2 rounded-lg transition-colors flex items-center gap-1 ${
                showTrailers ? 'bg-cyan-600 text-white' : 'bg-gray-700 text-gray-400'
              }`}
            >
              <Truck className="w-4 h-4" />
              <span className="hidden sm:inline text-xs">Trailers</span>
            </motion.button>

            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setShowCustodyLinks(!showCustodyLinks)}
              className={`p-2 rounded-lg transition-colors flex items-center gap-1 ${
                showCustodyLinks ? 'bg-teal-600 text-white' : 'bg-gray-700 text-gray-400'
              }`}
            >
              <Layers className="w-4 h-4" />
              <span className="hidden sm:inline text-xs">Custody</span>
            </motion.button>
            
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setShowLocations(!showLocations)}
              className={`p-2 rounded-lg transition-colors flex items-center gap-1 ${
                showLocations ? 'bg-purple-600 text-white' : 'bg-gray-700 text-gray-400'
              }`}
            >
              <MapPin className="w-4 h-4" />
              <span className="hidden sm:inline text-xs">Locations</span>
            </motion.button>
            
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setShowRoutes(!showRoutes)}
              className={`p-2 rounded-lg transition-colors flex items-center gap-1 ${
                showRoutes ? 'bg-emerald-600 text-white' : 'bg-gray-700 text-gray-400'
              }`}
            >
              <Navigation className="w-4 h-4" />
              <span className="hidden sm:inline text-xs">Routes</span>
            </motion.button>
          </div>
        </div>

        {/* Status Legend & Location Filter */}
        <div className="flex items-center justify-between">
          <div className="flex flex-wrap gap-3 text-xs">
            {Object.entries(statusColor).map(([status, color]) => (
              <motion.span
                key={status}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                className="flex items-center gap-1.5 text-gray-300"
              >
                <span 
                  className="inline-block w-2.5 h-2.5 rounded-full"
                  style={{ background: color }}
                />
                <span className="capitalize">{status}</span>
                <span className="text-gray-500">({statusSummary[status] || 0})</span>
              </motion.span>
            ))}
          </div>

          {/* Location Filter */}
          <select
            value={selectedLocation || ''}
            onChange={(e) => setSelectedLocation(e.target.value || null)}
            className="bg-gray-700 border border-gray-600 rounded-lg px-2 py-1 text-xs focus:outline-none focus:border-blue-500"
          >
            <option value="">All Locations</option>
            {locations?.map(loc => (
              <option key={loc.name} value={loc.name}>{loc.name}</option>
            ))}
          </select>
        </div>
        <div className="mt-2 text-xs text-gray-400">
          Last Geotab contact: {formatLastUpdated(lastUpdated)}
          <span className="mx-2 text-gray-600">|</span>
          Trailer feed: {formatLastUpdated(trailerLastUpdated)}
        </div>
      </div>

      {/* Map Container */}
      <div className="relative">
        {(!vehicles && !locations) ? (
          <div className="h-[420px] flex items-center justify-center bg-gray-800/50">
            <div className="flex items-center gap-3 text-gray-400">
              <div className="animate-spin w-6 h-6 border-2 border-gray-600 border-t-gray-400 rounded-full"></div>
              Loading map data...
            </div>
          </div>
        ) : (
          <MapContainer 
            center={center} 
            zoom={11} 
            style={{ height: 420 }} 
            scrollWheelZoom
            className="z-10"
          >
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              attribution='&copy; <a href="https://carto.com/">CARTO</a>'
            />
            <MapAutoFit positions={visiblePositions} />
            
            {/* Location zones and markers */}
            {showLocations && locations?.map(loc => (
              <div key={loc.name}>
                <Circle
                  center={[loc.latitude, loc.longitude]}
                  radius={300}
                  pathOptions={{ 
                    color: loc.safety_score >= 90 ? '#10b981' : loc.safety_score >= 85 ? '#f59e0b' : '#ef4444',
                    fillOpacity: 0.1, 
                    weight: 2,
                    dashArray: selectedLocation === loc.name ? '0' : '5, 5'
                  }}
                />
                <Marker
                  position={[loc.latitude, loc.longitude]}
                  icon={locationIcon(loc)}
                >
                  <Popup className="dark-popup">
                    <div className="text-sm">
                      <div className="font-semibold text-white mb-1">{loc.name}</div>
                      <div className="text-gray-300 space-y-1">
                        <div>🚗 {loc.vehicle_count} vehicles</div>
                        <div>🛡️ Safety: {loc.safety_score}%</div>
                        <div>📊 Utilization: {Math.round(loc.vehicle_count / 8 * 100)}%</div>
                      </div>
                    </div>
                  </Popup>
                </Marker>
              </div>
            ))}
            
            {/* Vehicle markers */}
            {showVehicles && filteredVehicles?.filter(v => v.position).map(v => (
              <Marker
                key={v.id}
                position={[v.position!.latitude, v.position!.longitude]}
                icon={vehicleIcon(
                  v.status,
                  v.status === 'active' && (v.position?.speed || 0) > 5,
                  selectedVehicleId === v.id
                )}
              >
                <Tooltip
                  direction="top"
                  offset={[0, -10]}
                  opacity={1}
                  sticky
                  className="fleet-vehicle-tooltip"
                >
                  <div className="text-xs">
                    <div className="font-semibold">Asset: {assetLabel(v)}</div>
                    <div className="capitalize">Status: {v.status}</div>
                    <div>Speed: {formatMph(v.position?.speed)}</div>
                  </div>
                </Tooltip>
                <Popup className="dark-popup">
                  <div className="text-sm">
                    <div className="font-semibold text-white mb-1 flex items-center gap-2">
                      {statusEmoji[v.status]} Asset {assetLabel(v)}
                    </div>
                    <div className="text-gray-300 space-y-1">
                      <div className="text-xs text-gray-400">Geotab ID: {v.id}</div>
                      <div>Status: <span className="capitalize">{v.status}</span></div>
                      <div>Speed: {formatMph(v.position?.speed)}</div>
                      {v.location_name && <div>📍 {v.location_name}</div>}
                      {v.last_contact && (
                        <div className="text-xs text-gray-400">
                          Last contact: {new Date(v.last_contact).toLocaleTimeString()}
                        </div>
                      )}
                    </div>
                  </div>
                </Popup>
              </Marker>
            ))}

            {/* Trailer markers */}
            {showTrailers && filteredTrailers.filter(trailer => trailer.position).map(trailer => (
              <Marker
                key={trailer.geotab_device_id || trailer.trailer_id}
                position={[trailer.position!.latitude, trailer.position!.longitude]}
                icon={trailerIcon(trailer)}
              >
                <Tooltip
                  direction="top"
                  offset={[0, -10]}
                  opacity={1}
                  sticky
                  className="fleet-vehicle-tooltip"
                >
                  <div className="text-xs">
                    <div className="font-semibold">Trailer: {trailer.trailer_id}</div>
                    <div>GPS: {trailer.gps_status}</div>
                    <div>Custody: {trailer.custody.vehicle_name || 'Unassigned'}</div>
                  </div>
                </Tooltip>
                <Popup className="dark-popup">
                  <div className="text-sm">
                    <div className="font-semibold text-white mb-1 flex items-center gap-2">
                      Trailer {trailer.trailer_id}
                    </div>
                    <div className="text-gray-300 space-y-1">
                      {trailer.geotab_device_id && <div className="text-xs text-gray-400">Geotab ID: {trailer.geotab_device_id}</div>}
                      <div>GPS: <span className="capitalize">{trailer.gps_status}</span></div>
                      <div>Speed: {formatMph(trailer.speed)}</div>
                      {trailer.location_name && <div>Location: {trailer.location_name}</div>}
                      {trailer.xtra_last_event && (
                        <div>XTRA: {trailer.xtra_last_event.event_type.replace('_', ' ')} {trailer.xtra_last_event.location ? `at ${trailer.xtra_last_event.location}` : ''}</div>
                      )}
                      <div>Vehicle: {trailer.custody.vehicle_name || 'Unassigned'}</div>
                      {trailer.custody.driver_name && <div>Driver: {trailer.custody.driver_name}</div>}
                      {trailer.custody.distance_meters !== null && <div>Distance: {Math.round(trailer.custody.distance_meters)} m</div>}
                      <div className="text-xs text-gray-400">Confidence: {trailer.custody.confidence}</div>
                    </div>
                  </div>
                </Popup>
              </Marker>
            ))}

            {/* Trailer-to-tractor custody inference links */}
            {showTrailers && showCustodyLinks && filteredTrailers
              .filter(trailer => trailer.position && trailer.custody.vehicle_position)
              .map(trailer => (
                <Polyline
                  key={`custody-${trailer.geotab_device_id || trailer.trailer_id}`}
                  positions={[
                    [trailer.position!.latitude, trailer.position!.longitude],
                    [trailer.custody.vehicle_position!.latitude, trailer.custody.vehicle_position!.longitude],
                  ]}
                  pathOptions={{
                    color: trailer.custody.confidence === 'high' ? '#06b6d4' : '#f59e0b',
                    weight: 2,
                    opacity: 0.7,
                    dashArray: '4, 6',
                  }}
                />
              ))}

            {/* Route trails */}
            {showRoutes && routeTrails.map(({ vehicleId, points, color }) => (
              <Polyline
                key={vehicleId}
                positions={points}
                pathOptions={{
                  color,
                  weight: 3,
                  opacity: 0.6,
                  dashArray: '10, 5'
                }}
              />
            ))}
          </MapContainer>
        )}

        {/* Map overlay info */}
        <div className="absolute bottom-4 left-4 bg-black/70 dark:bg-black/70 light:bg-white/90 backdrop-blur-sm rounded-lg p-3 text-xs text-white dark:text-white light:text-gray-900 z-20 border border-gray-700 dark:border-gray-700 light:border-gray-200 max-w-[calc(100%-2rem)]">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-1">
              <Activity className="w-3 h-3 text-emerald-400" />
              <span>{filteredVehicles?.filter(v => v.status === 'active').length || 0} active</span>
            </div>
            <div className="flex items-center gap-1">
              <MapPin className="w-3 h-3 text-blue-400" />
              <span>{locations?.length || 0} locations</span>
            </div>
            <div className="flex items-center gap-1">
              <Truck className="w-3 h-3 text-cyan-400" />
              <span>{filteredTrailers.filter(trailer => trailer.position).length} trailers</span>
            </div>
            <div className="flex items-center gap-1">
              <Layers className="w-3 h-3 text-teal-400" />
              <span>{filteredTrailers.filter(trailer => trailer.custody.vehicle_id).length} custody</span>
            </div>
            {selectedLocation && (
              <div className="text-yellow-400">
                Filtered: {selectedLocation}
              </div>
            )}
            {showRoutes && (
              <div className={routesError ? 'text-red-300' : 'text-emerald-300'}>
                {routesLoading
                  ? 'Loading Geotab routes...'
                  : routesError || `${routeTrails.length} live route trail${routeTrails.length === 1 ? '' : 's'}`}
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  )
}
