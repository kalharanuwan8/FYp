# Luma: request for expert review of attention-support prompts

**Prepared by:** Kalhara · **Date:** [date sent] · **Intended learners:** children with ADHD, [age range to confirm]

## Why I am asking for your review

Luma is a learning platform built for my undergraduate research project. During a lesson, it uses the webcam to estimate whether a child's visible attention has drifted from the screen. When it estimates that this has lasted a few seconds, it shows a supportive prompt.

The accurate position today is this: **Luma applies interventions informed by related educational research; their suitability is being reviewed, and their effectiveness in this particular platform has not yet been established.**

I am asking for your clinical judgement on whether these prompts are appropriate for children with ADHD, and how they should change. Your feedback will be reported in my thesis as an expert review of the design. It will not be presented as evidence that the prompts work; that would need a study with children.

## One limitation to keep in mind throughout

The webcam can estimate that a child is not visibly looking at the lesson. It cannot tell why. Boredom, confusion, tiredness, writing notes, a noise in the room, or a model error all look the same to it. Luma currently moves to stronger prompts simply because more time has passed, and each stronger prompt assumes a different cause. That escalation is the part I am least able to justify from research.

## The six prompts as they currently work

Exact on-screen wording is quoted. Times are seconds into one continuous period that the webcam judges as "distracted".

| Prompt | What the child sees | When it appears | How the child can respond | What happens next |
|---|---|---|---|---|
| **Gentle cue** | Small banner at the top: "Let's refocus together!" and an "I'm here" button. The video keeps playing. | About 6 s | Only "I'm here". The banner stays until clicked. | No further prompt for at least 30 s. If the child never clicks, no further prompts appear. |
| **Pacing pause** | The video pauses. "Quick check-in — Still with me? Tap to continue." Three faces: 😀 Going well, 😐 Okay, 😩 Tough. | Rarely in practice (only when the 30 s gap delays the first prompt) | Pick a face, or "Skip for now". | The video continues. The face chosen is not currently used. |
| **Brief quiz** | The video pauses. "Quick check — One question, then back to the lesson." One multiple-choice question set by the teacher, with an optional hint. | About 36 s | Answer, or "Skip". Gentle feedback either way, then "Continue lesson". | The video continues. |
| **Hint** (during a quiz instead of the brief quiz) | "A hint for this question … Skim the heading and first sentence of the current section." | About 36 s | One button: "Thanks — back to the quiz". | Back to the quiz. |
| **Pace reduction** | The video pauses. "Let's slow down a little — We'll play the video a little slower (at 75% speed) for now." | About 66 s, once per session | "Got it — continue" or "Dismiss". | The video continues at 75% speed for the rest of the video, whichever button is chosen. |
| **Suggested break** | "Stretch & breathe — Great effort! Time for a short break." A 60 s countdown in a slowly pulsing circle: "Inhale as it grows · exhale as it softens." | About 96 s, then possibly every ~30 s after that | "Ready to continue", or wait for the timer. | The video continues. |

Screenshots: [insert one screenshot per prompt here before sending]

## What the research does and does not support

| Prompt | Closest research | What it shows | How close Luma is |
|---|---|---|---|
| Gentle cue | Self-monitoring of attention in children with ADHD (Harris et al., 2005; Reid et al., 2005 review); gaze-detected redirection prompts in students (D'Mello et al., 2012; Hutt et al., 2021) | Prompted attention checks increased on-task behaviour in small ADHD studies; detected-drift prompts reoriented attention in older students | Partial. The ADHD studies used scheduled tones, self-recording and training, not detection-triggered banners. |
| Brief quiz | Short quizzes during video lectures (Szpunar et al., 2013); quizzing with 6th graders (Roediger et al., 2011); testing in adults with ADHD (Knouse et al., 2016) | Short questions reduced mind wandering and improved learning; the benefit held for adults with ADHD | Partial. Studies used questions on the section just studied, at planned points. Luma asks the module's first checkpoint question when distraction is detected. |
| Pacing pause | Splitting lessons into segments (Rey et al., 2019) | Segments at meaningful boundaries help, mostly in adults. Breaks without a question did not reduce mind wandering (Szpunar et al., 2013). | Weak. Exploratory design choice. |
| Hint | Hints in tutoring software (Aleven et al., 2016); re-reading after detected mind wandering (Mills et al., 2021) | Hints help when they are specific and the learner is partly skilled | Weak. Luma's hint is generic and triggered by looking away, not by difficulty. Exploratory. |
| Pace reduction | Lecture speed studies (Murphy et al., 2022) | No study found that slowing below normal speed helps. Optimal-stimulation theory (Zentall, 1975) suggests slower content could reduce engagement in ADHD. | Exploratory; possibly counterproductive. |
| Suggested break | Activity breaks in children (Mahar et al., 2006); 20 min of exercise in children with ADHD (Pontifex et al., 2013) | Physical-activity breaks of 10–20 minutes improved on-task behaviour or attention-task performance | Weak. Luma's break is 60 s of seated breathing. Exploratory. |
| Timings and order | None found | The closest classroom system waited at least 90 s between prompts and gave about one per session (Hutt et al., 2021) | Exploratory. Luma's 5/10/20/40 s steps and 30 s gap are design choices. |

Full references and study details are in the attached evidence table.

## How I propose to define "re-engagement"

| Observation | What it shows |
|---|---|
| Child clicks the prompt | Only that the prompt was acknowledged |
| Webcam estimate returns to "focused" | The system's estimate that visible focus returned |
| Child resumes a learning action themselves | Behavioural return to the task |
| Child answers a relevant question or completes an activity | Participation or understanding |

A click alone, or a webcam change alone, should not count as success. At the moment Luma records clicks as "re-engaged"; I plan to report these as acknowledgements.

## Questions for you

1. **Mechanisms.** For the intended age group, are the proposed reasons each prompt might help plausible? Are any based on a wrong assumption about ADHD?
2. **Wording and interruption.** Is the wording appropriate? Is pausing the video acceptable, and for which prompts?
3. **Counterproductive cases.** When could a cue, question, hint, slow-down or break make things worse (for example frustration, anxiety, loss of momentum, or reacting to a false alarm)?
4. **Choice.** Should the child have more options, such as "I was paying attention", "I'm confused", or "I need a break", and should the next step depend on their answer?
5. **Timing and escalation.** Are the current timings (first prompt at about 6 s, at least 30 s apart, a break by about 96 s) reasonable? Should escalation depend on time at all?
6. **Meaningful outcomes.** What would you consider meaningful evidence that a child has re-engaged?

Written comments on this document are ideal. If easier, I can show you a short live demonstration of each prompt (about 15 minutes).

Thank you for your time.
