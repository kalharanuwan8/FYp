import AmbientCue from './AmbientCue';
import PacingPrompt from './PacingPrompt';
import GamifiedBreak from './GamifiedBreak';
import MilestoneQuiz from './MilestoneQuiz';
import StructuralNotice from './StructuralNotice';
import HintInjectionPanel from './HintInjection';
import NoiseNotice from './NoiseNotice';

/**
 * Routes intervention_type → concrete overlay.
 * Falls back to tier-based mapping for legacy payloads.
 */
export default function InterventionOverlay({
  intervention,
  onRespond,
  onPauseContent,
  inlineHint = false,
}) {
  if (!intervention) return null;

  const type = intervention.intervention_type;
  const tier = intervention.tier;
  const id = intervention.intervention_id;
  const message = intervention.message;
  const payload = intervention.payload || {};

  const handleRespond = (interventionId, outcome, extra = {}) => {
    if (onRespond) onRespond(interventionId, outcome, extra);
  };

  // Prefer explicit type; fall back to tier for older clients
  const resolved =
    type ||
    ({
      1: 'ambient_cue',
      2: 'pacing_pause',
      3: 'milestone_quiz',
      4: 'suggest_break',
    }[tier] || 'ambient_cue');

  if (resolved === 'hint_injection') {
    if (inlineHint) {
      return (
        <HintInjectionPanel
          message={message}
          payload={payload}
          interventionId={id}
          onRespond={handleRespond}
        />
      );
    }
    return (
      <div className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center bg-bg/60 p-4">
        <div className="max-w-md w-full">
          <HintInjectionPanel
            message={message}
            payload={payload}
            interventionId={id}
            onRespond={handleRespond}
          />
        </div>
      </div>
    );
  }

  if (resolved === 'environment_noise_notice') {
    return (
      <NoiseNotice
        message={message}
        interventionId={id}
        onRespond={handleRespond}
        onPauseContent={onPauseContent}
      />
    );
  }

  if (resolved === 'ambient_cue') {
    return (
      <AmbientCue message={message} interventionId={id} onRespond={handleRespond} />
    );
  }

  if (resolved === 'pacing_pause') {
    return (
      <PacingPrompt
        message={message}
        interventionId={id}
        onRespond={handleRespond}
        onPauseContent={onPauseContent}
      />
    );
  }

  if (resolved === 'milestone_quiz') {
    return (
      <MilestoneQuiz
        message={message}
        payload={payload}
        interventionId={id}
        onRespond={handleRespond}
      />
    );
  }

  if (resolved === 'gamified_break') {
    if (Array.isArray(payload?.options) && payload.options.length > 0) {
      return (
        <MilestoneQuiz
          message={message}
          payload={payload}
          interventionId={id}
          onRespond={handleRespond}
        />
      );
    }
    return (
      <GamifiedBreak
        message={message}
        payload={payload}
        interventionId={id}
        onRespond={handleRespond}
      />
    );
  }

  if (resolved === 'suggest_break') {
    return (
      <StructuralNotice
        interventionType="suggest_break"
        message={message}
        payload={payload}
        interventionId={id}
        onRespond={handleRespond}
      />
    );
  }

  if (resolved === 'content_pacing_reduction') {
    return (
      <StructuralNotice
        interventionType={resolved}
        message={message}
        payload={payload}
        interventionId={id}
        onRespond={handleRespond}
      />
    );
  }

  return (
    <AmbientCue message={message} interventionId={id} onRespond={handleRespond} />
  );
}
