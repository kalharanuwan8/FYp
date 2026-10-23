import Button from './Button';

export default function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
  className = '',
}) {
  return (
    <div className={`text-center py-12 px-6 ${className}`}>
      {Icon && (
        <div className="mx-auto mb-4 w-14 h-14 rounded-2xl bg-primary-soft text-primary flex items-center justify-center">
          <Icon className="w-7 h-7" aria-hidden="true" />
        </div>
      )}
      <h3 className="font-display text-xl font-bold text-text mb-2">{title}</h3>
      {description && (
        <p className="text-text-muted prose-narrow mx-auto mb-6">{description}</p>
      )}
      {actionLabel && onAction && (
        <Button onClick={onAction}>{actionLabel}</Button>
      )}
    </div>
  );
}
