/**
 * PLAN 7 — turn heartbeat responses into plain-language lines for the
 * evaluation terminal. Pure functions (no React) so they can be unit-tested.
 */

const num = (v) => typeof v === 'number' && Number.isFinite(v);
const s1 = (v) => (num(v) ? v.toFixed(1) : '?');
const s2 = (v) => (num(v) ? v.toFixed(2) : '—');
const pct = (v) => (num(v) ? `${Math.round(v * 100)}%` : '—');

export const INTERVENTION_LABELS = {
  ambient_cue: 'ambient cue',
  pacing_pause: 'pacing pause',
  gamified_break: 'gamified break',
  milestone_quiz: 'milestone quiz',
  hint_injection: 'hint',
  content_pacing_reduction: 'content pacing reduction',
  suggest_break: 'break suggestion',
  environment_noise_notice: 'noise notice',
};

export const REASON_TEXT = {
  tab_hidden: 'tab hidden — student switched away from the lesson',
  window_blur: 'browser window not focused',
  body_no_face: 'face not visible, body still in view (turned away?)',
  absent: 'left the desk — no face or body in view',
  no_face: 'no face detected',
  low_face: 'face only partly visible — not scored',
  calibrating: 'calibrating personal baseline',
  warming_up: 'warming up — collecting frames',
  not_monitored: 'session not monitored',
  browser_signal_only: 'tab hidden — no camera frames this beat',
  no_frame_data: 'no camera frames received',
  stale_frames: 'frames older than the last one — skipped',
  ml_unavailable: 'ML pipeline unavailable',
  inference_exception: 'inference error on the server',
  test_injected: 'verdict injected by test',
  heuristic_gate: 'heuristic gate (no fusion model)',
};

