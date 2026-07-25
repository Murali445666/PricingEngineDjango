import { useQuery } from '@tanstack/react-query'
import { fetchContractConflicts } from '@/services/contractService'
import { LoadingSpinner } from '@/shared/ui'

interface ConflictWarningsPanelProps {
  contractId: number
}

export function ConflictWarningsPanel({ contractId }: ConflictWarningsPanelProps) {
  const { data: conflicts, isLoading } = useQuery({
    queryKey: ['contract-conflicts', contractId],
    queryFn: () => fetchContractConflicts(contractId),
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-4">
        <LoadingSpinner />
      </div>
    )
  }

  const open = conflicts ?? []
  if (open.length === 0) {
    return null
  }

  const errors = open.filter((c) => c.severity === 'ERROR')
  const warnings = open.filter((c) => c.severity === 'WARNING')

  return (
    <div className="mb-4 space-y-2 rounded border border-amber-200 bg-amber-50 p-4">
      <h3 className="text-sm font-semibold text-amber-900">Open validation conflicts</h3>
      {errors.length > 0 && (
        <ul className="space-y-1 text-sm text-red-800">
          {errors.map((c) => (
            <li key={c.id}>
              <span className="font-medium">{c.conflict_type}</span>: {c.message}
            </li>
          ))}
        </ul>
      )}
      {warnings.length > 0 && (
        <ul className="space-y-1 text-sm text-amber-800">
          {warnings.map((c) => (
            <li key={c.id}>
              <span className="font-medium">{c.conflict_type}</span>: {c.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
