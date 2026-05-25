import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { MapPin, Plus, ArrowDownToLine, ArrowUpFromLine, Clock, Shield } from 'lucide-react'

interface Zone {
  id: string
  name: string
  points: { lat: number; lng: number }[]
  color: string
  displayed: boolean
  zone_type: string
  comment: string
}

interface ZoneEvent {
  id: string
  vehicle: string
  event_type: 'enter' | 'exit'
  zone_name: string
  timestamp: string
}

export default function GeofenceManager() {
  const [zones, setZones] = useState<Zone[]>([])
  const [activity, setActivity] = useState<ZoneEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [newZone, setNewZone] = useState({ name: '', latitude: '', longitude: '', radius: '200' })

  useEffect(() => {
    Promise.all([
      fetch('/api/geofences/zones').then(r => r.json()),
      fetch('/api/geofences/activity').then(r => r.json()),
    ]).then(([z, a]) => {
      setZones(z)
      setActivity(a)
    }).finally(() => setLoading(false))
  }, [])

  const createZone = async () => {
    setCreateError(null)
    const latitude = Number(newZone.latitude)
    const longitude = Number(newZone.longitude)
    const radius = Number(newZone.radius)
    if (!newZone.name.trim() || !Number.isFinite(latitude) || !Number.isFinite(longitude) || !Number.isFinite(radius)) {
      setCreateError('Enter a zone name, latitude, longitude, and radius from the real Geotab boundary.')
      return
    }
    const res = await fetch('/api/geofences/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: newZone.name,
        latitude,
        longitude,
        radius_meters: radius,
      }),
    })
    const data = await res.json()
    if (!res.ok) {
      setCreateError(data.detail || 'Geotab rejected the geofence create request.')
      return
    }
    if (data.status === 'created') {
      setShowCreate(false)
      // Refresh zones
      const z = await fetch('/api/geofences/zones').then(r => r.json())
      setZones(z)
    }
  }

  const formatTime = (ts: string) => {
    try {
      const d = new Date(ts)
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch { return ts }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
      >
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Shield className="w-6 h-6 text-purple-400" />
            <div>
              <h2 className="text-xl font-bold">Geofence Manager</h2>
              <p className="text-sm text-gray-400">Monitor vehicle zone entries/exits and manage boundaries</p>
            </div>
          </div>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-2 px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-all"
          >
            <Plus className="w-4 h-4" />
            New Geofence
          </button>
        </div>

        {/* Create Form */}
        {showCreate && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            className="bg-gray-800/50 rounded-lg p-4 mb-6 grid grid-cols-1 md:grid-cols-5 gap-4"
          >
            <input
              type="text"
              placeholder="Zone Name"
              value={newZone.name}
              onChange={e => setNewZone({ ...newZone, name: e.target.value })}
              className="bg-gray-700/50 border border-gray-600 rounded-lg px-3 py-2 text-white placeholder-gray-400"
            />
            <input
              type="number"
              placeholder="Latitude"
              value={newZone.latitude}
              onChange={e => setNewZone({ ...newZone, latitude: e.target.value })}
              className="bg-gray-700/50 border border-gray-600 rounded-lg px-3 py-2 text-white"
              step="0.001"
            />
            <input
              type="number"
              placeholder="Longitude"
              value={newZone.longitude}
              onChange={e => setNewZone({ ...newZone, longitude: e.target.value })}
              className="bg-gray-700/50 border border-gray-600 rounded-lg px-3 py-2 text-white"
              step="0.001"
            />
            <input
              type="number"
              placeholder="Radius meters"
              value={newZone.radius}
              onChange={e => setNewZone({ ...newZone, radius: e.target.value })}
              className="bg-gray-700/50 border border-gray-600 rounded-lg px-3 py-2 text-white"
              min="1"
            />
            <button
              onClick={createZone}
              disabled={!newZone.name.trim() || !newZone.latitude || !newZone.longitude || !newZone.radius}
              className="bg-emerald-500 text-white rounded-lg px-4 py-2 hover:bg-emerald-600 disabled:opacity-50 transition-all"
            >
              Create Zone
            </button>
            {createError && (
              <p className="md:col-span-5 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                {createError}
              </p>
            )}
          </motion.div>
        )}

        {/* Zone Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
          {zones.length ? zones.map((zone, i) => (
            <motion.div
              key={zone.id}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.1 }}
              className="bg-gray-800/30 border border-gray-700/50 rounded-lg p-4"
            >
              <div className="flex items-center gap-3 mb-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: zone.color }} />
                <h3 className="font-semibold">{zone.name}</h3>
              </div>
              <p className="text-xs text-gray-500 mb-2">{zone.comment || zone.zone_type}</p>
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <MapPin className="w-3 h-3" />
                {zone.points.length > 0 && (
                  <span>{zone.points[0].lat.toFixed(3)}, {zone.points[0].lng.toFixed(3)}</span>
                )}
              </div>
            </motion.div>
          )) : (
            <div className="md:col-span-2 lg:col-span-3 rounded-lg border border-dashed border-gray-800 px-4 py-8 text-center text-sm text-gray-500">
              No source-backed Geotab zones returned.
            </div>
          )}
        </div>

        {/* Live Activity Feed */}
        <div>
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Clock className="w-5 h-5 text-blue-400" />
            Recent Zone Activity
          </h3>
          <div className="space-y-2">
            {activity.map((evt, i) => (
              <motion.div
                key={evt.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className="flex items-center gap-3 bg-gray-800/20 rounded-lg px-4 py-3"
              >
                {evt.event_type === 'enter' ? (
                  <ArrowDownToLine className="w-4 h-4 text-emerald-400" />
                ) : (
                  <ArrowUpFromLine className="w-4 h-4 text-amber-400" />
                )}
                <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                  evt.event_type === 'enter' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'
                }`}>
                  {evt.event_type.toUpperCase()}
                </span>
                <span className="font-medium">{evt.vehicle}</span>
                <span className="text-gray-500">→</span>
                <span className="text-gray-300">{evt.zone_name}</span>
                <span className="ml-auto text-xs text-gray-500">{formatTime(evt.timestamp)}</span>
              </motion.div>
            ))}
            {activity.length === 0 && (
              <p className="text-center text-gray-500 py-8">No recent zone activity</p>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  )
}
