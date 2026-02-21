interface LoadingSpinnerProps {
  size?: 'sm' | 'md'
  className?: string
}

export function LoadingSpinner({ size = 'md', className = '' }: LoadingSpinnerProps) {
  const sizeClass = size === 'sm' ? 'h-5 w-5 border-2' : 'h-8 w-8 border-2'
  return (
    <div
      className={`inline-block animate-spin rounded-full border-slate-200 border-t-primary-600 ${sizeClass} ${className}`}
      role="status"
      aria-label="Loading"
    />
  )
}
