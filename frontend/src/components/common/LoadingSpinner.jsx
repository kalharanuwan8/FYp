
export default function LoadingSpinner({ label = 'Loading…', className = '' }) {
  return (
    <div className={`flex flex-col items-center justify-center gap-3 py-12 ${className}`} role="status">
      <div
        className="w-10 h-10 rounded-full border-3 border-primary/30 border-t-primary animate-spin"
        style={{ borderWidth: 3 }}
        aria-hidden="true"
      />
      <span className="text-sm text-text-muted">{label}</span>
    </div>
  );
}
