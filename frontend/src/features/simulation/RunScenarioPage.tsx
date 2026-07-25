import { useState, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PageLayout, FormPanel, Button, Select, LoadingSpinner, ErrorState } from '@/shared/ui'
import { fetchContracts } from '@/services/contractService'
import { priceClaim } from '@/services/pricingService'
import type { PriceClaimResponse, PriceClaimLine } from '@/services/pricingService'
import type { Contract } from '@/types'

const defaultLine: PriceClaimLine = {
  procedure_code: '',
  billed_amount: 0,
  units: 1,
  modifiers: [],
}

function parseCsvLines(csvText: string): PriceClaimLine[] {
  const lines = csvText.trim().split(/\r?\n/)
  if (lines.length === 0) return []
  const header = lines[0].toLowerCase().split(',').map((h) => h.trim())
  const codeIdx = header.findIndex((h) => h === 'procedure_code' || h === 'code')
  const billedIdx = header.findIndex((h) => h === 'billed_amount' || h === 'billed')
  const unitsIdx = header.findIndex((h) => h === 'units')
  const modIdx = header.findIndex((h) => h === 'modifiers')
  if (codeIdx === -1 || billedIdx === -1) return []
  const out: PriceClaimLine[] = []
  for (let i = 1; i < lines.length; i++) {
    const cells = lines[i].split(',').map((c) => c.trim())
    const procedure_code = cells[codeIdx] ?? ''
    const billed_amount = parseFloat(cells[billedIdx] ?? '0') || 0
    const units = unitsIdx >= 0 ? parseInt(cells[unitsIdx] ?? '1', 10) || 1 : 1
    let modifiers: string[] = []
    if (modIdx >= 0 && cells[modIdx]) {
      modifiers = cells[modIdx].split(/[\s;]+/).filter(Boolean)
    }
    if (procedure_code) out.push({ procedure_code, billed_amount, units, modifiers })
  }
  return out
}

