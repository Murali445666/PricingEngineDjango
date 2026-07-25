import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, FormPanel, LoadingSpinner } from '@/shared/ui'
import { commitRateExhibit, previewRateExhibit } from '@/services/contractService'
import type { RateExhibitPreview } from '@/types'

interface RateExhibitPanelProps {
  contractId: number
  versionId: number | null
}

export function RateExhibitPanel({ contractId, versionId }: RateExhibitPanelProps) {
  const queryClient = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [year, setYear] = useState(2025)
  const [preview, setPreview] = useState<RateExhibitPreview | null>(null)
  const [error, setError] = useState<string | null>(null)

  const uploadOptions = versionId != null ? { year, versionId } : { year }

  const previewMutation = useMutation({
    mutationFn: (file: File) => previewRateExhibit(contractId, file, uploadOptions),
    onSuccess: (data) => {
      setPreview(data)
      setError(null)
    },
    onError: (err: Error) => setError(err.message),
  })

  const commitMutation = useMutation({
    mutationFn: (file: File) => commitRateExhibit(contractId, file, uploadOptions),
    onSuccess: () => {
      setPreview(null)
      setSelectedFile(null)
      if (fileRef.current) fileRef.current.value = ''
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['contract-rules', String(contractId)] })
      void queryClient.invalidateQueries({ queryKey: ['contract-explorer', String(contractId)] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null
    setSelectedFile(file)
    setPreview(null)
    setError(null)
  }

  const runPreview = () => {
    if (!selectedFile) {
      setError('Choose an Exhibit C CSV file first.')
      return
    }
    if (versionId == null) {
      setError('No DRAFT version found for this contract.')
      return
    }
    previewMutation.mutate(selectedFile)
  }

  const runCommit = () => {
    if (!selectedFile) {
      setError('Choose an Exhibit C CSV file first.')
      return
    }
    if (versionId == null) {
      setError('No DRAFT version found for this contract.')
      return
    }
    if (!window.confirm('Commit will upsert rules and remove rows not in the CSV. Continue?')) return
    commitMutation.mutate(selectedFile)
  }

  return (
    <FormPanel title="Rate exhibit (Exhibit C)" className="mb-6">
      <p className="mb-3 text-sm text-slate-600">
        Upload <code className="text-xs">Exhibit_C_Fee_Schedule.csv</code> — preview shows added/changed/removed
        rows before commit. Uses natural-key upsert so rule IDs stay stable on re-import.
      </p>

      {versionId == null && (
        <p className="mb-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          No DRAFT contract version available. Create a contract or add a DRAFT version before loading rates.
        </p>
      )}

      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">CSV file</label>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            onChange={onFileChange}
            className="block text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Materialized year</label>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="rounded border border-slate-300 px-2 py-1.5 text-sm"
          >
            <option value={2025}>2025 (allowed_2025)</option>
            <option value={2026}>2026 (allowed_2026)</option>
          </select>
        </div>
        <Button type="button" variant="secondary" onClick={runPreview} disabled={previewMutation.isPending || !selectedFile}>
          {previewMutation.isPending ? 'Previewing…' : 'Preview diff'}
        </Button>
        <Button
          type="button"
          onClick={runCommit}
          disabled={commitMutation.isPending || !selectedFile || !preview}
        >
          {commitMutation.isPending ? 'Committing…' : 'Commit'}
        </Button>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
      )}

      {(previewMutation.isPending || commitMutation.isPending) && (
        <div className="flex justify-center py-4">
          <LoadingSpinner />
        </div>
      )}

      {commitMutation.isSuccess && (
        <div className="mb-3 rounded border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">
          Commit complete — rules updated. Refresh the rules table below.
        </div>
      )}

      {preview && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-4 text-sm">
            <span>
              <strong className="text-green-700">{preview.counts.added}</strong> added
            </span>
            <span>
              <strong className="text-amber-700">{preview.counts.changed}</strong> changed
            </span>
            <span>
              <strong className="text-red-700">{preview.counts.removed}</strong> removed
            </span>
            {preview.counts.skipped > 0 && (
              <span className="text-slate-500">{preview.counts.skipped} skipped</span>
            )}
          </div>

          {preview.sample.length > 0 && (
            <div className="overflow-x-auto rounded border border-slate-200">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-3 py-2 font-medium">Change</th>
                    <th className="px-3 py-2 font-medium">Code</th>
                    <th className="px-3 py-2 font-medium">Entity</th>
                    <th className="px-3 py-2 font-medium">Rate</th>
                    <th className="px-3 py-2 font-medium">Methodology</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {preview.sample.map((row, i) => (
                    <tr key={`${row.change_type}-${row.procedure_code}-${i}`}>
                      <td className="px-3 py-2 capitalize">{row.change_type}</td>
                      <td className="px-3 py-2 font-mono text-xs">{row.procedure_code}</td>
                      <td className="px-3 py-2">{row.covered_entity}</td>
                      <td className="px-3 py-2">
                        {row.change_type === 'changed' && row.previous_flat_rate ? (
                          <span>
                            {row.previous_flat_rate} → {row.flat_rate}
                          </span>
                        ) : (
                          row.flat_rate ?? '—'
                        )}
                      </td>
                      <td className="px-3 py-2">{row.methodology_code ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </FormPanel>
  )
}
