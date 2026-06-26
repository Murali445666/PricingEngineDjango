/**
 * Step 12a – Conflicts panel (governance)
 *
 * Lists open ValidationResult rows from GET /api/contracts/<id>/conflicts/.
 * Each row is colour-coded by severity (ERROR=red, WARNING=amber).
 * Analysts can acknowledge a conflict by checking the resolve checkbox,
 * which calls PATCH /api/contracts/<id>/conflicts/<result_id>/resolve/.
 *
 * Feature flag: VITE_CONFLICT_WARNINGS_PANEL (defaults to enabled when unset)
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LoadingSpinner } from '@/shared/ui'
import { fetchContractConflicts, resolveContractConflict } from '@/services/contractService'
import type { ValidationResult } from '@/types'

interface Props {
  contractId: number
}

const FEATURE_ENABLED =
  import.meta.env.VITE_CONFLICT_WARNINGS_PANEL !== 'false'

// ── Row colour classes by severity ───────────────────────────────────────────

function rowClasses(severity: ValidationResult['severity'], resolved: boolean): string {
  if (resolved) return 'bg-slate-50 opacity-60'
  if (severity === 'ERROR') return 'bg-red-50 border-l-4 border-red-400'
  return 'bg-amber-50 border-l-4 border-amber-400'
}

function severityBadge(severity: ValidationResult['severity']) {
  if (severity === 'ERROR') {
    return (
      <span className="inline-flex items-center rounded border border-red-300 bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-800">
        ERROR
      </span>
    )
  }
  return (
    <span className="inline-flex items-center rounded border border-amber-300 bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
      WARNING
    </span>
  )
}

// ── Single conflict row ───────────────────────────────────────────────────────

function ConflictRow({
  result,
  contractId,
}: {
  result: ValidationResult
  contractId: number
}) {
  const queryClient = useQueryClient()

  const { mutate: toggleResolved, isPending } = useMutation({
    mutationFn: (resolved: boolean) =>
      resolveContractConflict(contractId, result.id, resolved),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contract-conflicts', contractId] })
      queryClient.invalidateQueries({ queryKey: ['contracts'] })
    },
  })

  return (
    <tr className={rowClasses(result.severity, result.resolved)}>
      {/* Resolve checkbox */}
      <td className="w-10 py-3 pl-4 pr-2 text-center">
        <input
          type="checkbox"
          checked={result.resolved}
          disabled={isPending}
          title={result.resolved ? 'Mark as unresolved' : 'Mark as resolved'}
          onChange={(e) => toggleResolved(e.target.checked)}
          className="h-4 w-4 cursor-pointer accent-slate-600"
        />
      </td>

      {/* Severity badge */}
      <td className="whitespace-nowrap py-3 pr-4 text-sm">{severityBadge(result.severity)}</td>

      {/* Conflict type */}
      <td className="py-3 pr-4 text-xs font-mono text-slate-600">
        {result.conflict_type}
      </td>

      {/* Message */}
      <td className="py-3 pr-4 text-sm text-slate-800">{result.message}</td>

      {/* Suggested action */}
      <td className="py-3 pr-4 text-xs text-slate-500 italic">
        {result.suggested_action || '—'}
      </td>

      {/* Timestamp */}
      <td className="whitespace-nowrap py-3 pr-4 text-xs text-slate-400">
        {new Date(result.validated_at).toLocaleString()}
      </td>
    </tr>
  )
}

// ── Panel header summary counts ───────────────────────────────────────────────

function PanelHeader({
  results,
  showAll,
  onToggleAll,
}: {
  results: ValidationResult[]
  showAll: boolean
  onToggleAll: () => void
}) {
  const errors = results.filter((r) => r.severity === 'ERROR' && !r.resolved).length
  const warnings = results.filter((r) => r.severity === 'WARNING' && !r.resolved).length

  return (
    <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
      <div className="flex items-center gap-3">
        <h3 className="text-sm font-semibold text-slate-800">Conflicts</h3>
        {errors > 0 && (
          <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700">
            {errors} error{errors !== 1 ? 's' : ''}
          </span>
        )}
        {warnings > 0 && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">
            {warnings} warning{warnings !== 1 ? 's' : ''}
          </span>
        )}
        {errors === 0 && warnings === 0 && (
          <span className="text-xs text-slate-400">No open conflicts</span>
        )}
      </div>
      <button
        onClick={onToggleAll}
        className="text-xs text-primary-600 hover:underline"
        type="button"
      >
        {showAll ? 'Hide resolved' : 'Show resolved'}
      </button>
    </div>
  )
}

// ── Main exported panel ───────────────────────────────────────────────────────

export function ConflictWarningsPanel({ contractId }: Props) {
  if (!FEATURE_ENABLED) return null

  return <ConflictWarningsPanelInner contractId={contractId} />
}

function ConflictWarningsPanelInner({ contractId }: Props) {
  const queryClient = useQueryClient()

  const [showAll, setShowAll] = useState(false)

  const { data: results = [], isLoading, error } = useQuery({
    queryKey: ['contract-conflicts', contractId, showAll],
    queryFn: () => fetchContractConflicts(contractId, showAll),
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-6">
        <LoadingSpinner />
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        Failed to load conflicts.
      </div>
    )
  }

  return (
    <div className="mt-6 overflow-hidden rounded border border-slate-200 bg-white shadow-sm">
      <PanelHeader
        results={results}
        showAll={showAll}
        onToggleAll={() => {
          setShowAll((v) => !v)
          queryClient.invalidateQueries({ queryKey: ['contract-conflicts', contractId] })
        }}
      />

      {results.length === 0 ? (
        <p className="px-4 py-4 text-sm text-slate-400">
          {showAll ? 'No conflict records found.' : 'No open conflicts for this contract.'}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="w-10 py-2 pl-4 pr-2" title="Resolve">✓</th>
                <th className="py-2 pr-4">Severity</th>
                <th className="py-2 pr-4">Type</th>
                <th className="py-2 pr-4">Message</th>
                <th className="py-2 pr-4">Suggested Action</th>
                <th className="py-2 pr-4">Detected At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {results.map((r) => (
                <ConflictRow key={r.id} result={r} contractId={contractId} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
