import { useCallback, useRef } from 'react';

/**
 * PLAN 8 — tiny fan-out for heartbeat responses.
 *
 * Pass `onHeartbeat` to `useMonitoringSession`; hand `subscribeHeartbeat` to any
 * component (e.g. GazeSelfTest) that wants the raw responses. Both are stable.
 */
export function useHeartbeatBus() {
  const listenersRef = useRef(new Set());

  const onHeartbeat = useCallback((response, info) => {
    listenersRef.current.forEach((fn) => {
      try {
        fn(response, info);
      } catch (err) {
        console.warn('heartbeat subscriber failed:', err);
      }
    });
  }, []);

  /** Subscribe; returns an unsubscribe function. */
  const subscribeHeartbeat = useCallback((fn) => {
    listenersRef.current.add(fn);
    return () => {
      listenersRef.current.delete(fn);
    };
  }, []);

  return { onHeartbeat, subscribeHeartbeat };
}

export default useHeartbeatBus;
