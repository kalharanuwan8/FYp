import { useEffect, useRef, useState } from 'react';
import { usePreferences } from '../../context/PreferencesContext';
import Dialog from '../common/Dialog';

/** Tier 4 / break — breathing timer the student can leave at any time. */
export default function GamifiedBreak({ message, payload, onRespond, interventionId }) {
  const total = Math.max(20, Number(payload?.break_seconds) || 60);
  const [left, setLeft] = useState(total);
  const respondedRef = useRef(false);
  const { sounds, reduceMotion } = usePreferences();

  const respondOnce = (outcome) => {
    if (respondedRef.current) return;
    respondedRef.current = true;
    onRespond(interventionId, outcome);
  };

  useEffect(() => {
    if (left <= 0) {
      respondOnce('reengaged');
      return undefined;
    }
    const id = setTimeout(() => setLeft((p) => p - 1), 1000);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [left, interventionId]);

  useEffect(() => {
    if (!sounds || reduceMotion) return undefined;
    // Soft optional beep each 4s inhale cue — skip if AudioContext blocked
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const tick = () => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.frequency.value = 220;
        gain.gain.value = 0.03;
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 0.08);
      };
      const id = setInterval(tick, 4000);
      return () => {
        clearInterval(id);
        ctx.close?.();
      };
    } catch {
      return undefined;
    }
  }, [sounds, reduceMotion]);

  const progress = 1 - left / total;

  return (
    <Dialog
      title="Stretch & breathe"
      description={message || 'A short break helps your brain reset. Follow the circle — or continue whenever you are ready.'}
      allowEscape={false}
      panelClassName="max-w-sm"
    >
      <div className="text-center space-y-5">
        <div className="relative mx-auto w-36 h-36 flex items-center justify-center">
          <div
            className="absolute inset-0 rounded-full bg-mint/25"
            style={{
              animation: reduceMotion ? 'none' : 'breathe-ring 4s ease-in-out infinite',
              transform: `scale(${0.85 + progress * 0.15})`,
            }}
            aria-hidden="true"
          />
          <div className="relative z-10 font-display text-3xl font-bold text-primary tabular-nums">
            {left}s
          </div>
        </div>

        <p className="text-xs text-text-muted" aria-live="polite">
          Inhale as it grows · exhale as it softens
        </p>

        <button
          type="button"
          onClick={() => respondOnce('reengaged')}
          className="w-full min-h-12 rounded-2xl bg-primary hover:bg-primary-hover text-on-primary text-base font-semibold cursor-pointer"
        >
          Ready to continue
        </button>
      </div>
    </Dialog>
  );
}
