import api from './api';

export const studentService = {
  getProfile: async () => {
    const response = await api.get('/student/profile');
    return response.data;
  },

  updateProfile: async (data) => {
    const response = await api.patch('/student/profile', data);
    return response.data;
  },

  /** Screen-gaze calibration without a learning session (frames + calibration_phase). */
  postGazeCalibration: async (payload) => {
    const response = await api.post('/student/gaze-calibration', payload);
    return response.data;
  },

  /** Persist that the student skipped screen calibration (shown in Settings). */
  skipGazeCalibration: async () => {
    const response = await api.post('/student/gaze-calibration/skip');
    return response.data;
  },

  getProgress: async () => {
    const response = await api.get('/student/progress');
    return response.data;
  },

  getBadges: async () => {
    const response = await api.get('/student/badges');
    return response.data;
  },

  getMyEnrollments: async () => {
    const response = await api.get('/courses/my-enrollments');
    return response.data;
  },

  enrollInSubject: async (subjectId) => {
    const response = await api.post(`/courses/subjects/${subjectId}/enroll`);
    return response.data;
  },

  unenrollFromSubject: async (subjectId) => {
    const response = await api.delete(`/courses/subjects/${subjectId}/enroll`);
    return response.data;
  },
};

export default studentService;
