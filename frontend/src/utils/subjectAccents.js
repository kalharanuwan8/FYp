const ACCENTS = [
  { key: 'lavender', color: 'var(--accent-lavender)', soft: 'color-mix(in srgb, var(--accent-lavender) 18%, transparent)' },
  { key: 'mint', color: 'var(--accent-mint)', soft: 'color-mix(in srgb, var(--accent-mint) 18%, transparent)' },
  { key: 'peach', color: 'var(--accent-peach)', soft: 'color-mix(in srgb, var(--accent-peach) 18%, transparent)' },
  { key: 'sun', color: 'var(--accent-sun)', soft: 'color-mix(in srgb, var(--accent-sun) 22%, transparent)' },
  { key: 'sky', color: 'var(--accent-sky)', soft: 'color-mix(in srgb, var(--accent-sky) 18%, transparent)' },
];

export function accentForId(id) {
  const n = Number(id) || 0;
  return ACCENTS[Math.abs(n) % ACCENTS.length];
}

export default ACCENTS;
