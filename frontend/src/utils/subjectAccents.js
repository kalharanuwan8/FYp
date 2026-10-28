/**
 * Muted subject accents for icons / borders / small labels.
 * Colour is never the sole indicator — pair with title or icon.
 * Soft fills stay low-saturation so cards do not compete.
 */
const ACCENTS = [
  {
    key: 'lavender',
    color: 'var(--accent-lavender)',
    soft: 'color-mix(in srgb, var(--accent-lavender) 12%, transparent)',
  },
  {
    key: 'mint',
    color: 'var(--accent-mint)',
    soft: 'color-mix(in srgb, var(--accent-mint) 12%, transparent)',
  },
  {
    key: 'peach',
    color: 'var(--accent-peach)',
    soft: 'color-mix(in srgb, var(--accent-peach) 12%, transparent)',
  },
  {
    key: 'sun',
    color: 'var(--accent-sun)',
    soft: 'color-mix(in srgb, var(--accent-sun) 14%, transparent)',
  },
  {
    key: 'sky',
    color: 'var(--accent-sky)',
    soft: 'color-mix(in srgb, var(--accent-sky) 12%, transparent)',
  },
];

export function accentForId(id) {
  const n = Number(id) || 0;
  return ACCENTS[Math.abs(n) % ACCENTS.length];
}

export default ACCENTS;
