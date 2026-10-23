import { useState, useEffect } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { analyticsService } from '../../services/analyticsService';
import studentService from '../../services/studentService';
import { Card, LoadingSpinner, ErrorBanner, BadgeChip, StreakChip } from '../../components/common';

function insightFromData(data, progress) {
  if ((progress?.current_streak || 0) >= 3) {
    return 'Your streak is growing — showing up regularly really helps.';
  }
  if ((data?.avg_focus_percentage || 0) >= 70) {
    return 'Your average focus across sessions is strong. Short, steady sessions seem to work well for you.';
  }
  if ((data?.total_study_minutes || 0) < 20) {
    return 'Start with a 10-minute session — small steps add up.';
  }
  return 'Every session adds up. Open a subject and pick up where you left off.';
}

function Stat({ label, value }) {
  return (
    <Card className="p-4">
      <p className="font-display text-2xl font-bold text-text">{value}</p>
      <p className="text-sm text-text-muted mt-1">{label}</p>
    </Card>
  );
}

export default function StudentAnalytics() {
  const [data, setData] = useState(null);
  const [progress, setProgress] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [analytics, prog] = await Promise.all([
          analyticsService.getStudentAnalytics(),
          studentService.getProgress().catch(() => null),
        ]);
        setData(analytics);
        setProgress(prog);
      } catch (err) {
        setError(err.response?.data?.error || 'Failed to load progress.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <LoadingSpinner label="Loading your progress…" />;
  if (error || !data) {
    return (
      <div className="max-w-4xl mx-auto">
        <ErrorBanner message={error || 'Could not load progress'} />
      </div>
    );
  }

  const subjects = data.subject_progress || [];
  const chartData = subjects.map((s) => ({
    name: s.title,
    focus: Math.round(s.avg_focus_percentage || 0),
    sessions: s.sessions_count || 0,
  }));
  const catalog = progress?.badge_catalog || [];
  const streak = progress?.current_streak || 0;
  const totalMinutes = progress?.total_focus_minutes ?? data.total_study_minutes ?? 0;

  return (
    <div className="space-y-8 max-w-4xl mx-auto animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-text">Your progress</h1>
        <p className="text-text-muted text-sm mt-1">
          Focus minutes, streaks, and badges — celebrated, not scored.
        </p>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <StreakChip streak={streak} />
        <span className="text-sm text-text-muted">{totalMinutes} focused minutes overall</span>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <Stat label="Study time (minutes)" value={data.total_study_minutes ?? 0} />
        <Stat label="Learning sessions" value={data.total_sessions ?? 0} />
        <Stat
          label="Average focus"
          value={
            data.avg_focus_percentage == null
              ? '—'
              : `${Math.round(data.avg_focus_percentage)}%`
          }
        />
        <Stat
          label="Monitoring coverage"
          value={
            data.avg_monitoring_coverage_pct == null
              ? '—'
              : `${Math.round(data.avg_monitoring_coverage_pct)}%`
          }
        />
        <Stat
          label="Quizzes finished"
          value={data.completed_quizzes ?? 0}
        />
      </div>
      {(data.completed_quizzes || 0) > 0 && (
        <p className="text-sm text-text-muted">
          Your average quiz score so far is {data.avg_quiz_score}%.
        </p>
      )}

      <Card className="p-5 md:p-6 space-y-3">
        <h2 className="font-display font-bold text-text">Focus by subject</h2>
        {subjects.length === 0 ? (
          <p className="text-sm text-text-muted">
            Once you start learning a subject, your focus for it will appear here.
          </p>
        ) : (
          <>
            <div className="h-56 w-full" aria-hidden="true">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} axisLine={false} />
                  <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 12 }} axisLine={false} unit="%" domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 12,
                      border: '1px solid var(--border)',
                      background: 'var(--surface)',
                    }}
                  />
                  <Bar dataKey="focus" fill="var(--primary)" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <ul className="space-y-2">
              {subjects.map((s) => (
                <li
                  key={s.subject_id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border bg-bg px-4 py-3 text-sm"
                >
                  <span className="font-semibold text-text">{s.title}</span>
                  <span className="text-text-muted">
                    {s.sessions_count} session{s.sessions_count === 1 ? '' : 's'} ·{' '}
                    {s.avg_focus_percentage == null
                      ? 'focus unavailable'
                      : `${Math.round(s.avg_focus_percentage)}% average focus`}
                    {s.avg_monitoring_coverage_pct != null
                      ? ` · ${Math.round(s.avg_monitoring_coverage_pct)}% coverage`
                      : ''}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <Card className="p-5 space-y-2">
        <h2 className="font-display font-bold text-text">A note for you</h2>
        <p className="text-text-muted prose-narrow">{insightFromData(data, progress)}</p>
      </Card>

      <div className="space-y-3">
        <h2 className="font-display font-bold text-text">Badge shelf</h2>
        {catalog.length === 0 ? (
          <Card className="p-6 text-sm text-text-muted">
            Earn badges by focusing and finishing quizzes.
          </Card>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {catalog.map((b) => (
              <BadgeChip
                key={b.code}
                icon={b.icon}
                name={b.name}
                description={b.description}
                earned={b.earned}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
