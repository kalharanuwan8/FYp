import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mail, Lock, Eye, EyeOff, ArrowRight, Brain, Sparkles, Activity } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

const HERO_SLIDES = [
  {
    icon: Brain,
    title: 'Personalized Learning',
    description: 'Tailored approaches to fit exactly how your unique brain works best.',
    color: 'bg-mint/25 text-success',
  },
  {
    icon: Sparkles,
    title: 'Adaptive Support',
    description: 'Gentle micro-interventions designed to preserve flow and restore focus seamlessly.',
    color: 'bg-sun/25 text-warning',
  },
  {
    icon: Activity,
    title: 'Real-Time Insights',
    description: 'Empowering students and educators with privacy-first learning telemetry.',
    color: 'bg-primary-soft text-primary',
  },
];

export const LoginPage = () => {
  const navigate = useNavigate();
  const { login, loading, error, setError } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [activeSlide, setActiveSlide] = useState(0);
  const [forgotNotice, setForgotNotice] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please fill in all fields.');
      return;
    }
    try {
      const user = await login(email, password);
      const role = String(user.role || '').toLowerCase();
      if (role === 'admin') {
        navigate('/admin/dashboard');
      } else if (role === 'teacher') {
        navigate('/teacher/dashboard');
      } else {
        navigate('/student/dashboard');
      }
    } catch {
      // Error handled by AuthContext
    }
  };

  const CurrentIcon = HERO_SLIDES[activeSlide].icon;

  return (
    <div className="min-h-screen bg-bg flex flex-col justify-between p-6 md:p-10 font-sans text-text">
      {/* Brand Header */}
      <header className="w-full max-w-6xl mx-auto flex items-center justify-between py-2">
        <div className="flex items-center gap-2">
          <span className="text-2xl font-extrabold text-primary tracking-tight">Luma</span>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="w-full max-w-6xl mx-auto my-auto py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 md:gap-12 items-center">
          
          {/* Left Hero Card */}
          <div className="order-2 md:order-1 bg-learning border border-border rounded-3xl p-10 md:p-14 flex flex-col justify-between items-center text-center min-h-[440px] shadow-soft">
            <div className="flex-1 flex flex-col items-center justify-center my-auto max-w-sm">
              <div className={`w-20 h-20 rounded-full ${HERO_SLIDES[activeSlide].color} flex items-center justify-center mb-6 border border-border`}>
                <CurrentIcon className="w-10 h-10" aria-hidden="true" />
              </div>
              <h2 className="text-2xl md:text-3xl font-bold text-text mb-3 tracking-tight">
                {HERO_SLIDES[activeSlide].title}
              </h2>
              <p className="text-text-muted text-sm leading-relaxed">
                {HERO_SLIDES[activeSlide].description}
              </p>
            </div>

            {/* Carousel Navigation Dots */}
            <div className="flex items-center gap-2.5 mt-8">
              {HERO_SLIDES.map((_, idx) => (
                <button
                  key={idx}
                  onClick={() => setActiveSlide(idx)}
                  className={`transition-all duration-300 rounded-full cursor-pointer ${
                    activeSlide === idx
                      ? 'w-3 h-3 bg-primary'
                      : 'w-3 h-3 bg-border hover:bg-text-muted'
                  }`}
                  aria-label={`Slide ${idx + 1}`}
                />
              ))}
            </div>
          </div>

          {/* Right Login Form Card */}
          <div className="order-1 md:order-2 bg-surface border border-border rounded-2xl p-8 md:p-12 shadow-lift flex flex-col justify-center">
            <div className="mb-8 text-center">
              <h1 className="text-3xl md:text-4xl font-bold text-text tracking-tight mb-2">
                Welcome back to Luma
              </h1>
              <p className="text-text-muted text-sm font-medium">
                Your learning. Your pace. Your way.
              </p>
            </div>

            {error && (
              <div
                role="alert"
                className="mb-6 p-3.5 rounded-lg bg-danger/10 border border-danger text-danger text-sm font-medium text-center"
              >
                {error}
              </div>
            )}
            {forgotNotice && (
              <p className="mb-6 text-sm text-text-muted text-center" role="status">
                Password resets are handled by your school — please ask your teacher or an administrator to reset it for you.
              </p>
            )}

            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Email Address */}
              <div>
                <label htmlFor="login-email" className="block text-xs font-bold text-text uppercase tracking-wider mb-2">
                  Email Address
                </label>
                <div className="relative flex items-center">
                  <Mail className="w-5 h-5 text-text-muted absolute left-3.5 pointer-events-none" aria-hidden="true" />
                  <input
                    id="login-email"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="e.g., student@example.com"
                    required
                    className="w-full bg-bg/80 border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg py-3.5 pl-11 pr-4 text-text placeholder:text-text-muted text-sm transition-all duration-200"
                  />
                </div>
              </div>

              {/* Password */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label htmlFor="login-password" className="text-xs font-bold text-text uppercase tracking-wider">
                    Password
                  </label>
                  <button
                    type="button"
                    onClick={() => setForgotNotice(true)}
                    className="text-xs font-medium text-primary hover:underline min-h-8 cursor-pointer"
                  >
                    Forgot Password?
                  </button>
                </div>
                <div className="relative flex items-center">
                  <Lock className="w-5 h-5 text-text-muted absolute left-3.5 pointer-events-none" aria-hidden="true" />
                  <input
                    id="login-password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    required
                    className="w-full bg-bg/80 border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg py-3.5 pl-11 pr-11 text-text placeholder:text-text-muted text-sm transition-all duration-200"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-2 min-h-11 min-w-11 inline-flex items-center justify-center text-text-muted hover:text-text cursor-pointer"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? (
                      <EyeOff className="w-5 h-5" />
                    ) : (
                      <Eye className="w-5 h-5" />
                    )}
                  </button>
                </div>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={loading}
                className="w-full mt-4 min-h-12 bg-primary hover:bg-primary-hover text-on-primary font-semibold py-3.5 px-6 rounded-lg flex items-center justify-center gap-2 shadow-soft transition-all duration-200 cursor-pointer disabled:opacity-70 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <span>Signing in...</span>
                ) : (
                  <>
                    <span>Sign In</span>
                    <ArrowRight className="w-5 h-5" />
                  </>
                )}
              </button>
            </form>
          </div>

        </div>
      </main>

      {/* Footer */}
      <footer className="w-full max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-text-muted py-4 border-t border-border/40">
        <div>
          © 2024 Luma Learning. Your pace. Your way.
        </div>
        <p>Accounts are created by your school — ask a teacher if you need help signing in.</p>
      </footer>
    </div>
  );
};

export default LoginPage;
