/**
 * Soft tinted pill for labels (role, module, session count, LIVE, etc.).
 * Uses theme tokens — never hard-codes palette colours.
 */
const tones = {
  primary: 'bg-primary-soft text-primary border-transparent',
  muted: 'bg-bg text-text-muted border-border',
  success: 'bg-success/15 text-success border-transparent',
  attention: 'bg-attention/15 text-attention border-transparent',
  warning: 'bg-warning/15 text-warning border-transparent',
  sun: 'bg-sun/15 text-sun border-transparent',
  peach: 'bg-peach/15 text-peach border-transparent',
};

export default function StatusBadge({
  children,
  tone = 'primary',
  className = '',
  as: Tag = 'span',
  ...props
}) {
  return (
    <Tag
      className={`inline-flex items-center gap-1.5 min-h-7 px-2.5 rounded-xl text-xs font-semibold border ${
        tones[tone] || tones.primary
      } ${className}`}
      {...props}
    >
      {children}
    </Tag>
  );
}
