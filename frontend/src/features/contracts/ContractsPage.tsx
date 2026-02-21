import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { PageLayout, DataTable, LoadingSpinner, ErrorState, StatusBadge } from '@/shared/ui'
import { fetchContracts } from '@/services/contractService'
import type { Contract } from '@/types'
import type { Column } from '@/shared/ui'

export function ContractsPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['contracts'],
    queryFn: fetchContracts,
  })

  const columns: Column<Contract>[] = [
    { key: 'contract_id', header: 'ID', sortable: true },
    {
      key: 'contract_name',
      header: 'Name',
      sortable: true,
      render: (row) => (
        <Link to={`/contracts/${row.contract_id}`} className="text-primary-600 hover:underline">
          {row.contract_name}
        </Link>
      ),
    },
    { key: 'legacy_contract_number', header: 'Legacy #', sortable: true },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <StatusBadge status={row.status} />,
    },
  ]

  return (
    <PageLayout
      title="Contracts"
      description="View and manage provider–payer contracts."
      metadata={<span>Active contracts are available for pricing requests.</span>}
    >
      {isLoading && (
        <div className="flex justify-center py-12">
          <LoadingSpinner />
        </div>
      )}
      {error && (
        <ErrorState
          title="Failed to load contracts"
          message={(error as Error).message}
          onRetry={() => refetch()}
        />
      )}
      {data && (
        <DataTable
          columns={columns}
          data={data}
          keyExtractor={(row) => row.contract_id}
          emptyMessage="No contracts. Feature under development or API not connected."
        />
      )}
    </PageLayout>
  )
}
