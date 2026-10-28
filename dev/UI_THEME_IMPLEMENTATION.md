# UI theme implementation — Luma Focus Learning

Short note for Chapter 5 (results / artefact description). Distinguishes
literature-informed *principles* from *project-specific* palette and layout
choices.

## 1. Design rationale (principles vs project choices)

**Paper-informed principles** (interpreted for a web LMS; not clinical claims):

- Reduce decorative clutter so the learning task stays dominant.
- Prefer predictable layouts and controlled colour saturation.
- Keep readable contrast; avoid faint text or invisible controls.
- Offer personal choice of appearance without changing interaction structure.
- Do not claim that a particular colour “treats” ADHD or guarantees attention.

Sources discussed in the brief (*Designing Learning Environment for School
Children*; *Immersive Quiet Rooms for Children with ADHD*) concern physical or
immersive spaces. Applying them here is a **design interpretation**.

**Project-specific choices** (exact hex values, token names, four named themes,
Lexend/Nunito typography, teal primary on sage) are implementation decisions for
this artefact, not prescriptions from those papers.

## 2. Semantic tokens and default palette

Tokens live in `frontend/src/index.css` as CSS custom properties, exposed to
Tailwind via `@theme` (`bg-bg`, `bg-learning`, `text-text`, `bg-primary`, etc.).

| Token role | CSS variable | Sage default | Purpose |
|---|---|---|---|
| Page background | `--bg` | `#EEF3EE` | Soft sage chrome |
| Main learning surface | `--learning-surface` | `#FAFAF7` | Warm off-white lesson/quiz panel |
| Primary text | `--text` | `#243444` | Dark slate body copy |
| Primary action | `--primary` | `#286B63` | Deep teal buttons / active controls |
| Primary hover | `--primary-hover` | `#1F564F` | Darker teal |
| On-primary text | `--on-primary` | `#FFFFFF` | Text on primary fills |
| Muted text | `--text-muted` | `#4A5A68` | Secondary labels |
| Border | `--border` | `#C9D4CC` | Surface separation |
| Focus ring | `--focus-ring` | `#286B63` | `:focus-visible` outline |
| Feedback | `--success`, `--warning`, `--danger`, `--attention`, `--info` | (see CSS) | Status, alerts |
| Subject accents | `--accent-*` | muted lavender/mint/peach/sun/sky | Icon/border labels only |

Contrast was checked for body text on page/learning surfaces and primary buttons
(white or dark on-primary on primary fills) aiming for **WCAG AA**. Soft fills
(`--primary-soft`, accent soft mixes) are used only behind stronger text or
icons—not as the sole text colour.

## 3. Themes and preferences

`PreferencesContext` (`frontend/src/context/PreferencesContext.jsx`):

| Theme id | Label | Page feel |
|---|---|---|
| `sage` | Sage (default) | Soft green page |
| `warm` | Warm neutral | Parchment page, olive action |
| `pale-blue` | Pale blue | Cool mist page, slate-blue action |
| `calm-dark` | Calm dark | Existing low-light surfaces |

- Legacy stored value `light` migrates to `sage` via `normalizeTheme()`.
- Theme is applied as `data-theme` on `<html>` and persisted in
  `localStorage` (`luma_ui_preferences`) plus student profile `ui_preferences`
  when logged in as a student.
- Layout and component structure are identical across themes; only token
  values change.
- Also preserved: text size (`s`/`m`/`l`), reduce motion, sounds, camera-preview
  default, break-interval minutes.

Settings UI: `frontend/src/pages/student/StudentSettings.jsx`.

## 4. Layout decisions

### Learning / quiz

- Solid page background (`--bg`); dominant panel via `.learning-panel` /
  `bg-learning`.
- No decorative gradients, patterns, immersive scenery, floating objects, or
  continuous background animation on lesson screens.
