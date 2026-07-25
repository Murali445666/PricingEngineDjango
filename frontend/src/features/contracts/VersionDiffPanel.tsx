import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FormPanel, LoadingSpinner } from '@/shared/ui'
import { fetchVersionDiff } from '@/services/contractService'
import type { ContractVersionDiff, ExplorerVersion } from '@/types'

interface VersionDiffPanelProps {
  contractId: number
  versions: ExplorerVersion[]
  /** When set, locks the "new" side and shows inline (draft amendment review). */
  inlineVersionId?: number | null
  defaultAgainstVersionId?: number | null
  title?: string
  className?: string
}

function formatPct(pct: number | null | undefined): string {
  if (pct == null || Number.isNaN(pct)) return '—'
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(2)}%`
}

function DiffSection({
  title,
  count,
  defaultOpen = false,
  children,
}: {
  title: string
  count: number
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen || count > 0)
  if (count === 0) return null
  return (
    <div className="rounded border border-slate-200 bg-white">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium text-slate-800"
        onClick={() => setOpen((v) => !v)}
      >
        <span>
          {title} ({count})
        </span>
        <span className="text-slate-400">{open ? '−' : '+'}</span>
      </button>
      {open && <div className="border-t border-slate-100 px-3 py-2">{children}</div>}
    </div>
  )
}

function DiffDetail({ diff }: { diff: ContractVersionDiff }) {
  const s = diff.summary
  return (
    <div className="space-y-3">
      <DiffSection title="Rate changes" count={s.rules.changed} defaultOpen>
        <div className="max-h-64 overflow-y-auto">
          <table className="min-w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="py-1 pr-3">Code</th>
                <th className="py-1 pr-3">Entity</th>
                <th className="py-1 pr-3">Old</th>
                <th className="py-1 pr-3">New</th>
                <th className="py-1">Δ%</th>
              </tr>
            </thead>
            <tbody>
              {diff.rates.changed.map((row) => (
                <tr key={`${row.code}-${row.covered_entity ?? ''}`} className="border-t border-slate-50">
                  <td className="py-1 pr-3 font-mono">{row.code}</td>
                  <td className="py-1 pr-3">{row.covered_entity ?? '—'}</td>
                  <td className="py-1 pr-3">{row.old_rate ?? '—'}</td>
                  <td className="py-1 pr-3">{row.new_rate ?? '—'}</td>
                  <td className="py-1">{formatPct(row.pct_change)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </DiffSection>

      <DiffSection title="Rates added" count={s.rules.added}>
        <ul className="space-y-1 text-xs">
          {diff.rates.added.map((row) => (
            <li key={row.code + (row.rule_name ?? '')}>
              <span className="font-mono">{row.code}</span> → {row.new_rate ?? '—'}
            </li>
          ))}
        </ul>
      </DiffSection>

      <DiffSection title="Rates removed" count={s.rules.removed}>
        <ul className="space-y-1 text-xs">
          {diff.rates.removed.map((row) => (
            <li key={row.code + (row.rule_name ?? '')}>
              <span className="font-mono">{row.code}</span> was {row.old_rate ?? '—'}
            </li>
          ))}
        </ul>
      </DiffSection>

      <DiffSection title="Covered entities added" count={s.entities.added}>
        <ul className="space-y-1 text-xs">
          {diff.covered_entities.added.map((row, i) => (
            <li key={i}>{row.label}</li>
          ))}
        </ul>
      </DiffSection>

      <DiffSection title="Covered entities removed" count={s.entities.removed}>
        <ul className="space-y-1 text-xs">
          {diff.covered_entities.removed.map((row, i) => (
            <li key={i}>{row.label}</li>
          ))}
        </ul>
      </DiffSection>

      <DiffSection title="Product scope added" count={s.scope.added}>
        <ul className="space-y-1 text-xs">
          {diff.product_scope.added.map((row, i) => (
            <li key={i}>{row.label}</li>
          ))}
        </ul>
      </DiffSection>

      <DiffSection title="Product scope removed" count={s.scope.removed}>
        <ul className="space-y-1 text-xs">
          {diff.product_scope.removed.map((row, i) => (
            <li key={i}>{row.label}</li>
          ))}
        </ul>
      </DiffSection>

      <DiffSection title="Cap / floor changes" count={s.cap_floors.changed}>
        <ul className="space-y-1 text-xs text-slate-600">
          {diff.cap_floors.changed.map((row, i) => (
            <li key={i}>{JSON.stringify(row.key)}</li>
          ))}
        </ul>
      </DiffSection>

      <DiffSection title="Contract header" count={s.contract_header.changed}>
        <ul className="space-y-1 text-xs">
          {diff.contract_header.map((row) => (
            <li key={row.field}>
              <span className="font-medium">{row.field}</span>: {String(row.old ?? '—')} →{' '}
              {String(row.new ?? '—')}
            </li>
          ))}
        </ul>
      </DiffSection>
    </div>
  )
}

export function VersionDiffPanel({
  contractId,
  versions,
  inlineVersionId = null,
  defaultAgainstVersionId = null,
  title = 'Compare versions',
  className = 'mb-4',
}: VersionDiffPanelProps) {
  const activeVersion = versions.find((v) => v.status === 'ACTIVE') ?? null
  const draftVersion = versions.find((v) => v.status === 'DRAFT') ?? null

  const [newVersionId, setNewVersionId] = useState<number | ''>(
    inlineVersionId ?? draftVersion?.version_id ?? '',
  )
  const [againstVersionId, setAgainstVersionId] = useState<number | ''>(
    defaultAgainstVersionId ?? activeVersion?.version_id ?? '',
  )

  useEffect(() => {
    const baseline = defaultAgainstVersionId ?? activeVersion?.version_id ?? null
    if (baseline != null) {
      setAgainstVersionId(baseline)
    }
  }, [defaultAgainstVersionId, activeVersion?.version_id])

  const resolvedNew = inlineVersionId ?? (newVersionId === '' ? null : newVersionId)
  const resolvedAgainst = againstVersionId === '' ? null : againstVersionId

  const { data: diff, isLoading, error, refetch } = useQuery({
    queryKey: ['version-diff', contractId, resolvedNew, resolvedAgainst],
    queryFn: () =>
      fetchVersionDiff(contractId, resolvedNew!, {
        against: resolvedAgainst ?? undefined,
      }),
    enabled: resolvedNew != null,
    staleTime: 0,
  })

  const sorted = [...versions].sort((a, b) => b.version_number - a.version_number)

  return (
    <FormPanel title={title} className={className}>
      {!inlineVersionId && (
        <div className="mb-3 grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">New version</span>
            <select
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={newVersionId}
              onChange={(e) => setNewVersionId(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">Select…</option>
              {sorted.map((v) => (
                <option key={v.version_id} value={v.version_id}>
                  v{v.version_number} ({v.status}) #{v.version_id}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">Compare against</span>
            <select
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={againstVersionId}
              onChange={(e) => setAgainstVersionId(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">Prior version (default)</option>
              {sorted.map((v) => (
                <option key={v.version_id} value={v.version_id}>
                  v{v.version_number} ({v.status}) #{v.version_id}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {isLoading && (
        <div className="flex justify-center py-6">
          <LoadingSpinner />
        </div>
      )}
      {error && (
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {(error as Error).message}
          <button type="button" className="ml-2 underline" onClick={() => refetch()}>
            Retry
          </button>
        </div>
      )}
      {diff && (
        <>
          <p className="mb-3 text-sm font-medium text-slate-800">{diff.headline}</p>
          <DiffDetail diff={diff} />
        </>
      )}
    </FormPanel>
  )
}
