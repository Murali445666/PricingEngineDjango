import { Button, Input, Select } from '@/shared/ui'
import type { RuleConditionRow } from '@/types'

const ALLOWED_ATTRIBUTE_NAMES = [
  { value: 'procedure_code', label: 'Procedure code' },
  { value: 'code', label: 'Code (alias)' },
  { value: 'modifier', label: 'Modifier' },
  { value: 'plan_id', label: 'Plan ID' },
  { value: 'group_id', label: 'Group ID' },
  { value: 'provider_id', label: 'Provider ID' },
]

const OPERATOR_EQ = 'EQ'

interface ConditionBuilderProps {
  value: RuleConditionRow[]
  onChange: (conditions: RuleConditionRow[]) => void
}

export function ConditionBuilder({ value, onChange }: ConditionBuilderProps) {
  const addRow = () => {
    onChange([
      ...value,
      { attribute_name: 'procedure_code', operator: OPERATOR_EQ, attribute_value: '' },
    ])
  }

  const removeRow = (index: number) => {
    onChange(value.filter((_, i) => i !== index))
  }

  const updateRow = (index: number, field: keyof RuleConditionRow, fieldValue: string) => {
    const next = value.map((row, i) =>
      i === index ? { ...row, [field]: fieldValue } : row
    )
    onChange(next)
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700">Conditions</span>
        <Button type="button" variant="secondary" onClick={addRow}>
          Add condition
        </Button>
      </div>
      {value.length === 0 && (
        <p className="text-sm text-slate-500">No conditions. Add at least one to match claims.</p>
      )}
      <ul className="space-y-2">
        {value.map((row, index) => (
          <li
            key={index}
            className="flex flex-wrap items-end gap-2 rounded border border-slate-200 bg-slate-50/50 p-2"
          >
            <Select
              label="Field"
              options={ALLOWED_ATTRIBUTE_NAMES}
              value={row.attribute_name}
              onChange={(e) => updateRow(index, 'attribute_name', e.target.value)}
              className="min-w-[140px]"
            />
            <div className="flex min-w-[60px] items-end pb-2">
              <span className="text-sm font-medium text-slate-500">EQ</span>
            </div>
            <Input
              label="Value"
              value={row.attribute_value}
              onChange={(e) => updateRow(index, 'attribute_value', e.target.value)}
              placeholder="e.g. 99213"
              className="min-w-[120px] flex-1"
            />
            <Button
              type="button"
              variant="secondary"
              onClick={() => removeRow(index)}
              className="shrink-0"
            >
              Remove
            </Button>
          </li>
        ))}
      </ul>
    </div>
  )
}
