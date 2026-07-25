import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { FormPanel, Button } from '@/shared/ui'
import { createContractAmendment } from '@/services/contractService'
import type { AmendmentCreatePayload } from '@/types'

interface AmendmentPanelProps {
  contractId: number
  isActive: boolean
  hasDraftVersion: boolean
}

export function AmendmentPanel({ contractId, isActive, hasDraftVersion }: AmendmentPanelProps) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<AmendmentCreatePayload>({
    amendment_number: '',
    effective_date: '',
    description: '',
  })

  const mutation = useMutation({
    mutationFn: () => createContractAmendment(contractId, form),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['contract', String(contractId)] })
      void queryClient.invalidateQueries({ queryKey: ['contract-explorer', String(contractId)] })
      void queryClient.invalidateQueries({ queryKey: ['contract-amendments', String(contractId)] })
      void queryClient.invalidateQueries({ queryKey: ['contract-rules', String(contractId)] })
      setForm({ amendment_number: '', effective_date: '', description: '' })
    },
    onError: (err: Error) => {
      window.alert(`Create amendment failed: ${err.message}`)
    },
  })

  if (!isActive) return null

  const canCreate = !hasDraftVersion && form.amendment_number && form.effective_date && form.description

  return (
    <FormPanel title="Amendments" className="mb-4">
      <p className="mb-3 text-sm text-slate-600">
        Start an amendment to clone the live version into an editable DRAFT. The current ACTIVE version keeps
        pricing until the amendment is published.
      </p>
      {hasDraftVersion ? (
        <p className="text-sm text-amber-800">
          A DRAFT version already exists — publish or discard it before starting another amendment.
        </p>
      ) : (
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (canCreate) mutation.mutate()
          }}
        >
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">Amendment number</span>
            <input
              type="text"
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={form.amendment_number}
              onChange={(e) => setForm((f) => ({ ...f, amendment_number: e.target.value }))}
              placeholder="AMD-2026-01"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">Effective date</span>
            <input
              type="date"
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={form.effective_date}
              onChange={(e) => setForm((f) => ({ ...f, effective_date: e.target.value }))}
            />
          </label>
          <label className="block text-sm sm:col-span-2">
            <span className="mb-1 block font-medium text-slate-700">Description</span>
            <textarea
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              rows={2}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="Annual +3% escalator"
            />
          </label>
          <div className="sm:col-span-2">
            <Button type="submit" disabled={!canCreate || mutation.isPending}>
              {mutation.isPending ? 'Creating…' : 'Create amendment'}
            </Button>
          </div>
        </form>
      )}
    </FormPanel>
  )
}
