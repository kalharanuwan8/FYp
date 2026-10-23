
export default function BadgeChip({ icon = '⭐', name, description, earned = true, className = '' }) {
  return (
    <div
      className={`flex items-center gap-3 rounded-2xl border px-3 py-3 transition-opacity ${
        earned
          ? 'bg-surface border-border shadow-soft'
          : 'bg-bg border-border opacity-50'
      } ${className}`}
      title={description}
    >
      <span
        className="w-11 h-11 rounded-full flex items-center justify-center text-xl bg-primary-soft"
        aria-hidden="true"
      >
        {icon}
      </span>
      <div className="min-w-0">
        <p className="font-display font-bold text-sm text-text truncate">{name}</p>
        {description && (
          <p className="text-xs text-text-muted line-clamp-2">{description}</p>
        )}
        <p className={`text-xs font-semibold ${earned ? 'text-success' : 'text-text-muted'}`}>
          {earned ? 'Earned' : 'Not yet earned'}
        </p>
      </div>
    </div>
  );
}
