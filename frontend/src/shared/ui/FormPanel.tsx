interface FormPanelProps {
  title?: string
  description?: string
  children: React.ReactNode
  className?: string
}

export function FormPanel({ title, description, children, className = '' }: FormPanelProps) {
  return (
    <div className={`rounded border border-slate-200 bg-white shadow-sm ${className}`}>
      {(title || description) && (
        <div className="border-b border-slate-200 px-4 py-3">
          {title && <h3 className="text-sm font-semibold text-slate-900">{title}</h3>}
          {description && <p className="mt-0.5 text-sm text-slate-500">{description}</p>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  )
}
