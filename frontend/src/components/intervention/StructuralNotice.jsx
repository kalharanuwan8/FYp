import GamifiedBreak from './GamifiedBreak';
import Dialog from '../common/Dialog';

/** Tier 4 — suggest_break opens the breathing break; pacing stays a soft notice. */
export default function StructuralNotice({
  interventionType,
  message,
  payload,
  onRespond,
  interventionId,
}) {
  const isBreak = interventionType === 'suggest_break';

  if (isBreak) {
    return (
      <GamifiedBreak
        message={message || 'Time for a short stretch break.'}
        payload={{ ...payload, break_seconds: payload?.break_seconds || 60 }}
        onRespond={onRespond}
        interventionId={interventionId}
      />
    );
  }

  return (
    <Dialog
      title="Let's slow down a little"
      description={
        message ||
        "We'll play the video a little slower so it's easier to follow. You can keep learning at this pace."
      }
      allowEscape={false}
    >
      <p className="text-center text-3xl" aria-hidden="true">
        🐢
      </p>
      {payload?.pacing_factor && (
        <p className="text-sm text-primary font-semibold text-center">
          We&apos;ll play the video a little slower (at{' '}
          {Math.round(Number(payload.pacing_factor) * 100)}% speed) for now.
        </p>
      )}
      <div className="space-y-2">
        <button
          type="button"
          onClick={() => onRespond(interventionId, 'reengaged')}
          className="w-full min-h-12 rounded-2xl bg-primary text-on-primary text-base font-semibold cursor-pointer"
        >
          Got it — continue
        </button>
        <button
          type="button"
          onClick={() => onRespond(interventionId, 'ignored')}
          className="w-full min-h-11 text-sm font-semibold text-text-muted cursor-pointer"
        >
          Dismiss
        </button>
      </div>
    </Dialog>
  );
}
