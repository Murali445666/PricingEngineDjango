interface PageLayoutProps {
  title: string
  description?: string
  metadata?: React.ReactNode
  children: React.ReactNode
}

export function PageLayout({ title, description, metadata, children }: PageLayoutProps) {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
      </div>
      {metadata && (
        <div className="rounded border border-slate-200 bg-slate-50/50 px-4 py-3 text-sm text-slate-600">
          {metadata}
        </div>
      )}
      <div className="min-h-[200px]">{children}</div>
    </div>
  )
}
