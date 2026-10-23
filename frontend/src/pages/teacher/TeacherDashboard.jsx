import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  BookOpen, 
  Plus, 
  Users, 
  ArrowRight, 
  FileText, 
  Lightbulb, 
  BarChart2, 
  Upload, 
  HelpCircle,
  TrendingUp,
  AlertTriangle,
  CheckCircle2
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { courseService } from '../../services/courseService';
import CreateSubjectModal from '../../components/teacher/CreateSubjectModal';

export const TeacherDashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createModalOpen, setCreateModalOpen] = useState(false);

  const teacherName = user ? `${user.first_name || ''}`.trim() || 'Teacher' : 'Teacher';

  const fetchTeacherSubjects = async () => {
    setLoading(true);
    try {
      const data = await courseService.getSubjects({ per_page: 10 });
      setSubjects(data.subjects || []);
    } catch (err) {
      console.error('Failed to fetch subjects', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTeacherSubjects();
  }, []);

  return (
    <div className="space-y-8 max-w-7xl mx-auto font-sans">
      {/* Header Greeting */}
      <div>
        <h1 className="text-3xl font-extrabold text-text tracking-tight">
          Good morning, {teacherName}
        </h1>
        <p className="text-text-muted text-sm font-medium mt-1">
          Here is an overview of your students' progress today.
        </p>
      </div>

      {/* Active Courses Section */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-text flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-primary" />
            <span>Active Courses</span>
          </h2>
          <button
            onClick={() => navigate('/teacher/courses')}
            className="text-xs font-bold text-primary hover:underline flex items-center gap-1"
          >
            <span>View All</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Courses Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {loading ? (
            <div className="col-span-3 bg-surface p-8 rounded-2xl border border-border text-center text-xs text-text-muted">
              Loading active courses...
            </div>
          ) : (
            <>
              {subjects.map((subj) => (
                <div
                  key={subj.id}
                  className="bg-surface border border-border/80 rounded-2xl p-6 shadow-xs hover:shadow-md transition-all flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between mb-4">
                      <div className="w-10 h-10 rounded-xl bg-bg flex items-center justify-center text-text-muted font-bold">
                        <BookOpen className="w-5 h-5" />
                      </div>
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
                        <TrendingUp className="w-3 h-3" />
                        <span>Active</span>
                      </span>
                    </div>

                    <h3 className="font-bold text-text text-lg mb-1 leading-snug line-clamp-1">
                      {subj.title}
                    </h3>
                    <p className="text-xs text-text-muted font-medium mb-4 flex items-center gap-1">
                      <Users className="w-3.5 h-3.5" />
                      <span>Grade: {subj.grade_level_name || 'Standard'}</span>
                    </p>
                  </div>

                  <button
                    onClick={() => navigate(`/teacher/courses/${subj.id}`)}
                    className="w-full bg-surface border border-border hover:bg-bg text-text font-semibold py-2.5 px-4 rounded-xl text-xs transition-all cursor-pointer text-center"
                  >
                    Manage Course
                  </button>
                </div>
              ))}

              {/* Create New Course Card */}
              <button
                onClick={() => setCreateModalOpen(true)}
                className="bg-bg/70 border-2 border-dashed border-border hover:border-primary hover:bg-bg/50 rounded-2xl p-8 flex flex-col items-center justify-center gap-3 text-text-muted hover:text-primary transition-all cursor-pointer min-h-[190px]"
              >
                <div className="w-12 h-12 rounded-full bg-surface border border-border flex items-center justify-center shadow-xs">
                  <Plus className="w-6 h-6" />
                </div>
                <span className="font-bold text-sm">Create New Course</span>
              </button>
            </>
          )}
        </div>
      </div>

      {/* Middle Row: Student Engagement Trends & Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Student Engagement Trends — daily history is not collected yet */}
        <div className="lg:col-span-2 bg-surface border border-border/80 rounded-2xl p-6 shadow-xs flex flex-col justify-between">
          <h2 className="text-lg font-bold text-text flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-primary" />
            <span>Student Engagement</span>
          </h2>
          <div className="flex-1 flex flex-col items-center justify-center text-center gap-3 py-10">
            <p className="text-sm text-text-muted max-w-md">
              Engagement trends over time are not available yet — Luma does not store a daily
              history. You can see current focus and quiz averages for your subjects on the
              Analytics page.
            </p>
            <button
              type="button"
              onClick={() => navigate('/teacher/analytics')}
              className="min-h-11 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold cursor-pointer"
            >
              Open analytics
            </button>
          </div>
        </div>

        {/* Quick Actions & Teaching Tip Column */}
        <div className="space-y-6 flex flex-col justify-between">
          
          {/* Quick Actions Box */}
          <div className="bg-bg/70 border border-border/80 rounded-2xl p-6">
            <h2 className="text-sm font-bold text-text mb-4 flex items-center gap-2">
              <span>⚡ Quick Actions</span>
            </h2>

            <div className="grid grid-cols-2 gap-3 mb-4">
              <button
                onClick={() => setCreateModalOpen(true)}
                className="bg-surface hover:bg-bg border border-border p-3 rounded-xl flex flex-col items-center gap-1.5 text-xs font-bold text-text shadow-xs cursor-pointer"
              >
                <Plus className="w-4 h-4 text-primary" />
                <span>New Course</span>
              </button>

              <button
                onClick={() => navigate('/teacher/courses')}
                className="bg-surface hover:bg-bg border border-border p-3 rounded-xl flex flex-col items-center gap-1.5 text-xs font-bold text-text shadow-xs cursor-pointer"
              >
                <BookOpen className="w-4 h-4 text-primary" />
                <span>Add Module</span>
              </button>

              <button
                onClick={() => navigate('/teacher/courses')}
                className="bg-surface hover:bg-bg border border-border p-3 rounded-xl flex flex-col items-center gap-1.5 text-xs font-bold text-text shadow-xs cursor-pointer"
              >
                <Upload className="w-4 h-4 text-text-muted" />
                <span>Upload File</span>
              </button>

              <button
                onClick={() => navigate('/teacher/courses')}
                className="bg-surface hover:bg-bg border border-border p-3 rounded-xl flex flex-col items-center gap-1.5 text-xs font-bold text-text shadow-xs cursor-pointer"
              >
                <FileText className="w-4 h-4 text-text-muted" />
                <span>Create Quiz</span>
              </button>
            </div>
          </div>

          {/* Teaching Tip Box matching screenshot */}
          <div className="bg-amber-50/70 border border-amber-200/80 rounded-2xl p-5 text-center">
            <div className="w-10 h-10 rounded-full bg-amber-600 text-white flex items-center justify-center mx-auto mb-3 shadow-xs">
              <Lightbulb className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-amber-900 text-xs mb-1">Teaching Tip</h3>
            <p className="text-[11px] text-amber-800 leading-relaxed font-medium">
              Breaking lessons into short, clearly-labelled steps can make it easier for students to start — and to pick up again after a break.
            </p>
          </div>

        </div>

      </div>

      {/* Recent activity — no live feed endpoint exists yet */}
      <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-xs">
        <h2 className="text-lg font-bold text-text mb-2">Recent Interventions</h2>
        <p className="text-sm text-text-muted">
          A live intervention feed is not available yet. Per-student session and focus details
          are on the Students and Analytics pages.
        </p>
      </div>

      {/* Create Subject Modal */}
      <CreateSubjectModal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        onSuccess={fetchTeacherSubjects}
      />
    </div>
  );
};

export default TeacherDashboard;
