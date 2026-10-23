import api from './api';

export const sessionService = {
  startSession: async (moduleId, isMonitored = true) => {
    const response = await api.post('/session/start', {
      module_id: moduleId,
      is_monitored: Boolean(isMonitored),
    });
    return response.data;
  },

  sendHeartbeat: async (sessionId, telemetryData) => {
    const response = await api.post(`/session/${sessionId}/heartbeat`, telemetryData);
    return response.data;
  },

  recordInterventionResponse: async (sessionId, interventionId, userResponse, extra = {}) => {
    const { defer_clear, dismiss_only, ...payload } = extra;
    const response = await api.post(`/session/${sessionId}/intervention-response`, {
      intervention_id: interventionId,
      user_response: userResponse,
      ...payload,
    });
    return response.data;
  },

  triggerIntervention: async (sessionId, tier, isQuizContext = false) => {
    const response = await api.post(`/session/${sessionId}/trigger-intervention`, {
      tier,
      is_quiz_context: Boolean(isQuizContext),
    });
    return response.data;
  },

  stopSession: async (sessionId) => {
    const response = await api.post(`/session/${sessionId}/stop`);
    return response.data;
  },
};

export default sessionService;
