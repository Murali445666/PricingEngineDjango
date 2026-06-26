import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  PageLayout,
  FormPanel,
  Input,
  Button,
  DataTable,
  LoadingSpinner,
  ErrorState,
} from '@/shared/ui'
import type { Column } from '@/shared/ui'
import { listProducts } from '@/services/productService'
import type { ProductListParams, ProductSummary } from '@/types/product'

const PAGE_SIZE = 25

export function ProductsPage() {
  const [payerId, setPayerId] = useState('')
  const [lob, setLob] = useState('')
  const [effectiveDate, setEffectiveDate] = useState('')
  const [applied, setApplied] = useState<ProductListParams>({})
  const [page, setPage] = useState(1)

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['products', applied, page],
    queryFn: () =>
      listProducts({
        ...applied,
        page,
        page_size: PAGE_SIZE,
      }),
  })

  const applyFilters = () => {
    setApplied({
      payer_id: payerId.trim() || undefined,
      lob: lob.trim() || undefined,
      effective_date: effectiveDate.trim() || undefined,
    })
    setPage(1)
  }

  const clearFilters = () => {
    setPayerId('')
    setLob('')
    setEffectiveDate('')
    setApplied({})
    setPage(1)
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.count / data.page_size)) : 1
  const rangeStart = data && data.count > 0 ? (data.page - 1) * data.page_size + 1 : 0
  const rangeEnd = data ? Math.min(data.page * data.page_size, data.count) : 0

  const columns: Column<ProductSummary>[] = [
    { key: 'id', header: 'ID', sortable: false },
    { key: 'name', header: 'Name', sortable: false },
    {
      key: 'product_code',
      header: 'Product code',
      sortable: false,
      render: (r) => r.product_code ?? '—',
    },
    { key: 'payer_id', header: 'Payer ID', sortable: false },
    { key: 'payer_name', header: 'Payer name', sortable: false },
    {
      key: 'lob',
      header: 'LOB',
      sortable: false,
      render: (r) => r.lob ?? '—',
    },
    { key: 'effective_date', header: 'Effective', sortable: false },
    {
      key: 'termination_date',
      header: 'Termination',
      sortable: false,
      render: (r) => r.termination_date ?? '—',
    },
  ]

  return (
    <PageLayout
      title="Products"
      description="Payer product catalog with LOB and effective-date filters."
      metadata={
        <span>
          Demo: filter LOB <code className="font-mono text-xs">COMMERCIAL</code> or payer{' '}
          <code className="font-mono text-xs">PAYER-S4-01</code>.
        </span>
      }
    >
      <FormPanel title="Filters" description="GET /api/products/ — server-side pagination.">
        <div className="grid gap-4 sm:grid-cols-3">
          <Input
            label="Payer ID"
            value={payerId}
            onChange={(e) => setPayerId(e.target.value)}
            placeholder="PAYER-S4-01"
          />
          <Input label="LOB" value={lob} onChange={(e) => setLob(e.target.value)} placeholder="COMMERCIAL" />
          <Input
            label="Effective date"
            type="date"
            value={effectiveDate}
            onChange={(e) => setEffectiveDate(e.target.value)}
          />
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
            title="Failed to load products"
            message={(error as Error).message}
            onRetry={() => void refetch()}
          />
        )}
        {data && !error && (
          <>
            <div className="mb-2 flex items-center justify-between text-sm text-slate-500">
              <span>
                {data.count === 0 ? 'No products' : `${rangeStart}–${rangeEnd} of ${data.count}`}
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
              emptyMessage="No products match the current filters."
              pageSize={PAGE_SIZE}
            />
          </>
        )}
      </div>
    </PageLayout>
  )
}
