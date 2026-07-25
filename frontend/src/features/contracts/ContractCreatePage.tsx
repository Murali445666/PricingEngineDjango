import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { PageLayout, FormPanel, Button, Input, Select, ErrorState } from '@/shared/ui'
import { createContract } from '@/services/contractService'
import type { ContractCreatePayload } from '@/types'

const ORIGIN_OPTIONS = [
  { value: 'DIRECT', label: 'Direct' },
  { value: 'LEASED', label: 'Leased' },
  { value: 'DELEGATED', label: 'Delegated' },
]

const LOB_OPTIONS = [
  { value: 'COMMERCIAL', label: 'Commercial' },
  { value: 'MEDICARE', label: 'Medicare' },
  { value: 'MEDICAID', label: 'Medicaid' },
]

export function ContractCreatePage() {
  const navigate = useNavigate()
  const [contractName, setContractName] = useState('')
  const [legacyNumber, setLegacyNumber] = useState('')
  const [payerOrg, setPayerOrg] = useState('10')
  const [providerOrg, setProviderOrg] = useState('KEYSTONE-IDN')
  const [network, setNetwork] = useState('HIGHMARK-PPO')
  const [lob, setLob] = useState('COMMERCIAL')
  const [originType, setOriginType] = useState<'DIRECT' | 'LEASED' | 'DELEGATED'>('DIRECT')
  const [priority, setPriority] = useState('10')
  const [startDate, setStartDate] = useState('2025-04-17')
  const [endDate, setEndDate] = useState('')

  const mutation = useMutation({
    mutationFn: (payload: ContractCreatePayload) => createContract(payload),
    onSuccess: (contract) => {
      navigate(`/contracts/${contract.contract_id}/summary`, { replace: true })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const payer = parseInt(payerOrg, 10)
    const prio = parseInt(priority, 10)
    if (!contractName.trim() || !legacyNumber.trim() || !providerOrg.trim() || !network.trim()) {
      window.alert('Fill in contract name, legacy number, provider org, and network.')
      return
    }
    if (Number.isNaN(payer)) {
      window.alert('Payer org must be a numeric ID.')
      return
    }
    mutation.mutate({
      contract_name: contractName.trim(),
      legacy_contract_number: legacyNumber.trim(),
      payer_org: payer,
      provider_org: providerOrg.trim(),
      network: network.trim(),
      line_of_business: lob,
      effective_start_date: startDate,
      effective_end_date: endDate.trim() || null,
      contract_origin_type: originType,
      resolution_priority: Number.isNaN(prio) ? 10 : prio,
    })
  }

  return (
    <PageLayout
      title="New agreement"
      description="Create a DRAFT contract with an initial DRAFT version 1. DRAFT contracts do not resolve for live repricing until published."
      metadata={
        <Link to="/contracts" className="text-primary-600 hover:underline">
          ← Back to contracts
        </Link>
      }
    >
      {mutation.error && (
        <ErrorState title="Create failed" message={(mutation.error as Error).message} />
      )}

      <form onSubmit={handleSubmit}>
        <FormPanel title="Contract header">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Contract name"
              value={contractName}
              onChange={(e) => setContractName(e.target.value)}
              required
            />
            <Input
              label="Legacy contract number"
              value={legacyNumber}
              onChange={(e) => setLegacyNumber(e.target.value)}
              required
            />
            <Input
              label="Payer org ID"
              value={payerOrg}
              onChange={(e) => setPayerOrg(e.target.value)}
            />
            <Input
              label="Provider org ID"
              value={providerOrg}
              onChange={(e) => setProviderOrg(e.target.value)}
            />
            <Input
              label="Network ID"
              value={network}
              onChange={(e) => setNetwork(e.target.value)}
            />
            <Select label="Line of business" value={lob} onChange={(e) => setLob(e.target.value)} options={LOB_OPTIONS} />
            <Select
              label="Contract origin"
              value={originType}
              onChange={(e) => setOriginType(e.target.value as typeof originType)}
              options={ORIGIN_OPTIONS}
            />
            <Input
              label="Resolution priority"
              type="number"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
            />
            <Input
              label="Effective start"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              required
            />
            <Input
              label="Effective end"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>

          <div className="mt-6 flex gap-2">
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? 'Creating…' : 'Create DRAFT agreement'}
            </Button>
            <Button type="button" variant="secondary" onClick={() => navigate('/contracts')}>
              Cancel
            </Button>
          </div>
        </FormPanel>
      </form>
    </PageLayout>
  )
}
