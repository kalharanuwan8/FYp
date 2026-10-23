import { useState, useEffect } from 'react';
import { 
  BarChart3, 
  Users, 
  BookOpen, 
  Activity, 
  Award, 
  TrendingUp,
  ShieldCheck,
  GraduationCap
} from 'lucide-react';
import { analyticsService } from '../../services/analyticsService';

export const AnalyticsPage = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchAnalytics = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await analyticsService.getAdminAnalytics();
      setData(res);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load system-wide analytics.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, []);

  if (loading) {
    return (
      <div className="bg-surface border border-border/80 rounded-2xl p-12 text-center text-xs text-text-muted max-w-7xl mx-auto font-sans">
        Loading system-wide platform metrics...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 text-xs p-6 rounded-2xl max-w-7xl mx-auto font-sans">
        {error || 'Failed to load admin analytics'}
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-7xl mx-auto font-sans">
      
      {/* Header */}
      <div>
        <h1 className="text-2xl font-extrabold text-text tracking-tight flex items-center gap-2">
          <BarChart3 className="w-6 h-6 text-primary" />
          <span>System-Wide Platform Analytics</span>
        </h1>
        <p className="text-xs text-text-muted font-medium mt-1">
          Aggregate platform metrics, active user breakdowns, learning sessions, and focus scores.
        </p>
      </div>

      {/* Summary Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-2xs space-y-2">
          <div className="flex items-center justify-between text-text-muted">
            <span className="text-xs font-semibold">Total Accounts</span>
            <Users className="w-4 h-4 text-primary" />
          </div>
          <p className="text-3xl font-extrabold text-text">{data.total_users}</p>
          <span className="text-[11px] text-text-muted font-medium">
            {data.total_students} Students • {data.total_teachers} Teachers
          </span>
        </div>

        <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-2xs space-y-2">
          <div className="flex items-center justify-between text-text-muted">
            <span className="text-xs font-semibold">Active Subjects</span>
            <BookOpen className="w-4 h-4 text-purple-600" />
          </div>
          <p className="text-3xl font-extrabold text-text">{data.total_subjects}</p>
          <span className="text-[11px] text-text-muted font-medium">Published course subjects</span>
        </div>

        <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-2xs space-y-2">
          <div className="flex items-center justify-between text-text-muted">
            <span className="text-xs font-semibold">Learning Sessions</span>
            <Activity className="w-4 h-4 text-primary" />
          </div>
          <p className="text-3xl font-extrabold text-text">{data.total_sessions}</p>
          <span className="text-[11px] text-text-muted font-medium">Monitored sessions logged</span>
        </div>

        <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-2xs space-y-2">
          <div className="flex items-center justify-between text-text-muted">
            <span className="text-xs font-semibold">Platform Avg Focus</span>
            <TrendingUp className="w-4 h-4 text-emerald-600" />
          </div>
          <p className="text-3xl font-extrabold text-emerald-600">{data.platform_avg_focus}%</p>
          <span className="text-[11px] text-text-muted font-medium">System-wide focus score</span>
        </div>
      </div>

      {/* Platform Distribution Card */}
      <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-2xs space-y-4">
        <h2 className="text-base font-bold text-text">Platform Usage Overview</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-2">
          <div className="bg-bg p-5 rounded-2xl border border-border/80 space-y-1">
            <span className="text-xs text-text-muted font-semibold block">Students Enrolled</span>
            <p className="text-2xl font-extrabold text-text">{data.total_students}</p>
          </div>

          <div className="bg-bg p-5 rounded-2xl border border-border/80 space-y-1">
            <span className="text-xs text-text-muted font-semibold block">Teachers Assigned</span>
            <p className="text-2xl font-extrabold text-primary">{data.total_teachers}</p>
          </div>

          <div className="bg-bg p-5 rounded-2xl border border-border/80 space-y-1">
            <span className="text-xs text-text-muted font-semibold block">Completed Quizzes</span>
            <p className="text-2xl font-extrabold text-emerald-600">{data.completed_quizzes}</p>
          </div>
        </div>
      </div>

    </div>
  );
};

export default AnalyticsPage;
