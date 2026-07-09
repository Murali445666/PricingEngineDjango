import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  PageLayout,
  FormPanel,
  LoadingSpinner,
  ErrorState,
  StatusBadge,
  DataTable,
} from '@/shared/ui'
import type { Column } from '@/shared/ui'
import { getContractSummary } from '@/services/contractSummaryService'
import type {
  ContractSummary,
  ContractSummaryArrangement,
  ContractSummaryCoveredEntity,
  ContractSummaryRule,
} from '@/types/contractSummary'

function originLabel(origin: string): string {
  const map: Record<string, string> = {
    DIRECT: 'Direct',
    LEASED: 'Leased',
    DELEGATED: 'Delegated',
  }
  return map[origin] ?? origin
}

function entityChipClass(entityType: string): string {
  switch (entityType) {
    case 'ORG':
      return 'bg-blue-50 text-blue-800 border-blue-200'
    case 'FACILITY':
      return 'bg-purple-50 text-purple-800 border-purple-200'
    case 'PROVIDER':
      return 'bg-teal-50 text-teal-800 border-teal-200'
    default:
      return 'bg-slate-50 text-slate-700 border-slate-200'
  }
}

function ruleCode(rule: ContractSummaryRule): string {
  return rule.codes?.length ? rule.codes.join(', ') : '—'
}

export function ContractSummaryPage() {
  const { id } = useParams<{ id: string }>()
  const contractId = id != null ? Number(id) : NaN

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['contract-summary', id],
    queryFn: () => getContractSummary(contractId),
    enabled: Number.isInteger(contractId) && contractId > 0,
  })

  const ruleColumns: Column<ContractSummaryRule & { _key: number }>[] = [
    {
      key: 'codes',
      header: 'Code',
      render: (row) => <span className="font-mono text-xs">{ruleCode(row)}</span>,
    },
    { key: 'rule_name', header: 'Rule' },
    {
      key: 'rate',
      header: 'Rate',
      render: (row) => (
        <div>
          <span className="font-medium">{row.rate ?? '—'}</span>
          {row.rate_basis && (
            <p className="mt-0.5 text-xs text-slate-500">
              {row.rate_basis}
              {row.materialized_year != null ? ` (${row.materialized_year})` : ''}
            </p>
          )}
        </div>
      ),
    },
  ]

  return (
    <PageLayout
      title={data?.header.contract_name ?? 'Contract summary'}
      description="Read-only contract abstraction — parties, coverage, arrangements, and terms."
      metadata={
        data ? (
          <span>
            <Link to={`/contracts/${data.contract_id}`} className="text-primary-600 hover:underline">
              ← Back to contract detail
            </Link>
            {' · '}
            <Link to="/contracts" className="text-primary-600 hover:underline">
              All contracts
            </Link>
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
          title="Failed to load contract summary"
          message={(error as Error).message}
          onRetry={() => refetch()}
        />
      )}
      {data && <SummaryContent summary={data} ruleColumns={ruleColumns} />}
    </PageLayout>
  )
}

