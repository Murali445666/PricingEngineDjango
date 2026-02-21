import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { PageLayout, DataTable, LoadingSpinner, ErrorState, StatusBadge, Select } from '@/shared/ui'
import { fetchRules } from '@/services/ruleService'
import type { PricingRule, RuleStatus } from '@/types'
import type { Column } from '@/shared/ui'

const STATUS_FILTER_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'DRAFT', label: 'Draft' },
  { value: 'ACTIVE', label: 'Active' },
  { value: 'RETIRED', label: 'Retired' },
]

export function RulesPage() {
  const [statusFilter, setStatusFilter] = useState<RuleStatus | ''>('')
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['rules', statusFilter || null],
    queryFn: () => fetchRules(statusFilter || undefined),
  })

  const columns: Column<PricingRule>[] = [
    { key: 'rule_id', header: 'ID', sortable: true },
    {
      key: 'rule_name',
      header: 'Name',
      sortable: true,
      render: (row) => (
        <Link to={`/rules/${row.rule_id}`} className="text-primary-600 hover:underline">
          {row.rule_name}
        </Link>
      ),
    },
    { key: 'methodology_code', header: 'Methodology', sortable: true },
    { key: 'rule_type', header: 'Type', sortable: true },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <StatusBadge status={row.status} />,
    },
  ]

  return (
    <PageLayout
      title="Rules"
      description="Pricing rules and conditions."
      metadata={<span>Rules are matched by specificity; each rule has conditions and a methodology.</span>}
    >
      <div className="mb-4 flex items-center gap-3">
        <label htmlFor="rule-status-filter" className="text-sm font-medium text-slate-700">
          Filter by status
        </label>
        <Select
          id="rule-status-filter"
          options={STATUS_FILTER_OPTIONS}
          value={statusFilter}
          onChange={(e) => setStatusFilter((e.target.value || '') as RuleStatus | '')}
          className="w-40"
        />
      </div>
      {isLoading && (
        <div className="flex justify-center py-12">
          <LoadingSpinner />
        </div>
      )}
      {error && (
        <ErrorState
          title="Failed to load rules"
          message={(error as Error).message}
          onRetry={() => refetch()}
        />
      )}
      {data && (
        <DataTable
          columns={columns}
          data={data}
          keyExtractor={(row) => row.rule_id}
          emptyMessage="No rules. Feature under development or API not connected."
        />
      )}
    </PageLayout>
  )
}
