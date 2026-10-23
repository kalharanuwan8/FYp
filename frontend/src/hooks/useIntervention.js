import { useCallback, useState } from 'react';
import sessionService from '../services/sessionService';

/**
 * Thin helper for recording intervention outcomes and tracking active overlay.
 */
export function useIntervention(sessionId) {
  const [activeIntervention, setActiveIntervention] = useState(null);

  const showIntervention = useCallback((intervention) => {
    if (intervention) setActiveIntervention(intervention);
  }, []);

  const clearIntervention = useCallback(() => {
    setActiveIntervention(null);
  }, []);

  const respond = useCallback(
    async (interventionId, userResponse) => {
      if (!sessionId || !interventionId) {
        setActiveIntervention(null);
        return null;
      }
      try {
        const data = await sessionService.recordInterventionResponse(
          sessionId,
          interventionId,
          userResponse
        );
        setActiveIntervention(null);
        return data;
      } catch (err) {
        console.error('Failed to record intervention response:', err);
        setActiveIntervention(null);
        throw err;
      }
    },
    [sessionId]
  );

  return {
    activeIntervention,
    setActiveIntervention,
    showIntervention,
    clearIntervention,
    respond,
  };
}

export default useIntervention;
