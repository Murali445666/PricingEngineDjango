import { Input, Select } from '@/shared/ui'
import type { FeeSchedule } from '@/types'

interface ParameterEditorProps {
  methodologyCode: string
  multiplier: string
  onMultiplierChange: (v: string) => void
  flatRate: string
  onFlatRateChange: (v: string) => void
  baseFeeScheduleId: string
  onBaseFeeScheduleIdChange: (v: string) => void
  feeSchedules: FeeSchedule[]
  feeSchedulesLoading?: boolean
}

export function ParameterEditor({
  methodologyCode,
  multiplier,
  onMultiplierChange,
  flatRate,
  onFlatRateChange,
  baseFeeScheduleId,
  onBaseFeeScheduleIdChange,
  feeSchedules,
  feeSchedulesLoading,
}: ParameterEditorProps) {
  const methodology = methodologyCode || ''

  const feeScheduleOptions = [
    { value: '', label: '— Select fee schedule —' },
    ...feeSchedules.map((fs) => ({
      value: String(fs.fee_schedule_id),
      label: fs.name || `ID ${fs.fee_schedule_id}`,
    })),
  ]

  if (methodology === 'RBRVS') {
    return (
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          label="Multiplier"
          type="number"
          step="0.0001"
          min="0"
          value={multiplier}
          onChange={(e) => onMultiplierChange(e.target.value)}
          placeholder="e.g. 1.5"
        />
        <div>
          <Select
            label="Base fee schedule"
            options={feeScheduleOptions}
            value={baseFeeScheduleId}
            onChange={(e) => onBaseFeeScheduleIdChange(e.target.value)}
            disabled={feeSchedulesLoading}
          />
          {feeSchedulesLoading && (
            <p className="mt-1 text-xs text-slate-500">Loading fee schedules…</p>
          )}
        </div>
      </div>
    )
  }

  if (methodology === 'FLAT_RATE') {
    return (
      <Input
        label="Flat rate (amount)"
        type="number"
        step="0.01"
        min="0"
        value={flatRate}
        onChange={(e) => onFlatRateChange(e.target.value)}
        placeholder="e.g. 75.00"
      />
    )
  }

  return (
    <p className="text-sm text-slate-500">
      No parameters required for {methodology || 'this methodology'} in this editor.
    </p>
  )
}
