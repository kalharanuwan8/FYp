import { useState } from 'react';
import { Zap, PauseCircle, HelpCircle, Gauge } from 'lucide-react';

const TIERS = [
  { tier: 1, label: 'Cue', hint: 'Ambient nudge', Icon: Zap },
  { tier: 2, label: 'Pause', hint: 'Pacing prompt', Icon: PauseCircle },
  { tier: 3, label: 'Quiz', hint: 'Milestone check', Icon: HelpCircle },
  { tier: 4, label: 'Pace', hint: 'Structural notice', Icon: Gauge },
];

/**
 * Student demo panel to manually fire intervention tiers 1–4.
 */
export default function ManualInterventionPanel({ onTrigger, disabled = false, busy = false }) {
  const [pendingTier, setPendingTier] = useState({});

  const handleClick = async (tier) => {
    if (disabled || busy || !onTrigger) return;
    setPendingTier((p) => ({ ...p, [tier]: true }));
    try {
      await onTrigger(tier);
    } finally {
      setPendingTier((p) => ({ ...p, [tier]: false }));
    }
  };

  return (
    <div className="rounded-xl border border-dashed border-border bg-bg/80 p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[10px] font-bold uppercase tracking-wider text-text-muted">
          Manual interventions
        </p>
        <span className="text-[10px] text-text-muted font-medium">Demo / practice</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {TIERS.map(({ tier, label, hint, Icon }) => (
          <button
            key={tier}
            type="button"
            disabled={disabled || busy || pendingTier[tier]}
            onClick={() => handleClick(tier)}
            className="flex flex-col items-start gap-1 p-2.5 rounded-lg border border-border bg-surface hover:border-primary hover:bg-primary-soft text-left transition-colors cursor-pointer disabled:opacity-50"
          >
            <span className="inline-flex items-center gap-1.5 text-[11px] font-bold text-text">
              <Icon className="w-3.5 h-3.5 text-primary" />
              T{tier} {label}
            </span>
            <span className="text-[10px] text-text-muted">{hint}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
