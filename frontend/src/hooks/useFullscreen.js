import { useCallback, useEffect, useRef, useState } from 'react';

const getFullscreenElement = () =>
  document.fullscreenElement || document.webkitFullscreenElement || null;

/**
 * Fullscreen for an arbitrary element (not native <video> fullscreen, which would
 * hide intervention overlays). `targetRef` should point at the stage container.
 * Syncs state with Esc / browser-initiated exits and supports the webkit prefix.
 */
export function useFullscreen(targetRef) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const ownedRef = useRef(false);

  useEffect(() => {
    const sync = () => {
      const el = getFullscreenElement();
      const owned = Boolean(el) && el === targetRef.current;
      ownedRef.current = owned;
      setIsFullscreen(owned);
    };
    document.addEventListener('fullscreenchange', sync);
    document.addEventListener('webkitfullscreenchange', sync);
    return () => {
      document.removeEventListener('fullscreenchange', sync);
      document.removeEventListener('webkitfullscreenchange', sync);
    };
  }, [targetRef]);

  const enter = useCallback(async () => {
    const el = targetRef.current;
    if (!el) return false;
    try {
      if (el.requestFullscreen) await el.requestFullscreen();
      else if (el.webkitRequestFullscreen) await el.webkitRequestFullscreen();
      else return false;
      return true;
    } catch (err) {
      console.warn('Fullscreen request failed:', err);
      return false;
    }
  }, [targetRef]);

  const exit = useCallback(async () => {
    if (!getFullscreenElement()) return;
    try {
      if (document.exitFullscreen) await document.exitFullscreen();
      else if (document.webkitExitFullscreen) await document.webkitExitFullscreen();
    } catch (err) {
      console.warn('Exit fullscreen failed:', err);
    }
  }, []);

  const toggle = useCallback(() => {
    if (getFullscreenElement() === targetRef.current) return exit();
    return enter();
  }, [enter, exit, targetRef]);

  // Leaving the component while fullscreen must not strand the browser in FS.
  useEffect(() => {
    return () => {
      if (ownedRef.current && getFullscreenElement()) {
        try {
          const p = document.exitFullscreen?.() ?? document.webkitExitFullscreen?.();
          if (p && typeof p.catch === 'function') p.catch(() => {});
        } catch {
          /* best-effort */
        }
      }
    };
  }, []);

  return { isFullscreen, enter, exit, toggle };
}

export default useFullscreen;
