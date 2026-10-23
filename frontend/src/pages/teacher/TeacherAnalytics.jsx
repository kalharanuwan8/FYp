import { useState, useEffect } from 'react';
import { 
  BarChart3, 
  Users, 
  BookOpen, 
  Activity, 
  Award, 
  TrendingUp, 
  AlertCircle,
  GraduationCap
} from 'lucide-react';
import { analyticsService } from '../../services/analyticsService';

export const TeacherAnalytics = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchAnalytics = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await analyticsService.getTeacherAnalytics();
      setData(res);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load teacher analytics report.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, []);

  if (loading) {
    return (
      <div className="bg-surface border border-border/80 rounded-2xl p-12 text-center text-xs text-text-muted max-w-6xl mx-auto font-sans">
        Loading class performance analytics...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 text-xs p-6 rounded-2xl max-w-6xl mx-auto font-sans">
        {error || 'Failed to load analytics'}
      </div>
    );
  }

  const getFocusBadge = (pct) => {
    if (pct >= 75) return <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-bold px-2 py-0.5 rounded-md">High Focus</span>;
    if (pct >= 50) return <span className="bg-primary-soft text-primary border border-primary/30 text-[10px] font-bold px-2 py-0.5 rounded-md">Moderate Focus</span>;
    return <span className="bg-amber-50 text-amber-700 border border-amber-200 text-[10px] font-bold px-2 py-0.5 rounded-md">Needs Attention</span>;
  };

  return (
    <div className="space-y-8 max-w-6xl mx-auto font-sans">
      
      {/* Header */}
      <div>
        <h1 className="text-2xl font-extrabold text-text tracking-tight flex items-center gap-2">
          <BarChart3 className="w-6 h-6 text-primary" />
          <span>Class Analytics & Engagement Report</span>
        </h1>
        <p className="text-xs text-text-muted font-medium mt-1">
          Real-time aggregated engagement metrics, focus scores, and quiz performance for your assigned courses.
        </p>
      </div>

      {/* Overview Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-2xs space-y-2">
          <div className="flex items-center justify-between text-text-muted">
            <span className="text-xs font-semibold">Total Students</span>
            <Users className="w-4 h-4 text-primary" />
          </div>
          <p className="text-3xl font-extrabold text-text">{data.total_students}</p>
          <span className="text-[11px] text-text-muted font-medium">Across assigned subjects</span>
        </div>

        <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-2xs space-y-2">
          <div className="flex items-center justify-between text-text-muted">
            <span className="text-xs font-semibold">Learning Sessions</span>
            <Activity className="w-4 h-4 text-purple-600" />
          </div>
          <p className="text-3xl font-extrabold text-text">{data.total_sessions}</p>
          <span className="text-[11px] text-text-muted font-medium">Completed telemetry sessions</span>
        </div>

        <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-2xs space-y-2">
          <div className="flex items-center justify-between text-text-muted">
            <span className="text-xs font-semibold">Avg Class Focus Score</span>
            <TrendingUp className="w-4 h-4 text-emerald-600" />
          </div>
          <p className="text-3xl font-extrabold text-emerald-600">{data.avg_focus_percentage}%</p>
          <span className="text-[11px] text-text-muted font-medium">Average sustained focus</span>
        </div>

        <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-2xs space-y-2">
          <div className="flex items-center justify-between text-text-muted">
            <span className="text-xs font-semibold">Avg Quiz Score</span>
            <Award className="w-4 h-4 text-amber-500" />
          </div>
          <p className="text-3xl font-extrabold text-amber-600">{data.avg_quiz_score}%</p>
          <span className="text-[11px] text-text-muted font-medium">Auto-graded assessment avg</span>
        </div>
      </div>

      {/* Subject Performance Breakdown Table */}
      <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-2xs space-y-4">
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div>
            <h2 className="text-base font-bold text-text">Subject Performance Breakdown</h2>
            <p className="text-xs text-text-muted font-medium">Detailed focus and quiz score comparisons per subject</p>
          </div>
        </div>

        {data.subject_breakdown.length === 0 ? (
          <div className="text-center py-8 text-xs text-text-muted font-medium">
            No subjects assigned yet to generate performance data.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-medium text-text">
              <thead>
                <tr className="border-b border-border text-text-muted text-[11px] uppercase tracking-wider">
                  <th className="pb-3 pl-2">Subject Title</th>
                  <th className="pb-3">Grade Level</th>
                  <th className="pb-3">Enrolled</th>
                  <th className="pb-3">Avg Focus Score</th>
                  <th className="pb-3">Avg Quiz Score</th>
                  <th className="pb-3 pr-2">Engagement Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.subject_breakdown.map((subj) => (
                  <tr key={subj.subject_id} className="hover:bg-bg/80 transition-colors">
                    <td className="py-3.5 pl-2 font-bold text-text">{subj.title}</td>
                    <td className="py-3.5 text-text-muted">{subj.grade_level_name}</td>
                    <td className="py-3.5 font-bold text-text">{subj.enrolled_students} Students</td>
                    <td className="py-3.5 font-extrabold text-emerald-600">{subj.avg_focus_percentage}%</td>
                    <td className="py-3.5 font-extrabold text-amber-600">{subj.avg_quiz_score}%</td>
                    <td className="py-3.5 pr-2">{getFocusBadge(subj.avg_focus_percentage)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
};

export default TeacherAnalytics;
