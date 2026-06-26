import { Button } from '@/shared/ui'
import type { RepriceClaimLineInput } from '@/types/reprice'

export function createEmptyClaimLine(overrides?: Partial<RepriceClaimLineInput>): RepriceClaimLineInput {
  return {
    procedure_code: '',
    units: 1,
    modifier_1: '',
    modifier_2: '',
    modifier_3: '',
    modifier_4: '',
    billed_amount: '',
    ...overrides,
  }
}

function modifiersToDisplay(line: RepriceClaimLineInput): string {
  return [line.modifier_1, line.modifier_2, line.modifier_3, line.modifier_4]
    .filter(Boolean)
    .join(', ')
}

function displayToModifiers(value: string): Pick<RepriceClaimLineInput, 'modifier_1' | 'modifier_2' | 'modifier_3' | 'modifier_4'> {
  const parts = value
    .split(',')
    .map((m) => m.trim())
    .filter(Boolean)
    .slice(0, 4)
  return {
    modifier_1: parts[0] ?? '',
    modifier_2: parts[1] ?? '',
    modifier_3: parts[2] ?? '',
    modifier_4: parts[3] ?? '',
  }
}

interface ClaimLineEntryGridProps {
  lines: RepriceClaimLineInput[]
  onChange: (lines: RepriceClaimLineInput[]) => void
  disabled?: boolean
}

export function ClaimLineEntryGrid({ lines, onChange, disabled = false }: ClaimLineEntryGridProps) {
  const updateLine = (index: number, patch: Partial<RepriceClaimLineInput>) => {
    onChange(lines.map((line, i) => (i === index ? { ...line, ...patch } : line)))
  }

  const addLine = () => {
    onChange([...lines, createEmptyClaimLine()])
  }

  const removeLine = (index: number) => {
    if (lines.length <= 1) return
    onChange(lines.filter((_, i) => i !== index))
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-3 py-2 font-medium">#</th>
              <th className="px-3 py-2 font-medium">Procedure</th>
              <th className="px-3 py-2 font-medium">Units</th>
              <th className="px-3 py-2 font-medium">Modifiers</th>
              <th className="px-3 py-2 font-medium">Billed</th>
              <th className="px-3 py-2 font-medium"> </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {lines.map((line, index) => (
              <tr key={index}>
                <td className="px-3 py-2 text-slate-500">{index + 1}</td>
                <td className="px-3 py-2">
                  <input
                    type="text"
                    value={line.procedure_code}
                    onChange={(e) => updateLine(index, { procedure_code: e.target.value })}
                    disabled={disabled}
                    placeholder="99213"
                    className="block w-full min-w-[5rem] rounded border border-slate-300 px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:bg-slate-50"
                  />
                </td>
                <td className="px-3 py-2">
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    value={line.units ?? 1}
                    onChange={(e) => updateLine(index, { units: e.target.value })}
                    disabled={disabled}
                    className="block w-20 rounded border border-slate-300 px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:bg-slate-50"
                  />
                </td>
                <td className="px-3 py-2">
                  <input
                    type="text"
                    value={modifiersToDisplay(line)}
                    onChange={(e) => updateLine(index, displayToModifiers(e.target.value))}
                    disabled={disabled}
                    placeholder="26, 50"
                    className="block w-full min-w-[6rem] rounded border border-slate-300 px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:bg-slate-50"
                  />
                </td>
                <td className="px-3 py-2">
                  <input
                    type="number"
                    step="0.01"
                    value={line.billed_amount ?? ''}
                    onChange={(e) => updateLine(index, { billed_amount: e.target.value })}
                    disabled={disabled}
                    placeholder="200.00"
                    className="block w-28 rounded border border-slate-300 px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:bg-slate-50"
                  />
                </td>
                <td className="px-3 py-2">
                  <Button
                    type="button"
                    variant="secondary"
                    className="!px-2 !py-1 !text-xs"
                    onClick={() => removeLine(index)}
                    disabled={disabled || lines.length <= 1}
                  >
                    Remove
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button type="button" variant="secondary" className="!py-1.5 !text-xs" onClick={addLine} disabled={disabled}>
        Add line
      </Button>
    </div>
  )
}

/** Validate lines before submit; returns error message or null */
export function validateClaimLines(lines: RepriceClaimLineInput[]): string | null {
  if (lines.length === 0) return 'At least one claim line is required.'
  for (let i = 0; i < lines.length; i++) {
    if (!lines[i].procedure_code?.trim()) {
      return `Line ${i + 1}: procedure code is required.`
    }
  }
  return null
}