- Session chrome (`.focus-session-chrome`) keeps navigation minimal during
  focus: timer/buddy, “I need a break”, end/complete, camera preview toggle.
- Hiding the camera preview never stops monitoring (copy + behaviour
  unchanged; preview is visibility-only).
- Focus Buddy is a small static status dot (on-track / wander) with text label;
  no pulse or flashing verdict text for students.

### Dashboard and navigation

- Priority: continue learning → subjects → quieter XP / streak / badges.
- Subject colour via muted left border + icon tint (`subjectAccents.js`), not
  full-card colour blocks.
- Progress chips use bordered surface styling so rewards stay secondary.

### Interventions (style only)

Overlays restyled to tokens; **triggers, payloads, grading, and response
values are unchanged**. Ambient cue remains non-modal and must not pause
playback (`interventionShouldPauseVideo`). Breathing animation exists only
inside the break dialog and respects reduce-motion.

## 5. Accessibility notes

- Shared `Dialog` focus trap, initial focus, Escape policy, body scroll lock.
- Visible `:focus-visible` via `--focus-ring`.
- Colour is paired with text, icons, or shapes (selected answers show “Selected”
  / check mark; themes use labels + swatches).
- OS `prefers-reduced-motion` and in-app `reduce-motion` both shorten
  transitions; learning backgrounds remain static regardless.
- Large quiz answer controls with clear selected and keyboard arrow support.

## 6. Verification (2026-10-23)

| Check | Result |
|---|---|
| `npm run build` | Passed (Vite production build) |
| Theme persistence | Confirmed in Settings — switching Sage / Warm / Pale blue / Calm dark shows ✓ Saved and updates `data-theme` immediately |
| Login → dashboard (sage) | Solid sage page; continue-learning card; quieter XP/streak chips |
| Courses explore | Sage chrome; empty catalogue for demo student grade (no subjects to enrol) |
| Lesson → intervention → summary | Layout/code path restyled; **not exercised end-to-end in browser** because demo student has no enrolable subjects in this DB |
| Quiz interaction | Restyled; same limitation (no quiz without enrolled module) |
| Keyboard / focus | Dialog focus trap preserved; `:focus-visible` uses `--focus-ring` |
| `npm run lint` | Reports pre-existing project lint errors (hooks/unused vars); none introduced as theme-only regressions |
| Screenshots | `dev/test_outputs/ui_theme_screenshots/` (demo account `student@luma.com`, no personal PII beyond seed name) |

## 7. Limitations

- Some admin/teacher analytics still use a few legacy Tailwind colour utilities
  (e.g. emerald/amber status pills); student learning path and shared controls
  are on semantic tokens.
- No optional nature-border asset was added (none existed in-repo; brief
  forbade building an asset library solely for that).
- Confetti celebration colours were muted to theme-adjacent hues; celebrations
  still respect reduce-motion / sounds preferences.
- Exact AA ratios were validated by design (dark slate on sage/off-white;
  white on `#286B63`; calm-dark light text on dark surfaces) rather than an
  automated contrast CI gate.
- Full monitored lesson / quiz / intervention screenshots need a subject with
  materials enrolled for the demo student’s grade.

## 8. Key files

| Area | Path |
|---|---|
| Tokens / shells | `frontend/src/index.css` |
| Preferences | `frontend/src/context/PreferencesContext.jsx` |
| Subject accents | `frontend/src/utils/subjectAccents.js` |
| Dashboard | `frontend/src/pages/student/StudentDashboard.jsx` |
| Settings | `frontend/src/pages/student/StudentSettings.jsx` |
| Lesson player | `frontend/src/components/student/VideoLearningPlayer.jsx` |
| Focus session | `frontend/src/pages/student/SubjectDetail.jsx` |
| Quiz | `frontend/src/pages/student/QuizAttempt.jsx` |
| Interventions | `frontend/src/components/intervention/*` |
| Shared Button / Dialog / forms | `frontend/src/components/common/*` |
