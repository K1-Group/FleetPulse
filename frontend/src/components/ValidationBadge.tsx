import { AlertTriangle, CheckCircle2, Clock3, XCircle } from 'lucide-react'
import type { DashboardValidationItem, DashboardValidationStatus } from '../types/fleet'

interface Props {
  className?: string
  compact?: boolean
  item?: DashboardValidationItem | null
  label?: string
  status?: DashboardValidationStatus
}

const styles: Record<DashboardValidationStatus, string> = {
  failed: 'border-red-500/35 bg-red-500/10 text-red-200 light:text-red-700',
  pending: 'border-amber-500/35 bg-amber-500/10 text-amber-200 light:text-amber-700',
  pending_no_audit: 'border-orange-500/35 bg-orange-500/10 text-orange-200 light:text-orange-700',
  pending_no_data: 'border-amber-500/35 bg-amber-500/10 text-amber-200 light:text-amber-700',
  stale: 'border-sky-500/35 bg-sky-500/10 text-sky-200 light:text-sky-700',
  verified: 'border-emerald-500/35 bg-emerald-500/10 text-emerald-200 light:text-emerald-700',
}

const labels: Record<DashboardValidationStatus, string> = {
  failed: 'Failed',
  pending: 'Pending',
  pending_no_audit: 'No Audit',
  pending_no_data: 'No Data',
  stale: 'Stale',
  verified: 'Verified',
}

const icons = {
  failed: XCircle,
  pending: Clock3,
  pending_no_audit: AlertTriangle,
  pending_no_data: Clock3,
  stale: AlertTriangle,
  verified: CheckCircle2,
}

export default function ValidationBadge({ className = '', compact = false, item, label, status }: Props) {
  const resolvedStatus = item?.status || status || 'pending'
  const Icon = icons[resolvedStatus]
  const text = label || labels[resolvedStatus]
  const title = item
    ? `${item.label}: ${item.message} Source: ${item.source_authority}`
    : text

  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold leading-none ${styles[resolvedStatus]} ${className}`}
      title={title}
      aria-label={title}
    >
      <Icon className={compact ? 'h-3 w-3' : 'h-3.5 w-3.5'} />
      <span>{text}</span>
    </span>
  )
}