export function RunScenarioPage() {
  const [contractId, setContractId] = useState<string>('')
  const [lines, setLines] = useState<PriceClaimLine[]>([{ ...defaultLine }])
  const [result, setResult] = useState<PriceClaimResponse | null>(null)
  const [submittedLines, setSubmittedLines] = useState<PriceClaimLine[]>([])
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: contracts = [], isLoading: contractsLoading, error: contractsError, refetch: refetchContracts } = useQuery({
    queryKey: ['contracts'],
    queryFn: () => fetchContracts(),
  })

  const contractOptions = [
    { value: '', label: 'Select contract…' },
    ...contracts.map((c: Contract) => ({ value: String(c.contract_id), label: `${c.contract_name} (${c.contract_id})` })),
  ]

  function addRow() {
    setLines((prev) => [...prev, { ...defaultLine }])
  }

  function removeRow(i: number) {
    setLines((prev) => prev.filter((_, idx) => idx !== i))
  }

  function updateRow(i: number, field: keyof PriceClaimLine, value: string | number | string[]) {
    setLines((prev) => {
      const next = [...prev]
      next[i] = { ...next[i], [field]: value }
      return next
    })
  }

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      const text = String(reader.result)
      const parsed = parseCsvLines(text)
      if (parsed.length > 0) setLines(parsed)
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  async function handleRun() {
    if (!contractId) {
      setError('Select a contract.')
      return
    }
    const valid = lines.filter((l) => l.procedure_code.trim() && Number(l.billed_amount) >= 0)
    if (valid.length === 0) {
      setError('Add at least one line with procedure code and billed amount.')
      return
    }
    setError(null)
    setResult(null)
    setSubmittedLines(valid)
    setRunning(true)
    try {
      const res = await priceClaim({
        contract_id: contractId,
        lines: valid.map((l) => ({
          procedure_code: l.procedure_code.trim(),
          billed_amount: Number(l.billed_amount),
          units: l.units ?? 1,
          modifiers: l.modifiers ?? [],
        })),
      })
      setResult(res)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <PageLayout
      title="Run scenario"
      description="Run a batch of claim lines against a contract and see per-line results."
      metadata={<span>Uses contract pricing rules; results show allowed amount and methodology per line.</span>}
    >
      <div className="space-y-6">
        {contractsLoading && (
          <div className="flex justify-center py-8">
            <LoadingSpinner />
          </div>
        )}
        {contractsError && (
          <ErrorState
            title="Failed to load contracts"
            message={(contractsError as Error).message}
            onRetry={() => refetchContracts()}
          />
        )}
        {!contractsLoading && !contractsError && (
          <>
            <FormPanel title="Scenario" description="Select contract and add claim lines (or upload CSV).">
              <div className="mb-4">
                <Select
                  label="Contract"
                  options={contractOptions}
                  value={contractId}
                  onChange={(e) => { setContractId(e.target.value); setResult(null) }}
                />
              </div>
              <div className="mb-2 flex items-center gap-2">
                <Button variant="secondary" onClick={addRow}>Add line</Button>
                <Button variant="secondary" onClick={() => fileInputRef.current?.click()}>Upload CSV</Button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.txt"
                  className="hidden"
                  onChange={handleFile}
                />
                <span className="text-sm text-slate-500">CSV: procedure_code, billed_amount, units, modifiers</span>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full border border-slate-200 text-sm">
                  <thead>
                    <tr className="bg-slate-50">
                      <th className="border border-slate-200 px-2 py-1 text-left">Procedure code</th>
                      <th className="border border-slate-200 px-2 py-1 text-left">Billed</th>
                      <th className="border border-slate-200 px-2 py-1 text-left">Units</th>
                      <th className="border border-slate-200 px-2 py-1 text-left">Modifiers</th>
                      <th className="w-16 border border-slate-200 px-2 py-1" />
                    </tr>
                  </thead>
                  <tbody>
                    {lines.map((line, i) => (
                      <tr key={i}>
                        <td className="border border-slate-200 px-2 py-1">
                          <input
                            className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
                            value={line.procedure_code}
                            onChange={(e) => updateRow(i, 'procedure_code', e.target.value)}
                            placeholder="e.g. 99213"
                          />
                        </td>
                        <td className="border border-slate-200 px-2 py-1">
                          <input
                            type="number"
                            step="0.01"
                            className="w-24 rounded border border-slate-300 px-2 py-1 text-sm"
                            value={line.billed_amount || ''}
                            onChange={(e) => updateRow(i, 'billed_amount', e.target.value === '' ? 0 : parseFloat(e.target.value))}
                          />
                        </td>
                        <td className="border border-slate-200 px-2 py-1">
                          <input
                            type="number"
                            min={1}
                            className="w-16 rounded border border-slate-300 px-2 py-1 text-sm"
                            value={line.units ?? 1}
                            onChange={(e) => updateRow(i, 'units', parseInt(e.target.value, 10) || 1)}
                          />
                        </td>
                        <td className="border border-slate-200 px-2 py-1">
                          <input
                            className="w-32 rounded border border-slate-300 px-2 py-1 text-sm"
                            value={Array.isArray(line.modifiers) ? line.modifiers.join(', ') : ''}
                            onChange={(e) => updateRow(i, 'modifiers', e.target.value ? e.target.value.split(/[\s,]+/).filter(Boolean) : [])}
                            placeholder="26, 50"
                          />
                        </td>
                        <td className="border border-slate-200 px-2 py-1">
                          <button type="button" className="text-red-600 hover:underline" onClick={() => removeRow(i)}>Remove</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-4 flex items-center gap-2">
                <Button onClick={handleRun} disabled={running}>
                  {running ? 'Running…' : 'Run scenario'}
                </Button>
                {error && <span className="text-sm text-red-600">{error}</span>}
              </div>
            </FormPanel>

            {result && (
              <FormPanel title="Results" description="Per-line allowed amount and methodology.">
                <div className="mb-2 text-sm">
                  <span className="font-medium text-slate-700">Total allowed:</span>{' '}
                  {result.total_allowed.toFixed(2)} · {result.line_count} line(s)
                  {result.request_time_ms != null && ` · ${result.request_time_ms} ms`}
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full border border-slate-200 text-sm">
                    <thead>
                      <tr className="bg-slate-50">
                        <th className="border border-slate-200 px-2 py-1 text-left">#</th>
                        <th className="border border-slate-200 px-2 py-1 text-left">Procedure</th>
                        <th className="border border-slate-200 px-2 py-1 text-right">Billed</th>
                        <th className="border border-slate-200 px-2 py-1 text-right">Allowed</th>
                        <th className="border border-slate-200 px-2 py-1 text-left">Rule</th>
                        <th className="border border-slate-200 px-2 py-1 text-left">Methodology</th>
                        <th className="border border-slate-200 px-2 py-1 text-left">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.lines.map((line, i) => {
                        const inputLine = submittedLines[i]
                        return (
                          <tr key={i}>
                            <td className="border border-slate-200 px-2 py-1">{i + 1}</td>
                            <td className="border border-slate-200 px-2 py-1">{inputLine?.procedure_code ?? '—'}</td>
                            <td className="border border-slate-200 px-2 py-1 text-right">
                              {inputLine?.billed_amount != null ? Number(inputLine.billed_amount).toFixed(2) : '—'}
                            </td>
                            <td className="border border-slate-200 px-2 py-1 text-right">
                              {typeof line.allowed_amount === 'number' ? line.allowed_amount.toFixed(2) : String(line.allowed_amount)}
                            </td>
                            <td className="border border-slate-200 px-2 py-1">{line.rule_id ?? '—'}</td>
                            <td className="border border-slate-200 px-2 py-1">{line.methodology ?? '—'}</td>
                            <td className="border border-slate-200 px-2 py-1">{line.status}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </FormPanel>
            )}
          </>
        )}
      </div>
    </PageLayout>
  )
}
