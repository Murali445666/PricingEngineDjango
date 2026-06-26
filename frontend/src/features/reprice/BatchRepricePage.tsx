import { useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  PageLayout,
  FormPanel,
  Button,
  Input,
  Select,
  LoadingSpinner,
  ErrorState,
  DataTable,
  StatusBadge,
} from '@/shared/ui'
import type { Column } from '@/shared/ui'
import { repriceClaimBatch } from '@/services/repriceService'
import {
  ClaimLineEntryGrid,
  createEmptyClaimLine,
  validateClaimLines,
} from '@/features/reprice/ClaimLineEntryGrid'
import { ResolutionTracePanel } from '@/features/reprice/ResolutionTracePanel'
import type {
  RepriceBatchResultRow,
  RepriceClaimLineInput,
  RepriceClaimRequest,
  RepriceTraceContext,
} from '@/types/reprice'
import { isBatchResultFailure, isBatchResultSuccess } from '@/types/reprice'

const MAX_CLAIMS = 50

interface BatchClaimDraft {
  key: number
  billing_npi: string
  rendering_npi: string
  member_id: string
  service_date: string
  claim_type: 'professional' | 'institutional'
  lines: RepriceClaimLineInput[]
}

interface MergedLineRow {
  _key: number
  lineNum: number
  inputProcedureCode: string
  inputUnits: string
  inputBilled: string
  allowedAmount: string
  lineStatus: string
  details: string
}

function createDemoClaim(key: number): BatchClaimDraft {
  return {
    key,
    billing_npi: 'BILLING-NPI-S4',
    rendering_npi: 'RENDER-NPI-S4',
    member_id: 'MEM-S4-001',
    service_date: '2025-06-15',
    claim_type: 'professional',
    lines: [createEmptyClaimLine({ procedure_code: '99213', units: 1, billed_amount: '200.00' })],
  }
}

function draftToRequest(draft: BatchClaimDraft): RepriceClaimRequest {
  return {
    billing_npi: draft.billing_npi.trim(),
    rendering_npi: draft.rendering_npi.trim() || undefined,
    member_id: draft.member_id.trim(),
    service_date: draft.service_date,
    claim_type: draft.claim_type,
    lines: draft.lines.map((line) => ({
      ...line,
      procedure_code: line.procedure_code.trim(),
      units: line.units ?? 1,
      billed_amount: line.billed_amount === '' ? undefined : line.billed_amount,
    })),
  }
}

function traceFromBatchResult(row: RepriceBatchResultRow): RepriceTraceContext {
  if (isBatchResultFailure(row)) {
    return {
      resolutionMode: row.status,
      contractId: null,
      provider: null,
      member: {
        member_id: row.member_id,
        lob: null,
        product_id: null,
        enrollment_id: null,
      },
      message: row.message,
    }
  }
  return {
    resolutionMode: row.resolution_mode,
    contractId: row.contract_id,
    provider: null,
    member: {
      member_id: row.member_id,
      lob: null,
      product_id: null,
      enrollment_id: null,
    },
    traceId: row.trace_id,
  }
}

function mergeLines(
  inputs: RepriceClaimLineInput[],
  outputs: RepriceBatchResultRow['lines'],
): MergedLineRow[] {
  return inputs.map((input, index) => ({
    _key: index,
    lineNum: index + 1,
    inputProcedureCode: input.procedure_code,
    inputUnits: String(input.units ?? 1),
    inputBilled:
      input.billed_amount != null && input.billed_amount !== ''
        ? String(input.billed_amount)
        : '—',
    allowedAmount: outputs[index]?.allowed_amount ?? '—',
    lineStatus: outputs[index]?.status ?? '—',
    details: outputs[index]?.details ?? '—',
  }))
}

