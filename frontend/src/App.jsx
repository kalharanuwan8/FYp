import { useContext } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, AuthContext } from './context/AuthContext';
import { PreferencesProvider } from './context/PreferencesContext';
import LoginPage from './pages/LoginPage';
import ProtectedRoute from './routes/ProtectedRoute';
import RoleRoute from './routes/RoleRoute';

import AdminLayout from './components/admin/AdminLayout';
import AdminDashboard from './pages/admin/AdminDashboard';
import UserManagement from './pages/admin/UserManagement';
import SystemLogs from './pages/admin/SystemLogs';
import AnalyticsPage from './pages/admin/AnalyticsPage';
import SettingsPage from './pages/admin/SettingsPage';

import TeacherLayout from './components/teacher/TeacherLayout';
import TeacherDashboard from './pages/teacher/TeacherDashboard';
import CourseList from './pages/teacher/CourseList';
import CourseEditor from './pages/teacher/CourseEditor';
import TeacherAnalytics from './pages/teacher/TeacherAnalytics';
import TeacherStudents from './pages/teacher/TeacherStudents';

import StudentLayout from './components/student/StudentLayout';
import StudentDashboard from './pages/student/StudentDashboard';
import CourseBrowser from './pages/student/CourseBrowser';
import SubjectDetail from './pages/student/SubjectDetail';
import QuizAttempt from './pages/student/QuizAttempt';
import StudentAnalytics from './pages/student/StudentAnalytics';

function CatchAllRedirect() {
  const { user, token } = useContext(AuthContext);
  if (token && user) {
    const role = (user.role || '').toLowerCase();
    if (role === 'admin') return <Navigate to="/admin/dashboard" replace />;
    if (role === 'teacher') return <Navigate to="/teacher/dashboard" replace />;
    return <Navigate to="/student/dashboard" replace />;
  }
  return <Navigate to="/login" replace />;
}

export function App() {
  return (
    <AuthProvider>
      <PreferencesProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />

            <Route element={<ProtectedRoute />}>
              <Route element={<RoleRoute allowedRoles={['admin']} />}>
                <Route element={<AdminLayout />}>
                  <Route path="/admin/dashboard" element={<AdminDashboard />} />
                  <Route path="/admin/users" element={<UserManagement />} />
                  <Route path="/admin/analytics" element={<AnalyticsPage />} />
                  <Route path="/admin/logs" element={<SystemLogs />} />
                  <Route path="/admin/settings" element={<SettingsPage />} />
                </Route>
              </Route>

              <Route element={<RoleRoute allowedRoles={['teacher']} />}>
                <Route element={<TeacherLayout />}>
                  <Route path="/teacher/dashboard" element={<TeacherDashboard />} />
                  <Route path="/teacher/courses" element={<CourseList />} />
                  <Route path="/teacher/courses/:id" element={<CourseEditor />} />
                  <Route path="/teacher/analytics" element={<TeacherAnalytics />} />
                  <Route path="/teacher/students" element={<TeacherStudents />} />
                  <Route path="/teacher/settings" element={<SettingsPage />} />
                </Route>
              </Route>

              <Route element={<RoleRoute allowedRoles={['student']} />}>
                <Route element={<StudentLayout />}>
                  <Route path="/student/dashboard" element={<StudentDashboard />} />
                  <Route path="/student/courses" element={<CourseBrowser />} />
                  <Route path="/student/my-courses" element={<Navigate to="/student/courses" replace />} />
                  <Route path="/student/subjects/:id" element={<SubjectDetail />} />
                  <Route path="/student/quizzes/:quizId" element={<QuizAttempt />} />
                  <Route path="/student/analytics" element={<StudentAnalytics />} />
                  <Route path="/student/settings" element={<SettingsPage />} />
                </Route>
              </Route>
            </Route>

            <Route path="*" element={<CatchAllRedirect />} />
          </Routes>
        </BrowserRouter>
      </PreferencesProvider>
    </AuthProvider>
  );
}

export default App;
