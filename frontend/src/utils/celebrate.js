/**
 * Fire a small confetti burst only when the student's preferences allow it.
 * Confetti is motion, so reduced-motion turns it off entirely.
 */
export async function celebrateIfAllowed({ reduceMotion } = {}) {
  if (reduceMotion) return;
  try {
    const confetti = (await import('canvas-confetti')).default;
    confetti({
      particleCount: 48,
      spread: 55,
      origin: { y: 0.7 },
      colors: ['#3CBF9A', '#5AB0EE', '#F4C152', '#8B7CF6'],
    });
  } catch {
    /* optional dependency — celebration is never essential */
  }
}

export default celebrateIfAllowed;
