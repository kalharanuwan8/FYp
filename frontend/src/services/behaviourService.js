import api from './api';

export const behaviourService = {
  recordIdle: async (payload) => {
    const response = await api.post('/behaviour/idle', payload);
    return response.data;
  },
};

export default behaviourService;
