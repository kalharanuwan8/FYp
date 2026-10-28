import api from './api';

export const quizService = {
  createQuiz: async (moduleId, quizData) => {
    const response = await api.post(`/courses/modules/${moduleId}/quizzes`, quizData);
    return response.data;
  },

  getQuizDetail: async (quizId) => {
    const response = await api.get(`/courses/quizzes/${quizId}`);
    return response.data;
  },

  listModuleQuizzes: async (moduleId) => {
    const response = await api.get(`/courses/modules/${moduleId}/quizzes`);
    return response.data;
  },

  startAttempt: async (quizId) => {
    const response = await api.post(`/courses/quizzes/${quizId}/attempts`);
    return response.data;
  },

  submitAttempt: async (attemptId, submissionData) => {
    const response = await api.post(`/courses/attempts/${attemptId}/submit`, submissionData);
    return response.data;
  },

  listQuizAttempts: async (quizId) => {
    const response = await api.get(`/courses/quizzes/${quizId}/attempts`);
    return response.data;
  },

  recordRemediationChoice: async (eventId, choice) => {
    const response = await api.post(`/courses/remediation/${eventId}/choice`, { choice });
    return response.data;
  },
};

export default quizService;
