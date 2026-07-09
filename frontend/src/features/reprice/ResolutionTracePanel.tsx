import { Link } from 'react-router-dom'
import { FormPanel } from '@/shared/ui'
import { NetworkStatusBadge } from '@/shared/ui/NetworkStatusBadge'
import type { RepriceTraceContext } from '@/types/reprice'

interface ResolutionTracePanelProps {
  context: RepriceTraceContext
}

function StepRow({
  step,
  label,
  children,
}: {
  step: number
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-100 text-xs font-semibold text-primary-800">
          {step}
        </span>
        <span className="mt-1 w-px flex-1 bg-slate-200" aria-hidden />
      </div>
      <div className="min-w-0 flex-1 pb-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
        <div className="mt-1 text-sm text-slate-800">{children}</div>
      </div>
    </div>
  )
}

function field(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

export function ResolutionTracePanel({ context }: ResolutionTracePanelProps) {
  const { resolutionMode, contractId, provider, member, traceId, message } = context

  return (
    <FormPanel
      title="Resolution trace"
      description="How member + provider identity resolved to a contract (identity-first path)."
    >
      {message && (resolutionMode === 'OON' || resolutionMode === 'NO_CONTRACT' || resolutionMode === 'AMBIGUOUS' || !contractId) && (
        <div
          role="alert"
          className="mb-4 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
        >
          {message}
        </div>
      )}

      <div className="max-w-xl">
        <StepRow step={1} label="Member">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <dt className="text-slate-500">member_id</dt>
            <dd className="font-mono text-xs">{field(member?.member_id)}</dd>
            <dt className="text-slate-500">LOB</dt>
            <dd>{field(member?.lob)}</dd>
            <dt className="text-slate-500">product_id</dt>
            <dd>{field(member?.product_id)}</dd>
            <dt className="text-slate-500">enrollment_id</dt>
            <dd>{field(member?.enrollment_id)}</dd>
          </dl>
        </StepRow>

        <StepRow step={2} label="Provider / network">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <dt className="text-slate-500">billing_org_id</dt>
            <dd className="font-mono text-xs">{field(provider?.billing_org_id)}</dd>
            <dt className="text-slate-500">network_status</dt>
            <dd>
              <NetworkStatusBadge
                status={provider?.network_status}
                tier={provider?.network_tier}
              />
            </dd>
            <dt className="text-slate-500">affiliation_verified</dt>
            <dd>{provider?.affiliation_verified ? 'Yes' : 'No'}</dd>
          </dl>
        </StepRow>

        <StepRow step={3} label="Contract">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <dt className="text-slate-500">resolution_mode</dt>
            <dd className="font-medium">{field(resolutionMode)}</dd>
            <dt className="text-slate-500">contract_id</dt>
            <dd>
              {contractId != null ? (
                <Link to={`/contracts/${contractId}`} className="font-mono text-xs text-primary-600 hover:underline">
                  {contractId}
                </Link>
              ) : (
                '—'
              )}
            </dd>
            {traceId && (
              <>
                <dt className="text-slate-500">trace_id</dt>
                <dd className="break-all font-mono text-xs text-slate-600">{traceId}</dd>
              </>
            )}
          </dl>
        </StepRow>
      </div>
    </FormPanel>
  )
}
