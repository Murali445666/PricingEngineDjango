import { PageLayout, FormPanel } from '@/shared/ui'

export function BatchMonitorPage() {
  return (
    <PageLayout
      title="Batch Monitor"
      description="Execution monitoring and batch job tracking."
      metadata={<span>Throughput and latency metrics.</span>}
    >
      <FormPanel title="Feature under development">
        <p className="text-sm text-slate-500">
          Batch job tracking and execution dashboard will be available here.
        </p>
      </FormPanel>
    </PageLayout>
  )
}
