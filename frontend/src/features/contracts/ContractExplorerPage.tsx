import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PageLayout, FormPanel, Select } from '@/shared/ui'
import { fetchContracts } from '@/services/contractService'
import { ContractExplorerPanel } from './ContractExplorerPanel'
import type { Contract } from '@/types'

export function ContractExplorerPage() {
  const [contractId, setContractId] = useState<string>('')

  const { data: contracts = [], isLoading: contractsLoading } = useQuery({
    queryKey: ['contracts'],
    queryFn: fetchContracts,
  })

  const contractIdNum = contractId ? Number(contractId) : NaN

  const contractOptions: { value: string; label: string }[] = [
    { value: '', label: '— Select contract —' },
    ...contracts.map((c: Contract) => ({
      value: String(c.contract_id),
      label: `${c.contract_name ?? c.legacy_contract_number ?? c.contract_id} (${c.contract_id})`,
    })),
  ]

  return (
    <PageLayout
      title="Contract Explorer"
      description="Read-only tree: versions, methodologies, rules, carve-outs, caps/floors, blending, stop-loss, outlier. Use Download JSON / CSV for exports."
    >
      <div className="space-y-4">
        <FormPanel title="Contract" description="Select a contract to load its explorer tree.">
          <Select
            value={contractId}
            onChange={(e) => setContractId(e.target.value)}
            options={contractOptions}
            label="Contract"
            disabled={contractsLoading}
          />
        </FormPanel>

        {contractId && Number.isInteger(contractIdNum) && contractIdNum > 0 && (
          <ContractExplorerPanel contractId={contractIdNum} />
        )}
      </div>
    </PageLayout>
  )
}
