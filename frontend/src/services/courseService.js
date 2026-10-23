import api from './api';

export const courseService = {
  getGradeLevels: async () => {
    const response = await api.get('/courses/grade-levels');
    return response.data;
  },

  getSubjects: async (params = {}) => {
    const { search, page = 1, per_page = 10 } = params;
    const queryParams = new URLSearchParams();
    if (search) queryParams.append('search', search);
    if (page) queryParams.append('page', page);
    if (per_page) queryParams.append('per_page', per_page);

    const response = await api.get(`/courses/subjects?${queryParams.toString()}`);
    return response.data;
  },

  getSubjectDetail: async (subjectId) => {
    const response = await api.get(`/courses/subjects/${subjectId}`);
    return response.data;
  },

  createSubject: async (data) => {
    const response = await api.post('/courses/subjects', data);
    return response.data;
  },

  updateSubject: async (subjectId, data) => {
    const response = await api.patch(`/courses/subjects/${subjectId}`, data);
    return response.data;
  },

  archiveSubject: async (subjectId, isArchived) => {
    const response = await api.patch(`/courses/subjects/${subjectId}/archive`, {
      is_archived: Boolean(isArchived),
    });
    return response.data;
  },

  getModules: async (subjectId) => {
    const response = await api.get(`/courses/subjects/${subjectId}/modules`);
    return response.data;
  },

  createModule: async (subjectId, data) => {
    const response = await api.post(`/courses/subjects/${subjectId}/modules`, data);
    return response.data;
  },

  updateModule: async (moduleId, data) => {
    const response = await api.patch(`/courses/modules/${moduleId}`, data);
    return response.data;
  },

  archiveModule: async (moduleId, isArchived) => {
    const response = await api.patch(`/courses/modules/${moduleId}/archive`, {
      is_archived: Boolean(isArchived),
    });
    return response.data;
  },

  createMaterial: async (moduleId, data) => {
    const response = await api.post(`/courses/modules/${moduleId}/materials`, data);
    return response.data;
  },

  getMaterial: async (materialId) => {
    const response = await api.get(`/courses/materials/${materialId}`);
    return response.data;
  },

  updateMaterial: async (materialId, data) => {
    const response = await api.patch(`/courses/materials/${materialId}`, data);
    return response.data;
  },

  generateMaterialPack: async (data) => {
    const response = await api.post('/courses/materials/generate-pack', data, {
      timeout: 120000,
    });
    return response.data;
  },

  deleteMaterial: async (materialId) => {
    const response = await api.delete(`/courses/materials/${materialId}`);
    return response.data;
  },

  uploadMaterialFile: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/courses/upload', formData);
    return response.data;
  },

  enroll: async (subjectId) => {
    const response = await api.post(`/courses/subjects/${subjectId}/enroll`);
    return response.data;
  },

  dropEnrollment: async (subjectId) => {
    const response = await api.delete(`/courses/subjects/${subjectId}/enroll`);
    return response.data;
  },

  listMyEnrollments: async () => {
    const response = await api.get('/courses/my-enrollments');
    return response.data;
  },

  getInterventionConfig: async (subjectId) => {
    const response = await api.get(`/courses/subjects/${subjectId}/intervention-config`);
    return response.data;
  },

  updateInterventionConfig: async (subjectId, data) => {
    const response = await api.patch(`/courses/subjects/${subjectId}/intervention-config`, data);
    return response.data;
  },
};

export default courseService;
