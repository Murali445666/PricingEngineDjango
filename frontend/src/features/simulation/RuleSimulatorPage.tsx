import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { PageLayout, FormPanel, Button, Input, Select, LoadingSpinner, ErrorState, StatusBadge } from '@/shared/ui'
import { fetchContracts, fetchContractById, fetchContractRules } from '@/services/contractService'
import { simulateLine } from '@/services/pricingService'
import type { Contract } from '@/types'
import type { PriceLineResult } from '@/types'
import type { PricingRule } from '@/types'

export function RuleSimulatorPage() {
  const [contractId, setContractId] = useState<string>('')
  const [procedureCode, setProcedureCode] = useState('')
  const [billedAmount, setBilledAmount] = useState('')
  const [units, setUnits] = useState('1')
  const [modifiersStr, setModifiersStr] = useState('')
  const [draftRuleId, setDraftRuleId] = useState<string>('')
  const [result, setResult] = useState<PriceLineResult | null>(null)
  const [simulateError, setSimulateError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  const { data: contracts = [], isLoading: contractsLoading, error: contractsError, refetch: refetchContracts } = useQuery({
    queryKey: ['contracts'],
    queryFn: fetchContracts,
  })

  const cId = contractId === '' ? null : Number(contractId)
  const { data: contractDetail } = useQuery({
    queryKey: ['contract', contractId],
    queryFn: () => fetchContractById(cId!),
    enabled: cId != null && !isNaN(cId),
  })
  const { data: rules = [], isLoading: rulesLoading } = useQuery({
    queryKey: ['contract-rules', contractId],
    queryFn: () => fetchContractRules(cId!),
    enabled: cId != null && !isNaN(cId),
  })

  const draftRules = rules.filter((r: PricingRule) => r.status === 'DRAFT')
  const contractOptions = [
    { value: '', label: 'Select contract…' },
    ...contracts.map((c: Contract) => ({ value: String(c.contract_id), label: `${c.contract_name} (${c.contract_id})` })),
  ]
  const draftOptions = [
    { value: '', label: 'No draft rule' },
    ...draftRules.map((r: PricingRule) => ({ value: String(r.rule_id), label: `${r.rule_name || 'Unnamed'} – ${r.methodology_code}` })),
  ]

  async function handleRun() {
    if (!contractId) {
      setSimulateError('Select a contract.')
      return
    }
    const proc = procedureCode.trim()
    const amt = billedAmount.trim()
    if (!proc || !amt) {
      setSimulateError('Procedure code and billed amount are required.')
      return
    }
    setSimulateError(null)
    setResult(null)
    setRunning(true)
    try {
      const modifiers = modifiersStr.trim() ? modifiersStr.split(/[\s,]+/).filter(Boolean) : []
      let draft_rule: Record<string, unknown> | undefined
      if (draftRuleId) {
        const rule = draftRules.find((r: PricingRule) => r.rule_id === Number(draftRuleId))
        if (rule) {
          draft_rule = {
            rule_id: rule.rule_id,
            rule_name: rule.rule_name,
            rule_type: rule.rule_type,
            methodology_code: rule.methodology_code,
            multiplier: rule.multiplier,
            flat_rate: rule.flat_rate,
            base_fee_schedule_id: rule.base_fee_schedule_id,
            conditions: (rule.conditions || []).map((c) => ({
              attribute_name: c.attribute_name,
              operator: c.operator,
              attribute_value: c.attribute_value,
            })),
          }
        }
      }
      const res = await simulateLine({
        contract_id: contractId,
        line: {
          procedure_code: proc,
          billed_amount: amt,
          units: units.trim() ? parseInt(units, 10) || 1 : 1,
          modifiers,
        },
        draft_rule,
      })
      setResult(res)
    } catch (e) {
      setSimulateError((e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <PageLayout
      title="Rule Simulator"
      description="Validate pricing outcomes before activating rules."
      metadata={<span>Simulation mode; results are not applied to production.</span>}
    >
      <div className="space-y-6">
        {contractsLoading && (
          <div className="flex justify-center py-8">
            <LoadingSpinner />
          </div>
        )}
        {contractsError && (
          <ErrorState
            title="Failed to load contracts"
            message={(contractsError as Error).message}
            onRetry={() => refetchContracts()}
          />
        )}
        {!contractsLoading && !contractsError && (
          <>
            {contractId && (
              <FormPanel title="Contract summary" description="Rules in this contract (links to detail).">
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-4 text-sm">
                    <span><span className="font-medium text-slate-700">Name:</span> {contractDetail?.contract_name ?? '—'}</span>
                    <span><span className="font-medium text-slate-700">ID:</span> {contractId}</span>
                    {contractDetail && <StatusBadge status={contractDetail.status} />}
                    {contractDetail?.legacy_contract_number && (
                      <span><span className="font-medium text-slate-700">Legacy #:</span> {contractDetail.legacy_contract_number}</span>
                    )}
                    {contractDetail?.effective_start_date && (
                      <span><span className="font-medium text-slate-700">Effective:</span> {contractDetail.effective_start_date}
                        {contractDetail.effective_end_date ? ` – ${contractDetail.effective_end_date}` : ''}</span>
                    )}
                    <Link to={`/contracts/${contractId}`} className="text-primary-600 hover:underline">View contract →</Link>
                  </div>
                  <div>
                    <h4 className="mb-2 text-sm font-semibold text-slate-800">Rules in this contract</h4>
                    {rules.length === 0 && !rulesLoading && <p className="text-sm text-slate-500">No rules.</p>}
                    {rules.length > 0 && (
                      <ul className="space-y-1 text-sm">
                        {rules.map((r: PricingRule) => (
                          <li key={r.rule_id} className="flex items-center gap-2">
                            <Link to={`/rules/${r.rule_id}`} className="text-primary-600 hover:underline">
                              {r.rule_name || 'Unnamed'}
                            </Link>
                            <span className="text-slate-500">{r.methodology_code}</span>
                            <StatusBadge status={r.status} />
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </FormPanel>
            )}
            <FormPanel title="Run single-line simulation" description="Choose a contract and claim line to see allowed amount and which rule matched.">
              <div className="grid gap-4 sm:grid-cols-2">
                <Select
                  label="Contract"
                  options={contractOptions}
                  value={contractId}
                  onChange={(e) => { setContractId(e.target.value); setDraftRuleId(''); setResult(null) }}
                />
                <Select
                  label="Include draft rule (optional)"
                  options={draftOptions}
                  value={draftRuleId}
                  onChange={(e) => setDraftRuleId(e.target.value)}
                  disabled={!contractId || rulesLoading}
                />
                <Input
                  label="Procedure code"
                  placeholder="e.g. 99213"
                  value={procedureCode}
                  onChange={(e) => setProcedureCode(e.target.value)}
                />
                <Input
                  label="Billed amount"
                  type="number"
                  step="0.01"
                  placeholder="0.00"
                  value={billedAmount}
                  onChange={(e) => setBilledAmount(e.target.value)}
                />
                <Input
                  label="Units"
                  type="number"
                  min={1}
                  value={units}
                  onChange={(e) => setUnits(e.target.value)}
                />
                <Input
                  label="Modifiers (comma or space separated)"
                  placeholder="e.g. 26, 50"
                  value={modifiersStr}
                  onChange={(e) => setModifiersStr(e.target.value)}
                />
              </div>
              <div className="mt-4 flex items-center gap-2">
                <Button onClick={handleRun} disabled={running}>
                  {running ? 'Running…' : 'Run'}
                </Button>
                {simulateError && <span className="text-sm text-red-600">{simulateError}</span>}
              </div>
            </FormPanel>

            {result && (
              <FormPanel title="Result" description="Allowed amount and which rule matched.">
                <div className="space-y-2 text-sm">
                  <p>
                    <span className="font-medium text-slate-700">Status:</span>{' '}
                    <span className={result.status === 'SUCCESS' ? 'text-green-600' : 'text-amber-600'}>{result.status}</span>
                  </p>
                  <p>
                    <span className="font-medium text-slate-700">Allowed amount:</span>{' '}
                    {typeof result.allowed_amount === 'number' ? result.allowed_amount.toFixed(2) : String(result.allowed_amount)}
                  </p>
                  <p>
                    <span className="font-medium text-slate-700">Methodology:</span> {result.methodology || '—'}
                  </p>
                  {result.rule_id !== undefined && result.rule_id !== 0 && (
                    <p>
                      <span className="font-medium text-slate-700">Rule ID:</span> {result.rule_id}
                    </p>
                  )}
                  {result.details && (
                    <p>
                      <span className="font-medium text-slate-700">Details:</span> {result.details}
                    </p>
                  )}
                </div>
                {result.trace_logs && result.trace_logs.length > 0 && (
                  <div className="mt-4">
                    <h4 className="mb-2 text-sm font-semibold text-slate-800">Why this amount?</h4>
                    <ul className="list-inside list-disc space-y-0.5 text-sm text-slate-600">
                      {result.trace_logs.map((log, i) => (
                        <li key={i}>{log}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </FormPanel>
            )}
          </>
        )}
      </div>
    </PageLayout>
  )
}
