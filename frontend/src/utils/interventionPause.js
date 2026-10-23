/**
 * Which intervention types should pause lesson video playback.
 * Tier-1 ambient_cue is intentionally non-pausing (gentle cue only).
 */
export const VIDEO_PAUSING_INTERVENTION_TYPES = new Set([
  'pacing_pause',
  'milestone_quiz',
  'hint_injection',
  'content_pacing_reduction',
  'suggest_break',
  'gamified_break',
  'environment_noise_notice',
]);

/**
 * @param {object|null|undefined} intervention
 * @returns {boolean}
 */
export function interventionShouldPauseVideo(intervention) {
  if (!intervention) return false;
  const type =
    intervention.intervention_type ||
    ({
      1: 'ambient_cue',
      2: 'pacing_pause',
      3: 'milestone_quiz',
      4: 'suggest_break',
    }[intervention.tier] || 'ambient_cue');
  return VIDEO_PAUSING_INTERVENTION_TYPES.has(type);
}
