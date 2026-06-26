type NetworkVariant = 'InNetwork' | 'OutOfNetwork' | 'Tier' | 'Unknown' | 'Other'

const variantClasses: Record<NetworkVariant, string> = {
  InNetwork: 'bg-green-50 text-green-800 border-green-200',
  OutOfNetwork: 'bg-red-50 text-red-800 border-red-200',
  Tier: 'bg-blue-50 text-blue-800 border-blue-200',
  Unknown: 'bg-slate-100 text-slate-600 border-slate-300',
  Other: 'bg-amber-50 text-amber-800 border-amber-200',
}

function normalizeNetworkStatus(
  status: string | null | undefined,
  tier?: string | null,
): { variant: NetworkVariant; label: string } {
  const s = (status ?? 'UNKNOWN').toUpperCase()
  if (s === 'IN_NETWORK') {
    if (tier === 'TIER_1' || tier === 'TIER_2') {
      return { variant: 'Tier', label: `IN NETWORK (${tier.replace('_', ' ')})` }
    }
    return { variant: 'InNetwork', label: 'IN NETWORK' }
  }
  if (s === 'OUT_OF_NETWORK') {
    return { variant: 'OutOfNetwork', label: 'OUT OF NETWORK' }
  }
  if (s === 'TIER_1' || s === 'TIER_2') {
    return { variant: 'Tier', label: s.replace('_', ' ') }
  }
  if (s === 'UNKNOWN' || !status) {
    return { variant: 'Unknown', label: 'UNKNOWN' }
  }
  return { variant: 'Other', label: status }
}

interface NetworkStatusBadgeProps {
  status: string | null | undefined
  tier?: string | null
  className?: string
}

export function NetworkStatusBadge({ status, tier, className = '' }: NetworkStatusBadgeProps) {
  const { variant, label } = normalizeNetworkStatus(status, tier)
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${variantClasses[variant]} ${className}`}
    >
      {label}
    </span>
  )
}
