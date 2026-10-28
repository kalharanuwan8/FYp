import { Flame } from 'lucide-react';

export default function StreakChip({ streak = 0, className = '' }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 min-h-9 px-3 rounded-2xl border border-transparent bg-peach/15 text-text font-semibold text-sm ${className}`}
      aria-label={`${streak} day streak`}
    >
      <Flame className="w-4 h-4 text-peach" aria-hidden="true" />
      {streak} day{streak === 1 ? '' : 's'} streak
    </span>
  );
}
