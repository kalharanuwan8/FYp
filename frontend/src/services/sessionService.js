import api from './api';

export const sessionService = {
  listCustomUploads: async () => {
    const response = await api.get('/session/custom/uploads');
    return response.data;
  },

  uploadCustomFile: async (file, title) => {
    const formData = new FormData();
    formData.append('file', file);
    if (title) formData.append('title', title);
    const response = await api.post('/session/custom/uploads', formData);
    return response.data;
  },

  deleteCustomUpload: async (uploadId) => {
    const response = await api.delete(`/session/custom/uploads/${uploadId}`);
    return response.data;
  },

  startCustomSession: async (uploadId) => {
    const response = await api.post('/session/custom/start', { upload_id: uploadId });
    return response.data;
  },

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

  /**
   * Manually fire a tier (demo / practice). `options.force` bypasses pending/cooldown
   * and is honoured by the server only when DEMO_MODE is on.
   */
  triggerIntervention: async (sessionId, tier, isQuizContext = false, options = {}) => {
    const body = {
      tier,
      is_quiz_context: Boolean(isQuizContext),
    };
    if (options.force) body.force = true;
    const response = await api.post(`/session/${sessionId}/trigger-intervention`, body);
    return response.data;
  },

  /** { demo_mode: boolean } — whether the demo sidebar should be offered. */
  getDemoConfig: async () => {
    const response = await api.get('/session/demo-config');
    return response.data;
  },

  stopSession: async (sessionId) => {
    const response = await api.post(`/session/${sessionId}/stop`);
    return response.data;
  },

  // Open sessions for the current student (e.g. monitoring left on after a closed tab)
  getActiveSessions: async () => {
    const response = await api.get('/session/active');
    return response.data;
  },

  stopActiveSessions: async () => {
    const response = await api.post('/session/stop-active');
    return response.data;
  },
};

export default sessionService;
