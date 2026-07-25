import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FormPanel, Button, StatusBadge } from '@/shared/ui'
import {
  fetchContractAmendments,
  revertContractVersionToDraft,
  discardContractDraftVersion,
} from '@/services/contractService'
import type { ContractAmendment, ExplorerVersion } from '@/types'

interface VersionHistoryPanelProps {
  contractId: number
  versions: ExplorerVersion[]
  contractStatus: string
}

function WhatChangedSummary({ whatChanged }: { whatChanged: ContractAmendment['what_changed'] }) {
  if (!whatChanged) return <span className="text-slate-500">No diff computed yet</span>
  return (
    <ul className="mt-1 space-y-0.5 text-xs text-slate-700">
      <li>
        Rules: +{whatChanged.rules.added} / ~{whatChanged.rules.changed} / −{whatChanged.rules.removed}
      </li>
      <li>
        Entities: +{whatChanged.entities.added} / −{whatChanged.entities.removed}
      </li>
      <li>
        Scope: +{whatChanged.scope.added} / ~{whatChanged.scope.changed} / −{whatChanged.scope.removed}
      </li>
    </ul>
  )
}

export function VersionHistoryPanel({ contractId, versions, contractStatus }: VersionHistoryPanelProps) {
  const queryClient = useQueryClient()

  const { data: amendments = [] } = useQuery({
    queryKey: ['contract-amendments', String(contractId)],
    queryFn: () => fetchContractAmendments(contractId),
  })

  const revertMutation = useMutation({
    mutationFn: (versionId: number) => revertContractVersionToDraft(versionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['contract', String(contractId)] })
      void queryClient.invalidateQueries({ queryKey: ['contract-explorer', String(contractId)] })
      void queryClient.invalidateQueries({ queryKey: ['contract-amendments', String(contractId)] })
    },
    onError: (err: Error) => {
      window.alert(`Revert to draft failed: ${err.message}`)
    },
  })

  const discardMutation = useMutation({
    mutationFn: (versionId: number) => discardContractDraftVersion(versionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['contract', String(contractId)] })
      void queryClient.invalidateQueries({ queryKey: ['contract-explorer', String(contractId)] })
      void queryClient.invalidateQueries({ queryKey: ['contract-amendments', String(contractId)] })
      void queryClient.invalidateQueries({ queryKey: ['version-diff', contractId] })
      void queryClient.invalidateQueries({ queryKey: ['contract-rules', String(contractId)] })
    },
    onError: (err: Error) => {
      window.alert(`Discard draft failed: ${err.message}`)
    },
  })

  const amendmentByVersion = new Map(
    amendments.filter((a) => a.version_id != null).map((a) => [a.version_id!, a]),
  )
  const hasDraft = versions.some((v) => v.status === 'DRAFT')
  const sorted = [...versions].sort((a, b) => b.version_number - a.version_number)

  return (
    <FormPanel title="Version history" className="mb-4">
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-600">
              <th className="py-2 pr-4">Version</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2 pr-4">Effective</th>
              <th className="py-2 pr-4">Amendment</th>
              <th className="py-2 pr-4">Changes</th>
              <th className="py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((v) => {
              const amendment = amendmentByVersion.get(v.version_id)
              return (
                <tr key={v.version_id} className="border-b border-slate-100">
                  <td className="py-2 pr-4">
                    v{v.version_number}{' '}
                    <span className="text-slate-500">#{v.version_id}</span>
                  </td>
                  <td className="py-2 pr-4">
                    <StatusBadge status={v.status} />
                  </td>
                  <td className="py-2 pr-4">{v.effective_start_date}</td>
                  <td className="py-2 pr-4">
                    {amendment ? (
                      <span title={amendment.description}>{amendment.amendment_number}</span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="py-2 pr-4">
                    {amendment ? <WhatChangedSummary whatChanged={amendment.what_changed} /> : '—'}
                  </td>
                  <td className="py-2">
                    {v.status === 'DRAFT' && (
                      <Button
                        type="button"
                        variant="secondary"
                        className="text-xs text-red-700 border-red-200 hover:bg-red-50"
                        disabled={discardMutation.isPending}
                        onClick={() => {
                          const amendLabel = amendment
                            ? ` and amendment ${amendment.amendment_number}`
                            : ''
                          if (
                            !window.confirm(
                              `Discard draft v${v.version_number}${amendLabel}? This can't be undone.`,
                            )
                          )
                            return
                          discardMutation.mutate(v.version_id)
                        }}
                      >
                        Discard
                      </Button>
                    )}
                    {v.status === 'ACTIVE' && contractStatus === 'ACTIVE' && !hasDraft && (
                      <Button
                        type="button"
                        variant="secondary"
                        className="text-xs"
                        disabled={revertMutation.isPending}
                        onClick={() => {
                          if (
                            !window.confirm(
                              `Revert v${v.version_number} to DRAFT? It will stop pricing until republished.`,
                            )
                          )
                            return
                          revertMutation.mutate(v.version_id)
                        }}
                      >
                        Return to draft
                      </Button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </FormPanel>
  )
}
