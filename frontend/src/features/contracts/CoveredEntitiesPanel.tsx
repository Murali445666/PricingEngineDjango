import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, FormPanel, Input, LoadingSpinner, Select } from '@/shared/ui'
import {
  addCoveredEntity,
  deleteCoveredEntity,
  fetchCoveredEntities,
} from '@/services/contractService'
import type { CoveredEntityCreatePayload } from '@/types'

const ENTITY_TYPE_OPTIONS = [
  { value: 'ORG', label: 'Organization' },
  { value: 'FACILITY', label: 'Facility' },
  { value: 'PROVIDER', label: 'Provider' },
]

interface CoveredEntitiesPanelProps {
  contractId: number
  isDraft: boolean
}

export function CoveredEntitiesPanel({ contractId, isDraft }: CoveredEntitiesPanelProps) {
  const queryClient = useQueryClient()
  const [entityType, setEntityType] = useState<'ORG' | 'FACILITY' | 'PROVIDER'>('ORG')
  const [entityRef, setEntityRef] = useState('KEYSTONE-CARD')
  const [isPrimary, setIsPrimary] = useState(false)
  const [startDate, setStartDate] = useState('2025-04-17')
  const [endDate, setEndDate] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { data: entities, isLoading } = useQuery({
    queryKey: ['covered-entities', contractId],
    queryFn: () => fetchCoveredEntities(contractId),
  })

  const addMutation = useMutation({
    mutationFn: (payload: CoveredEntityCreatePayload) => addCoveredEntity(contractId, payload),
    onSuccess: () => {
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['covered-entities', contractId] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (entityId: number) => deleteCoveredEntity(contractId, entityId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['covered-entities', contractId] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const refLabel =
    entityType === 'ORG'
      ? 'Organization ID'
      : entityType === 'PROVIDER'
        ? 'Provider ID (numeric)'
        : 'Facility ID (numeric)'

  const handleAdd = () => {
    if (!entityRef.trim()) {
      setError('Entity reference is required.')
      return
    }
    const payload: CoveredEntityCreatePayload = {
      entity_type: entityType,
      is_primary: isPrimary,
      effective_start_date: startDate.trim() || null,
      effective_end_date: endDate.trim() || null,
    }
    if (entityType === 'ORG') {
      payload.organization = entityRef.trim()
    } else if (entityType === 'PROVIDER') {
      const id = parseInt(entityRef, 10)
      if (Number.isNaN(id)) {
        setError('Provider ID must be a number.')
        return
      }
      payload.provider = id
    } else {
      const id = parseInt(entityRef, 10)
      if (Number.isNaN(id)) {
        setError('Facility ID must be a number.')
        return
      }
      payload.facility = id
    }
    addMutation.mutate(payload)
  }

  const handleRemove = (entityId: number) => {
    if (!window.confirm('Remove this covered entity from the roster?')) return
    deleteMutation.mutate(entityId)
  }

  return (
    <FormPanel title="Covered entities (Exhibit A)" className="mb-6">
      <p className="mb-3 text-sm text-slate-600">
        The resolver matches claims through this roster. A published contract with zero covered entities
        cannot price. Add orgs, facilities, or providers the agreement covers.
      </p>

      {!isDraft && (
        <p className="mb-3 rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
          Roster is read-only — contract is not DRAFT.
        </p>
      )}

      {isLoading && (
        <div className="flex justify-center py-4">
          <LoadingSpinner />
        </div>
      )}

      {entities && entities.length > 0 && (
        <div className="mb-4 overflow-x-auto rounded border border-slate-200">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Identifier</th>
                <th className="px-3 py-2 font-medium">Primary</th>
                <th className="px-3 py-2 font-medium">Effective</th>
                {isDraft && <th className="px-3 py-2 font-medium"> </th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {entities.map((row) => (
                <tr key={row.id}>
                  <td className="px-3 py-2">{row.entity_type}</td>
                  <td className="px-3 py-2">{row.name}</td>
                  <td className="px-3 py-2 font-mono text-xs">{row.identifier}</td>
                  <td className="px-3 py-2">{row.is_primary ? 'Yes' : '—'}</td>
                  <td className="px-3 py-2 text-xs text-slate-600">
                    {row.effective_start_date ?? '—'}
                    {row.effective_end_date ? ` → ${row.effective_end_date}` : ''}
                  </td>
                  {isDraft && (
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        onClick={() => handleRemove(row.id)}
                        className="text-sm text-red-600 hover:underline"
                        disabled={deleteMutation.isPending}
                      >
                        Remove
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {entities && entities.length === 0 && (
        <p className="mb-3 text-sm text-amber-700">No covered entities — validation will flag NO_COVERED_ENTITIES.</p>
      )}

      {isDraft && (
        <div className="space-y-3 border-t border-slate-100 pt-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Select
              label="Entity type"
              value={entityType}
              onChange={(e) => {
                const next = e.target.value as typeof entityType
                setEntityType(next)
                setEntityRef(next === 'ORG' ? 'KEYSTONE-CARD' : '')
              }}
              options={ENTITY_TYPE_OPTIONS}
            />
            <Input
              label={refLabel}
              value={entityRef}
              onChange={(e) => setEntityRef(e.target.value)}
            />
            <Input
              label="Effective start"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
            <Input
              label="Effective end"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={isPrimary}
              onChange={(e) => setIsPrimary(e.target.checked)}
            />
            Primary covered entity
          </label>
          {error && (
            <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
          )}
          <Button type="button" onClick={handleAdd} disabled={addMutation.isPending}>
            {addMutation.isPending ? 'Adding…' : 'Add covered entity'}
          </Button>
        </div>
      )}
    </FormPanel>
  )
}
