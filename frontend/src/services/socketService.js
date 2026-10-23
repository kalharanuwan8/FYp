import { io } from 'socket.io-client';

/**
 * Optional Socket.IO client for telemetry parity with REST heartbeats.
 * REST remains the primary path used by useMonitoringSession.
 */
let socket = null;

function getSocketUrl() {
  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api';
  return apiBase.replace(/\/api\/?$/, '');
}

export const socketService = {
  connect(token) {
    if (socket?.connected) return socket;
    socket = io(getSocketUrl(), {
      auth: { token },
      transports: ['websocket', 'polling'],
    });
    return socket;
  },

  disconnect() {
    if (socket) {
      socket.disconnect();
      socket = null;
    }
  },

  joinSession(sessionId) {
    if (!socket) return;
    socket.emit('join_session', { session_id: sessionId });
  },

  emitTelemetryWindow(payload) {
    if (!socket) return;
    socket.emit('telemetry_window', payload);
  },

  emitInterventionOutcome(payload) {
    if (!socket) return;
    socket.emit('intervention_outcome', payload);
  },

  on(event, handler) {
    if (!socket) return () => {};
    socket.on(event, handler);
    return () => socket.off(event, handler);
  },

  getSocket() {
    return socket;
  },
};

export default socketService;
