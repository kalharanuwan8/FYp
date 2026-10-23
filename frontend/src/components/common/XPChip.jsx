import { Star } from 'lucide-react';

export default function XPChip({ xp = 0, className = '' }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 min-h-11 px-3 rounded-full bg-sun/20 text-text font-semibold text-sm ${className}`}
      aria-label={`${xp} experience points`}
    >
      <Star className="w-4 h-4 text-sun fill-sun" aria-hidden="true" />
      {xp} XP
    </span>
  );
}
