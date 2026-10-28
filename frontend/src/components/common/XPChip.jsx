import { Star } from 'lucide-react';

export default function XPChip({ xp = 0, className = '' }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 min-h-9 px-3 rounded-2xl border border-transparent bg-sun/15 text-text font-semibold text-sm ${className}`}
      aria-label={`${xp} experience points`}
    >
      <Star className="w-4 h-4 text-sun fill-sun/30" aria-hidden="true" />
      {xp} XP
    </span>
  );
}
