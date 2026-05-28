import { useMemo, useState } from 'react'
import {
  CheckCircle2,
  CircleSlash,
  Eye,
  Lock,
  ShieldCheck,
  UserRoundCheck,
  type LucideIcon,
} from 'lucide-react'
import type { AuthSession } from '../types/fleet'

type AccessPreviewNavItem = {
  tab: string
  label: string
  shortLabel: string
  Icon: LucideIcon
}

type SeatDefinition = {
  id: string
  displayName: string
  tabs: string[]
}

type ConfiguredPreviewUser = {
  display_name?: unknown
  displayName?: unknown
  email?: unknown
  seat_ids?: unknown
  seatIds?: unknown
  tabs?: unknown
}

type PreviewProfile = {
  id: string
  label: string
  email?: string | null
  seatIds: string[]
  source: 'public' | 'current' | 'seat' | 'configured'
  tabs: string[]
}

interface Props {
  activePreviewId?: string | null
  activeTab: string
  navItems: AccessPreviewNavItem[]
  onApplyPreview: (profile: { id: string; label: string; tabs: string[] }) => void
  onClearPreview: () => void
  onSelectTab: (tab: string) => void
  session: AuthSession | null
  loading?: boolean
}

const DEFAULT_PUBLIC_TABS = ['dashboard', 'control-tower', 'maintenance', 'stability']

const SEAT_DEFINITIONS: SeatDefinition[] = [
  {
    id: 'executive_command',
    displayName: 'Executive Command Seat',
    tabs: [
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
    ],
  },
  {
    id: 'revenue_manager',
    displayName: 'Revenue Manager Seat',
    tabs: ['dashboard', 'control-tower', 'finance', 'operating-system', 'stability'],
  },
  {
    id: 'operations_manager',
    displayName: 'Operations Manager Seat',
    tabs: ['dashboard', 'control-tower', 'operating-system', 'replay', 'stability', 'reports'],
  },
  {
    id: 'finance_controller',
    displayName: 'Finance Controller Seat',
    tabs: ['dashboard', 'control-tower', 'finance', 'operating-system', 'fuel'],
  },
  {
    id: 'fleet_compliance_manager',
    displayName: 'Fleet & Compliance Manager Seat',
    tabs: [
      'dashboard',
      'control-tower',
      'maintenance',
      'coaching',
      'replay',
      'geofences',
      'fuel',
      'compliance',
      'data-connector',
    ],
  },
  {
    id: 'people_systems_manager',
    displayName: 'People & Systems Manager Seat',
    tabs: ['dashboard', 'operating-system', 'hr-recruiting', 'reports'],
  },
]

function unique(values: string[]) {
  return [...new Set(values.filter(Boolean))]
}

function parseCsv(value?: string) {
  return (value || '')
    .split(',')
    .map(item => item.trim().toLowerCase())
    .filter(Boolean)
}

function stringArray(value: unknown) {
  if (Array.isArray(value)) return value.map(item => String(item).trim()).filter(Boolean)
  if (typeof value === 'string') return value.split(',').map(item => item.trim()).filter(Boolean)
  return []
}

function configuredProfiles(rawJson: string | undefined, publicTabs: string[]) {
  if (!rawJson) return []

  try {
    const parsed = JSON.parse(rawJson) as unknown
    const rows = Array.isArray(parsed) ? parsed : []

    return rows.flatMap((row, index): PreviewProfile[] => {
      const candidate = row as ConfiguredPreviewUser
      const email = typeof candidate.email === 'string' ? candidate.email.trim() : ''
      const displayName =
        typeof candidate.display_name === 'string'
          ? candidate.display_name.trim()
          : typeof candidate.displayName === 'string'
            ? candidate.displayName.trim()
            : email
      const seatIds = stringArray(candidate.seat_ids || candidate.seatIds)
      const directTabs = stringArray(candidate.tabs)
      const seatTabs = seatIds.flatMap(seatId => SEAT_DEFINITIONS.find(seat => seat.id === seatId)?.tabs || [])
      const tabs = unique([...publicTabs, ...seatTabs, ...directTabs])

      if (!displayName || tabs.length === 0) return []

      return [
        {
          email: email || null,
          id: `configured-${email || index}`,
          label: displayName,
          seatIds,
          source: 'configured',
          tabs,
        },
      ]
    })
  } catch {
    return []
  }
}

