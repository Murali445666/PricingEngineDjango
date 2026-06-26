import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  PageLayout,
  FormPanel,
  Input,
  Button,
  DataTable,
  LoadingSpinner,
  ErrorState,
  StatusBadge,
  Modal,
  ModalFooter,
  NetworkStatusBadge,
} from '@/shared/ui'
import type { Column } from '@/shared/ui'
import { getProviderNetworkStatus, listProviders } from '@/services/providerService'
import type { ProviderListParams, ProviderSummary } from '@/types/provider'

const PAGE_SIZE = 25

export function ProvidersPage() {
  const [npi, setNpi] = useState('')
  const [name, setName] = useState('')
  const [specialty, setSpecialty] = useState('')
  const [status, setStatus] = useState('')
  const [applied, setApplied] = useState<ProviderListParams>({})
  const [page, setPage] = useState(1)

  const [networkModalOpen, setNetworkModalOpen] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState<ProviderSummary | null>(null)
  const [networkId, setNetworkId] = useState('1')
  const [serviceDate, setServiceDate] = useState('2025-06-15')

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['providers', applied, page],
    queryFn: () =>
      listProviders({
        ...applied,
        page,
        page_size: PAGE_SIZE,
      }),
  })

  const networkMutation = useMutation({
    mutationFn: () => {
      if (!selectedProvider) throw new Error('No provider selected')
      const nid = networkId.trim() ? Number(networkId) : undefined
      return getProviderNetworkStatus(selectedProvider.id, {
        network_id: nid,
        service_date: serviceDate || undefined,
      })
    },
  })

  const applyFilters = () => {
    setApplied({
      npi: npi.trim() || undefined,
      name: name.trim() || undefined,
      specialty: specialty.trim() || undefined,
      status: status.trim() || undefined,
    })
    setPage(1)
  }

  const clearFilters = () => {
    setNpi('')
    setName('')
    setSpecialty('')
    setStatus('')
    setApplied({})
    setPage(1)
  }

  const openNetworkCheck = (provider: ProviderSummary) => {
    setSelectedProvider(provider)
    setNetworkModalOpen(true)
    networkMutation.reset()
  }

  const closeNetworkModal = () => {
    setNetworkModalOpen(false)
    setSelectedProvider(null)
    networkMutation.reset()
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.count / data.page_size)) : 1
  const rangeStart = data && data.count > 0 ? (data.page - 1) * data.page_size + 1 : 0
  const rangeEnd = data ? Math.min(data.page * data.page_size, data.count) : 0

  const columns: Column<ProviderSummary>[] = [
    { key: 'npi', header: 'NPI', sortable: false },
    {
      key: 'first_name',
      header: 'Name',
      sortable: false,
      render: (row) => `${row.first_name} ${row.last_name}`.trim(),
    },
    { key: 'credential', header: 'Credential', sortable: false, render: (r) => r.credential ?? '—' },
    {
      key: 'primary_specialty',
      header: 'Specialty',
      sortable: false,
      render: (r) => r.primary_specialty ?? '—',
    },
    {
      key: 'status',
      header: 'Status',
      sortable: false,
      render: (r) => <StatusBadge status={r.status} />,
    },
    {
      key: 'id',
      header: 'Network',
      sortable: false,
      render: (row) => (
        <Button
          type="button"
          variant="secondary"
          className="!px-2 !py-1 !text-xs"
          onClick={() => openNetworkCheck(row)}
        >
          Check network
        </Button>
      ),
    },
  ]

  return (
    <PageLayout
      title="Providers"
      description="Provider directory with in/out-of-network checks against a products.Network."
      metadata={
        <span>
          Demo: filter NPI <code className="font-mono text-xs">RENDER-NPI-S4</code>, then check network
          with a seeded <code className="font-mono text-xs">network_id</code> and date 2025-06-15.
        </span>
      }
    >
      <FormPanel title="Filters" description="GET /api/providers/ — server-side pagination.">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Input label="NPI" value={npi} onChange={(e) => setNpi(e.target.value)} placeholder="RENDER-NPI-S4" />
          <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Last or first" />
          <Input label="Specialty code" value={specialty} onChange={(e) => setSpecialty(e.target.value)} placeholder="FAM" />
          <Input label="Status" value={status} onChange={(e) => setStatus(e.target.value)} placeholder="ACTIVE" />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button type="button" onClick={applyFilters}>
            Apply filters
          </Button>
          <Button type="button" variant="secondary" onClick={clearFilters}>
            Clear
          </Button>
        </div>
      </FormPanel>

      <div className="mt-6">
        {isLoading && (
          <div className="flex justify-center py-12">
            <LoadingSpinner />
          </div>
        )}
        {error && (
          <ErrorState
            title="Failed to load providers"
            message={(error as Error).message}
            onRetry={() => void refetch()}
          />
        )}
        {data && !error && (
          <>
            <div className="mb-2 flex items-center justify-between text-sm text-slate-500">
              <span>
                {data.count === 0 ? 'No providers' : `${rangeStart}–${rangeEnd} of ${data.count}`}
                {isFetching && !isLoading ? ' (refreshing…)' : ''}
              </span>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  className="!px-2 !py-1 !text-xs"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Previous
                </Button>
                <span className="self-center text-xs">
                  Page {data.page} / {totalPages}
                </span>
                <Button
                  type="button"
                  variant="secondary"
                  className="!px-2 !py-1 !text-xs"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
            <DataTable
              columns={columns}
              data={data.results}
              keyExtractor={(row) => row.id}
              emptyMessage="No providers match the current filters."
              pageSize={PAGE_SIZE}
            />
          </>
        )}
      </div>

      <Modal
        isOpen={networkModalOpen}
        onClose={closeNetworkModal}
        title="Network status check"
        panelClassName="max-w-md"
        footer={
          <ModalFooter>
            <Button type="button" variant="secondary" onClick={closeNetworkModal}>
              Close
            </Button>
            <Button
              type="button"
              onClick={() => networkMutation.mutate()}
              disabled={networkMutation.isPending}
            >
              {networkMutation.isPending ? 'Checking…' : 'Check status'}
            </Button>
          </ModalFooter>
        }
      >
        {selectedProvider && (
          <div className="space-y-4 text-sm text-slate-700">
            <p>
              Provider <span className="font-mono text-xs">{selectedProvider.npi}</span> —{' '}
              {selectedProvider.first_name} {selectedProvider.last_name}
            </p>
            <Input
              label="Network ID (products.Network)"
              type="number"
              min={1}
              value={networkId}
              onChange={(e) => setNetworkId(e.target.value)}
              placeholder="1"
            />
            <Input
              label="Service date"
              type="date"
              value={serviceDate}
              onChange={(e) => setServiceDate(e.target.value)}
            />
            {networkMutation.isError && (
              <p className="text-sm text-red-600" role="alert">
                {networkMutation.error.message}
              </p>
            )}
            {networkMutation.isSuccess && (
              <div className="rounded border border-slate-200 bg-slate-50 p-3">
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2">
                  <dt className="text-slate-500">network_status</dt>
                  <dd>
                    <NetworkStatusBadge
                      status={networkMutation.data.network_status}
                      tier={networkMutation.data.network_tier}
                    />
                  </dd>
                  <dt className="text-slate-500">as_of_date</dt>
                  <dd>{String(networkMutation.data.as_of_date)}</dd>
                </dl>
              </div>
            )}
          </div>
        )}
      </Modal>
    </PageLayout>
  )
}
