import { useState, useCallback, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { PageLayout, FormPanel, Button, Select, TextArea, Input, DataTable, StatusBadge, NetworkStatusBadge } from '@/shared/ui'
import { fetchContracts, fetchContractExplorer } from '@/services/contractService'
import { priceClaimSimulate } from '@/services/pricingService'
import type { Contract } from '@/types'
import type {
  ClaimSimulateRequest,
  ClaimPricingResult,
  ClaimSimulateLineResult,
  ExecutionTraceEntry,
  ClaimSimulateResponse,
} from '@/types'
import type { Column } from '@/shared/ui'

function buildSimulateCurl(baseUrl: string, payload: ClaimSimulateRequest): string {
  const root = (baseUrl || '').replace(/\/$/, '')
  const path = root ? `${root}/price-claim-simulate/` : '/api/price-claim-simulate/'
  return `curl -X POST "${path}" -H "Content-Type: application/json" -d ${JSON.stringify(JSON.stringify(payload))}`
}

/** DEMO_DRG: procedure_code = DRG code for line-level DRG weight lookup. */
export const EXAMPLE_DRG_470 = `{
  "service_date": "2026-06-01",
  "pricing_date": "2026-06-01",
  "claim_type": "INPATIENT",
  "lines": [
    {
      "line_id": "L1",
      "procedure_code": "470",
      "billed_amount": "50000.00",
      "units": 1,
      "modifiers": []
    }
  ]
}`

/** DEMO_RBRVS: 99213 × fee schedule × multiplier. */
export const EXAMPLE_RBRVS_99213 = `{
  "service_date": "2026-06-01",
  "pricing_date": "2026-06-01",
  "claim_type": "PROFESSIONAL",
  "lines": [
    {
      "line_id": "L1",
      "procedure_code": "99213",
      "billed_amount": "200.00",
      "units": 1,
      "modifiers": []
    }
  ]
}`

/** DEMO_FLAT: flat amount for procedure 00100. */
export const EXAMPLE_FLAT_00100 = `{
  "service_date": "2026-06-01",
  "pricing_date": "2026-06-01",
  "claim_type": "OUTPATIENT",
  "lines": [
    {
      "line_id": "L1",
      "procedure_code": "00100",
      "billed_amount": "300.00",
      "units": 1,
      "modifiers": []
    }
  ]
}`

/** DEMO_PCT_BILLED: percent of billed (e.g. 0.8 × billed). */
export const EXAMPLE_PCT_99213 = `{
  "service_date": "2026-06-01",
  "pricing_date": "2026-06-01",
  "claim_type": "OUTPATIENT",
  "lines": [
    {
      "line_id": "L1",
      "procedure_code": "99213",
      "billed_amount": "200.00",
      "units": 1,
      "modifiers": []
    }
  ]
}`

const SAMPLE_CLAIM_JSON = EXAMPLE_FLAT_00100

export function ClaimSimulationPage() {
  const [contractId, setContractId] = useState<string>('')
  const [versionId, setVersionId] = useState<string>('')
  const [claimJson, setClaimJson] = useState<string>(SAMPLE_CLAIM_JSON)
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [validateExpanded, setValidateExpanded] = useState(false)
  const [memberId, setMemberId] = useState('')
  const [billingNpi, setBillingNpi] = useState('')
  const [renderingNpi, setRenderingNpi] = useState('')
  const [result, setResult] = useState<ClaimPricingResult | null>(null)
  const [lastSimulate, setLastSimulate] = useState<ClaimSimulateResponse | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)

  const { data: contracts = [], isLoading: contractsLoading } = useQuery({
    queryKey: ['contracts'],
    queryFn: () => fetchContracts(),
  })

  const contractIdNum = contractId ? Number(contractId) : NaN
  const {
    data: explorer,
    isLoading: explorerLoading,
    isError: explorerError,
    error: explorerErrObj,
  } = useQuery({
    queryKey: ['contract-explorer', contractId],
    queryFn: () => fetchContractExplorer(contractIdNum),
    enabled: Number.isInteger(contractIdNum) && contractIdNum > 0,
    staleTime: 60_000,
  })

  const versionOptionsFromExplorer = (explorer?.versions ?? [])
    .slice()
    .sort((a, b) => b.version_number - a.version_number)
    .map((v) => ({
      value: String(v.version_id),
      label: `v${v.version_number} (ID ${v.version_id}) · ${v.status}`,
    }))

  useEffect(() => {
    setVersionId('')
    setResult(null)
    setLastSimulate(null)
    setApiError(null)
  }, [contractId])

  const mutateSimulate = useMutation({
    mutationFn: priceClaimSimulate,
    onMutate: () => {
      setResult(null)
      setLastSimulate(null)
    },
    onSuccess: (res) => {
      setResult(res.result)
      setLastSimulate(res)
      setApiError(null)
    },
    onError: (err: Error) => {
      const msg = err.message ?? 'Simulation failed'
      window.alert(`Simulation failed: ${msg}`)
      setApiError(msg)
      setResult(null)
      setLastSimulate(null)
    },
  })

  const parseClaimJson = useCallback((): ClaimSimulateRequest['claim'] | null => {
    setJsonError(null)
    const trimmed = claimJson.trim()
    if (!trimmed) {
      setJsonError('Claim JSON is empty.')
      return null
    }
    try {
      const parsed = JSON.parse(trimmed) as unknown
      if (!parsed || typeof parsed !== 'object' || parsed === null) {
        setJsonError('Claim must have a "lines" array.')
        return null
      }
      const obj = parsed as Record<string, unknown>
      let claim: Record<string, unknown> = obj
      const inner = obj.claim
      if (
        !Array.isArray(obj.lines) &&
        inner != null &&
        typeof inner === 'object' &&
        !Array.isArray(inner) &&
        Array.isArray((inner as Record<string, unknown>).lines)
      ) {
        claim = inner as Record<string, unknown>
      }
      if (!Array.isArray(claim.lines)) {
        setJsonError('Claim must have a "lines" array.')
        return null
      }
      return claim as unknown as ClaimSimulateRequest['claim']
    } catch (e) {
      const message = e instanceof SyntaxError ? e.message : 'Invalid JSON'
      setJsonError(`Invalid JSON: ${message}`)
      return null
    }
  }, [claimJson])

  const handleRun = () => {
    const claim = parseClaimJson()
    if (!claim) return
    const cId = contractId ? Number(contractId) : NaN
    const vId = versionId ? Number(versionId) : NaN
    if (!Number.isInteger(cId) || cId < 1) {
      const msg = 'Select a valid contract.'
      window.alert(msg)
      setApiError(msg)
      return
    }
    if (!Number.isInteger(vId) || vId < 1) {
      const msg = 'Select or enter a valid version (positive integer).'
      window.alert(msg)
      setApiError(msg)
      return
    }
    setApiError(null)
    const payload: ClaimSimulateRequest = { contract_id: cId, version_id: vId, claim }
    const trimmedMember = memberId.trim()
    const trimmedBilling = billingNpi.trim()
    const trimmedRendering = renderingNpi.trim()
    if (trimmedMember) payload.member_id = trimmedMember
    if (trimmedBilling) payload.billing_npi = trimmedBilling
    if (trimmedRendering) payload.rendering_npi = trimmedRendering
    mutateSimulate.mutate(payload)
  }

  const handleCopyCurl = async () => {
    const claim = parseClaimJson()
    if (!claim) return
    const cId = contractId ? Number(contractId) : NaN
    const vId = versionId ? Number(versionId) : NaN
    if (!Number.isInteger(cId) || cId < 1 || !Number.isInteger(vId) || vId < 1) {
      window.alert('Select contract and version before copying cURL.')
      return
    }
    const payload: ClaimSimulateRequest = { contract_id: cId, version_id: vId, claim }
    const trimmedMember = memberId.trim()
    const trimmedBilling = billingNpi.trim()
    const trimmedRendering = renderingNpi.trim()
    if (trimmedMember) payload.member_id = trimmedMember
    if (trimmedBilling) payload.billing_npi = trimmedBilling
    if (trimmedRendering) payload.rendering_npi = trimmedRendering
    const curl = buildSimulateCurl(import.meta.env.VITE_API_BASE_URL ?? '', payload)
    try {
      await navigator.clipboard.writeText(curl)
      window.alert('cURL copied to clipboard.')
    } catch {
      window.alert(curl)
    }
  }

  const handleDownloadResult = () => {
    if (!lastSimulate) return
    const blob = new Blob([JSON.stringify(lastSimulate, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `claim-simulate-${contractId || 'contract'}-${versionId || 'version'}.json`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const contractOptions: { value: string; label: string }[] = [
    { value: '', label: '— Select contract —' },
    ...contracts.map((c: Contract) => ({
      value: String(c.contract_id),
      label: `${c.contract_name ?? c.legacy_contract_number ?? c.contract_id} (${c.contract_id})`,
    })),
  ]

  const runDisabledWhileExplorerLoading =
    contractId !== '' && explorerLoading && versionOptionsFromExplorer.length === 0 && !explorerError

  const lineColumns: Column<ClaimSimulateLineResult & { _lineKey: number }>[] = [
    {
      key: '_lineKey',
      header: 'Line',
      sortable: false,
      render: (r) => String(r._lineKey),
    },
    { key: 'rule_id', header: 'Rule ID' },
    { key: 'status', header: 'Status' },
    { key: 'methodology', header: 'Methodology' },
    { key: 'allowed_amount', header: 'Allowed amount', render: (r) => String(r.allowed_amount ?? '') },
    {
      key: 'base_allowed_amount',
      header: 'Base allowed',
      render: (r) => (r.base_allowed_amount != null ? String(r.base_allowed_amount) : '—'),
    },
    {
      key: 'blended_allowed_amount',
      header: 'Blended allowed',
      render: (r) => (r.blended_allowed_amount != null ? String(r.blended_allowed_amount) : '—'),
    },
    {
      key: 'carveout_applied',
      header: 'Carveout applied',
      render: (r) => (r.carveout_applied ? 'Yes' : 'No'),
    },
    {
      key: 'carveout_id',
      header: 'Carveout ID',
      render: (r) => (r.carveout_id != null ? String(r.carveout_id) : '—'),
    },
  ]

  const traceColumns: Column<ExecutionTraceEntry & { _idx: number }>[] = [
    { key: 'stage', header: 'Stage', render: (r) => r.stage ?? '—' },
    { key: 'phase', header: 'Phase', render: (r) => r.phase ?? '—' },
    {
      key: 'line_index',
      header: 'Line index',
      render: (r) => (r.line_index != null ? String(r.line_index) : '—'),
    },
    { key: 'rule_id', header: 'Rule ID', render: (r) => (r.rule_id != null ? String(r.rule_id) : '—') },
    { key: 'methodology_code', header: 'Methodology', render: (r) => r.methodology_code ?? '—' },
    { key: 'message', header: 'Message', render: (r) => r.message ?? '—' },
  ]

  const hasResult = result != null
  const validationRan = lastSimulate?.validation?.ran === true
  const validation = validationRan ? lastSimulate!.validation : null
  const lines = result?.lines ?? []
  const executionTrace = (result?.execution_trace ?? []).map((e, i) => ({ ...e, _idx: i }))
  const claimTrace = result?.claim_trace ?? []

  return (
    <PageLayout
      title="Claim Simulation Workbench"
      description="Step 12f (first slice): POST /api/price-claim-simulate/ with contract_id, version_id, and claim. Versions load from GET /api/contracts/:id/explorer/."
    >
      <div className="space-y-6">
        <FormPanel
          title="Inputs"
          description="Claim JSON is the inner claim object (service_date, pricing_date, claim_type, lines). Contract/version above are always sent with the request. Scenario persistence: TODO."
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Select
              label="Contract"
              options={contractOptions}
              value={contractId}
              onChange={(e) => setContractId(e.target.value)}
              disabled={contractsLoading}
            />
            {contractId && versionOptionsFromExplorer.length > 0 ? (
              <Select
                label="Version"
                options={[{ value: '', label: '— Select version —' }, ...versionOptionsFromExplorer]}
                value={versionId}
                onChange={(e) => setVersionId(e.target.value)}
                disabled={explorerLoading}
              />
            ) : contractId && explorerLoading ? (
              <div className="text-sm text-slate-500 pt-6">Loading versions…</div>
            ) : contractId && explorerError ? (
              <div className="space-y-2">
                <p className="text-sm text-amber-800">
                  Could not load versions ({explorerErrObj instanceof Error ? explorerErrObj.message : 'error'}). Enter
                  version ID manually.
                </p>
                <Input
                  label="Version ID"
                  type="number"
                  min={1}
                  value={versionId}
                  onChange={(e) => setVersionId(e.target.value)}
                  placeholder="e.g. 2"
                />
              </div>
            ) : contractId && !explorerLoading && versionOptionsFromExplorer.length === 0 && !explorerError ? (
              <div className="space-y-2">
                <p className="text-sm text-slate-600">No versions returned for this contract. Enter version ID manually.</p>
                <Input
                  label="Version ID"
                  type="number"
                  min={1}
                  value={versionId}
                  onChange={(e) => setVersionId(e.target.value)}
                  placeholder="e.g. 2"
                />
              </div>
            ) : (
              <div className="text-sm text-slate-500 pt-6">Select a contract to choose a version.</div>
            )}
          </div>
          <div className="mt-4 rounded border border-slate-200 bg-slate-50/80">
            <button
              type="button"
              className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-slate-800"
              onClick={() => setValidateExpanded((v) => !v)}
              aria-expanded={validateExpanded}
            >
              <span>Validate against member/provider (optional)</span>
              <span className="text-slate-500">{validateExpanded ? '▾' : '▸'}</span>
            </button>
            {validateExpanded && (
              <div className="border-t border-slate-200 px-4 pb-4 pt-3">
                <p className="mb-3 text-xs text-slate-600">
                  Advisory checks only — simulation still prices the selected contract and version.
                  Leave blank to skip validation.
                </p>
                <div className="grid gap-4 sm:grid-cols-3">
                  <Input
                    label="Member ID"
                    value={memberId}
                    onChange={(e) => setMemberId(e.target.value)}
                    placeholder="e.g. MEM-S4-001"
                  />
                  <Input
                    label="Billing NPI"
                    value={billingNpi}
                    onChange={(e) => setBillingNpi(e.target.value)}
                    placeholder="e.g. BILLING-NPI-S4"
                  />
                  <Input
                    label="Rendering NPI"
                    value={renderingNpi}
                    onChange={(e) => setRenderingNpi(e.target.value)}
                    placeholder="Optional"
                  />
                </div>
              </div>
            )}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="self-center text-xs text-slate-500">Load example (seeded demos):</span>
            <Button
              type="button"
              variant="secondary"
              className="!py-1.5 !text-xs"
              onClick={() => {
                setClaimJson(EXAMPLE_DRG_470)
                setJsonError(null)
              }}
            >
              DRG 470
            </Button>
            <Button
              type="button"
              variant="secondary"
              className="!py-1.5 !text-xs"
              onClick={() => {
                setClaimJson(EXAMPLE_RBRVS_99213)
                setJsonError(null)
              }}
            >
              RBRVS 99213
            </Button>
            <Button
              type="button"
              variant="secondary"
              className="!py-1.5 !text-xs"
              onClick={() => {
                setClaimJson(EXAMPLE_FLAT_00100)
                setJsonError(null)
              }}
            >
              FLAT 00100
            </Button>
            <Button
              type="button"
              variant="secondary"
              className="!py-1.5 !text-xs"
              onClick={() => {
                setClaimJson(EXAMPLE_PCT_99213)
                setJsonError(null)
              }}
            >
              PCT 99213
            </Button>
          </div>
          <div className="mt-2">
            <TextArea
              label="Claim JSON"
              value={claimJson}
              onChange={(e) => setClaimJson(e.target.value)}
              error={jsonError ?? undefined}
              rows={14}
              className="font-mono text-sm"
            />
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Button
              onClick={handleRun}
              disabled={
                !contractId ||
                !versionId ||
                mutateSimulate.isPending ||
                contractsLoading ||
                runDisabledWhileExplorerLoading
              }
            >
              {mutateSimulate.isPending ? 'Running…' : 'Run Simulation'}
            </Button>
            <Button type="button" variant="secondary" onClick={() => void handleCopyCurl()}>
              Copy cURL
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={handleDownloadResult}
              disabled={!lastSimulate}
            >
              Download result JSON
            </Button>
          </div>
        </FormPanel>

        {apiError && (
          <div
            role="alert"
            className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          >
            {apiError}
          </div>
        )}

        {!hasResult && !apiError && !mutateSimulate.isPending && (
          <div className="rounded-lg border-2 border-dashed border-slate-200 bg-slate-50/50 px-6 py-10 text-center text-sm text-slate-600">
            <p className="font-medium text-slate-700">Ready to simulate</p>
            <p className="mt-2 max-w-md mx-auto">
              Pick a contract and version, load one of the four demo claim examples (DRG / RBRVS / FLAT / PCT), or paste
              your own claim JSON. Run to see summary, line results, and traces.
            </p>
          </div>
        )}

        {mutateSimulate.isPending && (
          <div className="rounded border border-slate-200 bg-white px-4 py-6 text-center text-sm text-slate-600">
            Running simulation…
          </div>
        )}

        {hasResult && (
          <>
            {validationRan && validation && 'resolution_mode' in validation && (
              <FormPanel
                title="Validation"
                description="Advisory member/provider checks — pricing used the selected contract regardless."
              >
                <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                  <dt className="text-slate-500">Resolution mode</dt>
                  <dd className="font-medium text-slate-900">{validation.resolution_mode ?? '—'}</dd>
                  <dt className="text-slate-500">Selected contract</dt>
                  <dd>{validation.selected_contract_id ?? '—'}</dd>
                  <dt className="text-slate-500">Resolved contract</dt>
                  <dd
                    className={
                      validation.matches_selected_contract === false
                        ? 'font-medium text-amber-800'
                        : 'text-slate-900'
                    }
                  >
                    {validation.resolved_contract_id != null
                      ? String(validation.resolved_contract_id)
                      : '—'}
                    {validation.matches_selected_contract === false && (
                      <span className="ml-2 text-xs text-amber-700">(mismatch)</span>
                    )}
                  </dd>
                  <dt className="text-slate-500">Network status</dt>
                  <dd>
                    <NetworkStatusBadge
                      status={validation.provider?.network_status}
                      tier={validation.provider?.network_tier}
                    />
                  </dd>
                  <dt className="text-slate-500">Member enrolled</dt>
                  <dd>{validation.member?.enrolled ? 'Yes' : 'No'}</dd>
                  <dt className="text-slate-500">Member LOB</dt>
                  <dd>{validation.member?.lob ?? '—'}</dd>
                </dl>
                {(validation.warnings?.length ?? 0) > 0 && (
                  <ul className="mt-4 space-y-2" role="list">
                    {validation.warnings!.map((warning, i) => (
                      <li
                        key={i}
                        className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
                      >
                        {warning}
                      </li>
                    ))}
                  </ul>
                )}
              </FormPanel>
            )}

            <FormPanel title="Summary">
              <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                <dt className="text-slate-500">Status</dt>
                <dd>
                  <StatusBadge status={result.status} />
                </dd>
                <dt className="text-slate-500">total_allowed</dt>
                <dd className="font-medium text-slate-900">{String(result.total_allowed)}</dd>
                <dt className="text-slate-500">final_total_allowed</dt>
                <dd className="font-medium text-slate-900">
                  {result.final_total_allowed != null ? String(result.final_total_allowed) : '—'}
                </dd>
                <dt className="text-slate-500">blended_total_allowed</dt>
                <dd>{result.blended_total_allowed != null ? String(result.blended_total_allowed) : '—'}</dd>
                <dt className="text-slate-500">request_time_ms</dt>
                <dd>
                  {lastSimulate?.request_time_ms != null ? String(lastSimulate.request_time_ms) : '—'}
                </dd>
                <dt className="text-slate-500">contract_id</dt>
                <dd>{result.contract_id}</dd>
                <dt className="text-slate-500">version_id</dt>
                <dd>{lastSimulate?.version_id != null ? String(lastSimulate.version_id) : '—'}</dd>
                <dt className="text-slate-500">applied_stop_loss_rule_id</dt>
                <dd>{result.applied_stop_loss_rule_id != null ? String(result.applied_stop_loss_rule_id) : '—'}</dd>
                <dt className="text-slate-500">applied_outlier_rule_id</dt>
                <dd>{result.applied_outlier_rule_id != null ? String(result.applied_outlier_rule_id) : '—'}</dd>
                <dt className="text-slate-500">applied_cap_floor_id</dt>
                <dd>{result.applied_cap_floor_id != null ? String(result.applied_cap_floor_id) : '—'}</dd>
                <dt className="text-slate-500">applied_blending_rule_ids</dt>
                <dd>
                  {result.applied_blending_rule_ids != null && result.applied_blending_rule_ids.length > 0
                    ? result.applied_blending_rule_ids.join(', ')
                    : '—'}
                </dd>
                <dt className="text-slate-500">original_total_allowed</dt>
                <dd>{result.original_total_allowed != null ? String(result.original_total_allowed) : '—'}</dd>
                <dt className="text-slate-500">pre_cap_total_allowed</dt>
                <dd>{result.pre_cap_total_allowed != null ? String(result.pre_cap_total_allowed) : '—'}</dd>
              </dl>
            </FormPanel>

            <FormPanel title="Line Results">
              <DataTable
                columns={lineColumns}
                data={lines.map((row, i) => ({ ...row, _lineKey: i }))}
                keyExtractor={(row) => `line-${row._lineKey}`}
                emptyMessage="No lines"
                pageSize={20}
              />
            </FormPanel>

            <FormPanel title="Execution Trace">
              <DataTable
                columns={traceColumns}
                data={executionTrace}
                keyExtractor={(row) => `trace-${row._idx}`}
                emptyMessage="No trace entries"
                pageSize={20}
              />
            </FormPanel>

            <FormPanel title="Claim Trace">
              {claimTrace.length === 0 ? (
                <p className="text-sm text-slate-500">No claim trace entries.</p>
              ) : (
                <ul className="list-inside list-disc space-y-1 text-sm text-slate-700">
                  {claimTrace.map((msg, i) => (
                    <li key={i}>{msg}</li>
                  ))}
                </ul>
              )}
            </FormPanel>
          </>
        )}
      </div>
    </PageLayout>
  )
}
