/**
 * Step 12e: read-only contract explorer (JSON tree from GET …/explorer/).
 * TODO: add RTL render test when frontend test harness exists.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  FormPanel,
  Button,
  DataTable,
  LoadingSpinner,
  ErrorState,
  StatusBadge,
} from '@/shared/ui'
import { fetchContractExplorer, fetchContractExplorerCsv } from '@/services/contractService'
import type {
  ContractExplorerResponse,
  ExplorerVersion,
  ExplorerMethodology,
  ExplorerPricingRule,
  ExplorerCarveout,
  ExplorerCapFloor,
  ExplorerBlendingRule,
  ExplorerStopLossRule,
  ExplorerOutlierRule,
} from '@/types'
import type { Column } from '@/shared/ui'

export function CollapsibleSection({
  title,
  defaultOpen = false,
  children,
  badge,
}: {
  title: string
  defaultOpen?: boolean
  children: React.ReactNode
  badge?: string | number
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="overflow-hidden rounded border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between bg-slate-50 px-4 py-3 text-left font-medium text-slate-900 hover:bg-slate-100"
      >
        <span className="flex items-center gap-2">
          {title}
          {badge != null && (
            <span className="text-xs font-normal text-slate-500">({badge})</span>
          )}
        </span>
        <span className="text-slate-400">{open ? '▼' : '▶'}</span>
      </button>
      {open && <div className="border-t border-slate-200 p-4">{children}</div>}
    </div>
  )
}

export interface ContractExplorerPanelProps {
  contractId: number
}

export function ContractExplorerPanel({ contractId }: ContractExplorerPanelProps) {
  const [csvError, setCsvError] = useState<string | null>(null)
  const {
    data: explorer,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['contract-explorer', String(contractId)],
    queryFn: () => fetchContractExplorer(contractId),
    enabled: Number.isInteger(contractId) && contractId > 0,
  })

  const apiNotFound =
    error && (error as { response?: { status?: number } })?.response?.status === 404

  const downloadJson = () => {
    if (!explorer) return
    const blob = new Blob([JSON.stringify(explorer, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `contract_${contractId}_explorer.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const downloadCsv = async () => {
    setCsvError(null)
    try {
      const blob = await fetchContractExplorerCsv(contractId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `contract_${contractId}_explorer.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setCsvError((e as Error).message ?? 'CSV download failed')
    }
  }

  if (!Number.isInteger(contractId) || contractId < 1) {
    return <p className="text-sm text-slate-500">Invalid contract.</p>
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <LoadingSpinner />
      </div>
    )
  }

  if (error) {
    return (
      <ErrorState
        title={apiNotFound ? 'Contract not found' : 'Failed to load explorer'}
        message={
          apiNotFound
            ? 'No contract exists for this ID.'
            : (error as Error).message
        }
        onRetry={() => refetch()}
      />
    )
  }

  if (!explorer) {
    return <p className="text-sm text-slate-500">No data.</p>
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="secondary" onClick={downloadJson}>
          Download JSON
        </Button>
        <Button type="button" variant="secondary" onClick={() => void downloadCsv()}>
          Download CSV
        </Button>
      </div>
      {csvError && (
        <div
          className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
          role="alert"
        >
          {csvError}
        </div>
      )}
      <ExplorerContent data={explorer} />
    </div>
  )
}

function ExplorerContent({ data }: { data: ContractExplorerResponse }) {
  const versions = data.versions ?? []
  const c = data.contract
  const counts = data.open_conflict_counts ?? { errors: 0, warnings: 0 }
  const openErrors = counts.errors ?? 0
  const openWarnings = counts.warnings ?? 0

  return (
    <div className="space-y-6">
      <FormPanel title="Contract">
        <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-slate-500">Contract ID</dt>
            <dd className="font-medium">{c.id}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Name</dt>
            <dd className="font-medium">{c.contract_name}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Legacy number</dt>
            <dd className="font-medium">{c.legacy_contract_number ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Open conflicts</dt>
            <dd className="font-medium">
              <span className="inline-flex flex-wrap gap-2">
                {openErrors > 0 && (
                  <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
                    {openErrors} error{openErrors !== 1 ? 's' : ''}
                  </span>
                )}
                {openWarnings > 0 && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
                    {openWarnings} warning{openWarnings !== 1 ? 's' : ''}
                  </span>
                )}
                {openErrors === 0 && openWarnings === 0 && (
                  <span className="text-slate-600">None</span>
                )}
                {(openErrors > 0 || openWarnings > 0) && (
                  <Link
                    to={`/contracts/${c.id}`}
                    className="text-primary-600 hover:underline"
                  >
                    View conflicts
                  </Link>
                )}
              </span>
            </dd>
          </div>
        </dl>
      </FormPanel>

      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-slate-900">Versions</h2>
        {versions.length === 0 ? (
          <p className="text-sm text-slate-500">No versions for this contract.</p>
        ) : (
          versions.map((ver) => <VersionBlock key={ver.version_id} version={ver} />)
        )}
      </div>
    </div>
  )
}

function VersionBlock({ version }: { version: ExplorerVersion }) {
  const methodologies = version.methodologies ?? []
  const rules = version.rules ?? []
  const carveouts = version.carveouts ?? []
  const capFloors = version.cap_floors ?? []
  const blendingRules = version.blending_rules ?? []
  const stopLossRules = version.stop_loss_rules ?? []
  const outlierRules = version.outlier_rules ?? []

  const methodologyColumns: Column<ExplorerMethodology & { _key: number }>[] = [
    { key: 'id', header: 'ID', sortable: true },
    { key: 'methodology_type', header: 'Type', sortable: true },
    { key: 'effective_date', header: 'Effective', sortable: true },
    { key: 'termination_date', header: 'Termination', sortable: true },
    { key: 'priority', header: 'Priority', sortable: true },
    { key: 'claim_type', header: 'Claim type', sortable: true },
    { key: 'site_of_service', header: 'Site', sortable: true },
  ]
  const ruleColumns: Column<ExplorerPricingRule & { _key: number }>[] = [
    { key: 'rule_id', header: 'ID', sortable: true },
    {
      key: 'rule_name',
      header: 'Name',
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
    {
      key: 'conditions',
      header: 'Conditions',
      render: (row) =>
        row.conditions?.length ? `${row.conditions.length} condition(s)` : '—',
    },
  ]
  const carveoutColumns: Column<ExplorerCarveout & { _key: number }>[] = [
    { key: 'carveout_id', header: 'ID', sortable: true },
    { key: 'code_type', header: 'Code type', sortable: true },
    { key: 'code_value', header: 'Code value', sortable: true },
    { key: 'carveout_methodology', header: 'Methodology', sortable: true },
    { key: 'carveout_percentage', header: '%', sortable: true },
    { key: 'carveout_rate', header: 'Rate', sortable: true },
    { key: 'status', header: 'Status', sortable: true },
  ]
  const capFloorColumns: Column<ExplorerCapFloor & { _key: number }>[] = [
    { key: 'cap_floor_id', header: 'ID', sortable: true },
    { key: 'scope', header: 'Scope', sortable: true },
    { key: 'cap_type', header: 'Type', sortable: true },
    { key: 'value', header: 'Value', sortable: true },
    { key: 'percentage', header: '%', sortable: true },
    { key: 'code_value', header: 'Code', sortable: true },
    { key: 'priority', header: 'Priority', sortable: true },
    { key: 'status', header: 'Status', sortable: true },
  ]
  const blendingColumns: Column<ExplorerBlendingRule & { _key: number }>[] = [
    { key: 'blending_rule_id', header: 'ID', sortable: true },
    { key: 'blend_type', header: 'Blend type', sortable: true },
    { key: 'scope', header: 'Scope', sortable: true },
    { key: 'primary_methodology', header: 'Primary', sortable: true },
    { key: 'secondary_methodology', header: 'Secondary', sortable: true },
    { key: 'blend_percentage', header: '%', sortable: true },
    { key: 'priority', header: 'Priority', sortable: true },
    { key: 'status', header: 'Status', sortable: true },
  ]
  const stopLossColumns: Column<ExplorerStopLossRule & { _key: number }>[] = [
    { key: 'id', header: 'ID', sortable: true },
    { key: 'cost_threshold', header: 'Cost threshold', sortable: true },
    { key: 'reimbursement_percentage', header: 'Reimb %', sortable: true },
    { key: 'priority', header: 'Priority', sortable: true },
    { key: 'effective_start_date', header: 'Start', sortable: true },
    { key: 'effective_end_date', header: 'End', sortable: true },
  ]
  const outlierColumns: Column<ExplorerOutlierRule & { _key: number }>[] = [
    { key: 'id', header: 'ID', sortable: true },
    { key: 'threshold_amount', header: 'Threshold', sortable: true },
    { key: 'threshold_scope', header: 'Scope', sortable: true },
    { key: 'reimbursement_percentage', header: 'Reimb %', sortable: true },
    { key: 'cost_to_charge_ratio', header: 'Cost/charge', sortable: true },
    { key: 'priority', header: 'Priority', sortable: true },
    { key: 'effective_start_date', header: 'Start', sortable: true },
    { key: 'effective_end_date', header: 'End', sortable: true },
  ]

  const methData = methodologies.map((m, i) => ({ ...m, _key: i }))
  const ruleData = rules.map((r, i) => ({ ...r, _key: i }))
  const carveData = carveouts.map((c, i) => ({ ...c, _key: i }))
  const capData = capFloors.map((c, i) => ({ ...c, _key: i }))
  const blendData = blendingRules.map((b, i) => ({ ...b, _key: i }))
  const stopData = stopLossRules.map((s, i) => ({ ...s, _key: i }))
  const outData = outlierRules.map((o, i) => ({ ...o, _key: i }))

  return (
    <div className="space-y-3">
      <h3 className="text-base font-medium text-slate-800">
        Version {version.version_number} (ID: {version.version_id}) · {version.status}
        {version.pricing_engine_mode != null &&
          version.pricing_engine_mode !== '' &&
          ` · Engine: ${version.pricing_engine_mode}`}
        {version.claim_level_drg_enabled != null &&
          ` · Claim-level DRG: ${version.claim_level_drg_enabled ? 'Yes' : 'No'}`}
        {version.effective_start_date && ` · ${version.effective_start_date}`}
        {version.effective_end_date && ` – ${version.effective_end_date}`}
      </h3>
      <div className="grid gap-3">
        <CollapsibleSection title="Methodologies" badge={methodologies.length} defaultOpen>
          <DataTable
            columns={methodologyColumns}
            data={methData}
            keyExtractor={(row) => `meth-${row.id}-${row._key}`}
            emptyMessage="No methodologies"
            pageSize={20}
          />
        </CollapsibleSection>
        <CollapsibleSection title="Pricing rules" badge={rules.length} defaultOpen>
          <DataTable
            columns={ruleColumns}
            data={ruleData}
            keyExtractor={(row) => `rule-${row.rule_id}-${row._key}`}
            emptyMessage="No pricing rules"
            pageSize={20}
          />
          {rules.length > 0 && (
            <div className="mt-4 space-y-3 border-t border-slate-100 pt-4">
              <h4 className="text-sm font-semibold text-slate-800">Conditions by rule</h4>
              <ul className="space-y-2">
                {rules.map((r) => (
                  <li
                    key={r.rule_id}
                    className="rounded border border-slate-100 bg-slate-50/80 px-3 py-2 text-sm"
                  >
                    <span className="font-medium text-slate-800">
                      {r.rule_id} · {r.rule_name || 'Unnamed'}
                    </span>
                    {r.conditions != null && r.conditions.length > 0 ? (
                      <ul className="mt-1 list-inside list-disc text-slate-600">
                        {r.conditions.map((cond) => (
                          <li key={cond.condition_id}>
                            {cond.attribute_name} {cond.operator} {cond.attribute_value}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-1 text-slate-500">No conditions</p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CollapsibleSection>
        <CollapsibleSection title="Carve-outs" badge={carveouts.length}>
          <DataTable
            columns={carveoutColumns}
            data={carveData}
            keyExtractor={(row) => `carve-${row.carveout_id}-${row._key}`}
            emptyMessage="No carve-outs"
            pageSize={20}
          />
        </CollapsibleSection>
        <CollapsibleSection title="Caps / Floors" badge={capFloors.length}>
          <DataTable
            columns={capFloorColumns}
            data={capData}
            keyExtractor={(row) => `cap-${row.cap_floor_id}-${row._key}`}
            emptyMessage="No caps/floors"
            pageSize={20}
          />
        </CollapsibleSection>
        <CollapsibleSection title="Blending rules" badge={blendingRules.length}>
          <DataTable
            columns={blendingColumns}
            data={blendData}
            keyExtractor={(row) => `blend-${row.blending_rule_id}-${row._key}`}
            emptyMessage="No blending rules"
            pageSize={20}
          />
        </CollapsibleSection>
        <CollapsibleSection title="Stop-loss rules" badge={stopLossRules.length}>
          <DataTable
            columns={stopLossColumns}
            data={stopData}
            keyExtractor={(row) => `stop-${row.id}-${row._key}`}
            emptyMessage="No stop-loss rules"
            pageSize={20}
          />
        </CollapsibleSection>
        <CollapsibleSection title="Outlier rules" badge={outlierRules.length}>
          <DataTable
            columns={outlierColumns}
            data={outData}
            keyExtractor={(row) => `outlier-${row.id}-${row._key}`}
            emptyMessage="No outlier rules"
            pageSize={20}
          />
        </CollapsibleSection>
      </div>
    </div>
  )
}
