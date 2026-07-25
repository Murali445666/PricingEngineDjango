import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, FormPanel, Input, LoadingSpinner, Select } from '@/shared/ui'
import {
  addContractScope,
  deleteContractScope,
  fetchContractScope,
} from '@/services/contractService'
import { listProducts } from '@/services/productService'
import type { ProductScopeCreatePayload } from '@/types'

interface ProductScopePanelProps {
  contractId: number
  isDraft: boolean
  defaultLob?: string
}

export function ProductScopePanel({ contractId, isDraft, defaultLob }: ProductScopePanelProps) {
  const queryClient = useQueryClient()
  const [productId, setProductId] = useState('24')
  const [lobCode, setLobCode] = useState(defaultLob ?? 'COMMERCIAL')
  const [effectiveDate, setEffectiveDate] = useState('2025-04-17')
  const [terminationDate, setTerminationDate] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { data: scopes, isLoading: scopesLoading } = useQuery({
    queryKey: ['contract-scope', contractId],
    queryFn: () => fetchContractScope(contractId),
  })

  const { data: productsData, isLoading: productsLoading } = useQuery({
    queryKey: ['products', 'scope-picker'],
    queryFn: () => listProducts({ page_size: 100 }),
    enabled: isDraft,
  })

  const productOptions =
    productsData?.results.map((p) => ({
      value: String(p.id),
      label: `${p.name}${p.product_code ? ` (${p.product_code})` : ''} · LOB ${p.lob ?? '—'}`,
    })) ?? []

  const addMutation = useMutation({
    mutationFn: (payload: ProductScopeCreatePayload) => addContractScope(contractId, payload),
    onSuccess: () => {
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['contract-scope', contractId] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (scopeId: number) => deleteContractScope(contractId, scopeId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['contract-scope', contractId] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const handleAdd = () => {
    const pid = parseInt(productId, 10)
    if (Number.isNaN(pid)) {
      setError('Select a product.')
      return
    }
    addMutation.mutate({
      product_id: pid,
      lob_code: lobCode.trim() || null,
      effective_date: effectiveDate.trim() || null,
      termination_date: terminationDate.trim() || null,
    })
  }

  const handleRemove = (scopeId: number) => {
    if (!window.confirm('Remove this product scope row?')) return
    deleteMutation.mutate(scopeId)
  }

  const isLoading = scopesLoading || (isDraft && productsLoading)

  return (
    <FormPanel title="Product scope (Exhibit B)" className="mb-6">
      <p className="mb-3 text-sm text-slate-600">
        Links this contract to payer products at the LOB level. The resolver filters by product scope
        before tie-breaking — without a row here, a rostered contract still cannot resolve.
      </p>

      {!isDraft && (
        <p className="mb-3 rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
          Product scope is read-only — contract is not DRAFT.
        </p>
      )}

      {isLoading && (
        <div className="flex justify-center py-4">
          <LoadingSpinner />
        </div>
      )}

      {scopes && scopes.length > 0 && (
        <div className="mb-4 overflow-x-auto rounded border border-slate-200">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="px-3 py-2 font-medium">Product</th>
                <th className="px-3 py-2 font-medium">LOB</th>
                <th className="px-3 py-2 font-medium">Network</th>
                <th className="px-3 py-2 font-medium">Effective</th>
                {isDraft && <th className="px-3 py-2 font-medium"> </th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {scopes.map((row) => (
                <tr key={row.id}>
                  <td className="px-3 py-2">
                    <span className="font-medium">{row.product_name ?? '—'}</span>
                    {row.product_code && (
                      <span className="ml-1 font-mono text-xs text-slate-500">{row.product_code}</span>
                    )}
                    <span className="block text-xs text-slate-400">id {row.product_id}</span>
                  </td>
                  <td className="px-3 py-2">{row.lob_code ?? '—'}</td>
                  <td className="px-3 py-2 font-mono text-xs">{row.network_id ?? '—'}</td>
                  <td className="px-3 py-2 text-xs text-slate-600">
                    {row.effective_date ?? '—'}
                    {row.termination_date ? ` → ${row.termination_date}` : ''}
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

      {scopes && scopes.length === 0 && (
        <p className="mb-3 text-sm text-amber-700">
          No product scope — validation will flag NO_PRODUCT_SCOPE when a roster exists.
        </p>
      )}

      {isDraft && productOptions.length > 0 && (
        <div className="space-y-3 border-t border-slate-100 pt-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Select
              label="Product"
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              options={productOptions}
            />
            <Input
              label="LOB code"
              value={lobCode}
              onChange={(e) => setLobCode(e.target.value)}
            />
            <Input
              label="Effective date"
              type="date"
              value={effectiveDate}
              onChange={(e) => setEffectiveDate(e.target.value)}
            />
            <Input
              label="Termination date"
              type="date"
              value={terminationDate}
              onChange={(e) => setTerminationDate(e.target.value)}
            />
          </div>
          {error && (
            <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
          )}
          <Button type="button" onClick={handleAdd} disabled={addMutation.isPending}>
            {addMutation.isPending ? 'Adding…' : 'Add product scope'}
          </Button>
        </div>
      )}
    </FormPanel>
  )
}
