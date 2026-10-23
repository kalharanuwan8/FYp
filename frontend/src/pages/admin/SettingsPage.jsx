import { useContext } from 'react';
import { AuthContext } from '../../context/AuthContext';
import SystemSettings from './SystemSettings';
import StudentSettings from '../student/StudentSettings';
import TeacherSettings from '../teacher/TeacherSettings';

export const SettingsPage = () => {
  const { user } = useContext(AuthContext);
  const role = (user?.role || '').toLowerCase();

  if (role === 'admin') {
    return <SystemSettings />;
  }

  if (role === 'teacher') {
    return <TeacherSettings />;
  }

  return <StudentSettings />;
};

export default SettingsPage;
