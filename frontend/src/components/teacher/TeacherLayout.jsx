import { Outlet } from 'react-router-dom';
import TeacherSidebar from './TeacherSidebar';
import Topbar from '../admin/Topbar';

export const TeacherLayout = ({ children }) => {
  return (
    <div className="flex min-h-screen bg-bg font-sans text-text">
      <TeacherSidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar />
        <main className="flex-1 p-8 overflow-y-auto">
          {children || <Outlet />}
        </main>
      </div>
    </div>
  );
};

export default TeacherLayout;
