import { type ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'danger'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  children: React.ReactNode
}

const variantClasses: Record<Variant, string> = {
  primary: 'bg-primary-600 text-white hover:bg-primary-700 border-transparent',
  secondary: 'bg-slate-100 text-slate-700 hover:bg-slate-200 border-slate-300',
  danger: 'bg-red-600 text-white hover:bg-red-700 border-transparent',
}

export function Button({ variant = 'primary', className = '', disabled, children, ...props }: ButtonProps) {
  return (
    <button
      type="button"
      className={`
        inline-flex items-center justify-center gap-2 rounded border px-3 py-2 text-sm font-medium
        focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1
        disabled:cursor-not-allowed disabled:opacity-50
        ${variantClasses[variant]}
        ${className}
      `}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  )
}
