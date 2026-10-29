import { useEffect, useRef } from 'react';
import api from '../services/api';

const IDLE_THRESHOLD_MS = 15_000;
const ACTIVITY_EVENTS = ['click', 'keydown', 'touchstart', 'scroll', 'pointermove'];

/**
 * Record-only idle tracker for quiz / document pages.
 * When the user is idle ≥ 15 s and then becomes active again (or unmounts),
 * posts one behaviour/idle episode. Video pages must not use this hook.
 */
export function useIdleTracker({
  enabled = false,
  context,
  quizAttemptId = null,
  moduleContentId = null,
  thresholdMs = IDLE_THRESHOLD_MS,
} = {}) {
  const lastActiveRef = useRef(Date.now());
  const idleStartedRef = useRef(null);
  const timerRef = useRef(null);
  const metaRef = useRef({ context, quizAttemptId, moduleContentId });

  metaRef.current = { context, quizAttemptId, moduleContentId };

  useEffect(() => {
    if (!enabled || !context) return undefined;

    const postIdle = async (startedAt, durationSec) => {
      if (durationSec < thresholdMs / 1000) return;
      const meta = metaRef.current;
      try {
        await api.post('/behaviour/idle', {
          context: meta.context,
          duration_seconds: durationSec,
          started_at: new Date(startedAt).toISOString(),
          quiz_attempt_id: meta.quizAttemptId || undefined,
          module_content_id: meta.moduleContentId || undefined,
        });
      } catch {
        /* record-only; ignore network errors for UX */
      }
    };

    const flushIfIdle = () => {
      if (idleStartedRef.current != null) {
        const durationSec = (Date.now() - idleStartedRef.current) / 1000;
        const started = idleStartedRef.current;
        idleStartedRef.current = null;
        postIdle(started, durationSec);
      }
    };

    const onActivity = () => {
      flushIfIdle();
      lastActiveRef.current = Date.now();
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        if (idleStartedRef.current == null) {
          idleStartedRef.current = Date.now();
        }
      }, thresholdMs);
    };

    ACTIVITY_EVENTS.forEach((ev) =>
      window.addEventListener(ev, onActivity, { passive: true })
    );
    onActivity();

    return () => {
      ACTIVITY_EVENTS.forEach((ev) => window.removeEventListener(ev, onActivity));
      if (timerRef.current) clearTimeout(timerRef.current);
      flushIfIdle();
    };
  }, [enabled, context, thresholdMs, quizAttemptId, moduleContentId]);
}

export default useIdleTracker;
