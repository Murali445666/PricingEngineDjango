import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  PageLayout,
  DataTable,
  LoadingSpinner,
  ErrorState,
  StatusBadge,
  Modal,
  ModalFooter,
  Button,
} from '@/shared/ui'
import { bulkValidateContracts, fetchContracts } from '@/services/contractService'
import type { BulkValidationRow, Contract } from '@/types'
import type { Column } from '@/shared/ui'

export function ContractsPage() {
  const queryClient = useQueryClient()
  const [bulkOpen, setBulkOpen] = useState(false)
  const [selected, setSelected] = useState<Record<number, boolean>>({})
  const [allListed, setAllListed] = useState(false)
  const [persistResults, setPersistResults] = useState(false)
  const [bulkResults, setBulkResults] = useState<BulkValidationRow[] | null>(null)
  const [bulkError, setBulkError] = useState<string | null>(null)

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['contracts'],
    queryFn: fetchContracts,
  })

  const nameById = (id: number) => data?.find((c) => c.contract_id === id)?.contract_name ?? '—'

  const bulkMutation = useMutation({
    mutationFn: (ids: number[]) => bulkValidateContracts(ids, { save: persistResults }),
    onSuccess: (rows) => {
      setBulkResults(rows)
      setBulkError(null)
      void queryClient.invalidateQueries({ queryKey: ['contracts'] })
    },
    onError: (err: Error) => {
      setBulkError(err.message)
      window.alert(`Bulk validation failed: ${err.message}`)
    },
  })

  const openBulkModal = () => {
    setBulkOpen(true)
    setBulkResults(null)
    setBulkError(null)
    setSelected({})
    setAllListed(false)
    setPersistResults(false)
  }

  const closeBulkModal = () => {
    setBulkOpen(false)
    bulkMutation.reset()
  }

  const toggleRow = (id: number) => {
    setSelected((s) => ({ ...s, [id]: !s[id] }))
  }

  const selectAllInList = () => {
    if (!data?.length) return
    const next: Record<number, boolean> = {}
    for (const c of data) next[c.contract_id] = true
    setSelected(next)
    setAllListed(false)
  }

  const clearSelection = () => {
    setSelected({})
    setAllListed(false)
  }

  const runBulk = () => {
    if (!data?.length) return
    const ids = allListed
      ? data.map((c) => c.contract_id)
      : data.filter((c) => selected[c.contract_id]).map((c) => c.contract_id)
    if (ids.length === 0) {
      window.alert('Select at least one contract, or enable “Validate all listed contracts”.')
      return
    }
    bulkMutation.mutate(ids)
  }

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
    {
      key: 'open_error_count',
      header: 'Errors',
      render: (row) =>
        (row.open_error_count ?? 0) > 0 ? (
          <span className="inline-flex items-center rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700">
            {row.open_error_count}
          </span>
        ) : (
          <span className="text-slate-300 text-xs">—</span>
        ),
    },
    {
      key: 'open_warning_count',
      header: 'Warnings',
      render: (row) =>
        (row.open_warning_count ?? 0) > 0 ? (
          <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">
            {row.open_warning_count}
          </span>
        ) : (
          <span className="text-slate-300 text-xs">—</span>
        ),
    },
    {
      key: 'actions',
      header: '',
      render: (row) => (
        <Link
          to={`/contracts/${row.contract_id}/summary`}
          className="text-primary-600 hover:underline text-sm"
        >
          Summary
        </Link>
      ),
    },
  ]

  return (
    <PageLayout
      title="Contracts"
      description="View and manage provider–payer contracts."
      metadata={<span>Active contracts are available for pricing requests.</span>}
    >
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button type="button" variant="secondary" onClick={openBulkModal} disabled={!data?.length}>
          Run bulk validation
        </Button>
      </div>

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

      <Modal
        isOpen={bulkOpen}
        onClose={closeBulkModal}
        title="Bulk validation"
        panelClassName="max-w-3xl"
        footer={
          <ModalFooter>
            <Button type="button" variant="secondary" onClick={closeBulkModal}>
              Close
            </Button>
            <Button type="button" onClick={runBulk} disabled={bulkMutation.isPending || !data?.length}>
              {bulkMutation.isPending ? 'Validating…' : 'Run validation'}
            </Button>
          </ModalFooter>
        }
      >
        <div className="space-y-4 text-sm text-slate-700">
          <p>
            Choose contracts on this page, or validate every contract in the list below. Optional: persist results
            updates open error/warning badges after refresh.
          </p>
          {bulkError && (
            <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-red-800">{bulkError}</div>
          )}
          <label className="flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={allListed}
              onChange={(e) => {
                setAllListed(e.target.checked)
                if (e.target.checked) setSelected({})
              }}
            />
            <span>Validate all listed contracts ({data?.length ?? 0})</span>
          </label>
          <label className="flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={persistResults}
              onChange={(e) => setPersistResults(e.target.checked)}
            />
            <span>Persist validation results (?save=1)</span>
          </label>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" className="!py-1 !text-xs" onClick={selectAllInList}>
              Select all
            </Button>
            <Button type="button" variant="secondary" className="!py-1 !text-xs" onClick={clearSelection}>
              Clear selection
            </Button>
          </div>
          <div className="max-h-48 overflow-y-auto rounded border border-slate-200">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="px-2 py-2 font-medium"> </th>
                  <th className="px-2 py-2 font-medium">ID</th>
                  <th className="px-2 py-2 font-medium">Name</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data?.map((c) => (
                  <tr key={c.contract_id}>
                    <td className="px-2 py-1">
                      <input
                        type="checkbox"
                        disabled={allListed}
                        checked={!!selected[c.contract_id]}
                        onChange={() => toggleRow(c.contract_id)}
                        aria-label={`Select ${c.contract_name}`}
                      />
                    </td>
                    <td className="px-2 py-1 font-mono text-xs">{c.contract_id}</td>
                    <td className="px-2 py-1">{c.contract_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {bulkMutation.isPending && (
            <div className="flex justify-center py-4">
              <LoadingSpinner />
            </div>
          )}

          {bulkResults && bulkResults.length > 0 && (
            <div>
              <h3 className="mb-2 font-semibold text-slate-900">Results</h3>
              <div className="overflow-x-auto rounded border border-slate-200">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-3 py-2 font-medium">ID</th>
                      <th className="px-3 py-2 font-medium">Name</th>
                      <th className="px-3 py-2 font-medium">Errors</th>
                      <th className="px-3 py-2 font-medium">Warnings</th>
                      <th className="px-3 py-2 font-medium">Notes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {bulkResults.map((row) => (
                      <tr key={row.contract_id}>
                        <td className="px-3 py-2 font-mono text-xs">{row.contract_id}</td>
                        <td className="px-3 py-2">{nameById(row.contract_id)}</td>
                        <td className="px-3 py-2">
                          {row.error_count > 0 ? (
                            <span className="font-semibold text-red-700">{row.error_count}</span>
                          ) : (
                            <span className="text-slate-400">0</span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          {row.warning_count > 0 ? (
                            <span className="font-semibold text-amber-700">{row.warning_count}</span>
                          ) : (
                            <span className="text-slate-400">0</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-xs text-slate-600">
                          {row.errors ? <span className="text-red-700">{row.errors}</span> : null}
                          {!row.errors && row.conflicts?.length ? (
                            <span className="text-slate-500">
                              {row.conflicts.length} conflict{row.conflicts.length !== 1 ? 's' : ''}
                            </span>
                          ) : null}
                          {!row.errors && !row.conflicts?.length ? '—' : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </Modal>
    </PageLayout>
  )
}
