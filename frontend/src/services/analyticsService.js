import api from './api';

export const analyticsService = {
  getTeacherAnalytics: async () => {
    const response = await api.get('/analytics/teacher');
    return response.data;
  },

  getStudentAnalytics: async () => {
    const response = await api.get('/analytics/student');
    return response.data;
  },

  getAdminAnalytics: async () => {
    const response = await api.get('/analytics/admin');
    return response.data;
  },

  listTeacherStudents: async () => {
    const response = await api.get('/analytics/teacher/students');
    return response.data;
  },

  getTeacherStudentDsmProfile: async (studentId, days = 7) => {
    const response = await api.get(
      `/analytics/teacher/students/${studentId}/dsm-profile`,
      { params: { days } }
    );
    return response.data;
  },
};

export default analyticsService;
