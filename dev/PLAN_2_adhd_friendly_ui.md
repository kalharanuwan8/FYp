# PLAN 2 — ADHD-friendly, colourful-but-calm student UI (ages 14–18)

## Context
The frontend (React 19 + Vite + Tailwind 4, `frontend/`) works end-to-end with the Flask backend, but it is an **adult admin-style LMS**:
- 10–12 px grey text, a slate-only palette, no theme tokens (`frontend/src/index.css` is just `@import "tailwindcss"`)
- 3 overlapping nav items, a dead search box/bell in the Topbar
- the child is shown **"DISTRACTED", confidence %, "Model: fallback", session IDs**, which feels like surveillance
- jarring full-screen pulses and dark backdrops for interventions
- a quiz with all questions on one page
- a session summary that counts "Interventions Triggered" (reads as punishment)
- **no gamification**, no reduced-motion or text-size support
- the student ticks their own guardian-consent box

**Goal:** a student experience that is **attractive, colourful and motivating but calm** (low visual noise, no harsh contrast or neon, no flashing). It should be easy to demo to an ADHD student and to examiners. Teacher/admin screens only get demo-cleanup polish.

## Design principles (cite in the thesis: ADHD/UDL guidance)
1. **One clear next action per screen.** A big primary button ("Continue lesson"), and everything else secondary.
2. **Chunking + visible progress.** Short steps, progress rings and a path/journey view of modules.
3. **Calm colour.** Soft, mid-saturation hues on warm off-white. Each subject gets its own accent. Never pure black on pure white, never saturated red. Text still meets WCAG AA contrast.
4. **Readable type.** **Lexend** (designed for reading fluency) for body, 17–18 px base, 1.6 line height, max ~65 characters per line, sentence case (no tiny uppercase labels).
5. **Positive, non-judgemental language.** "Focus buddy", "Let's get back on track 👋", never "DISTRACTED". Celebrate focus minutes, don't count failures.
6. **Gentle motion only.** Short fades and slides, and respect `prefers-reduced-motion` plus a manual "Reduce motion" toggle. No `animate-pulse` on the child's screen.
7. **Student control.** Theme (Light / Calm dark), text size, sounds on/off, and "I need a break" always available.
8. **Teen-appropriate.** Playful but not childish: rounded cards, friendly illustrations/emoji, XP and streaks like Duolingo, no cartoon baby mascot.

## Visual system (`frontend/src/index.css` → Tailwind v4 `@theme` tokens)
| Token | Light | Calm dark |
|---|---|---|
| `--bg` | `#F6F7FB` (soft off-white) | `#141A2A` |
| `--surface` | `#FFFFFF` | `#1D2438` |
| `--text` | `#1F2A44` | `#E7EAF3` |
| `--text-muted` | `#5B6478` (AA on bg) | `#A9B0C3` |
| `--primary` | `#3D7A9C` (keep the Luma brand teal) | `#6FB3D6` |
| Accents (subjects) | lavender `#8B7CF6`, mint `#3CBF9A`, peach `#FF9F7A`, sun `#F4C152`, sky `#5AB0EE` | same, at 85% |
| `--success` | `#3CBF9A` | |
| `--attention` (instead of red) | soft coral `#F2836B` | |

Radius 16–24 px, soft shadows, 8 px spacing grid, 44 px minimum touch targets. Fonts loaded from Google Fonts (Lexend + Nunito for headings). Add `lucide-react` icons (already installed) in coloured round "chips".

## Screens to redesign (student role)

1. **Shell / navigation** (`components/student/StudentLayout.jsx`, `StudentSidebar.jsx`; drop the admin `Topbar` for students)
   - Nav has 4 items only: **Home · My Subjects · Progress · Settings**. Merge "Browse Courses" and "My Courses" into "My Subjects", with an "Explore" tab inside.
   - Top bar: greeting, 🔥 streak, ⭐ XP, avatar. No fake search or bell.

2. **Home / "Today"** (`pages/student/StudentDashboard.jsx`)
   - Hero "Continue where you left off" card with a big button.
   - Daily focus goal ring (e.g. 20 focused minutes), streak, and the last badge earned.
   - Subject cards in their accent colours, each with a progress ring.

3. **Subject → learning path** (`pages/student/SubjectDetail.jsx`)
   - Modules as a vertical **journey path** (done ✓ / current / locked-soft). Materials appear as steps inside a module.
   - One "Start focus session" button per step. No stat-box clutter.

