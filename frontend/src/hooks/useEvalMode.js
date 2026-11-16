import { useEffect, useState } from 'react';
import sessionService from '../services/sessionService';

function urlEvalFlag() {
  try {
    return new URLSearchParams(window.location.search).get('eval') === '1';
  } catch {
    return false;
  }
}

/**
 * PLAN 7: whether the evaluation terminal may be shown — page URL has `?eval=1`
 * (also opens it immediately) or the backend runs with DEMO_MODE.
 */
export function useEvalMode() {
  const [urlFlag] = useState(urlEvalFlag);
  const [demo, setDemo] = useState(false);
  useEffect(() => {
    let cancelled = false;
    sessionService
      .getDemoConfig()
      .then((cfg) => {
        if (!cancelled) setDemo(Boolean(cfg?.demo_mode));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return { enabled: urlFlag || demo, autoOpen: urlFlag };
}

export default useEvalMode;
