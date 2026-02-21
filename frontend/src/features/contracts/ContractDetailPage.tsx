import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { PageLayout, DataTable, LoadingSpinner, ErrorState, StatusBadge } from '@/shared/ui'
import { fetchContractById, fetchContractRules } from '@/services/contractService'
import type { PricingRule } from '@/types'
import type { Column } from '@/shared/ui'

export function ContractDetailPage() {
  const { id } = useParams<{ id: string }>()
  const contractId = id != null ? Number(id) : NaN

  const {
    data: contract,
    isLoading: contractLoading,
    error: contractError,
    refetch: refetchContract,
  } = useQuery({
    queryKey: ['contract', id],
    queryFn: () => fetchContractById(contractId),
    enabled: Number.isInteger(contractId),
  })

  const {
    data: rules,
    isLoading: rulesLoading,
    error: rulesError,
    refetch: refetchRules,
  } = useQuery({
    queryKey: ['contract-rules', id],
    queryFn: () => fetchContractRules(contractId),
    enabled: Number.isInteger(contractId),
  })

  const isLoading = contractLoading || rulesLoading
  const error = contractError ?? rulesError
  const refetch = () => {
    refetchContract()
    refetchRules()
  }

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
      title={contract ? `Contract: ${contract.contract_name}` : 'Contract'}
      description="Contract details and associated rules."
      metadata={
        contract ? (
          <span>
            ID: {contract.contract_id} · Status: {contract.status}
            {contract.legacy_contract_number && ` · Legacy: ${contract.legacy_contract_number}`}
          </span>
        ) : null
      }
    >
      {isLoading && (
        <div className="flex justify-center py-12">
          <LoadingSpinner />
        </div>
      )}
      {error && (
        <ErrorState
          title="Failed to load contract"
          message={(error as Error).message}
          onRetry={() => refetch()}
        />
      )}
      {contract && rules && (
        <>
          <div className="mb-4">
            <Link
              to={`/contracts/${contract.contract_id}/rules/new`}
              className="inline-flex items-center rounded border border-primary-600 bg-white px-3 py-2 text-sm font-medium text-primary-600 hover:bg-primary-50"
            >
              Create New Rule
            </Link>
          </div>
          <DataTable
            columns={columns}
            data={rules}
            keyExtractor={(row) => row.rule_id}
            emptyMessage="No rules for this contract."
          />
        </>
      )}
    </PageLayout>
  )
}