4. **Focus session / study screen** (`SubjectDetail.jsx` session area, `components/student/VideoLearningPlayer.jsx`)
   - **Focus mode:** sidebar hidden, content centred, a soft accent frame.
   - A small **"Focus buddy" ring** in the corner replaces the ML pill. It glows calm green when on track and soft amber when wandering. No words like "distracted", no confidence, no model mode.
   - The webcam preview is optional ("show my camera"), with a privacy note.
   - Session timer with a suggested break every ~15–20 min (Pomodoro-style for ADHD), plus an always-visible "I need a break" button.
   - Move dev-only text (ML mode, confidence, session #) into a **hidden demo panel** (keyboard shortcut, e.g. `Ctrl+Shift+D`) so you can still show examiners the live model output.

5. **Interventions** (`components/intervention/*`)
   - **T1 AmbientCue:** a gentle animated border glow + small toast "👀 Still with us?". No full-screen pulse.
   - **T2 PacingPrompt:** a friendly bottom-sheet card: "Quick check-in: how's it going?" with emoji buttons 😀 / 😐 / 😩 (the answer is logged as self-report, which helps Plan 1 too).
   - **T3 MilestoneQuiz:** one question card on a light, blurred backdrop (not dark), confetti-lite on a correct answer, encouraging wording on a wrong one, "Show a hint".
   - **T4 Break:** reuse and revive `GamifiedBreak.jsx` as a 60 s **breathing/stretch break** (animated circle, optional sound), then "Ready to continue".
   - Map engine types in `InterventionOverlay.jsx`. Make the backend send `suggest_break` → the break screen.

6. **Quiz** (`pages/student/QuizAttempt.jsx`)
   - **One question per screen**, large options as tappable cards, a progress dots row, instant gentle feedback, and an XP reward at the end.

7. **Session summary**
   - Celebrate: "🎉 18 focused minutes", "+40 XP", "Longest focus streak: 7 min", any new badge.
   - Show duration in minutes. **Remove the "Interventions Triggered" count** from the student view (teachers still see it).

8. **Progress page** (`pages/student/StudentAnalytics.jsx`)
   - Weekly focus-minutes bar chart, streak calendar and a badge shelf. Plain-language insights ("You focus best in the morning").

9. **Onboarding + consent** (`components/student/FirstTimeOnboardingModal.jsx`)
   - 3 short friendly steps: Welcome → "How your focus buddy works" (camera explained, data stays private, you can pause anytime) → choose theme and text size.
   - Guardian consent is **recorded by teacher/admin** (or confirmed via the guardian email), not self-ticked by the student. For 14–18, show it as information plus a student assent checkbox.

10. **Settings** (`pages/student/StudentSettings` via `SettingsPage.jsx`)
    - Theme, text size (S/M/L), reduce motion, sounds, camera preview on/off, break interval.

## Backend support needed (small)
- **Gamification tables** in `backend/app/db_models/`: `StudentProgress` (xp, level, current_streak, longest_streak, last_active_date, daily_goal_minutes) and `Badge` / `StudentBadge`.
- **Service** `backend/app/services/gamification_service.py`: award XP on session stop (per focused minute), quiz submit (per correct answer) and completed module; update the streak; unlock badges (first session, 3-day streak, 60 focus minutes, quiz ace…).
  - Hook it into `routes/session.py` (`/stop`) and `routes/quizzes.py` (`/submit`).
- **Endpoints:** `GET /api/student/progress`, `GET /api/student/badges`. Add `ui_preferences` (JSON) to the student profile `PATCH /api/student/profile`.
- Tests: `backend/tests/test_gamification.py`.

## Frontend implementation notes
- Tokens in `src/index.css` (`@theme` + `[data-theme="calm-dark"]`). Text size via a root `font-size` class.
- New `src/context/PreferencesContext.jsx` (theme, text size, motion, sound), persisted to the profile and localStorage.
- Shared UI kit in the currently empty `src/components/common/`: `Button`, `Card`, `ProgressRing`, `Badge`, `XPChip`, `StreakChip`, `EmptyState`, `LoadingSpinner`, `ErrorBanner`.
- Small additions: `canvas-confetti` (tiny) for celebrations, `recharts` for the progress chart. Motion via CSS transitions plus a `motion-safe:` variant.
- Demo cleanup: set the `index.html` title to "Luma – Focus Learning"; hide or replace `alert()` placeholder buttons (Teacher dashboard, admin sidebar, Topbar bell); remove dead files or fill them; fix the `getModules`/`archiveModule` 404 calls; read the API URL only from `VITE_API_BASE_URL`.
- Accessibility: ARIA labels on icon buttons, focus-visible rings, keyboard navigation for quiz and overlays, `aria-live="polite"` for the focus buddy.

## Critical files
`frontend/src/index.css`, `frontend/index.html`, `frontend/src/App.jsx`, `frontend/src/components/student/*`, `frontend/src/components/intervention/*`, `frontend/src/components/common/*`, `frontend/src/pages/student/{StudentDashboard,SubjectDetail,QuizAttempt,StudentAnalytics}.jsx`, `frontend/src/hooks/useMonitoringSession.js`, `backend/app/db_models/`, `backend/app/routes/{session,quizzes,student}.py`

## 3-week timeline (runs in parallel with Plan 1)
| Week | Work |
|---|---|
| 1 | Tokens, fonts, Preferences context, common UI kit · new student shell + Home · gamification DB/service/endpoints |
| 2 | Learning path · Focus session screen + focus buddy + hidden demo panel · intervention redesigns + break screen · one-question quiz |
| 3 | Summary + Progress page · onboarding/consent · settings · demo cleanup · quick usability test |

### Verification
- `npm run lint && npm run build` in `frontend/`; `pytest` in `backend/`.
- Manual walkthrough as `student@luma.com`: login → onboarding → Home → subject → focus session → trigger T1–T4 (demo panel) → quiz → summary shows XP/badge → Progress page updates. Repeat in calm-dark, large text, reduced motion.
- Contrast check of the token pairs (WebAIM checker, AA ≥ 4.5:1 for body text).
- **Mini usability study (3–5 students aged 14–18):** a SUS questionnaire + 3 questions ("felt watched?", "felt calm?", "wanted to continue?"). Strong evidence for the thesis.