function SummaryContent({
  summary,
  ruleColumns,
}: {
  summary: ContractSummary
  ruleColumns: Column<ContractSummaryRule & { _key: number }>[]
}) {
  const payerName = summary.parties.payer_org?.name ?? '—'
  const provider = summary.parties.provider_org

  return (
    <div className="space-y-6">
      {/* 1. Header row */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">
            {summary.header.contract_name ?? `Contract #${summary.contract_id}`}
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            #{summary.contract_id}
            {payerName !== '—' ? ` · ${payerName}` : ''}
            {summary.header.legacy_contract_number
              ? ` · ${summary.header.legacy_contract_number}`
              : ''}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge status={summary.header.status} />
          <span className="inline-flex items-center rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-700">
            {originLabel(summary.header.contract_origin_type)}
          </span>
        </div>
      </div>

      {/* 2. Abstract banner */}
      <div className="rounded-lg border border-primary-200 bg-primary-50 px-5 py-4 text-sm leading-relaxed text-primary-950">
        {summary.abstract}
      </div>

      {/* 3. Parties */}
      <div className="grid gap-4 md:grid-cols-2">
        <FormPanel title="Payer" description="Plan / payer organization">
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="text-slate-500">Name</dt>
              <dd className="font-medium text-slate-900">{payerName}</dd>
            </div>
            {summary.parties.payer_org && (
              <div>
                <dt className="text-slate-500">Type</dt>
                <dd>{summary.parties.payer_org.payer_type}</dd>
              </div>
            )}
            <div>
              <dt className="text-slate-500">Network / LOB</dt>
              <dd>
                {summary.parties.network.network_name ?? summary.parties.network.network_id}
                {summary.parties.network.line_of_business
                  ? ` · ${summary.parties.network.line_of_business}`
                  : ''}
              </dd>
            </div>
          </dl>
        </FormPanel>
        <FormPanel title="Provider" description="Billing / contracted organization">
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="text-slate-500">Organization</dt>
              <dd className="font-medium text-slate-900">{provider.name}</dd>
            </div>
            {provider.parent_org_name && (
              <div>
                <dt className="text-slate-500">Hierarchy</dt>
                <dd>under {provider.parent_org_name}</dd>
              </div>
            )}
            {provider.npi && (
              <div>
                <dt className="text-slate-500">NPI</dt>
                <dd className="font-mono text-xs">{provider.npi}</dd>
              </div>
            )}
          </dl>
        </FormPanel>
      </div>

      {/* 4. Covered entities */}
      <FormPanel
        title="Covered entities"
        description="Who and what this contract covers (ContractCoveredEntity)."
      >
        {summary.covered_entities.length === 0 ? (
          <p className="text-sm text-slate-500">No covered entities defined.</p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded border border-slate-200">
            {summary.covered_entities.map((entity) => (
              <CoveredEntityRow key={entity.id} entity={entity} />
            ))}
          </ul>
        )}
      </FormPanel>

      {/* 5. Pricing arrangements */}
      <FormPanel title="Pricing arrangements" description="Arrangements and nested rules (always expanded).">
        <div className="space-y-4">
          {summary.arrangements.length === 0 ? (
            <p className="text-sm text-slate-500">No arrangements defined.</p>
          ) : (
            summary.arrangements.map((arr) => (
              <ArrangementBlock key={arr.id ?? arr.name} arrangement={arr} ruleColumns={ruleColumns} />
            ))
          )}
        </div>
      </FormPanel>

      {/* 6. Terms & Amendments */}
      <div className="grid gap-4 md:grid-cols-2">
        <FormPanel title="Terms & policy" description="Scopes and policy summaries.">
          {summary.terms.length === 0 ? (
            <p className="text-sm text-slate-500">No additional terms recorded.</p>
          ) : (
            <ul className="list-inside list-disc space-y-1 text-sm text-slate-700">
              {summary.terms.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
        </FormPanel>
        <FormPanel title="Amendments" description="Contract change history.">
          {summary.amendments.length === 0 ? (
            <p className="text-sm text-slate-500">No amendments on file.</p>
          ) : (
            <ul className="space-y-3 text-sm">
              {summary.amendments.map((am) => (
                <li key={am.id} className="rounded border border-slate-100 bg-slate-50 px-3 py-2">
                  <span className="font-medium text-slate-900">#{am.amendment_number}</span>
                  <span className="text-slate-500"> · {am.effective_date}</span>
                  <p className="mt-1 text-slate-700">{am.description}</p>
                </li>
              ))}
            </ul>
          )}
        </FormPanel>
      </div>

      {/* 7. Documents */}
      <FormPanel title="Documents" description="Source documents and rate exhibits.">
        {summary.documents.length === 0 ? (
          <p className="text-sm text-slate-500">No documents attached.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {summary.documents.map((doc) => (
              <span
                key={doc.id}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-800"
              >
                <span aria-hidden className="text-slate-400">
                  📄
                </span>
                <span className="font-medium">{doc.title}</span>
                {doc.doc_type && (
                  <span className="text-xs text-slate-500">({doc.doc_type})</span>
                )}
              </span>
            ))}
          </div>
        )}
      </FormPanel>
    </div>
  )
}

function CoveredEntityRow({ entity }: { entity: ContractSummaryCoveredEntity }) {
  return (
    <li className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
      <span
        className={`inline-flex rounded border px-2 py-0.5 text-xs font-semibold ${entityChipClass(entity.entity_type)}`}
      >
        {entity.entity_type}
      </span>
      <span className="font-medium text-slate-900">{entity.name}</span>
      {entity.detail && <span className="font-mono text-xs text-slate-500">{entity.detail}</span>}
      {entity.is_primary && (
        <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
          primary
        </span>
      )}
    </li>
  )
}

function ArrangementBlock({
  arrangement,
  ruleColumns,
}: {
  arrangement: ContractSummaryArrangement
  ruleColumns: Column<ContractSummaryRule & { _key: number }>[]
}) {
  const rules = arrangement.rules.map((r, i) => ({ ...r, _key: i }))
  return (
    <div className="rounded border border-slate-200 bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="font-medium text-slate-900">{arrangement.name}</h3>
        {arrangement.arrangement_type && (
          <span className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-600">
            {arrangement.arrangement_type.replace(/_/g, ' ')}
          </span>
        )}
        {arrangement.claim_type && (
          <span className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-600">
            {arrangement.claim_type}
          </span>
        )}
      </div>
      {rules.length === 0 ? (
        <p className="text-sm text-slate-500">No rules under this arrangement.</p>
      ) : (
        <DataTable
          columns={ruleColumns}
          data={rules}
          keyExtractor={(row) => row._key}
          emptyMessage="No rules"
          pageSize={50}
        />
      )}
    </div>
  )
}
