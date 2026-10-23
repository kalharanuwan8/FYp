import api from './api';

export const adminService = {
  getDashboardStats: async () => {
    const response = await api.get('/admin/dashboard/stats');
    return response.data;
  },

  getUsers: async (params = {}) => {
    const { role, search, page = 1, per_page = 10 } = params;
    const queryParams = new URLSearchParams();
    if (role) queryParams.append('role', role);
    if (search) queryParams.append('search', search);
    if (page) queryParams.append('page', page);
    if (per_page) queryParams.append('per_page', per_page);

    const response = await api.get(`/admin/users?${queryParams.toString()}`);
    return response.data;
  },

  updateUserStatus: async (userId, isActive) => {
    const response = await api.patch(`/admin/users/${userId}/status`, {
      is_active: isActive,
    });
    return response.data;
  },

  createUser: async (userData) => {
    const response = await api.post('/auth/register', userData);
    return response.data;
  },

  bulkImportUsers: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/admin/users/bulk-import', formData);
    return response.data;
  },

  getSettings: async () => {
    const response = await api.get('/admin/settings');
    return response.data;
  },

  updateSettings: async (settingsData) => {
    const response = await api.patch('/admin/settings', settingsData);
    return response.data;
  },
};
