/**
 * Client-side intervention previews (`intervention_id: null`).
 * Copy matches the engine messages so a manual trigger looks like a real prompt.
 * The server cannot force a noise notice or choose which tier-4 variant to fire,
 * so those always come from here. Responding just closes the overlay.
 */
const LOCAL_INTERVENTIONS = {
  ambient: {
    tier: 1,
    intervention_type: 'ambient_cue',
    message: "Let's refocus together!",
    payload: { trigger_source: 'manual' },
  },
  pacing: {
    tier: 2,
    intervention_type: 'pacing_pause',
    message: 'Still with me? Tap to continue.',
    payload: { trigger_source: 'manual' },
  },
  milestone: {
    tier: 3,
    intervention_type: 'milestone_quiz',
    message: 'Quick checkpoint — answer to continue.',
    payload: {
      trigger_source: 'manual',
      generated_question: 'What is the main idea of this material?',
      options: [
        'The core concept from the lesson',
        'An unrelated topic',
        'A homework deadline',
        'None of the above',
      ],
      hint_text: 'Skim the summary for the key idea.',
    },
  },
  pace: {
    tier: 4,
    intervention_type: 'content_pacing_reduction',
    message: "We'll slow the pace a bit so you can catch up.",
    payload: { trigger_source: 'manual', pacing_factor: 0.75 },
  },
  break: {
    tier: 4,
    intervention_type: 'suggest_break',
    message: 'Great effort! Time for a short break.',
    payload: { trigger_source: 'manual', break_seconds: 60 },
  },
  noise: {
    tier: 1,
    intervention_type: 'environment_noise_notice',
    message:
      "It's quite noisy where you are — that can make it hard to concentrate. What would you like to do?",
    payload: { trigger_source: 'manual' },
  },
};

export function buildLocalDemoIntervention(kind) {
  const spec = LOCAL_INTERVENTIONS[kind] || LOCAL_INTERVENTIONS.break;
  return {
    intervention_id: null,
    tier: spec.tier,
    intervention_type: spec.intervention_type,
    message: spec.message,
    payload: { ...spec.payload },
  };
}
