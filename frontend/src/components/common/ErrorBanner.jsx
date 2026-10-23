import { AlertCircle } from 'lucide-react';

export default function ErrorBanner({ message, onDismiss, className = '' }) {
  if (!message) return null;
  return (
    <div
      className={`flex items-start gap-3 rounded-2xl border border-attention/40 bg-attention/10 text-text px-4 py-3 ${className}`}
      role="alert"
    >
      <AlertCircle className="w-5 h-5 text-attention shrink-0 mt-0.5" aria-hidden="true" />
      <p className="flex-1 text-sm">{message}</p>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="text-sm font-semibold text-text-muted hover:text-text min-h-11 px-2"
          aria-label="Dismiss"
        >
          Dismiss
        </button>
      )}
    </div>
  );
}
