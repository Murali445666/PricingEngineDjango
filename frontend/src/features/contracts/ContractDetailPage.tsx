import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PageLayout, DataTable, LoadingSpinner, ErrorState, StatusBadge, Button, FormPanel } from '@/shared/ui'
import {
  fetchContractById,
  fetchContractRules,
  fetchContractExplorer,
  validateContract,
  activateContractVersion,
} from '@/services/contractService'
import { ConflictWarningsPanel } from './ConflictWarningsPanel'
import { ContractExplorerPanel } from './ContractExplorerPanel'
import { RateExhibitPanel } from './RateExhibitPanel'
import { CoveredEntitiesPanel } from './CoveredEntitiesPanel'
import { ProductScopePanel } from './ProductScopePanel'
import { AmendmentPanel } from './AmendmentPanel'
import { VersionHistoryPanel } from './VersionHistoryPanel'
import { VersionDiffPanel } from './VersionDiffPanel'
import type { PricingRule, ContractValidationResponse } from '@/types'
import type { Column } from '@/shared/ui'

type ContractTab = 'overview' | 'explorer'

export function ContractDetailPage() {
  const { id } = useParams<{ id: string }>()
  const contractId = id != null ? Number(id) : NaN
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<ContractTab>('overview')
  const [validation, setValidation] = useState<ContractValidationResponse | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)

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

  const { data: explorer } = useQuery({
    queryKey: ['contract-explorer', id],
    queryFn: () => fetchContractExplorer(contractId),
    enabled: Number.isInteger(contractId),
  })

  const draftVersion = explorer?.versions.find((v) => v.status === 'DRAFT') ?? null
  const isEditable = contract?.status === 'DRAFT' || draftVersion != null

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

  const validateMutation = useMutation({
    mutationFn: () => validateContract(contractId, { save: true }),
    onSuccess: (data) => {
      setValidation(data)
      setValidationError(null)
      void queryClient.invalidateQueries({ queryKey: ['contract-conflicts', contractId] })
      void queryClient.invalidateQueries({ queryKey: ['contract', id] })
    },
    onError: (err: Error) => {
      setValidationError(err.message)
    },
  })

  const publishMutation = useMutation({
    mutationFn: (versionId: number) => activateContractVersion(versionId),
    onSuccess: () => {
      setValidation(null)
      void queryClient.invalidateQueries({ queryKey: ['contract', id] })
      void queryClient.invalidateQueries({ queryKey: ['contract-explorer', id] })
      refetchContract()
      refetchRules()
    },
    onError: (err: Error) => {
      window.alert(`Publish failed: ${err.message}`)
    },
  })

  const isLoading = contractLoading || rulesLoading
  const error = contractError ?? rulesError
  const refetch = () => {
    refetchContract()
    refetchRules()
  }

  const hasValidationErrors = (validation?.error_count ?? 0) > 0
  const canPublish =
    draftVersion != null &&
    !hasValidationErrors &&
    !validateMutation.isPending

  const runValidate = () => validateMutation.mutate()

  const runPublish = () => {
    if (!draftVersion) return
    if (hasValidationErrors) {
      window.alert('Resolve validation errors before publishing.')
      return
    }
    if (!validation) {
      window.alert('Run Validate first — publish is blocked until lint passes.')
      return
    }
    if (!window.confirm('Publish will activate this version (or schedule activation). Continue?')) return
    publishMutation.mutate(draftVersion.version_id)
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
            {draftVersion && ` · DRAFT v${draftVersion.version_number} (#${draftVersion.version_id})`}
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
          <div className="mb-4 mt-2 flex flex-wrap items-center gap-2 border-b border-slate-200 pb-2">
            <button
              type="button"
              onClick={() => setTab('overview')}
              className={`rounded px-3 py-1.5 text-sm font-medium ${
                tab === 'overview'
                  ? 'bg-primary-600 text-white'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              Overview
            </button>
            <button
              type="button"
              onClick={() => setTab('explorer')}
              className={`rounded px-3 py-1.5 text-sm font-medium ${
                tab === 'explorer'
                  ? 'bg-primary-600 text-white'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              Explorer
            </button>
            <Link
              to={`/contracts/${contract.contract_id}/summary`}
              className="ml-auto inline-flex items-center rounded border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Summary
            </Link>
          </div>

          {tab === 'overview' && (
            <>
              <AmendmentPanel
                contractId={contract.contract_id}
                isActive={contract.status === 'ACTIVE'}
                hasDraftVersion={draftVersion != null}
              />

              {explorer && (
                <VersionHistoryPanel
                  contractId={contract.contract_id}
                  versions={explorer.versions}
                  contractStatus={contract.status}
                />
              )}

              {isEditable && draftVersion && (
                <section className="mb-4 rounded-lg border border-primary-200 bg-primary-50/40 p-4">
                  <h2 className="mb-3 text-lg font-semibold text-slate-900">
                    Edit draft v{draftVersion.version_number}
                  </h2>
                  <RateExhibitPanel
                    contractId={contract.contract_id}
                    versionId={draftVersion.version_id}
                  />
                  <CoveredEntitiesPanel contractId={contract.contract_id} isDraft={isEditable} />
                  <ProductScopePanel
                    contractId={contract.contract_id}
                    isDraft={isEditable}
                    defaultLob={contract.line_of_business}
                  />
                </section>
              )}

              {explorer && draftVersion && (
                <VersionDiffPanel
                  contractId={contract.contract_id}
                  versions={explorer.versions}
                  inlineVersionId={draftVersion.version_id}
                  defaultAgainstVersionId={
                    explorer.versions.find((v) => v.status === 'ACTIVE')?.version_id ??
                    explorer.versions.find((v) => v.status === 'SUPERSEDED')?.version_id ??
                    null
                  }
                  title="Amendment changes (draft vs. live)"
                />
              )}

              {explorer && (
                <VersionDiffPanel
                  contractId={contract.contract_id}
                  versions={explorer.versions}
                  title="Compare versions"
                />
              )}

              <FormPanel title="Authoring" className="mb-4">
                <p className="mb-3 text-sm text-slate-600">
                  DRAFT versions do not resolve for live repricing until published. Validate before publish —
                  errors block activation.
                </p>
                <div className="mb-3 flex flex-wrap gap-2">
                  <Button type="button" variant="secondary" onClick={runValidate} disabled={validateMutation.isPending}>
                    {validateMutation.isPending ? 'Validating…' : 'Validate'}
                  </Button>
                  {draftVersion && (
                    <Button
                      type="button"
                      onClick={runPublish}
                      disabled={!canPublish || publishMutation.isPending || !validation}
                      title={
                        !validation
                          ? 'Run Validate first'
                          : hasValidationErrors
                            ? 'Fix validation errors first'
                            : undefined
                      }
                    >
                      {publishMutation.isPending ? 'Publishing…' : 'Publish (DRAFT → ACTIVE)'}
                    </Button>
                  )}
                </div>

                {validationError && (
                  <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                    {validationError}
                  </div>
                )}

                {validation && (
                  <div
                    className={`rounded border px-3 py-2 text-sm ${
                      validation.error_count > 0
                        ? 'border-red-200 bg-red-50 text-red-900'
                        : validation.warning_count > 0
                          ? 'border-amber-200 bg-amber-50 text-amber-900'
                          : 'border-green-200 bg-green-50 text-green-900'
                    }`}
                  >
                    <p className="font-medium">
                      {validation.error_count} error(s), {validation.warning_count} warning(s)
                    </p>
                    {validation.conflicts.length > 0 && (
                      <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-xs">
                        {validation.conflicts.map((c, i) => (
                          <li key={`${c.conflict_type}-${i}`}>
                            <span className="font-semibold">{c.severity}</span> · {c.conflict_type}: {c.message}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </FormPanel>

              {isEditable && !draftVersion && (
                <>
                  <CoveredEntitiesPanel contractId={contract.contract_id} isDraft={isEditable} />
                  <ProductScopePanel
                    contractId={contract.contract_id}
                    isDraft={isEditable}
                    defaultLob={contract.line_of_business}
                  />
                  <RateExhibitPanel contractId={contract.contract_id} versionId={null} />
                </>
              )}

              {!isEditable && (
                <>
                  <CoveredEntitiesPanel contractId={contract.contract_id} isDraft={false} />
                  <ProductScopePanel
                    contractId={contract.contract_id}
                    isDraft={false}
                    defaultLob={contract.line_of_business}
                  />
                  <RateExhibitPanel contractId={contract.contract_id} versionId={null} />
                </>
              )}

              <ConflictWarningsPanel contractId={contract.contract_id} />

              <div className="mb-4 mt-6">
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

          {tab === 'explorer' && (
            <div className="mt-4">
              <ContractExplorerPanel contractId={contract.contract_id} />
            </div>
          )}
        </>
      )}
    </PageLayout>
  )
}
