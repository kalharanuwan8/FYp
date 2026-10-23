import { useEffect } from 'react';
import { Button, BadgeChip, XPChip, Dialog } from '../common';
import { usePreferences } from '../../context/PreferencesContext';
import { celebrateIfAllowed } from '../../utils/celebrate';

export default function SessionSummary({ summary, onClose, onContinue }) {
  const { reduceMotion } = usePreferences();
  const focusMinutes =
    summary?.focus_minutes ??
    Math.max(1, Math.round((summary?.duration_seconds || 0) / 60));
  const xp = summary?.xp_gained || 0;
  const badges = summary?.new_badges || [];
  const streak = summary?.progress?.current_streak;

  useEffect(() => {
    if (!summary) return;
    if (xp > 0 || badges.length > 0) {
      celebrateIfAllowed({ reduceMotion });
    }
  }, [summary, xp, badges.length, reduceMotion]);

  if (!summary) return null;

  return (
    <Dialog title="Nice session!" allowEscape={false} panelClassName="max-w-md">
      <div className="text-center space-y-5">
        <p className="text-4xl" aria-hidden="true">
          🎉
        </p>
        <p className="text-lg text-text">
          <span className="font-display font-bold">{focusMinutes}</span> focused minutes
        </p>

        <div className="flex flex-wrap items-center justify-center gap-2">
          {xp > 0 && <XPChip xp={xp} />}
          {streak != null && (
            <span className="inline-flex items-center min-h-9 px-3 rounded-2xl border border-border bg-surface text-sm font-medium text-text-muted">
              Streak: {streak} day{streak === 1 ? '' : 's'}
            </span>
          )}
        </div>

        {badges.length > 0 && (
          <div className="space-y-2 text-left">
            <p className="text-sm font-semibold text-text text-center">New badge unlocked</p>
            {badges.map((b) => (
              <BadgeChip
                key={b.id || b.badge?.code}
                icon={b.badge?.icon || '⭐'}
                name={b.badge?.name || 'Badge'}
                description={b.badge?.description}
              />
            ))}
          </div>
        )}

        <div className="flex flex-col gap-2 pt-2">
          {onContinue && (
            <Button size="lg" onClick={onContinue}>
              Continue learning
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            Back to subject
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
