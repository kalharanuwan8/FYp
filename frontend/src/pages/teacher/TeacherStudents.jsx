import { Users, Search, GraduationCap } from 'lucide-react';

export const TeacherStudents = () => {
  return (
    <div className="space-y-6 max-w-7xl mx-auto font-sans">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text tracking-tight">Student Roster</h1>
          <p className="text-xs text-text-muted font-medium mt-1">
            Manage enrolled students across your assigned course subjects.
          </p>
        </div>
      </div>

      <div className="bg-surface border border-border/80 rounded-2xl p-8 text-center text-text-muted text-xs space-y-3 shadow-xs">
        <div className="p-3 bg-primary-soft text-primary rounded-2xl w-fit mx-auto border border-primary/30">
          <GraduationCap className="w-6 h-6" />
        </div>
        <h3 className="text-sm font-bold text-text">No separate roster page yet</h3>
        <p className="max-w-md mx-auto text-text-muted">
          A combined student roster is not available yet. Enrolled students are managed within
          each subject&apos;s course editor pages.
        </p>
      </div>
    </div>
  );
};

export default TeacherStudents;
