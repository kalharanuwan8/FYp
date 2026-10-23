import { NavLink, useNavigate } from 'react-router-dom';
import { Home, BookOpen, TrendingUp, Settings, LogOut, Compass } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';

const navItems = [
  { name: 'Home', path: '/student/dashboard', icon: Home, end: true },
  { name: 'My Subjects', path: '/student/courses', icon: BookOpen },
  { name: 'Progress', path: '/student/analytics', icon: TrendingUp },
  { name: 'Settings', path: '/student/settings', icon: Settings },
];

export default function StudentSidebar({ focusMode = false }) {
  const { logout } = useAuth();
  const navigate = useNavigate();

  if (focusMode) return null;

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <>
      {/* Desktop / tablet sidebar */}
      <aside className="hidden md:flex w-60 shrink-0 bg-surface border-r border-border flex-col justify-between p-5 min-h-screen sticky top-0 h-screen">
        <div>
          <div className="mb-8 flex items-center gap-3">
            <div className="w-11 h-11 rounded-2xl bg-primary text-on-primary flex items-center justify-center shadow-soft">
              <Compass className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <p className="font-display text-lg font-bold text-text leading-tight">Luma</p>
              <p className="text-xs text-text-muted">Focus Learning</p>
            </div>
          </div>

          <nav className="space-y-1.5" aria-label="Student navigation">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.name}
                  to={item.path}
                  end={item.end}
                  className={({ isActive }) =>
                    `flex items-center gap-3 min-h-11 px-3.5 rounded-2xl text-sm font-semibold transition-all ${
                      isActive
                        ? 'bg-primary-soft text-primary'
                        : 'text-text-muted hover:bg-bg hover:text-text'
                    }`
                  }
                >
                  <Icon className="w-5 h-5" aria-hidden="true" />
                  <span>{item.name}</span>
                </NavLink>
              );
            })}
          </nav>
        </div>

        <button
          type="button"
          onClick={handleLogout}
          className="flex items-center gap-3 min-h-11 px-3.5 w-full text-sm font-semibold text-text-muted hover:text-attention hover:bg-attention/10 rounded-2xl transition-all cursor-pointer"
        >
          <LogOut className="w-5 h-5" aria-hidden="true" />
          <span>Log out</span>
        </button>
      </aside>

      {/* Mobile bottom navigation */}
      <nav
        aria-label="Student navigation"
        className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-surface border-t border-border pb-[env(safe-area-inset-bottom)]"
      >
        <div className="grid grid-cols-5">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.name}
                to={item.path}
                end={item.end}
                className={({ isActive }) =>
                  `flex flex-col items-center justify-center gap-0.5 min-h-14 px-1 text-[11px] font-semibold ${
                    isActive ? 'text-primary' : 'text-text-muted'
                  }`
                }
              >
                <Icon className="w-5 h-5" aria-hidden="true" />
                <span>{item.name}</span>
              </NavLink>
            );
          })}
          <button
            type="button"
            onClick={handleLogout}
            className="flex flex-col items-center justify-center gap-0.5 min-h-14 px-1 text-[11px] font-semibold text-text-muted cursor-pointer"
          >
            <LogOut className="w-5 h-5" aria-hidden="true" />
            <span>Log out</span>
          </button>
        </div>
      </nav>
    </>
  );
}
