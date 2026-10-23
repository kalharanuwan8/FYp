import { useState, useEffect } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { BookOpen, ArrowRight, Sparkles } from 'lucide-react';
import { courseService } from '../../services/courseService';
import { analyticsService } from '../../services/analyticsService';
import { useAuth } from '../../hooks/useAuth';
import { Button, Card, ProgressRing, BadgeChip, EmptyState, LoadingSpinner, ErrorBanner, XPChip, StreakChip } from '../../components/common';
import { accentForId } from '../../utils/subjectAccents';

export default function StudentDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { progress, refreshProgress } = useOutletContext() || {};

  const [enrollments, setEnrollments] = useState([]);
  const [subjectStats, setSubjectStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [data, analytics] = await Promise.all([
          courseService.listMyEnrollments(),
          analyticsService.getStudentAnalytics().catch(() => null),
        ]);
        if (cancelled) return;
        setEnrollments(data.enrollments || []);
        const byId = {};
        (analytics?.subject_progress || []).forEach((s) => {
          byId[s.subject_id] = s;
        });
        setSubjectStats(byId);
        refreshProgress?.();
      } catch (err) {
        if (!cancelled) {
          setError(err.response?.data?.error || 'Failed to load your subjects.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshProgress]);

  const continueCourse = enrollments[0];
  const goal = progress?.daily_goal_minutes || 20;
  const todayMins = progress?.today_focus_minutes || 0;
  const lastBadge = (progress?.badges || [])[0];
  const continueAccent = continueCourse ? accentForId(continueCourse.id) : null;
  const continueStats = continueCourse ? subjectStats[continueCourse.id] : null;

  return (
    <div className="space-y-8 max-w-5xl mx-auto animate-fade-in">
      <div>
        <h1 className="font-display text-2xl md:text-3xl font-bold text-text">
          Hi {user?.first_name || 'there'}, ready to learn?
        </h1>
        <p className="text-text-muted mt-1">One step at a time — pick up a subject below.</p>
      </div>

      {/* Continue learning — the one clear next action */}
      <Card className="p-6 md:p-8 relative overflow-hidden">
        <div
          className="absolute inset-0 opacity-40 pointer-events-none"
          style={{
            background:
              'radial-gradient(ellipse at top right, color-mix(in srgb, var(--primary) 22%, transparent), transparent 55%)',
          }}
          aria-hidden="true"
        />
        <div className="relative z-10 space-y-4 max-w-xl">
          <p className="text-sm font-semibold text-primary inline-flex items-center gap-2">
            <Sparkles className="w-4 h-4" aria-hidden="true" /> Continue learning
          </p>
          {continueCourse ? (
            <>
              <h2 className="font-display text-2xl font-bold text-text">{continueCourse.title}</h2>
              <p className="text-text-muted prose-narrow">
                {continueStats?.sessions_count
                  ? `You've had ${continueStats.sessions_count} focus session${continueStats.sessions_count === 1 ? '' : 's'} in this subject. Open it to choose your next lesson.`
                  : 'Open this subject to choose your next lesson.'}
              </p>
              <Button size="lg" onClick={() => navigate(`/student/subjects/${continueCourse.id}`)}>
                Continue lesson
                <ArrowRight className="w-5 h-5" aria-hidden="true" />
              </Button>
              <span
                className="inline-block w-3 h-3 rounded-full align-middle ml-1"
                style={{ background: continueAccent?.color }}
                aria-hidden="true"
              />
            </>
          ) : (
            <>
              <h2 className="font-display text-2xl font-bold text-text">Find your first subject</h2>
              <p className="text-text-muted prose-narrow">
                Explore subjects for your grade and enrol — your lessons will appear here.
              </p>
              <Button size="lg" onClick={() => navigate('/student/courses?tab=explore')}>
                Explore subjects
                <ArrowRight className="w-5 h-5" aria-hidden="true" />
              </Button>
            </>
          )}
        </div>
      </Card>

      {/* Compact daily goal */}
      <Card className="p-5 flex items-center gap-4">
        <ProgressRing value={todayMins} max={goal} size={72} color="var(--success)" label="Daily focus goal">
          <span className="font-display font-bold text-sm text-text">{todayMins}m</span>
        </ProgressRing>
        <div>
          <h2 className="font-display font-bold text-text">Today&apos;s focus goal</h2>
          <p className="text-sm text-text-muted">
            {todayMins} of {goal} minutes so far. Any amount counts — nice work showing up.
          </p>
        </div>
      </Card>

      {/* Secondary rewards row */}
      <div className="flex flex-wrap items-center gap-3" aria-label="Your rewards">
        <XPChip xp={progress?.xp || 0} />
        <span className="inline-flex items-center min-h-9 px-3 rounded-full bg-lavender/20 text-text text-sm font-semibold">
          Level {progress?.level || 1}
        </span>
        <StreakChip streak={progress?.current_streak || 0} />
        {lastBadge?.badge ? (
          <BadgeChip icon={lastBadge.badge.icon} name={lastBadge.badge.name} description="Latest badge" />
        ) : (
          <span className="text-sm text-text-muted">Finish a focus session to earn your first badge.</span>
        )}
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-display text-xl font-bold text-text">Your subjects</h2>
          <button
            type="button"
            onClick={() => navigate('/student/courses')}
            className="text-sm font-semibold text-primary min-h-11 px-2 cursor-pointer"
          >
            See all
          </button>
        </div>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
        {loading ? (
          <LoadingSpinner label="Loading subjects…" />
        ) : enrollments.length === 0 ? (
          <Card>
            <EmptyState
              icon={BookOpen}
              title="No subjects yet"
              description="Explore courses for your grade and enrol with one tap."
              actionLabel="Explore subjects"
              onAction={() => navigate('/student/courses?tab=explore')}
            />
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {enrollments.map((course) => {
              const accent = accentForId(course.id);
              const stats = subjectStats[course.id];
              return (
                <Card
                  as="button"
                  type="button"
                  key={course.id}
                  className="p-5 flex items-center gap-4 hover:shadow-lift transition-shadow cursor-pointer text-left w-full"
                  onClick={() => navigate(`/student/subjects/${course.id}`)}
                  style={{ borderLeft: `4px solid ${accent.color}` }}
                >
                  <span
                    className="w-12 h-12 rounded-2xl flex items-center justify-center shrink-0"
                    style={{ background: accent.soft, color: accent.color }}
                    aria-hidden="true"
                  >
                    <BookOpen className="w-6 h-6" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-xs font-semibold text-text-muted">
                      {course.grade_level_name || 'Subject'}
                    </span>
                    <span className="block font-display font-bold text-text truncate">{course.title}</span>
                    <span className="block text-sm text-text-muted line-clamp-1">
                      {stats
                        ? `${stats.sessions_count} session${stats.sessions_count === 1 ? '' : 's'} · ${Math.round(stats.avg_focus_percentage || 0)}% average focus`
                        : course.description || 'Open to see your lessons'}
                    </span>
                  </span>
                  <ArrowRight className="w-5 h-5 text-text-muted shrink-0" aria-hidden="true" />
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
