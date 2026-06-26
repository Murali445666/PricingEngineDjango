type StatusVariant = 'Draft' | 'Active' | 'Retired' | 'Error' | 'Success'

const variantClasses: Record<StatusVariant, string> = {
  Draft: 'bg-slate-100 text-slate-700 border-slate-300',
  Active: 'bg-green-50 text-green-800 border-green-200',
  Retired: 'bg-red-50 text-red-700 border-red-200',
  Error: 'bg-red-50 text-red-700 border-red-200',
  Success: 'bg-green-50 text-green-700 border-green-200',
}

function normalizeStatus(value: string): StatusVariant {
  const v = value?.toLowerCase() ?? ''
  if (v === 'draft') return 'Draft'
  if (v === 'active') return 'Active'
  if (v === 'retired') return 'Retired'
  if (
    v === 'error' ||
    v === 'denied' ||
    v === 'failed' ||
    v.includes('denied') ||
    v.includes('missing') ||
    v.includes('calculation_error')
  ) {
    return 'Error'
  }
  if (v === 'success' || v === 'payable') return 'Success'
  if (v.includes('applied') || v.includes('cap') || v.includes('floor') || v.includes('blending')) {
    return 'Active'
  }
  return 'Draft'
}

interface StatusBadgeProps {
  status: string
  className?: string
}

export function StatusBadge({ status, className = '' }: StatusBadgeProps) {
  const variant = normalizeStatus(status)
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${variantClasses[variant]} ${className}`}
    >
      {status}
    </span>
  )
}
