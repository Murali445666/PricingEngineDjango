import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PageLayout, FormPanel, LoadingSpinner, ErrorState, DataTable, Select, StatusBadge } from '@/shared/ui'
import { fetchRuleById, fetchRuleHistory, updateRuleStatus } from '@/services/ruleService'
import { RuleSimulateConflictPanel } from './RuleSimulateConflictPanel'
import type { Column } from '@/shared/ui'
import type { PricingRuleCondition, RuleHistory, RuleStatus } from '@/types'

const STATUS_OPTIONS: { value: RuleStatus; label: string }[] = [
  { value: 'DRAFT', label: 'Draft' },
  { value: 'ACTIVE', label: 'Active' },
  { value: 'RETIRED', label: 'Retired' },
]

export function RuleDetailPage() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['rule', id],
    queryFn: () => fetchRuleById(id!),
    enabled: !!id,
  })

  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: ['rule-history', id],
    queryFn: () => fetchRuleHistory(id!),
    enabled: !!id,
  })

  const statusMutation = useMutation({
    mutationFn: (newStatus: RuleStatus) => updateRuleStatus(Number(id!), newStatus),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule', id] })
      queryClient.invalidateQueries({ queryKey: ['rule-history', id] })
    },
  })

  const formatDateTime = (iso: string) => {
    if (!iso) return '—'
    try {
      const d = new Date(iso)
      return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
    } catch {
      return iso
    }
  }

  const historyColumns: Column<RuleHistory>[] = [
    {
      key: 'change_date',
      header: 'Date',
      sortable: true,
      render: (row) => formatDateTime(row.change_date),
    },
    {
      key: 'previous_status',
      header: 'Previous Status',
      sortable: true,
      render: (row) => row.previous_status || '—',
    },
    { key: 'new_status', header: 'New Status', sortable: true },
    { key: 'change_reason', header: 'Reason', sortable: false },
  ]

  const conditionColumns: Column<PricingRuleCondition>[] = [
    { key: 'condition_id', header: 'ID', sortable: true },
    { key: 'attribute_name', header: 'Attribute', sortable: true },
    { key: 'operator', header: 'Operator', sortable: true },
    { key: 'attribute_value', header: 'Value', sortable: true },
  ]

  const is404 = error && (error as { response?: { status?: number } })?.response?.status === 404

  return (
    <PageLayout
      title={data ? data.rule_name : `Rule ${id ?? ''}`}
      description="Rule details, conditions, and parameters."
      metadata={
        <span>
          Rule ID: {id}
          {data?.contract_id != null && (
            <>
              {' · '}
              <Link to={`/contracts/${data.contract_id}`} className="text-primary-600 hover:underline">
                Back to contract
              </Link>
            </>
          )}
        </span>
      }
    >
      {isLoading && (
        <div className="flex justify-center py-12">
          <LoadingSpinner />
        </div>
      )}
      {is404 && (
        <ErrorState
          title="Rule not found"
          message={`No rule with ID ${id} was found.`}
          onRetry={() => refetch()}
        />
      )}
      {error && !is404 && (
        <ErrorState
          title="Failed to load rule"
          message={(error as Error).message}
          onRetry={() => refetch()}
        />
      )}
      {data && (
        <>
          <FormPanel title="Rule detail">
            <dl className="grid gap-2 text-sm">
              <div><dt className="font-medium text-slate-500">Rule name</dt><dd>{data.rule_name}</dd></div>
              <div><dt className="font-medium text-slate-500">Methodology</dt><dd>{data.methodology_code}</dd></div>
              <div><dt className="font-medium text-slate-500">Type</dt><dd>{data.rule_type}</dd></div>
              <div className="flex flex-wrap items-center gap-2">
                <dt className="font-medium text-slate-500">Status</dt>
                <dd className="flex items-center gap-2">
                  <StatusBadge status={data.status} />
                  <Select
                    options={STATUS_OPTIONS}
                    value={data.status}
                    onChange={(e) => statusMutation.mutate(e.target.value as RuleStatus)}
                    disabled={statusMutation.isPending}
                    className="w-32"
                  />
                  {statusMutation.isPending && <span className="text-xs text-slate-500">Updating…</span>}
                  {statusMutation.isError && (
                    <span className="text-xs text-red-600">{(statusMutation.error as Error).message}</span>
                  )}
                </dd>
              </div>
              {data.specificity_score != null && (
                <div><dt className="font-medium text-slate-500">Specificity score</dt><dd>{data.specificity_score}</dd></div>
              )}
              {data.multiplier != null && (
                <div><dt className="font-medium text-slate-500">Multiplier</dt><dd>{data.multiplier}</dd></div>
              )}
              {data.flat_rate != null && (
                <div><dt className="font-medium text-slate-500">Flat rate</dt><dd>{data.flat_rate}</dd></div>
              )}
              {data.base_fee_schedule_id != null && (
                <div><dt className="font-medium text-slate-500">Base fee schedule ID</dt><dd>{data.base_fee_schedule_id}</dd></div>
              )}
            </dl>
          </FormPanel>
          {data.conditions && data.conditions.length > 0 && (
            <FormPanel title="Conditions" className="mt-4">
              <DataTable
                columns={conditionColumns}
                data={data.conditions}
                keyExtractor={(row) => row.condition_id}
                emptyMessage="No conditions."
              />
            </FormPanel>
          )}
          <div className="mt-4">
            <RuleSimulateConflictPanel
              contractId={data.contract_id}
              useDraftLineSimulation={data.status === 'DRAFT'}
              buildDraftRule={() => ({
                rule_id: data.rule_id,
                rule_name: data.rule_name,
                rule_type: data.rule_type,
                methodology_code: data.methodology_code,
                multiplier: data.multiplier,
                flat_rate: data.flat_rate,
                base_fee_schedule_id: data.base_fee_schedule_id ?? undefined,
                conditions: (data.conditions ?? []).map((c) => ({
                  attribute_name: c.attribute_name,
                  attribute_value: c.attribute_value,
                })),
              })}
              conditionsForConflicts={
                (data.conditions ?? []).map((c) => ({
                  attribute_name: c.attribute_name,
                  operator: c.operator,
                  attribute_value: c.attribute_value,
                }))
              }
              excludeRuleId={data.rule_id}
            />
          </div>
          <FormPanel title="Audit History" className="mt-4">
            {historyLoading && (
              <div className="flex justify-center py-4">
                <LoadingSpinner />
              </div>
            )}
            {!historyLoading && history && (
              <DataTable
                columns={historyColumns}
                data={history}
                keyExtractor={(row) => row.id}
                emptyMessage="No audit history for this rule."
              />
            )}
          </FormPanel>
        </>
      )}
    </PageLayout>
  )
}
