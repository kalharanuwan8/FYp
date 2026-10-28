
const variants = {
  primary:
    'bg-primary text-on-primary hover:brightness-105 shadow-soft border border-transparent',
  secondary:
    'bg-surface text-text border border-border hover:bg-primary-soft',
  ghost: 'bg-transparent text-text-muted hover:bg-primary-soft hover:text-text',
  attention: 'bg-attention text-on-primary hover:brightness-105',
  success: 'bg-success text-on-primary hover:brightness-105',
};

const sizes = {
  sm: 'min-h-11 px-4 text-sm rounded-2xl',
  md: 'min-h-11 px-5 text-base rounded-2xl',
  lg: 'min-h-12 px-6 text-lg rounded-2xl',
};

export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  className = '',
  type = 'button',
  disabled,
  ...props
}) {
  return (
    <button
      type={type}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 font-semibold transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${variants[variant] || variants.primary} ${sizes[size] || sizes.md} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
