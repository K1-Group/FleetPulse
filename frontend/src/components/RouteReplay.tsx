import React, { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { MapContainer, TileLayer, Polyline, Marker, useMap } from 'react-leaflet'
import L, { LatLngExpression } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Play, Pause, RotateCcw, Calendar, Clock, MapPin, Gauge, Route, ArrowLeft } from 'lucide-react'
import { formatMph, kmhToMph } from '../utils/units'

// Fix for default markers in Leaflet with Webpack
delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
})

// Vehicle marker icon
const vehicleIcon = new L.Icon({
  iconUrl: 'data:image/svg+xml;base64,' + btoa(`
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#3B82F6">
      <path d="M18.92 5.01C18.72 4.42 18.16 4 17.5 4h-11c-.66 0-1.22.42-1.42 1.01L3 11v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.5 15c-.83 0-1.5-.67-1.5-1.5S5.67 12 6.5 12s1.5.67 1.5 1.5S7.33 15 6.5 15zm11 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zM5 10l1.5-4.5h11L19 10H5z"/>
    </svg>
  `),
  iconSize: [32, 32],
  iconAnchor: [16, 16],
})

interface RoutePoint {
  timestamp: string
  latitude: number
  longitude: number
  speed_kmh: number
}

interface Trip {
  id: string
  start: {
    timestamp: string
    latitude: number
    longitude: number
  }
  stop: {
    timestamp: string
    latitude: number
    longitude: number
  }
  distance_km: number
  duration_min: number
  driver_name: string
}

interface SpeedData {
  timestamp: string
  speed_kmh: number
}

interface RouteReplayProps {
  vehicleId?: string
  onClose?: () => void
}

// Component to handle map bounds when route changes
function RouteBounds({ points }: { points: RoutePoint[] }) {
  const map = useMap()
  
  useEffect(() => {
    if (points.length > 0) {
      const bounds = L.latLngBounds(points.map(p => [p.latitude, p.longitude]))
      map.fitBounds(bounds, { padding: [20, 20] })
    }
  }, [points, map])
  
  return null
}

