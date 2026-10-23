import { NavLink, useNavigate } from 'react-router-dom';
import { 
  LayoutDashboard, 
  BookOpen, 
  Users, 
  BarChart3, 
  Settings, 
  LogOut 
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';

export const TeacherSidebar = () => {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItems = [
    { name: 'Dashboard', path: '/teacher/dashboard', icon: LayoutDashboard },
    { name: 'Courses', path: '/teacher/courses', icon: BookOpen },
    { name: 'Students', path: '/teacher/students', icon: Users },
    { name: 'Analytics', path: '/teacher/analytics', icon: BarChart3 },
    { name: 'Settings', path: '/teacher/settings', icon: Settings },
  ];

  return (
    <aside className="w-64 bg-bg/80 border-r border-border/80 flex flex-col justify-between p-6 min-h-screen font-sans">
      <div>
        {/* Brand Header matching screenshot */}
        <div className="mb-8 flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-primary text-on-primary flex items-center justify-center font-bold shadow-sm">
            <BookOpen className="w-5 h-5" />
          </div>
          <div>
            <p className="text-base font-bold text-text leading-tight">Luma</p>
            <p className="text-[11px] text-text-muted font-semibold">Teacher Dashboard</p>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="space-y-1.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.name}
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-all ${
                    isActive
                      ? 'bg-border/70 text-primary font-bold shadow-xs'
                      : 'text-text-muted hover:bg-bg hover:text-text'
                  }`
                }
              >
                <Icon className="w-4 h-4" />
                <span>{item.name}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Bottom Logout Button */}
      <div className="pt-6 border-t border-border/60">
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold text-text-muted hover:bg-red-50 hover:text-red-600 text-left cursor-pointer transition-colors"
        >
          <LogOut className="w-4 h-4" />
          <span>Logout</span>
        </button>
      </div>
    </aside>
  );
};

export default TeacherSidebar;
