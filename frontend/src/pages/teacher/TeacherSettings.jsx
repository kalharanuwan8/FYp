import { useContext } from 'react';
import { User, Mail, Shield, BookOpen } from 'lucide-react';
import { AuthContext } from '../../context/AuthContext';

export const TeacherSettings = () => {
  const { user } = useContext(AuthContext);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-blue-700 to-indigo-700 rounded-3xl p-6 md:p-8 text-white shadow-xl">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 bg-surface/20 backdrop-blur-md rounded-xl flex items-center justify-center">
            <User className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-2xl font-black tracking-tight">Teacher Account Settings</h1>
        </div>
        <p className="text-blue-100 text-xs font-medium max-w-xl">
          Manage your instructor account information and classroom preferences.
        </p>
      </div>

      {/* Account Info Card */}
      <div className="bg-surface dark:bg-surface border border-border dark:border-border rounded-3xl p-6 shadow-xs space-y-5">
        <h3 className="text-sm font-extrabold text-text uppercase tracking-wider flex items-center gap-2">
          <Shield className="w-4 h-4 text-blue-600" /> Instructor Profile Details
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-bold text-text-muted mb-1">Full Name</label>
            <div className="relative">
              <input
                type="text"
                disabled
                value={`${user?.first_name || ''} ${user?.last_name || ''}`}
                className="w-full bg-bg dark:bg-surface/60 border border-border dark:border-border rounded-xl px-4 py-2.5 pl-10 text-xs text-text dark:text-text-muted font-semibold cursor-not-allowed"
              />
              <User className="w-4 h-4 text-text-muted absolute left-3 top-3" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold text-text-muted mb-1">Email Address</label>
            <div className="relative">
              <input
                type="text"
                disabled
                value={user?.email || ''}
                className="w-full bg-bg dark:bg-surface/60 border border-border dark:border-border rounded-xl px-4 py-2.5 pl-10 text-xs text-text dark:text-text-muted font-semibold cursor-not-allowed"
              />
              <Mail className="w-4 h-4 text-text-muted absolute left-3 top-3" />
            </div>
          </div>
        </div>

        <div className="p-4 bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800/60 rounded-2xl flex items-center gap-3">
          <BookOpen className="w-5 h-5 text-blue-600 shrink-0" />
          <div className="text-xs text-text dark:text-text-muted">
            <span className="font-bold">Role: </span>
            <span className="capitalize font-semibold text-blue-700 dark:text-blue-400">Teacher / Course Instructor</span>
            <p className="text-text-muted dark:text-text-muted text-[11px] mt-0.5">
              Course creation, module management, and live student focus analytics are enabled for your profile.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TeacherSettings;
