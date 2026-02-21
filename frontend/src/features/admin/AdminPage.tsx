import { PageLayout, FormPanel } from '@/shared/ui'

export function AdminPage() {
  return (
    <PageLayout
      title="Admin"
      description="Platform configuration and governance."
      metadata={<span>Tenant and service configuration.</span>}
    >
      <FormPanel title="Feature under development">
        <p className="text-sm text-slate-500">
          Tenant, service version, and integration configuration will be available here.
        </p>
      </FormPanel>
    </PageLayout>
  )
}
