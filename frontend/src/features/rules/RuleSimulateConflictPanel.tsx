/**
 * Step 12c: single-line simulate + conflict check on rule create / detail.
 * TODO: add Vitest with mocked priceLine / simulateLine / checkRuleConflicts when test harness exists.
 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { FormPanel, Button, Input, Select } from '@/shared/ui'
import { priceLine, simulateLine } from '@/services/pricingService'
import { checkRuleConflicts } from '@/services/ruleService'
import type { PriceLineResult, RuleConditionRow, RuleConflictItem } from '@/types'

const CLAIM_TYPE_OPTIONS = [
  { value: '', label: '— Default —' },
  { value: 'OUTPATIENT', label: 'OUTPATIENT' },
  { value: 'INPATIENT', label: 'INPATIENT' },
  { value: 'PROFESSIONAL', label: 'PROFESSIONAL' },
]

export interface RuleSimulateConflictPanelProps {
  contractId: number
  /** When true, POST /api/simulate-line/ with draft_rule (unsaved rule or DRAFT in DB). Else POST /api/price-line/. */
  useDraftLineSimulation: boolean
  buildDraftRule: () => Record<string, unknown>
  conditionsForConflicts: RuleConditionRow[]
  /** Omit self when checking conflicts from rule detail */
  excludeRuleId?: number
}

export function RuleSimulateConflictPanel({
  contractId,
  useDraftLineSimulation,
  buildDraftRule,
  conditionsForConflicts,
  excludeRuleId,
}: RuleSimulateConflictPanelProps) {
  const [procedureCode, setProcedureCode] = useState('')
  const [billedAmount, setBilledAmount] = useState('200.00')
  const [units, setUnits] = useState('1')
  const [modifiersStr, setModifiersStr] = useState('')
  const [serviceDate, setServiceDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [claimType, setClaimType] = useState('')
  const [conflicts, setConflicts] = useState<RuleConflictItem[]>([])

  const simulateMutation = useMutation({
    mutationFn: async (): Promise<PriceLineResult> => {
      const proc = procedureCode.trim()
      const amt = billedAmount.trim()
      const modifiers = modifiersStr.trim() ? modifiersStr.split(/[\s,]+/).filter(Boolean) : []
      const u = units.trim() ? parseInt(units, 10) || 1 : 1
      const line = {
        procedure_code: proc,
        billed_amount: amt,
        units: u,
        modifiers,
        ...(serviceDate.trim() ? { service_date: serviceDate.trim() } : {}),
        ...(claimType.trim() ? { claim_type: claimType.trim() } : {}),
        ...(serviceDate.trim() ? { pricing_date: serviceDate.trim() } : {}),
      }
      if (useDraftLineSimulation) {
        return simulateLine({
          contract_id: contractId,
          line,
          draft_rule: { ...buildDraftRule(), contract_id: contractId },
        })
      }
      return priceLine({
        contract_id: contractId,
        ...line,
      })
    },
  })

  const conflictsMutation = useMutation({
    mutationFn: () =>
      checkRuleConflicts(contractId, conditionsForConflicts, excludeRuleId),
    onSuccess: (list) => setConflicts(list),
  })

  const simulateReady =
    procedureCode.trim() !== '' &&
    billedAmount.trim() !== '' &&
    Number.isInteger(contractId) &&
    contractId > 0

  const conflictsReady =
    conditionsForConflicts.some((c) => c.attribute_name.trim() && c.attribute_value.trim() !== '') &&
    contractId > 0

  const result = simulateMutation.data ?? null

  return (
    <FormPanel
      title="Simulate line"
      description={
        useDraftLineSimulation
          ? 'POST /api/simulate-line/ with your draft rule (preview before save or for DRAFT rules).'
          : 'POST /api/price-line/ against live ACTIVE rules for this contract.'
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          label="Procedure code"
          placeholder="e.g. 99213"
          value={procedureCode}
          onChange={(e) => setProcedureCode(e.target.value)}
        />
        <Input
          label="Billed amount"
          type="text"
          inputMode="decimal"
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
        <Input
          label="Service date"
          type="date"
          value={serviceDate}
          onChange={(e) => setServiceDate(e.target.value)}
        />
        <Select
          label="Claim type"
          options={CLAIM_TYPE_OPTIONS}
          value={claimType}
          onChange={(e) => setClaimType(e.target.value)}
        />
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          onClick={() => simulateMutation.mutate()}
          disabled={!simulateReady || simulateMutation.isPending}
        >
          {simulateMutation.isPending ? 'Running…' : 'Simulate line'}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => {
            setConflicts([])
            conflictsMutation.mutate()
          }}
          disabled={!conflictsReady || conflictsMutation.isPending}
        >
          {conflictsMutation.isPending ? 'Checking…' : 'Check conflicts'}
        </Button>
      </div>
      {simulateMutation.isError && (
        <div
          className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
          role="alert"
        >
          {(simulateMutation.error as Error).message}
        </div>
      )}
      {conflictsMutation.isError && (
        <div
          className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
          role="alert"
        >
          {(conflictsMutation.error as Error).message}
        </div>
      )}
      {conflicts.length > 0 && (
        <div
          className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
          role="status"
        >
          <p className="mb-1 font-medium">Overlapping conditions on this contract</p>
          <ul className="list-inside list-disc space-y-0.5">
            {conflicts.map((c, i) => (
              <li key={i}>{c.message}</li>
            ))}
          </ul>
        </div>
      )}
      {conflictsMutation.isSuccess && conflicts.length === 0 && conflictsReady && (
        <p className="mt-3 text-sm text-slate-600">No conflicts found for the current conditions.</p>
      )}
      {result && (
        <div className="mt-4 space-y-2 border-t border-slate-200 pt-4 text-sm">
          <p>
            <span className="font-medium text-slate-700">Status:</span>{' '}
            <span className={result.status === 'SUCCESS' ? 'text-green-600' : 'text-amber-600'}>
              {result.status}
            </span>
          </p>
          <p>
            <span className="font-medium text-slate-700">Allowed amount:</span>{' '}
            {typeof result.allowed_amount === 'number'
              ? result.allowed_amount.toFixed(2)
              : String(result.allowed_amount)}
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
          {result.trace_logs && result.trace_logs.length > 0 && (
            <div className="mt-2">
              <h4 className="mb-1 text-sm font-semibold text-slate-800">Trace</h4>
              <ul className="list-inside list-disc space-y-0.5 text-slate-600">
                {result.trace_logs.map((log, i) => (
                  <li key={i}>{log}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </FormPanel>
  )
}
