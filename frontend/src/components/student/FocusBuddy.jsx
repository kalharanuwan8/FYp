
/**
 * Calm focus indicator — green when on track, soft amber when wandering.
 * No "distracted", confidence, or model labels.
 */
export default function FocusBuddy({ onTrack = true, className = '' }) {
  const label = onTrack ? 'Focus buddy: on track' : "Focus buddy: let's get back on track";

  return (
    <div
      className={`flex items-center gap-2 ${className}`}
      role="status"
      aria-live="polite"
      aria-label={label}
      title={label}
    >
      <span
        className={`w-3.5 h-3.5 rounded-full ${
          onTrack ? 'buddy-ring-good' : 'buddy-ring-wander'
        }`}
        style={{
          animation: 'buddy-breathe 2.8s ease-in-out infinite',
        }}
      />
      <span className="text-xs font-semibold text-text-muted hidden sm:inline">
        Focus buddy
      </span>
    </div>
  );
}
