/**
 * Lightweight regression check for ambient-cue pause behaviour.
 * Run: node frontend/scripts/check_intervention_pause.mjs
 */
import {
  interventionShouldPauseVideo,
  VIDEO_PAUSING_INTERVENTION_TYPES,
} from '../src/utils/interventionPause.js';

function assert(cond, msg) {
  if (!cond) {
    console.error('FAIL:', msg);
    process.exitCode = 1;
  } else {
    console.log('ok:', msg);
  }
}

assert(
  !interventionShouldPauseVideo({ intervention_type: 'ambient_cue', tier: 1 }),
  'ambient_cue must not pause video'
);
assert(
  !interventionShouldPauseVideo({ tier: 1 }),
  'tier-1 fallback (ambient) must not pause video'
);
assert(
  interventionShouldPauseVideo({ intervention_type: 'pacing_pause', tier: 2 }),
  'pacing_pause must pause video'
);
assert(
  interventionShouldPauseVideo({ intervention_type: 'milestone_quiz', tier: 3 }),
  'milestone_quiz must pause video'
);
assert(
  interventionShouldPauseVideo({ intervention_type: 'suggest_break', tier: 4 }),
  'suggest_break must pause video'
);
assert(
  interventionShouldPauseVideo({
    intervention_type: 'environment_noise_notice',
    tier: 1,
  }),
  'noise notice must pause video'
);
assert(
  !VIDEO_PAUSING_INTERVENTION_TYPES.has('ambient_cue'),
  'ambient_cue not in pausing set'
);

if (!process.exitCode) {
  console.log('All intervention pause checks passed.');
}