export function BatchRepricePage() {
  const nextKey = useRef(2)
  const [claims, setClaims] = useState<BatchClaimDraft[]>(() => [createDemoClaim(1)])
  const [validationError, setValidationError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Record<number, boolean>>({})

  const mutation = useMutation({
    mutationFn: repriceClaimBatch,
    onMutate: () => setValidationError(null),
  })

  const updateClaim = (index: number, patch: Partial<BatchClaimDraft>) => {
    setClaims((prev) => prev.map((c, i) => (i === index ? { ...c, ...patch } : c)))
  }

  const addClaim = () => {
    if (claims.length >= MAX_CLAIMS) return
    const key = nextKey.current++
    setClaims((prev) => [...prev, createDemoClaim(key)])
  }

  const removeClaim = (index: number) => {
    if (claims.length <= 1) return
    setClaims((prev) => prev.filter((_, i) => i !== index))
  }

  const validateAll = (): RepriceClaimRequest[] | null => {
    if (claims.length > MAX_CLAIMS) {
      setValidationError(`At most ${MAX_CLAIMS} claims per batch.`)
      return null
    }
    for (let i = 0; i < claims.length; i++) {
      const c = claims[i]
      if (!c.billing_npi.trim()) {
        setValidationError(`Claim ${i + 1}: billing NPI is required.`)
        return null
      }
      if (!c.member_id.trim()) {
        setValidationError(`Claim ${i + 1}: member ID is required.`)
        return null
      }
      if (!c.service_date.trim()) {
        setValidationError(`Claim ${i + 1}: service date is required.`)
        return null
      }
      const lineError = validateClaimLines(c.lines)
      if (lineError) {
        setValidationError(`Claim ${i + 1}: ${lineError}`)
        return null
      }
    }
    setValidationError(null)
    return claims.map(draftToRequest)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const payload = validateAll()
    if (!payload) return
    setExpanded({})
    mutation.mutate({ claims: payload })
  }

  const toggleExpanded = (index: number) => {
    setExpanded((prev) => ({ ...prev, [index]: !prev[index] }))
  }

  const lineColumns: Column<MergedLineRow>[] = [
    { key: 'lineNum', header: '#', sortable: false },
    { key: 'inputProcedureCode', header: 'Procedure (input)' },
    { key: 'inputUnits', header: 'Units' },
    { key: 'inputBilled', header: 'Billed (input)' },
    {
      key: 'allowedAmount',
      header: 'Allowed',
      render: (row) => <span className="font-medium">{row.allowedAmount}</span>,
    },
    {
      key: 'lineStatus',
      header: 'Status',
      render: (row) => (row.lineStatus !== '—' ? <StatusBadge status={row.lineStatus} /> : '—'),
    },
    {
      key: 'details',
      header: 'Details',
      render: (row) => <span className="text-xs text-slate-600">{row.details}</span>,
    },
  ]

  return (
    <PageLayout
      title="Batch Reprice"
      description="Submit up to 50 identity-first claims; each is context-resolved and priced independently."
      metadata={
        <span>
          POST /api/reprice-claim-batch/ — per-claim failures do not fail the batch. Demo claim
          pre-filled with <code className="font-mono text-xs">BILLING-NPI-S4</code> /{' '}
          <code className="font-mono text-xs">MEM-S4-001</code>.
        </span>
      }
    >
      <div className="space-y-6">
        <FormPanel
          title="Claims"
          description={`Add claims (max ${MAX_CLAIMS}). Each claim uses the same identity + line shape as Reprice Claim.`}
        >
          <form onSubmit={handleSubmit} className="space-y-6">
            {claims.map((claim, claimIndex) => (
              <div
                key={claim.key}
                className="rounded border border-slate-200 bg-slate-50/30 p-4"
              >
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-sm font-semibold text-slate-900">Claim {claimIndex + 1}</h4>
                  <Button
                    type="button"
                    variant="secondary"
                    className="!px-2 !py-1 !text-xs"
                    onClick={() => removeClaim(claimIndex)}
                    disabled={claims.length <= 1 || mutation.isPending}
                  >
                    Remove claim
                  </Button>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Input
                    label="Billing NPI"
                    value={claim.billing_npi}
                    onChange={(e) => updateClaim(claimIndex, { billing_npi: e.target.value })}
                    maxLength={15}
                    disabled={mutation.isPending}
                  />
                  <Input
                    label="Rendering NPI"
                    value={claim.rendering_npi}
                    onChange={(e) => updateClaim(claimIndex, { rendering_npi: e.target.value })}
                    maxLength={15}
                    disabled={mutation.isPending}
                  />
                  <Input
                    label="Member ID"
                    value={claim.member_id}
                    onChange={(e) => updateClaim(claimIndex, { member_id: e.target.value })}
                    disabled={mutation.isPending}
                  />
                  <Input
                    label="Service date"
                    type="date"
                    value={claim.service_date}
                    onChange={(e) => updateClaim(claimIndex, { service_date: e.target.value })}
                    disabled={mutation.isPending}
                  />
                  <Select
                    label="Claim type"
                    value={claim.claim_type}
                    onChange={(e) =>
                      updateClaim(claimIndex, {
                        claim_type: e.target.value as 'professional' | 'institutional',
                      })
                    }
                    disabled={mutation.isPending}
                    options={[
                      { value: 'professional', label: 'Professional' },
                      { value: 'institutional', label: 'Institutional' },
                    ]}
                  />
                </div>
                <div className="mt-4">
                  <p className="mb-2 text-sm font-medium text-slate-700">Lines</p>
                  <ClaimLineEntryGrid
                    lines={claim.lines}
                    onChange={(lines) => updateClaim(claimIndex, { lines })}
                    disabled={mutation.isPending}
                  />
                </div>
              </div>
            ))}

            {claims.length >= MAX_CLAIMS && (
              <p className="text-sm text-amber-800" role="status">
                Maximum of {MAX_CLAIMS} claims reached.
              </p>
            )}

            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={addClaim}
                disabled={claims.length >= MAX_CLAIMS || mutation.isPending}
              >
                Add claim
              </Button>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? <LoadingSpinner size="sm" /> : `Reprice ${claims.length} claim(s)`}
              </Button>
            </div>

            {validationError && (
              <p className="text-sm text-red-600" role="alert">
                {validationError}
              </p>
            )}
          </form>
        </FormPanel>

        {mutation.isError && (
          <ErrorState
            title="Batch request failed"
            message={mutation.error?.message ?? 'Validation or network error.'}
            onRetry={() => {
              const payload = validateAll()
              if (payload) mutation.mutate({ claims: payload })
            }}
          />
        )}

        {mutation.isSuccess && (
          <FormPanel
            title="Results"
            description={`${mutation.data.count} result(s) — expand a row for trace and line detail.`}
          >
            <div className="space-y-3">
              {mutation.data.results.map((row) => {
                const isOpen = !!expanded[row.index]
                const inputLines = claims[row.index]?.lines ?? []
                return (
                  <div
                    key={row.index}
                    className="rounded border border-slate-200 bg-white"
                  >
                    <button
                      type="button"
                      className="flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left text-sm hover:bg-slate-50"
                      onClick={() => toggleExpanded(row.index)}
                    >
                      <span className="font-mono text-xs text-slate-500">#{row.index + 1}</span>
                      <StatusBadge status={row.status} />
                      <span className="text-slate-700">
                        member <span className="font-mono text-xs">{row.member_id}</span>
                      </span>
                      {isBatchResultSuccess(row) && (
                        <>
                          <span className="text-slate-500">·</span>
                          <span>contract {row.contract_id}</span>
                          <span className="text-slate-500">·</span>
                          <span>{row.resolution_mode}</span>
                        </>
                      )}
                      {isBatchResultFailure(row) && (
                        <span className="text-amber-800">{row.message}</span>
                      )}
                      <span className="ml-auto text-xs text-slate-400">
                        {isOpen ? 'Hide' : 'Show'} details
                      </span>
                    </button>

                    {isOpen && (
                      <div className="space-y-4 border-t border-slate-100 px-4 py-4">
                        {isBatchResultFailure(row) && (
                          <div
                            role="status"
                            className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
                          >
                            <p className="font-medium">{row.status}</p>
                            <p className="mt-1">{row.message}</p>
                          </div>
                        )}
                        <ResolutionTracePanel context={traceFromBatchResult(row)} />
                        {isBatchResultSuccess(row) && row.lines.length > 0 && (
                          <div>
                            <p className="mb-2 text-sm font-medium text-slate-700">Priced lines</p>
                            <DataTable
                              columns={lineColumns}
                              data={mergeLines(inputLines, row.lines)}
                              keyExtractor={(r) => r._key}
                              emptyMessage="No lines"
                              pageSize={20}
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </FormPanel>
        )}
      </div>
    </PageLayout>
  )
}
