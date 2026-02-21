import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { PageLayout, FormPanel, Button, Input, Select, LoadingSpinner, ErrorState } from '@/shared/ui'
import { createRule, fetchFeeSchedules } from '@/services/ruleService'
import { ConditionBuilder } from './ConditionBuilder'
import { ParameterEditor } from './ParameterEditor'
import type { RuleConditionRow, RuleCreatePayload } from '@/types'

const RULE_TYPE_OPTIONS = [
  { value: 'BASE', label: 'Base' },
  { value: 'ADJUSTMENT', label: 'Adjustment' },
]

const METHODOLOGY_OPTIONS = [
  { value: 'RBRVS', label: 'RBRVS' },
  { value: 'FLAT_RATE', label: 'Flat rate' },
  { value: 'PERCENT_BILLED', label: 'Percent of billed' },
  { value: 'DRG', label: 'DRG' },
  { value: 'PER_DIEM', label: 'Per diem' },
  { value: 'ANESTHESIA', label: 'Anesthesia' },
]

const defaultConditions: RuleConditionRow[] = [
  { attribute_name: 'procedure_code', operator: 'EQ', attribute_value: '' },
]

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

export function RuleCreatePage() {
  const { contractId } = useParams<{ contractId: string }>()
  const navigate = useNavigate()
  const cid = contractId != null ? Number(contractId) : NaN

  const [ruleName, setRuleName] = useState('')
  const [ruleType, setRuleType] = useState('BASE')
  const [methodologyCode, setMethodologyCode] = useState('RBRVS')
  const [conditions, setConditions] = useState<RuleConditionRow[]>(defaultConditions)
  const [multiplier, setMultiplier] = useState('1')
  const [flatRate, setFlatRate] = useState('')
  const [baseFeeScheduleId, setBaseFeeScheduleId] = useState('')
  const [effectiveStartDate, setEffectiveStartDate] = useState(todayISO)
  const [effectiveEndDate, setEffectiveEndDate] = useState('')

  const { data: feeSchedules = [], isLoading: feeSchedulesLoading } = useQuery({
    queryKey: ['fee-schedules'],
    queryFn: fetchFeeSchedules,
  })

  const createMutation = useMutation({
    mutationFn: (payload: RuleCreatePayload) => createRule(cid, payload),
    onSuccess: () => {
      navigate(`/contracts/${cid}`, { replace: true })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const payload: RuleCreatePayload = {
      rule_name: ruleName.trim() || undefined,
      rule_type: ruleType,
      methodology_code: methodologyCode,
      effective_start_date: effectiveStartDate,
      effective_end_date: effectiveEndDate.trim() || undefined,
      conditions: conditions.filter((c) => c.attribute_value.trim() !== ''),
    }
    if (methodologyCode === 'RBRVS') {
      const m = parseFloat(multiplier)
      if (!Number.isNaN(m)) payload.multiplier = m
      if (baseFeeScheduleId) payload.base_fee_schedule_id = parseInt(baseFeeScheduleId, 10)
    }
    if (methodologyCode === 'FLAT_RATE') {
      const f = parseFloat(flatRate)
      if (!Number.isNaN(f)) payload.flat_rate = f
    }
    createMutation.mutate(payload)
  }

  if (!Number.isInteger(cid)) {
    return (
      <PageLayout title="Create rule" description="Invalid contract.">
        <ErrorState
          title="Invalid contract"
          message="Contract ID is missing or invalid."
          onRetry={() => navigate('/contracts')}
        />
      </PageLayout>
    )
  }

  return (
    <PageLayout
      title="Create new rule"
      description="Add a pricing rule to this contract. Save as draft to activate later."
      metadata={<span>Contract ID: {cid}</span>}
    >
      <form onSubmit={handleSubmit} className="space-y-6">
        <FormPanel title="Basics">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Rule name"
              value={ruleName}
              onChange={(e) => setRuleName(e.target.value)}
              placeholder="e.g. Office Visit RBRVS"
            />
            <Select
              label="Rule type"
              options={RULE_TYPE_OPTIONS}
              value={ruleType}
              onChange={(e) => setRuleType(e.target.value)}
            />
            <Select
              label="Methodology"
              options={METHODOLOGY_OPTIONS}
              value={methodologyCode}
              onChange={(e) => setMethodologyCode(e.target.value)}
              className="sm:col-span-2"
            />
            <Input
              label="Effective start date (required)"
              type="date"
              value={effectiveStartDate}
              onChange={(e) => setEffectiveStartDate(e.target.value)}
              required
            />
            <Input
              label="Effective end date (optional)"
              type="date"
              value={effectiveEndDate}
              onChange={(e) => setEffectiveEndDate(e.target.value)}
            />
          </div>
        </FormPanel>

        <FormPanel title="Parameters">
          <ParameterEditor
            methodologyCode={methodologyCode}
            multiplier={multiplier}
            onMultiplierChange={setMultiplier}
            flatRate={flatRate}
            onFlatRateChange={setFlatRate}
            baseFeeScheduleId={baseFeeScheduleId}
            onBaseFeeScheduleIdChange={setBaseFeeScheduleId}
            feeSchedules={feeSchedules}
            feeSchedulesLoading={feeSchedulesLoading}
          />
        </FormPanel>

        <FormPanel title="Conditions">
          <ConditionBuilder value={conditions} onChange={setConditions} />
        </FormPanel>

        {createMutation.isError && (
          <ErrorState
            title="Failed to create rule"
            message={(createMutation.error as Error).message}
            onRetry={() => createMutation.reset()}
          />
        )}

        <div className="flex gap-2">
          <Button
            type="submit"
            disabled={
              createMutation.isPending ||
              !effectiveStartDate.trim() ||
              conditions.every((c) => !c.attribute_value.trim())
            }
          >
            {createMutation.isPending ? 'Saving…' : 'Save as Draft'}
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => navigate(`/contracts/${cid}`)}
          >
            Cancel
          </Button>
        </div>
      </form>
    </PageLayout>
  )
}
