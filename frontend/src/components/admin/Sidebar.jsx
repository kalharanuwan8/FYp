import { NavLink, useNavigate } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Users, 
  BarChart3, 
  FileText, 
  Settings, 
  Plus, 
  HelpCircle, 
  LogOut 
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';

export const Sidebar = () => {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItems = [
    { name: 'Dashboard', path: '/admin/dashboard', icon: LayoutDashboard },
    { name: 'Users', path: '/admin/users', icon: Users },
    { name: 'Analytics', path: '/admin/analytics', icon: BarChart3 },
    { name: 'Logs', path: '/admin/logs', icon: FileText },
    { name: 'Settings', path: '/admin/settings', icon: Settings },
  ];

  return (
    <aside className="w-64 bg-bg/80 border-r border-border/80 flex flex-col justify-between p-6 min-h-screen">
      <div>
        {/* Brand Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2">
            <span className="w-8 h-8 rounded-full bg-primary text-on-primary font-bold flex items-center justify-center text-lg">
              L
            </span>
            <div>
              <p className="text-lg font-bold text-text leading-tight">Luma Admin</p>
              <p className="text-xs text-text-muted font-medium">Management Suite</p>
            </div>
          </div>
        </div>

        {/* Action Button */}
        <button
          type="button"
          onClick={() => navigate('/admin/analytics')}
          className="w-full bg-primary hover:bg-primary-hover text-on-primary font-medium py-2.5 px-4 rounded-lg flex items-center justify-center gap-2 shadow-sm transition-all text-sm mb-6 cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          <span>View analytics</span>
        </button>

        {/* Navigation Items */}
        <nav className="space-y-1.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.name}
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-border/70 text-primary font-semibold'
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

      {/* Bottom Nav Items */}
      <div className="pt-6 border-t border-border/60 space-y-1.5 text-sm">
        <p className="flex items-center gap-3 px-3.5 py-2 text-text-muted">
          <HelpCircle className="w-4 h-4" aria-hidden="true" />
          <span>Need help? Ask your system administrator.</span>
        </p>
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3.5 py-2 rounded-lg text-text-muted hover:bg-red-50 hover:text-red-600 text-left cursor-pointer transition-colors"
        >
          <LogOut className="w-4 h-4" />
          <span>Logout</span>
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
