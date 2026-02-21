import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { PageLayout, FormPanel, Button, Input, LoadingSpinner, ErrorState } from '@/shared/ui'
import { priceLine } from '@/services/pricingService'

export function PricingSandboxPage() {
  const [contractId, setContractId] = useState('CONT-MATRIX-2026')
  const [procedureCode, setProcedureCode] = useState('99213')
  const [billedAmount, setBilledAmount] = useState('200.00')
  const [units, setUnits] = useState(1)
  const [modifiers, setModifiers] = useState('')

  const mutation = useMutation({
    mutationFn: () =>
      priceLine({
        contract_id: contractId,
        procedure_code: procedureCode,
        billed_amount: billedAmount,
        units,
        modifiers: modifiers ? modifiers.split(',').map((m) => m.trim()).filter(Boolean) : [],
      }),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    mutation.mutate()
  }

  return (
    <PageLayout
      title="Pricing Sandbox"
      description="Run a single line pricing request and view the result."
      metadata={<span>Contract and procedure code determine which rule and methodology apply.</span>}
    >
      <FormPanel title="Single line pricing" description="Enter claim line details and execute pricing.">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Contract ID"
              value={contractId}
              onChange={(e) => setContractId(e.target.value)}
              placeholder="e.g. CONT-MATRIX-2026 or 1"
            />
            <Input
              label="Procedure code"
              value={procedureCode}
              onChange={(e) => setProcedureCode(e.target.value)}
              placeholder="e.g. 99213"
            />
            <Input
              label="Billed amount"
              type="number"
              step="0.01"
              value={billedAmount}
              onChange={(e) => setBilledAmount(e.target.value)}
            />
            <Input
              label="Units"
              type="number"
              min={1}
              value={units}
              onChange={(e) => setUnits(Number(e.target.value))}
            />
            <Input
              label="Modifiers (comma-separated)"
              value={modifiers}
              onChange={(e) => setModifiers(e.target.value)}
              placeholder="e.g. 26, 50"
            />
          </div>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? <LoadingSpinner size="sm" /> : 'Price line'}
          </Button>
        </form>
        {mutation.isSuccess && (
          <div className="mt-4 rounded border border-slate-200 bg-slate-50 p-4 font-mono text-sm">
            <pre className="whitespace-pre-wrap">{JSON.stringify(mutation.data, null, 2)}</pre>
          </div>
        )}
        {mutation.isError && (
          <ErrorState
            title="Pricing failed"
            message={mutation.error?.message}
            onRetry={() => mutation.mutate()}
          />
        )}
      </FormPanel>
    </PageLayout>
  )
}