function isAccessPreviewEnabled() {
  return import.meta.env.DEV || import.meta.env.VITE_ACCESS_PREVIEW_ENABLED === 'true'
}

function canCurrentUserPreview(session: AuthSession | null) {
  if (import.meta.env.DEV) return true

  const adminEmails = parseCsv(import.meta.env.VITE_ACCESS_PREVIEW_ADMIN_EMAILS)
  const currentEmail = session?.user?.email?.trim().toLowerCase()
  const seatIds = session?.seat_access.seats.map(seat => seat.id) || []

  return (
    seatIds.includes('executive_command') ||
    Boolean(currentEmail && adminEmails.includes(currentEmail))
  )
}

function seatLabel(seatId: string) {
  return SEAT_DEFINITIONS.find(seat => seat.id === seatId)?.displayName || seatId
}

export default function AccessPreviewCard({
  activePreviewId,
  activeTab,
  navItems,
  onApplyPreview,
  onClearPreview,
  onSelectTab,
  session,
  loading,
}: Props) {
  const publicTabs = session?.seat_access.public_tabs?.length
    ? session.seat_access.public_tabs
    : DEFAULT_PUBLIC_TABS
  const allowedTabs = session?.seat_access.allowed_tabs?.length ? session.seat_access.allowed_tabs : publicTabs
  const currentSeats = session?.seat_access.seats.map(seat => seat.id) || []

  const profiles = useMemo(() => {
    const publicProfile: PreviewProfile = {
      id: 'public',
      label: 'Public view',
      seatIds: [],
      source: 'public',
      tabs: publicTabs,
    }
    const currentProfile: PreviewProfile = {
      email: session?.user?.email || null,
      id: 'current',
      label: session?.user?.display_name || 'Current signed-in user',
      seatIds: currentSeats,
      source: 'current',
      tabs: allowedTabs,
    }
    const seatProfiles: PreviewProfile[] = SEAT_DEFINITIONS.map(seat => ({
      id: `seat-${seat.id}`,
      label: seat.displayName,
      seatIds: [seat.id],
      source: 'seat',
      tabs: unique([...publicTabs, ...seat.tabs]),
    }))
    const userProfiles = configuredProfiles(import.meta.env.VITE_ACCESS_PREVIEW_USERS_JSON, publicTabs)

    return [publicProfile, currentProfile, ...userProfiles, ...seatProfiles]
  }, [allowedTabs, currentSeats, publicTabs, session?.user?.display_name, session?.user?.email])

  const [selectedProfileId, setSelectedProfileId] = useState('current')

  if (!isAccessPreviewEnabled() || !canCurrentUserPreview(session)) return null

  const selectedProfile = profiles.find(profile => profile.id === selectedProfileId) || profiles[0]
  const previewActive = activePreviewId === selectedProfile.id
  const visibleTabs = new Set(selectedProfile.tabs)
  const visibleNavItems = navItems.filter(item => visibleTabs.has(item.tab))
  const blockedNavItems = navItems.filter(item => !visibleTabs.has(item.tab))
  const sourceAuthority = session?.seat_access.source_authority || 'Microsoft Entra security groups'
  const authorizationMode = session?.seat_access.authorization_mode || 'optional'
  const configReady = session?.seat_access.config_ready

  return (
    <section className="rounded-lg border border-sky-400/20 bg-gray-950/70 p-4 shadow-sm light:border-sky-200 light:bg-white sm:p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-sky-400/25 bg-sky-500/10 text-sky-200 light:text-sky-700">
            <Eye className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold text-white light:text-gray-950">Access Preview</h2>
              <span className="inline-flex items-center gap-1 rounded-md border border-emerald-400/25 bg-emerald-500/10 px-2 py-1 text-[11px] font-semibold text-emerald-200 light:text-emerald-700">
                <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                Read-only
              </span>
              <span className="inline-flex items-center gap-1 rounded-md border border-gray-700 bg-gray-900 px-2 py-1 text-[11px] font-semibold text-gray-300 light:border-gray-200 light:bg-gray-50 light:text-gray-700">
                <Lock className="h-3.5 w-3.5" aria-hidden="true" />
                {authorizationMode === 'enforced' ? 'Enforced' : 'Optional'}
              </span>
              {previewActive && (
                <span className="inline-flex items-center gap-1 rounded-md border border-sky-400/25 bg-sky-500/10 px-2 py-1 text-[11px] font-semibold text-sky-200 light:text-sky-700">
                  <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                  Active
                </span>
              )}
            </div>
            <p className="mt-1 text-sm text-gray-400 light:text-gray-600">
              {sourceAuthority}
            </p>
          </div>
        </div>

        <div className="flex w-full flex-col gap-2 lg:max-w-sm">
          <label className="flex flex-col gap-2 text-sm text-gray-300 light:text-gray-700">
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Preview user</span>
            <select
              value={selectedProfile.id}
              onChange={event => setSelectedProfileId(event.target.value)}
              className="h-11 rounded-lg border border-gray-700 bg-gray-900 px-3 text-sm font-medium text-white outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-400/25 light:border-gray-200 light:bg-white light:text-gray-950"
            >
              {profiles.map(profile => (
                <option key={profile.id} value={profile.id}>
                  {profile.label}
                </option>
              ))}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => onApplyPreview({
                id: selectedProfile.id,
                label: selectedProfile.label,
                tabs: selectedProfile.tabs,
              })}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-sky-400/30 bg-sky-500/15 px-3 text-sm font-semibold text-sky-100 transition hover:bg-sky-500/25 light:text-sky-800"
            >
              <Eye className="h-4 w-4" aria-hidden="true" />
              Preview
            </button>
            <button
              type="button"
              onClick={onClearPreview}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-gray-700 bg-gray-900 px-3 text-sm font-semibold text-gray-200 transition hover:bg-gray-800 light:border-gray-200 light:bg-white light:text-gray-800 light:hover:bg-gray-50"
            >
              <CircleSlash className="h-4 w-4" aria-hidden="true" />
              Clear
            </button>
          </div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-4">
        <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3 light:border-gray-200 light:bg-gray-50">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-gray-500">Visible</p>
          <p className="mt-2 text-2xl font-semibold text-white light:text-gray-950">{visibleNavItems.length}</p>
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3 light:border-gray-200 light:bg-gray-50">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-gray-500">Blocked</p>
          <p className="mt-2 text-2xl font-semibold text-white light:text-gray-950">{blockedNavItems.length}</p>
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3 light:border-gray-200 light:bg-gray-50">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-gray-500">Seat</p>
          <p className="mt-2 truncate text-sm font-semibold text-white light:text-gray-950">
            {selectedProfile.seatIds.length ? selectedProfile.seatIds.map(seatLabel).join(', ') : 'No assigned seat'}
          </p>
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3 light:border-gray-200 light:bg-gray-50">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-gray-500">Config</p>
          <p className="mt-2 text-sm font-semibold text-white light:text-gray-950">
            {loading ? 'Checking' : configReady ? 'Mapped' : 'Default'}
          </p>
        </div>
      </div>

      {selectedProfile.email && (
        <div className="mt-3 flex items-center gap-2 text-sm text-gray-400 light:text-gray-600">
          <UserRoundCheck className="h-4 w-4 text-sky-300 light:text-sky-700" aria-hidden="true" />
          <span className="truncate">{selectedProfile.email}</span>
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {navItems.map(({ tab, label, Icon }) => {
          const allowed = visibleTabs.has(tab)
          const current = activeTab === tab
          return (
            <button
              key={tab}
              type="button"
              disabled={!allowed}
              onClick={() => allowed && onSelectTab(tab)}
              className={`flex min-h-[58px] items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left transition ${
                allowed
                  ? current
                    ? 'border-sky-400/40 bg-sky-500/15 text-white light:bg-sky-50 light:text-sky-950'
                    : 'border-gray-800 bg-gray-900/50 text-gray-200 hover:border-sky-400/30 hover:bg-gray-900 light:border-gray-200 light:bg-white light:text-gray-800 light:hover:bg-sky-50'
                  : 'border-gray-900 bg-gray-950/50 text-gray-600 light:border-gray-200 light:bg-gray-50 light:text-gray-400'
              } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950 disabled:cursor-not-allowed`}
            >
              <span className="flex min-w-0 items-center gap-2">
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="truncate text-sm font-medium">{label}</span>
              </span>
              {allowed ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-300 light:text-emerald-700" aria-hidden="true" />
              ) : (
                <CircleSlash className="h-4 w-4 shrink-0 text-gray-600 light:text-gray-400" aria-hidden="true" />
              )}
            </button>
          )
        })}
      </div>
    </section>
  )
}
