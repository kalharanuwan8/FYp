/**
 * Calm focus indicator.
 * - FOCUSED → on track (teal)
 * - DISTRACTED → quiet wander (amber)
 * - UNKNOWN / missing → neutral (not "on track", not alarming distracted)
 * No continuous animation or fabricated confidence.
 */
export default function FocusBuddy({ onTrack = true, unknown = false, className = '' }) {
  let label = "Focus buddy: let's get back on track";
  let ringClass = 'buddy-ring-wander';
  if (unknown) {
    label = 'Focus buddy: signal unclear';
    ringClass = 'buddy-ring-unknown';
  } else if (onTrack) {
    label = 'Focus buddy: on track';
    ringClass = 'buddy-ring-good';
  }

  return (
    <div
      className={`flex items-center gap-2 ${className}`}
      role="status"
      aria-live="polite"
      aria-label={label}
      title={label}
    >
      <span
        className={`w-3 h-3 rounded-full border border-border ${ringClass}`}
        aria-hidden="true"
      />
      <span className="text-xs font-semibold text-text-muted hidden sm:inline">
        Focus buddy
      </span>
    </div>
  );
}
