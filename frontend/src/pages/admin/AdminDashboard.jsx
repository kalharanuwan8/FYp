import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { 
  Users, 
  LogIn, 
  BookOpen, 
  Cloud, 
  UserPlus, 
  Upload, 
  FileText, 
  BarChart2, 
  ArrowRight,
  AlertCircle
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { adminService } from '../../services/adminService';
import StatCard from '../../components/admin/StatCard';

export const AdminDashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  const adminName = user ? `${user.first_name || ''} ${user.last_name || ''}`.trim() || 'Admin Name' : 'Admin Name';

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await adminService.getDashboardStats();
        setStats(data);
      } catch (err) {
        console.error('Failed to fetch dashboard stats', err);
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  // Display real counts when present, or "—" for null fields (not yet implemented)
  const totalUsers = stats?.total_users !== null && stats?.total_users !== undefined ? stats.total_users : '—';
  const totalStudents = stats?.total_students !== null && stats?.total_students !== undefined ? stats.total_students : 0;
  const totalTeachers = stats?.total_teachers !== null && stats?.total_teachers !== undefined ? stats.total_teachers : 0;
  const totalAdmins = stats?.total_admins !== null && stats?.total_admins !== undefined ? stats.total_admins : 0;

  const activeSessions = stats?.active_sessions !== null && stats?.active_sessions !== undefined ? stats.active_sessions : '—';
  const totalCourses = stats?.total_courses !== null && stats?.total_courses !== undefined ? stats.total_courses : '—';
  const storageUsed = stats?.storage_used_mb !== null && stats?.storage_used_mb !== undefined ? `${stats.storage_used_mb} MB` : '—';

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Header Greeting */}
      <div>
        <h1 className="text-3xl font-extrabold text-text tracking-tight">
          Good morning, {adminName}
        </h1>
        <p className="text-text-muted text-sm font-medium mt-1">
          Here's what's happening across Luma today.
        </p>
      </div>

      {/* Note alert if backend placeholders exist */}
      {stats?.note && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 text-xs px-4 py-3 rounded-xl flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0" />
          <span>{stats.note}</span>
        </div>
      )}

      {/* 4 Stat Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          label="TOTAL USERS"
          value={loading ? '...' : (typeof totalUsers === 'number' ? totalUsers.toLocaleString() : totalUsers)}
          subtext="Registered accounts"
          icon={Users}
        />
        <StatCard
          label="ACTIVE SESSIONS"
          value={loading ? '...' : activeSessions}
          subtext={stats?.active_sessions === null ? 'Coming soon (Session model pending)' : 'Live right now'}
          icon={LogIn}
        />
        <StatCard
          label="TOTAL COURSES"
          value={loading ? '...' : totalCourses}
          subtext={stats?.total_courses === null ? 'Coming soon (Course model pending)' : 'Active courses'}
          icon={BookOpen}
        />
        <StatCard
          label="STORAGE USED"
          value={loading ? '...' : storageUsed}
          subtext={stats?.storage_used_mb === null ? 'Coming soon' : 'Total media storage'}
          icon={Cloud}
        />
      </div>

      {/* Middle Row: Platform Activity & User Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Platform activity history is not stored yet */}
        <div className="lg:col-span-2 bg-surface border border-border/80 rounded-2xl p-6 shadow-sm flex flex-col justify-between">
          <h2 className="text-lg font-bold text-text mb-4">Platform Activity</h2>
          <div className="flex-1 flex flex-col items-center justify-center text-center gap-3 py-10">
            <p className="text-sm text-text-muted max-w-md">
              Activity over time is not available yet — Luma does not store a daily activity
              history. Current totals are shown above, and focus/quiz averages are on the
              Analytics page.
            </p>
            <Link
              to="/admin/analytics"
              className="min-h-11 px-4 inline-flex items-center rounded-xl bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold"
            >
              Open analytics
            </Link>
          </div>
        </div>

        {/* User Overview Box */}
        <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-sm flex flex-col justify-between">
          <div>
            <h2 className="text-lg font-bold text-text mb-6">User Overview</h2>
            
            <div className="space-y-5">
              {/* Students */}
              <div>
                <div className="flex justify-between text-xs font-bold text-text mb-1.5">
                  <span>Students</span>
                  <span>{totalStudents}</span>
                </div>
                <div className="w-full bg-bg rounded-full h-2">
                  <div 
                    className="bg-primary h-2 rounded-full transition-all duration-500" 
                    style={{ width: `${totalUsers > 0 ? (totalStudents / totalUsers) * 100 : 0}%` }}
                  ></div>
                </div>
              </div>

              {/* Teachers */}
              <div>
                <div className="flex justify-between text-xs font-bold text-text mb-1.5">
                  <span>Teachers</span>
                  <span>{totalTeachers}</span>
                </div>
                <div className="w-full bg-bg rounded-full h-2">
                  <div 
                    className="bg-emerald-500 h-2 rounded-full transition-all duration-500" 
                    style={{ width: `${totalUsers > 0 ? (totalTeachers / totalUsers) * 100 : 0}%` }}
                  ></div>
                </div>
              </div>

              {/* Admins */}
              <div>
                <div className="flex justify-between text-xs font-bold text-text mb-1.5">
                  <span>Admins</span>
                  <span>{totalAdmins}</span>
                </div>
                <div className="w-full bg-bg rounded-full h-2">
                  <div 
                    className="bg-amber-600 h-2 rounded-full transition-all duration-500" 
                    style={{ width: `${totalUsers > 0 ? (totalAdmins / totalUsers) * 100 : 0}%` }}
                  ></div>
                </div>
              </div>
            </div>
          </div>

          <Link
            to="/admin/users"
            className="mt-6 flex items-center justify-between text-xs font-semibold text-primary hover:underline pt-4 border-t border-border"
          >
            <span>View all users</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

      </div>

      {/* Bottom Row: Recent Activity & Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Recent Activity Feed */}
        <div className="lg:col-span-2 bg-surface border border-border/80 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-bold text-text">Recent Activity</h2>
            <Link to="/admin/logs" className="text-xs font-semibold text-primary hover:underline flex items-center gap-1">
              <span>View all logs</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <p className="text-sm text-text-muted">
            No activity feed is available yet. User changes can be reviewed on the Users page.
          </p>
        </div>

        {/* Quick Actions Box */}
        <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-sm flex flex-col justify-between">
          <h2 className="text-lg font-bold text-text mb-4">Quick Actions</h2>
          
          <div className="space-y-3">
            <button
              onClick={() => navigate('/admin/users')}
              className="w-full bg-primary hover:bg-primary-hover text-on-primary font-medium py-3 px-4 rounded-xl flex items-center justify-center gap-2 shadow-sm transition-all text-xs cursor-pointer"
            >
              <UserPlus className="w-4 h-4" />
              <span>Create User</span>
            </button>

            <button
              onClick={() => navigate('/admin/users')}
              className="w-full bg-surface border border-border hover:bg-bg text-text font-medium py-3 px-4 rounded-xl flex items-center justify-center gap-2 transition-all text-xs cursor-pointer"
            >
              <Upload className="w-4 h-4 text-text-muted" />
              <span>Import Users</span>
            </button>
          </div>

          <div className="pt-4 border-t border-border space-y-2 mt-4 text-xs font-medium text-text-muted">
            <Link to="/admin/logs" className="flex items-center gap-2 hover:text-primary p-1.5 rounded-lg hover:bg-bg transition-colors">
              <FileText className="w-4 h-4" />
              <span>View Logs</span>
            </Link>
            <Link to="/admin/analytics" className="flex items-center gap-2 hover:text-primary p-1.5 rounded-lg hover:bg-bg transition-colors">
              <BarChart2 className="w-4 h-4" />
              <span>View Analytics</span>
            </Link>
          </div>
        </div>

      </div>
    </div>
  );
};

export default AdminDashboard;