export const DECISION_TEXT = {
  focused: () => 'on track — nothing to do',
  unknown: () => 'signal unclear — no open episode',
  unknown_hold: (d) => `signal unclear — episode clock paused at ${s1(d.episode_sec)}s`,
  too_short: (d) => `episode ${s1(d.episode_sec)}s — too short to act (needs ≥5s)`,
  pending: (d) =>
    d.pending
      ? `prompt T${d.pending.tier} already on screen${
          num(d.pending.left_sec) ? ` (${s1(d.pending.left_sec)}s left)` : ' (break, no timeout)'
        }`
      : 'prompt already on screen',
  cooldown: (d) => `cooldown — ${s1(d.cooldown_left_sec)}s until the next prompt is allowed`,
  paused_grace: (d) =>
    `video paused by student — grace ${s1(d.pause_left_sec)}s before a gentle nudge`,
  paused_by_intervention: () => 'video paused by a prompt — waiting for the answer',
  ended: () => 'lesson ended — no prompts',
  held: () => 'episode held',
  low_coverage: () => 'camera coverage too low (<50% in last 30s)',
  tier_disabled: (d) => `level ${d.level ?? '?'} reached but that tier is disabled for this subject`,
  fired: (d) =>
    `FIRED T${d.tier} ${INTERVENTION_LABELS[d.intervention_type] || d.intervention_type || ''}${
      d.intervention_id != null ? ` (#${d.intervention_id})` : ''
    } at episode ${s1(d.episode_sec)}s`,
  escalation_t1_ignored: (d) =>
    `T1 unanswered → escalated to T${d.tier} ${INTERVENTION_LABELS[d.intervention_type] || ''}`,
  noise: () => 'FIRED noise notice (sustained loud room)',
};

/** Off-screen frame = ●, on-screen = ○, unknown = · */
export function frameStrip(frames) {
  if (!Array.isArray(frames) || frames.length === 0) return '';
  return frames
    .map((f) => (f.on_screen === false ? '●' : f.on_screen === true ? '○' : '·'))
    .join('');
}

export function explainFrame(f, t0 = null) {
  if (!f) return '';
  const rel = num(t0) && num(f.t) ? `+${(f.t - t0).toFixed(2)}s` : `${s2(f.t)}s`;
  const parts = [rel];
  if (!f.face) {
    parts.push(f.body ? 'no face, body in view' : 'no face, no body');
  } else {
    parts.push('face ✓');
    if (f.on_screen === false) parts.push('OFF-screen');
    else if (f.on_screen === true) parts.push('on-screen');
    if (num(f.sx) && num(f.sy)) parts.push(`gaze x=${s2(f.sx)} y=${s2(f.sy)}`);
    if (num(f.yaw_dev)) parts.push(`yaw ${f.yaw_dev > 0 ? '+' : ''}${s1(f.yaw_dev)}°`);
    if (num(f.pitch_dev)) parts.push(`pitch ${f.pitch_dev > 0 ? '+' : ''}${s1(f.pitch_dev)}°`);
    if (num(f.blink) && f.blink > 0.5) parts.push('eyes closed/blink');
  }
  return parts.join(' · ');
}

/** Plain-language observations for one heartbeat (what the model saw). */
export function describeObservation(res) {
  const out = [];
  if (!res) return out;
  const g = res.gaze_debug || {};
  const diag = res.diagnostics || {};
  const wf = diag.window_features || {};
  const reason = res.reason;
  const source = diag.source || g.source;

  if (reason && REASON_TEXT[reason]) out.push(REASON_TEXT[reason]);
  else if (reason) out.push(reason);

  if (g.on_screen === false) {
    out.push(`eyes off screen for ${s1(g.off_dwell_sec)}s`);
  } else if (g.on_screen === true && res.verdict === 'FOCUSED') {
    out.push('looking at the screen');
  }
  if (num(wf.head_yaw_dev) && Math.abs(wf.head_yaw_dev) >= 15) {
    out.push(`head turned sideways ~${Math.round(Math.abs(wf.head_yaw_dev))}°`);
  }
  if (num(wf.head_pitch_dev) && Math.abs(wf.head_pitch_dev) >= 15) {
    out.push(`head tilted up/down ~${Math.round(Math.abs(wf.head_pitch_dev))}°`);
  }
  if (num(wf.on_screen_ratio) && wf.on_screen_ratio < 0.6) {
    out.push(`on screen only ${pct(wf.on_screen_ratio)} of the window`);
  }
  if (num(wf.face_present_ratio) && wf.face_present_ratio < 0.9) {
    out.push(`face visible ${pct(wf.face_present_ratio)} of frames`);
  }
  if (num(wf.glance_count) && wf.glance_count >= 2) {
    out.push(`${Math.round(wf.glance_count)} glances away`);
  }
  if (source === 'gaze_screen' && res.verdict === 'DISTRACTED') {
    out.push('decided by the screen-gaze dwell rule');
  } else if (source === 'tab' || source === 'blur') {
    out.push('browser signal overrides the camera');
  }
  if (res.noise_triggered) out.push('room noise above baseline');
  return out;
}

/** Numeric line: probabilities, thresholds, model path. */
export function describeNumbers(res) {
  if (!res) return '';
  const g = res.gaze_debug || {};
  const d = res.diagnostics || {};
  const parts = [];
  if (num(g.p_model)) parts.push(`model p=${s2(g.p_model)}`);
  if (num(g.p_gaze) && g.p_gaze > 0) parts.push(`gaze p=${s2(g.p_gaze)}`);
  if (num(d.distract_prob)) {
    parts.push(
      `fused ${s2(d.distract_prob)}${num(d.fusion_threshold) ? ` vs thr ${s2(d.fusion_threshold)}` : ''}`
    );
  }
  if (d.raw_fusion_verdict && d.hysteresis_state && d.raw_fusion_verdict !== d.hysteresis_state) {
    parts.push(`raw ${d.raw_fusion_verdict} → held ${d.hysteresis_state} (hysteresis)`);
  }
  if (d.source) parts.push(`source ${d.source}`);
  if (d.inference_path) parts.push(`path ${d.inference_path}`);
  if (num(d.n_frames)) parts.push(`${d.n_frames} frames in window`);
  if (res.ml_mode) parts.push(`mode ${res.ml_mode}`);
  if (res.evidence) {
    const ev = Object.entries(res.evidence)
      .filter(([, lvl]) => lvl && lvl !== 'normal')
      .map(([k, lvl]) => `${k} ${String(lvl).toUpperCase()}`);
    if (ev.length) parts.push(`evidence: ${ev.join(' · ')}`);
    if (res.rule) parts.push(`rule ${res.rule}`);
  }
  return parts.join(' · ');
}

/** What the intervention engine did with this verdict. */
export function describeDecision(res) {
  const d = res?.intervention_debug;
  if (!d) {
    if (res?.intervention_triggered && res.intervention) {
      return DECISION_TEXT.fired({ ...res.intervention, episode_sec: null });
    }
    return 'no engine decision (unmonitored or no session)';
  }
  const fn = DECISION_TEXT[d.why];
  let text = fn ? fn(d) : `${d.action}: ${d.why}`;
  if (num(d.held_sec) && d.held_sec > 0 && d.why !== 'unknown_hold') {
    text += ` · ${s1(d.held_sec)}s held (not counted)`;
  }
  return text;
}

/** Flat row for CSV export / offline evaluation. */
export function toRow(entry) {
  const r = entry.res || {};
  const g = r.gaze_debug || {};
  const d = r.diagnostics || {};
  const dbg = r.intervention_debug || {};
  return {
    time_iso: new Date(entry.ts).toISOString(),
    kind: entry.kind,
    verdict: r.verdict ?? '',
    confidence: r.confidence ?? '',
    reason: r.reason ?? '',
    source: d.source ?? g.source ?? '',
    p_model: g.p_model ?? '',
    p_gaze: g.p_gaze ?? '',
    p_fused: d.distract_prob ?? '',
    threshold: d.fusion_threshold ?? '',
    on_screen: g.on_screen ?? '',
    off_dwell_sec: g.off_dwell_sec ?? '',
    face_ratio: d.window_features?.face_present_ratio ?? '',
    frames: frameStrip(r.frames_debug),
    episode_sec: dbg.episode_sec ?? '',
    held_sec: dbg.held_sec ?? '',
    action: dbg.action ?? '',
    why: dbg.why ?? '',
    tier: dbg.tier ?? r.intervention?.tier ?? '',
    intervention_type: dbg.intervention_type ?? r.intervention?.intervention_type ?? '',
    content_state: entry.sent?.content_state ?? '',
    pause_reason: entry.sent?.pause_reason ?? '',
    noise_dbfs: entry.sent?.noise_dbfs ?? '',
    mark: entry.kind === 'mark' ? entry.text : '',
    error: entry.kind === 'error' ? entry.text : '',
  };
}

export function toCsv(entries) {
  const rows = entries.map(toRow);
  if (!rows.length) return '';
  const cols = Object.keys(rows[0]);
  const esc = (v) => {
    const s = String(v ?? '');
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cols.join(','), ...rows.map((row) => cols.map((c) => esc(row[c])).join(','))].join('\n');
}

export function toJsonl(entries) {
  // Thumbnails are local-only evidence; keep exports small and image-free.
  return entries
    .map((entry) => {
      const rest = { ...entry };
      delete rest.thumb;
      return JSON.stringify(rest);
    })
    .join('\n');
}
