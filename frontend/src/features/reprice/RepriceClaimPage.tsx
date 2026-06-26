import { useState } from 'react'
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
import { repriceClaim } from '@/services/repriceService'
import {
  ClaimLineEntryGrid,
  createEmptyClaimLine,
  validateClaimLines,
} from '@/features/reprice/ClaimLineEntryGrid'
import { ResolutionTracePanel } from '@/features/reprice/ResolutionTracePanel'
import type {
  RepriceClaimLineInput,
  RepriceClaimRequest,
  RepriceClaimResponse,
  RepriceTraceContext,
} from '@/types/reprice'
import { isRepriceResolutionFailure, isRepriceSuccess } from '@/types/reprice'

const DEMO_DEFAULTS = {
  billing_npi: 'BILLING-NPI-S4',
  rendering_npi: 'RENDER-NPI-S4',
  member_id: 'MEM-S4-001',
  service_date: '2025-06-15',
  claim_type: 'professional' as const,
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

function buildTraceContext(response: RepriceClaimResponse | null): RepriceTraceContext | null {
  if (!response) return null
  if (isRepriceResolutionFailure(response)) {
    return {
      resolutionMode: response.status,
      contractId: null,
      provider: null,
      member: null,
      message: response.message,
    }
  }
  if (isRepriceSuccess(response)) {
    return {
      resolutionMode: response.resolution_mode,
      contractId: response.contract_id,
      provider: response.provider,
      member: response.member,
      traceId: response.trace_id,
    }
  }
  return null
}

function mergeLines(
  inputs: RepriceClaimLineInput[],
  response: RepriceClaimResponse | null,
): MergedLineRow[] {
  const outputs = response && isRepriceSuccess(response) ? response.lines : []
  return inputs.map((input, index) => ({
    _key: index,
    lineNum: index + 1,
    inputProcedureCode: input.procedure_code,
    inputUnits: String(input.units ?? 1),
    inputBilled: input.billed_amount != null && input.billed_amount !== '' ? String(input.billed_amount) : '—',
    allowedAmount: outputs[index]?.allowed_amount ?? '—',
    lineStatus: outputs[index]?.status ?? '—',
    details: outputs[index]?.details ?? '—',
  }))
}

export function RepriceClaimPage() {
  const [billingNpi, setBillingNpi] = useState(DEMO_DEFAULTS.billing_npi)
  const [renderingNpi, setRenderingNpi] = useState(DEMO_DEFAULTS.rendering_npi)
  const [memberId, setMemberId] = useState(DEMO_DEFAULTS.member_id)
  const [serviceDate, setServiceDate] = useState(DEMO_DEFAULTS.service_date)
  const [claimType, setClaimType] = useState<'professional' | 'institutional'>(DEMO_DEFAULTS.claim_type)
  const [lines, setLines] = useState<RepriceClaimLineInput[]>([
    createEmptyClaimLine({ procedure_code: '99213', units: 1, billed_amount: '200.00' }),
  ])
  const [validationError, setValidationError] = useState<string | null>(null)
  const [businessOutcome, setBusinessOutcome] = useState<'OON' | 'NO_CONTRACT' | null>(null)

  const mutation = useMutation({
    mutationFn: repriceClaim,
    onMutate: () => {
      setValidationError(null)
      setBusinessOutcome(null)
    },
    onSuccess: (data) => {
      if (isRepriceResolutionFailure(data)) {
        setBusinessOutcome(data.status)
      }
    },
  })

  const buildPayload = (): RepriceClaimRequest | null => {
    const lineError = validateClaimLines(lines)
    if (lineError) {
      setValidationError(lineError)
      return null
    }
    if (!billingNpi.trim()) {
      setValidationError('Billing NPI is required.')
      return null
    }
    if (!memberId.trim()) {
      setValidationError('Member ID is required.')
      return null
    }
    if (!serviceDate.trim()) {
      setValidationError('Service date is required.')
      return null
    }
    setValidationError(null)
    return {
      billing_npi: billingNpi.trim(),
      rendering_npi: renderingNpi.trim() || undefined,
      member_id: memberId.trim(),
      service_date: serviceDate,
      claim_type: claimType,
      lines: lines.map((line) => ({
        ...line,
        procedure_code: line.procedure_code.trim(),
        units: line.units ?? 1,
        billed_amount: line.billed_amount === '' ? undefined : line.billed_amount,
      })),
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const payload = buildPayload()
    if (!payload) return
    mutation.mutate(payload)
  }

  const traceContext = buildTraceContext(mutation.data ?? null)
  const mergedLines = mergeLines(lines, mutation.data ?? null)
  const pricingStatus =
    mutation.data && isRepriceSuccess(mutation.data) ? mutation.data.status : null

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
      title="Reprice Claim"
      description="Submit member + provider identity; the system resolves enrollment → product → network → contract automatically."
      metadata={
        <span>
          Seeded demo: billing NPI <code className="font-mono text-xs">BILLING-NPI-S4</code>, member{' '}
          <code className="font-mono text-xs">MEM-S4-001</code>, service date 2025-06-15. Distinct from
          Pricing Sandbox (contract-first).
        </span>
      }
    >
      <div className="space-y-6">
        <FormPanel
          title="Claim identity"
          description="POST /api/reprice-claim/ — no contract_id required."
        >
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2">
              <Input
                label="Billing NPI"
                value={billingNpi}
                onChange={(e) => setBillingNpi(e.target.value)}
                placeholder="BILLING-NPI-S4"
                maxLength={15}
              />
              <Input
                label="Rendering NPI"
                value={renderingNpi}
                onChange={(e) => setRenderingNpi(e.target.value)}
                placeholder="RENDER-NPI-S4"
                maxLength={15}
              />
              <Input
                label="Member ID"
                value={memberId}
                onChange={(e) => setMemberId(e.target.value)}
                placeholder="MEM-S4-001"
              />
              <Input
                label="Service date"
                type="date"
                value={serviceDate}
                onChange={(e) => setServiceDate(e.target.value)}
              />
              <Select
                label="Claim type"
                value={claimType}
                onChange={(e) => setClaimType(e.target.value as 'professional' | 'institutional')}
                options={[
                  { value: 'professional', label: 'Professional' },
                  { value: 'institutional', label: 'Institutional' },
                ]}
              />
            </div>

            <div>
              <p className="mb-2 text-sm font-medium text-slate-700">Claim lines</p>
              <ClaimLineEntryGrid
                lines={lines}
                onChange={setLines}
                disabled={mutation.isPending}
              />
            </div>

            {validationError && (
              <p className="text-sm text-red-600" role="alert">
                {validationError}
              </p>
            )}

            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? <LoadingSpinner size="sm" /> : 'Reprice claim'}
            </Button>
          </form>
        </FormPanel>

        {mutation.isError && (
          <ErrorState
            title="Reprice failed"
            message={mutation.error?.message ?? 'Request failed (network or ENGINE_ERROR).'}
            onRetry={() => {
              const payload = buildPayload()
              if (payload) mutation.mutate(payload)
            }}
          />
        )}

        {businessOutcome && mutation.data && isRepriceResolutionFailure(mutation.data) && (
          <div
            role="status"
            className="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
          >
            <p className="font-medium">Contract not resolved ({businessOutcome})</p>
            <p className="mt-1">{mutation.data.message}</p>
          </div>
        )}

        {traceContext && mutation.isSuccess && (
          <ResolutionTracePanel context={traceContext} />
        )}

        {mutation.isSuccess && isRepriceSuccess(mutation.data) && (
          <FormPanel title="Pricing summary">
            <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
              <dt className="text-slate-500">Status</dt>
              <dd>
                {pricingStatus ? <StatusBadge status={pricingStatus} /> : '—'}
              </dd>
              <dt className="text-slate-500">contract_id</dt>
              <dd className="font-mono text-xs">{mutation.data.contract_id}</dd>
              <dt className="text-slate-500">trace_id</dt>
              <dd className="break-all font-mono text-xs">{mutation.data.trace_id}</dd>
            </dl>
          </FormPanel>
        )}

        {mutation.isSuccess && !isRepriceResolutionFailure(mutation.data) && (
          <FormPanel
            title="Line results"
            description="Output lines are correlated to input by index — the API does not echo procedure codes."
          >
            <DataTable
              columns={lineColumns}
              data={mergedLines}
              keyExtractor={(row) => row._key}
              emptyMessage="No lines"
              pageSize={20}
            />
          </FormPanel>
        )}
      </div>
    </PageLayout>
  )
}
