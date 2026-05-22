import { AlertTriangle, Loader2, LogIn, LogOut, ShieldCheck, UserCircle } from 'lucide-react'
import type { AuthSession } from '../types/fleet'

interface Props {
  session: AuthSession | null
  loading: boolean
  error?: string | null
}

function userLabel(session: AuthSession) {
  return session.user?.display_name || session.user?.email || 'Signed in'
}

function modeLabel(session: AuthSession | null) {
  if (!session) return 'Auth pending'
  if (session.auth_required && !session.authenticated) return 'Sign in required'
  if (session.authenticated) return 'Signed in'
  if (session.login_enabled) return 'Public view'
  return 'SSO off'
}

export default function UserLoginStatus({ session, loading, error }: Props) {
  if (loading) {
    return (
      <div className="inline-flex h-10 items-center gap-2 rounded-lg border border-gray-800 bg-gray-900/60 px-3 text-sm text-gray-400 light:border-gray-200 light:bg-white light:text-gray-600">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        <span className="hidden md:inline">Auth check</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="inline-flex h-10 items-center gap-2 rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 text-sm text-amber-200 light:text-amber-700">
        <AlertTriangle className="h-4 w-4" aria-hidden="true" />
        <span className="hidden md:inline">Auth unavailable</span>
      </div>
    )
  }

  const authenticated = Boolean(session?.authenticated)
  const loginUrl = session?.login_url
  const logoutUrl = session?.logout_url

  return (
    <div className="inline-flex h-10 max-w-full items-center gap-2 rounded-lg border border-gray-800 bg-gray-900/60 px-2.5 text-sm text-gray-300 light:border-gray-200 light:bg-white light:text-gray-700">
      <div className="flex min-w-0 items-center gap-2">
        {authenticated ? (
          <UserCircle className="h-4 w-4 shrink-0 text-emerald-300 light:text-emerald-600" aria-hidden="true" />
        ) : (
          <ShieldCheck className="h-4 w-4 shrink-0 text-sky-300 light:text-sky-600" aria-hidden="true" />
        )}
        <div className="min-w-0 leading-tight">
          <div className="truncate text-xs font-semibold text-white light:text-gray-950">
            {authenticated && session ? userLabel(session) : modeLabel(session)}
          </div>
          <div className="hidden truncate text-[10px] text-gray-500 light:text-gray-500 sm:block">
            {session?.source_authority || 'Microsoft Entra'}
          </div>
        </div>
      </div>

      {!authenticated && loginUrl && (
        <a
          className="inline-flex shrink-0 items-center gap-1 rounded-md bg-sky-500 px-2.5 py-1.5 text-xs font-semibold text-white transition hover:bg-sky-400"
          href={loginUrl}
        >
          <LogIn className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">Sign in</span>
        </a>
      )}

      {authenticated && logoutUrl && (
        <a
          aria-label="Sign out"
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-gray-700 text-gray-300 transition hover:border-gray-500 hover:text-white light:border-gray-200 light:text-gray-600 light:hover:text-gray-900"
          href={logoutUrl}
          title="Sign out"
        >
          <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
      )}
    </div>
  )
}