export default function RouteReplay({ vehicleId, onClose }: RouteReplayProps) {
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0])
  const [trips, setTrips] = useState<Trip[]>([])
  const [selectedTrip, setSelectedTrip] = useState<Trip | null>(null)
  const [routePoints, setRoutePoints] = useState<RoutePoint[]>([])
  const [speedData, setSpeedData] = useState<SpeedData[]>([])
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentPointIndex, setCurrentPointIndex] = useState(0)
  const [playbackSpeed, setPlaybackSpeed] = useState(1)
  const [loading, setLoading] = useState(false)
  
  const intervalRef = useRef<number | null>(null)
  
  // Fetch trips for selected date
  const fetchTrips = async () => {
    if (!vehicleId) return
    
    setLoading(true)
    try {
      const response = await fetch(`/api/trips/vehicle/${vehicleId}?date=${selectedDate}`)
      const data = await response.json()
      setTrips(data.trips || [])
      if (data.trips && data.trips.length > 0) {
        setSelectedTrip(data.trips[0])
      }
    } catch (error) {
      console.error('Failed to fetch trips:', error)
    } finally {
      setLoading(false)
    }
  }
  
  // Fetch route data for selected trip
  const fetchRouteData = async (trip: Trip) => {
    if (!vehicleId) return
    
    setLoading(true)
    try {
      const [routeResponse, speedResponse] = await Promise.all([
        fetch(`/api/trips/vehicle/${vehicleId}/route?from=${trip.start.timestamp}&to=${trip.stop.timestamp}`),
        fetch(`/api/trips/vehicle/${vehicleId}/speed?from=${trip.start.timestamp}&to=${trip.stop.timestamp}`)
      ])
      
      const routeData = await routeResponse.json()
      const speedData = await speedResponse.json()
      
      setRoutePoints(routeData.points || [])
      setSpeedData(speedData.speed_data || [])
      setCurrentPointIndex(0)
      setIsPlaying(false)
    } catch (error) {
      console.error('Failed to fetch route data:', error)
    } finally {
      setLoading(false)
    }
  }
  
  // Effect to fetch trips when date or vehicle changes
  useEffect(() => {
    fetchTrips()
  }, [selectedDate, vehicleId])
  
  // Effect to fetch route data when trip changes
  useEffect(() => {
    if (selectedTrip) {
      fetchRouteData(selectedTrip)
    }
  }, [selectedTrip])
  
  // Playback control
  useEffect(() => {
    if (isPlaying && routePoints.length > 0) {
      intervalRef.current = setInterval(() => {
        setCurrentPointIndex(prev => {
          if (prev >= routePoints.length - 1) {
            setIsPlaying(false)
            return routePoints.length - 1
          }
          return prev + 1
        })
      }, 1000 / playbackSpeed)
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [isPlaying, routePoints.length, playbackSpeed])
  
  // Get color for route segment based on speed
  const getSpeedColor = (speedKmh: number) => {
    const speedMph = kmhToMph(speedKmh)
    if (speedMph > 70) return '#EF4444' // Red for high speed
    if (speedMph > 50) return '#F59E0B' // Yellow for medium speed
    return '#10B981' // Green for normal speed
  }
  
  // Create colored route segments
  const createRouteSegments = () => {
    if (routePoints.length < 2) return []
    
    const segments = []
    for (let i = 0; i < routePoints.length - 1; i++) {
      const point1 = routePoints[i]
      const point2 = routePoints[i + 1]
      const avgSpeed = (point1.speed_kmh + point2.speed_kmh) / 2
      
      segments.push({
        positions: [[point1.latitude, point1.longitude], [point2.latitude, point2.longitude]] as LatLngExpression[],
        color: getSpeedColor(avgSpeed),
        opacity: i <= currentPointIndex ? 1 : 0.3
      })
    }
    
    return segments
  }
  
  const currentPoint = routePoints[currentPointIndex]
  const currentSpeed = currentPoint?.speed_kmh || 0
  const routeSegments = createRouteSegments()
  
  // Calculate progress and stats
  const progress = routePoints.length > 0 ? (currentPointIndex / (routePoints.length - 1)) * 100 : 0
  const elapsedTime = currentPoint && selectedTrip 
    ? new Date(currentPoint.timestamp).getTime() - new Date(selectedTrip.start.timestamp).getTime()
    : 0
  const elapsedMinutes = Math.floor(elapsedTime / 1000 / 60)
  const elapsedSeconds = Math.floor((elapsedTime / 1000) % 60)
  
  return (
    <div className="fixed inset-0 bg-black z-50">
      {/* Header */}
      <div className="absolute top-0 left-0 right-0 z-10 bg-gradient-to-r from-gray-900/95 to-gray-800/95 backdrop-blur-sm border-b border-gray-700 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="p-2 rounded-lg bg-gray-700/50 hover:bg-gray-600/50 text-gray-300 hover:text-white transition-colors"
              title="Back to Dashboard"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <h1 className="text-xl font-bold text-white flex items-center gap-2">
              <Route className="w-5 h-5 text-blue-400" />
              Route Replay
              {vehicleId && <span className="text-sm text-gray-400">Vehicle {vehicleId}</span>}
            </h1>
          </div>
          
          <div className="flex items-center gap-4">
            {/* Date Picker */}
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-gray-400" />
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="bg-gray-800 border border-gray-600 rounded px-3 py-1 text-white text-sm"
              />
            </div>
            
            {/* Trip Selector */}
            {trips.length > 0 && (
              <select
                value={selectedTrip?.id || ''}
                onChange={(e) => {
                  const trip = trips.find(t => t.id === e.target.value)
                  if (trip) setSelectedTrip(trip)
                }}
                className="bg-gray-800 border border-gray-600 rounded px-3 py-1 text-white text-sm"
              >
                {trips.map((trip, index) => (
                  <option key={trip.id} value={trip.id}>
                    Trip {index + 1} ({trip.distance_km.toFixed(1)} km)
                  </option>
                ))}
              </select>
            )}
            
            {onClose && (
              <button
                onClick={onClose}
                className="bg-red-600 hover:bg-red-700 text-white px-4 py-1 rounded text-sm"
              >
                Close
              </button>
            )}
          </div>
        </div>
      </div>
      
      {/* Map */}
      <div className="h-full pt-20 pb-32">
        {routePoints.length > 0 && (
          <MapContainer
            center={[routePoints[0].latitude, routePoints[0].longitude]}
            zoom={13}
            className="h-full w-full"
            zoomControl={false}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            
            <RouteBounds points={routePoints} />
            
            {/* Route segments with speed-based colors */}
            {routeSegments.map((segment, index) => (
              <Polyline
                key={index}
                positions={segment.positions}
                color={segment.color}
                weight={4}
                opacity={segment.opacity}
              />
            ))}
            
            {/* Current position marker */}
            {currentPoint && (
              <Marker
                position={[currentPoint.latitude, currentPoint.longitude]}
                icon={vehicleIcon}
              />
            )}
            
            {/* Start and end markers */}
            {selectedTrip && (
              <>
                <Marker position={[selectedTrip.start.latitude, selectedTrip.start.longitude]} />
                <Marker position={[selectedTrip.stop.latitude, selectedTrip.stop.longitude]} />
              </>
            )}
          </MapContainer>
        )}
        
        {loading && (
          <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-20">
            <div className="flex flex-col items-center gap-3">
              <div className="w-10 h-10 border-4 border-blue-400 border-t-transparent rounded-full animate-spin" />
              <div className="text-white text-lg">Loading route data...</div>
            </div>
          </div>
        )}
      </div>
      
      {/* Control Panel */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-gray-900 to-gray-900/95 backdrop-blur-sm border-t border-gray-700 p-4">
        {/* Speed Graph */}
        {speedData.length > 0 && (
          <div className="mb-4">
            <div className="h-16 bg-gray-800 rounded-lg p-2 relative overflow-hidden">
              <svg className="w-full h-full">
                {speedData.map((point, index) => {
                  const x = (index / (speedData.length - 1)) * 100
                  const maxSpeed = Math.max(...speedData.map(p => p.speed_kmh))
                  const y = 100 - (point.speed_kmh / maxSpeed) * 80
                  
                  return (
                    <circle
                      key={index}
                      cx={`${x}%`}
                      cy={`${y}%`}
                      r="1"
                      fill={index <= currentPointIndex ? getSpeedColor(point.speed_kmh) : '#374151'}
                    />
                  )
                })}
              </svg>
              
              {/* Progress indicator */}
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-white opacity-50"
                style={{ left: `${progress}%` }}
              />
            </div>
          </div>
        )}
        
        {/* Progress Bar */}
        <div className="mb-4">
          <input
            type="range"
            min="0"
            max={routePoints.length - 1}
            value={currentPointIndex}
            onChange={(e) => {
              setCurrentPointIndex(parseInt(e.target.value))
              setIsPlaying(false)
            }}
            className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer slider"
          />
        </div>
        
        {/* Controls */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {/* Play/Pause */}
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              disabled={routePoints.length === 0}
              className="flex items-center justify-center w-12 h-12 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-full text-white"
            >
              {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6 ml-1" />}
            </button>
            
            {/* Reset */}
            <button
              onClick={() => {
                setCurrentPointIndex(0)
                setIsPlaying(false)
              }}
              disabled={routePoints.length === 0}
              className="flex items-center justify-center w-10 h-10 bg-gray-600 hover:bg-gray-700 disabled:bg-gray-700 rounded-full text-white"
            >
              <RotateCcw className="w-5 h-5" />
            </button>
            
            {/* Speed Controls */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">Speed:</span>
              {[1, 2, 5, 10].map(speed => (
                <button
                  key={speed}
                  onClick={() => setPlaybackSpeed(speed)}
                  className={`px-3 py-1 rounded text-sm ${
                    playbackSpeed === speed
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {speed}x
                </button>
              ))}
            </div>
          </div>
          
          {/* Info Panel */}
          <div className="flex items-center gap-6 text-sm text-gray-300">
            <div className="flex items-center gap-2">
              <Gauge className="w-4 h-4 text-blue-400" />
              <span>{formatMph(currentSpeed)}</span>
            </div>
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-green-400" />
              <span>{elapsedMinutes}:{elapsedSeconds.toString().padStart(2, '0')}</span>
            </div>
            {selectedTrip && (
              <>
                <div className="flex items-center gap-2">
                  <MapPin className="w-4 h-4 text-purple-400" />
                  <span>{selectedTrip.distance_km.toFixed(1)} km</span>
                </div>
                <div className="text-gray-400">
                  Driver: {selectedTrip.driver_name}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
