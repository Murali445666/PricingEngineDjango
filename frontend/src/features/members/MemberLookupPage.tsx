import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  PageLayout,
  FormPanel,
  Input,
  Button,
  LoadingSpinner,
  ErrorState,
  StatusBadge,
} from '@/shared/ui'
import { getMemberEnrollment } from '@/services/memberService'

function field(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

export function MemberLookupPage() {
  const [memberId, setMemberId] = useState('MEM-S4-001')
  const [serviceDate, setServiceDate] = useState('2025-06-15')
  const [lookupKey, setLookupKey] = useState<{ memberId: string; serviceDate: string } | null>(null)

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['member-enrollment', lookupKey?.memberId, lookupKey?.serviceDate],
    queryFn: () =>
      getMemberEnrollment(lookupKey!.memberId, {
        service_date: lookupKey!.serviceDate || undefined,
      }),
    enabled: lookupKey != null && lookupKey.memberId.trim().length > 0,
  })

  const handleLookup = (e: React.FormEvent) => {
    e.preventDefault()
    if (!memberId.trim()) return
    setLookupKey({ memberId: memberId.trim(), serviceDate })
  }

  const showResults = lookupKey != null && !isLoading && !error && data != null

  return (
    <PageLayout
      title="Members"
      description="Active coverage lookup — product, LOB, and network for a member on a service date."
      metadata={
        <span>
          Demo: member <code className="font-mono text-xs">MEM-S4-001</code>, service date 2025-06-15.
          {' '}
          <Link to="/reprice-claim" className="text-primary-600 hover:underline">
            Open Reprice Claim
          </Link>
        </span>
      }
    >
      <FormPanel title="Lookup" description="GET /api/members/&lt;member_id&gt;/enrollment/">
        <form onSubmit={handleLookup} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Member ID"
              value={memberId}
              onChange={(e) => setMemberId(e.target.value)}
              placeholder="MEM-S4-001"
            />
            <Input
              label="Service date"
              type="date"
              value={serviceDate}
              onChange={(e) => setServiceDate(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={!memberId.trim() || isFetching}>
            {isFetching ? <LoadingSpinner size="sm" /> : 'Look up enrollment'}
          </Button>
        </form>
      </FormPanel>

      {lookupKey && isLoading && (
        <div className="mt-6 flex justify-center py-12">
          <LoadingSpinner />
        </div>
      )}

      {lookupKey && error && (
        <div className="mt-6">
          <ErrorState
            title="Enrollment lookup failed"
            message={(error as Error).message}
            onRetry={() => void refetch()}
          />
        </div>
      )}

      {showResults && !data.enrolled && (
        <FormPanel title="Coverage" className="mt-6">
          <div className="rounded border border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-600">
            <p className="font-medium text-slate-800">Not enrolled</p>
            <p className="mt-2">
              No active enrollment for <span className="font-mono text-xs">{data.member_id}</span> on{' '}
              {field(data.as_of_date)}.
            </p>
          </div>
        </FormPanel>
      )}

      {showResults && data.enrolled && (
        <FormPanel title="Coverage" className="mt-6">
          <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <dt className="text-slate-500">Enrolled</dt>
            <dd>
              <StatusBadge status="ACTIVE" />
            </dd>
            <dt className="text-slate-500">member_id</dt>
            <dd className="font-mono text-xs">{field(data.member_id)}</dd>
            <dt className="text-slate-500">enrollment_id</dt>
            <dd>{field(data.enrollment_id)}</dd>
            <dt className="text-slate-500">product_name</dt>
            <dd>{field(data.product_name)}</dd>
            <dt className="text-slate-500">product_id</dt>
            <dd>{field(data.product_id)}</dd>
            <dt className="text-slate-500">lob</dt>
            <dd>{field(data.lob)}</dd>
            <dt className="text-slate-500">network_id</dt>
            <dd>
              {field(data.network_id)}
              {data.network_id == null && (
                <span className="ml-2 text-xs text-slate-400">(null when no ALL claim-type network config)</span>
              )}
            </dd>
            <dt className="text-slate-500">effective_date</dt>
            <dd>{field(data.effective_date)}</dd>
            <dt className="text-slate-500">termination_date</dt>
            <dd>{field(data.termination_date)}</dd>
            <dt className="text-slate-500">as_of_date</dt>
            <dd>{field(data.as_of_date)}</dd>
          </dl>
        </FormPanel>
      )}

      {!lookupKey && (
        <div className="mt-6 rounded-lg border-2 border-dashed border-slate-200 bg-slate-50/50 px-6 py-10 text-center text-sm text-slate-600">
          Enter a member ID and service date, then run lookup.
        </div>
      )}
    </PageLayout>
  )
}
