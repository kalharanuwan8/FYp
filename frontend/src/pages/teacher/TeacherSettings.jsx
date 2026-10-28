import { useContext } from 'react';
import { User, Mail, Shield, BookOpen } from 'lucide-react';
import { AuthContext } from '../../context/AuthContext';
import { Card } from '../../components/common';

export const TeacherSettings = () => {
  const { user } = useContext(AuthContext);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold text-text">Teacher account</h1>
        <p className="text-sm text-text-muted mt-1">
          Your instructor profile details for this platform.
        </p>
      </div>

      <Card className="p-6 space-y-5">
        <h2 className="text-sm font-bold text-text flex items-center gap-2">
          <Shield className="w-4 h-4 text-primary" aria-hidden="true" /> Profile
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1" htmlFor="teacher-name">
              Full name
            </label>
            <div className="relative">
              <input
                id="teacher-name"
                type="text"
                disabled
                value={`${user?.first_name || ''} ${user?.last_name || ''}`}
                className="w-full bg-bg border border-border rounded-xl px-4 py-2.5 pl-10 text-sm text-text font-medium cursor-not-allowed"
              />
              <User className="w-4 h-4 text-text-muted absolute left-3 top-3" aria-hidden="true" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1" htmlFor="teacher-email">
              Email
            </label>
            <div className="relative">
              <input
                id="teacher-email"
                type="email"
                disabled
                value={user?.email || ''}
                className="w-full bg-bg border border-border rounded-xl px-4 py-2.5 pl-10 text-sm text-text font-medium cursor-not-allowed"
              />
              <Mail className="w-4 h-4 text-text-muted absolute left-3 top-3" aria-hidden="true" />
            </div>
          </div>
        </div>

        <p className="text-sm text-text-muted flex items-start gap-2">
          <BookOpen className="w-4 h-4 shrink-0 mt-0.5 text-primary" aria-hidden="true" />
          Course authoring and intervention settings live in each subject&apos;s course editor.
        </p>
      </Card>
    </div>
  );
};

export default TeacherSettings;
