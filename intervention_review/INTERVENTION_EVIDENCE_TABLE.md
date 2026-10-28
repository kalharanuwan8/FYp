# Luma interventions: specification and evidence table

Working research document (research task 1 of the intervention review). It feeds the doctor-facing brief (`DOCTOR_REVIEW_BRIEF.md`) and, after her review, Chapters 2, 3, 6 and 7 of the thesis.

**Status statement (use this wording externally):** Luma applies interventions informed by related educational research; their suitability is being reviewed, and their effectiveness in this particular platform has not yet been established.

All behaviour described in Part A was read from the code, not from design notes. Source files:
`backend/app/services/intervention_engine.py`, `backend/app/routes/session.py` (heartbeat, milestone enrichment, intervention-response),
`frontend/src/components/intervention/*.jsx`, `frontend/src/components/student/VideoLearningPlayer.jsx`, `frontend/src/utils/interventionPause.js`.

---

## Part A. What each intervention actually does

### A1. Shared trigger logic (applies to every intervention)

| Item | Current behaviour |
|---|---|
| Input signal | Webcam frame every 2 s during a monitored session. The model returns FOCUSED, DISTRACTED or UNKNOWN (no face / unusable frame), scored over a short window of recent frames. |
| What is measured | Length of the current continuous DISTRACTED "episode". A FOCUSED verdict ends the episode and resets escalation. UNKNOWN ends the episode without counting as a return, and does not escalate. |
| Severity from elapsed time | Episode ≥ 5 s → tier 1; ≥ 10 s → tier 2; ≥ 20 s → tier 3; ≥ 40 s → tier 4. |
| Spacing | At least 30 s between interventions (admin setting `intervention_min_cooldown_seconds`, default 30). No new intervention while one is still awaiting a response. |
| Escalation on "ignored" | If the previous response was an explicit Skip/Dismiss, the next intervention is at least one tier higher. |
| Tier → intervention | 1 gentle cue · 2 pacing pause · 3 brief quiz (in a quiz: hint) · 4 first time pace reduction, afterwards suggested break. |
| Teacher control | A teacher can disable tiers per subject; a disabled tier falls back to the next lower enabled tier. |
| Not driven by the webcam | Background noise can trigger a separate one-off "noisy room" notice. It never escalates visual interventions and is outside the scope of this review. |

**Sequence a child actually experiences.** The engine was simulated with a single uninterrupted DISTRACTED episode (2 s heartbeat, 30 s gap):

| Child's response to each prompt | What fires, at seconds into the episode |
|---|---|
| Responds to each prompt but the webcam still estimates distraction | ~6 s gentle cue → ~36 s brief quiz → ~66 s pace reduction → ~96 s break → another break every ~30 s after that |
| Explicitly skips each prompt | Same sequence (the elapsed time already demands the higher tier) |
| Never touches the first cue | ~6 s gentle cue, then nothing else for the rest of the episode |

Consequences that matter for the review:

- The pacing pause (tier 2) is never reached in a single continuous episode. It only appears when the 30 s gap delays the first prompt of a new episode until 10–20 s in.
- Escalation is driven by elapsed time, not by how the child responds. Pressing "I'm here" does not stop the next, stronger prompt if the webcam still estimates distraction.
- A child who ignores the cue completely receives no further support, while a child who interacts with every prompt is escalated fastest.
- Breaks can repeat back-to-back: each break lasts up to 60 s, which is longer than the 30 s gap, so another break can fire as soon as one ends.

### A2. Per-intervention specification

Wording is quoted exactly as it appears on screen.

#### Gentle cue (tier 1, `ambient_cue`)

| Item | Current behaviour |
|---|---|
| Wording | "Let's refocus together!" with a hand icon and one button: "I'm here". |
| Presentation | Small banner at the top of the screen. Non-modal, nothing flashes, no sound. The video keeps playing. |
| Trigger | Episode ≥ 5 s (in practice ~6 s with the 2 s heartbeat), subject to the 30 s gap. |
| Duration | No timeout. Stays on screen until clicked, even if the webcam verdict returns to FOCUSED. |
| Dismissal options | Only "I'm here". There is no "not now" or "I was already focused" option. |
| Logged as | `reengaged`, with time-to-click stored as `reengaged_in_seconds`. |
| Afterwards | Escalation resets; the next prompt is possible 30 s after this one was shown. |

#### Pacing pause (tier 2, `pacing_pause`)

| Item | Current behaviour |
|---|---|
| Wording | Title "Quick check-in"; text "Still with me? Tap to continue."; three buttons 😀 "Going well", 😐 "Okay", 😩 "Tough"; link "Skip for now". |
| Presentation | Modal dialog; Escape is disabled; the video pauses. |
| Trigger | Episode 10–20 s old at the moment a prompt is allowed (rare in practice, see A1). |
| Duration | No timeout. |
| Dismissal options | Any emoji is logged as `reengaged`; "Skip for now" as `ignored` (next prompt escalates). |
| Afterwards | Video resumes automatically for every option, including Skip. The emoji choice is sent to the server but **not stored and not acted on**, so a child choosing "Tough" is treated the same as "Going well". |

#### Brief quiz (tier 3 outside quizzes, `milestone_quiz`)

| Item | Current behaviour |
|---|---|
| Wording | Title "Quick check"; "One question, then back to the lesson."; a multiple-choice question; optional "Show a hint"; buttons "Skip" and "Check answer". Feedback: correct → "Nice work — that matches the lesson! ✨" plus confetti (unless reduced motion is on); incorrect → "Not quite — that's okay, you're still learning. Keep going!"; then "Continue lesson". |
| Question source | The first active teacher-approved checkpoint question in the module, by sequence order. The same question is therefore chosen every time within a module, and it is not linked to the part of the video just watched. If the module has no checkpoint question, a generic fallback is used: "What is the main idea of this material?" with options "The core concept from the lesson / An unrelated topic / A homework deadline / None of the above". |
| Presentation | Modal; Escape disabled; video paused. |
| Trigger | Episode ≥ 20 s (in practice ~36 s, the second prompt of an episode). |
| Duration | No timeout. |
| Dismissal options | Answer (logged `reengaged`, correctness graded server-side and stored) or Skip (`ignored`). |
| Afterwards | Video resumes when "Continue lesson" is pressed. |

#### Hint (tier 3 inside a quiz, `hint_injection`)

| Item | Current behaviour |
|---|---|
| Wording | Header "A hint for this question"; text "What is the main idea of the section you just read?"; hint "Skim the heading and first sentence of the current section."; button "Thanks — back to the quiz". |
| Presentation | Panel inline on the quiz page. |
| Trigger | Webcam-estimated distraction ≥ 20 s while a quiz is open. It is **not** triggered by wrong answers, time on a question, or any sign of difficulty. |
| Content | Fixed generic text. It is not linked to the quiz question the child is on. |
| Dismissal options | One button only, logged `reengaged`. |
| Afterwards | Child returns to the quiz. |

#### Pace reduction (first tier 4, `content_pacing_reduction`)

| Item | Current behaviour |
|---|---|
| Wording | Title "Let's slow down a little"; "We'll slow the pace a bit so you can catch up."; 🐢; "We'll play the video a little slower (at 75% speed) for now."; buttons "Got it — continue" and "Dismiss". |
| Effect | Video playback is set to 0.75× and paused **as soon as the dialog appears**, before the child chooses. Nothing in the code restores normal speed for the rest of that video, "Dismiss" does not undo it, and the player has no speed control. In a quiz or document there is no video, so the message has no matching effect. |
| Trigger | Episode ≥ 40 s (in practice ~66 s), first time per session. |
| Dismissal options | "Got it — continue" (`reengaged`) or "Dismiss" (`ignored`). |
| Afterwards | Video resumes at 0.75×. |

#### Suggested break (later tier 4, `suggest_break`)

| Item | Current behaviour |
|---|---|
| Wording | Title "Stretch & breathe"; "Great effort! Time for a short break."; a 60 s countdown inside a slowly pulsing circle; "Inhale as it grows · exhale as it softens"; button "Ready to continue". A soft tone every 4 s if sounds are on and reduced motion is off. |
| Presentation | Modal; Escape disabled; video paused. |
| Trigger | Tier 4 after pace reduction has already been used this session (in practice ~96 s into an episode). |
| Duration | 60 s, or until the child presses "Ready to continue". |
| Dismissal options | "Ready to continue" or the timer running out. **Both are logged as `reengaged`.** |
| Afterwards | Video resumes automatically, including when the timer simply runs out (the child may not be present). Another break can fire immediately if the webcam still estimates distraction. |

---

## Part B. Intervention-to-evidence table

### How to read this table

Each intervention gets two separate ratings, because evidence that a type of intervention can help does not justify Luma's particular trigger, timing or escalation order.

| Rating | Meaning |
|---|---|
| **Related evidence** | Studies of a similar intervention type with relevant outcomes, including at least some evidence in children or ADHD populations. Delivery still differs from Luma. |
| **Partial / by analogy** | Evidence for a related mechanism, but the population, delivery or trigger differs substantially. |
| **Exploratory design choice** | Little or no direct evidence for the intervention as Luma delivers it. The rationale is theoretical or a design judgement. |

### Summary

| Intervention | Evidence for the intervention type | Evidence for Luma's version (trigger, timing, wording, place in sequence) |
|---|---|---|
| Gentle cue | Related evidence (self-monitoring cues, ADHD children; detection-triggered prompts, older students) | Exploratory |
| Brief quiz | Related evidence (retrieval practice incl. 6th graders and ADHD adults; interpolated tests in video lectures) | Exploratory |
| Pacing pause | Partial / by analogy (segmenting, mostly adults) | Exploratory |
| Hint | Partial / by analogy (tutor hints; re-reading after detected mind wandering) | Exploratory: triggered by distraction, not difficulty |
| Pace reduction | Exploratory; one plausible counter-argument | Exploratory |
| Suggested break | Partial / by analogy (activity breaks of 10–20 min; brief task switches in adults) | Exploratory: 60 s seated breathing is untested |
| Time-based escalation order and thresholds | None found | Exploratory: requires expert review |

### B1. Gentle cue (priority)

| Study | Participants | What was delivered | Outcome measured | Population | Match to Luma | Still an assumption |
|---|---|---|---|---|---|---|
| Harris, Friedlander, Saddler, Frizzelle & Graham (2005) | 6 students with ADHD in grades 3–5, all on medication, general-education classroom | Self-monitoring of attention: a taped tone at random intervals (average 45 s, range 10–90 s) through headphones; the child asked "Was I paying attention?" and ticked yes/no on a tally sheet. Trained beforehand with a teacher. | Observed on-task behaviour; correct spelling-practice responses | Children with ADHD | Partial. Shared: a brief prompt to check attention. Different: tones were on a schedule, not triggered by detected distraction; the child self-recorded; there was prior training. Luma's cue asks for no self-assessment. | That a detection-triggered banner works like a scheduled self-monitoring tone; that the effect holds without self-recording and training. |
| Amato-Zech, Hoff & Doepke (2006) | 3 fifth-graders (age 11) in a self-contained special-education class (speech/language impairment, learning disability, emotional disturbance; not ADHD) | Vibrating MotivAider at fixed intervals (starting at 1 min); child recorded "yes/no, I was paying attention" | On-task behaviour (55% → over 90%); teacher and student acceptability | Children with other special educational needs | Partial, as above. Notable: on-task behaviour fell when the device was removed. | Generalisation to ADHD; whether effects persist without the prompt. |
| Reid, Trout & Schartz (2005) | Meta-analysis of self-regulation studies with children with ADHD | Self-monitoring, self-monitoring plus reinforcement, self-management, self-reinforcement | On-task, inappropriate behaviour, academic accuracy and productivity (combined effect sizes > 1.0) | Children with ADHD | Type-level support for prompted self-monitoring; small single-case studies dominate. | Same as above. |
| D'Mello, Olney, Williams & Hays (2012), Gaze Tutor | 48 undergraduates | Eye tracker detected extended looking away; the tutor delivered messages telling the student to attend to the tutor agent | Attention reorientation; learning gains; motivation and self-reported engagement | Adults, general learning | Close in mechanism (system-detected disengagement → on-screen redirect). Different population, research-grade eye tracker. Gains were limited to deep-reasoning questions; motivation and self-reported engagement were barely affected. | That the effect transfers to children with ADHD and to a webcam estimate with Luma's error rate. |
| Hutt, Krasich, Brockmole & D'Mello (2021) | 287 high-school students across two classroom studies | Gaze-based mind-wandering detector → tutor redirects attention (sometimes using the student's name) and then repeats content or asks a question. At least 90 s between interventions; probabilistic triggering to "fail soft" when detection is wrong. | Mind wandering; delayed retention | Adolescents, general learning | Close in mechanism. Its cue is combined with content (repetition or a question) rather than a bare reminder. Benefits only for low-prior-knowledge students who mind-wandered occasionally. | That a bare reminder without content is enough; that a 30 s gap is acceptable when the cited classroom system used 90 s. |

### B2. Brief quiz (priority)

| Study | Participants | What was delivered | Outcome measured | Population | Match to Luma | Still an assumption |
|---|---|---|---|---|---|---|
| Szpunar, Khan & Schacter (2013) | 80 university students, two experiments | 21-min statistics video in four segments; brief tests after segments vs. restudy or unrelated arithmetic | Self-reported mind wandering; note-taking; final test | Adults, general learning | Strong match in medium (video lecture + short questions). Different: tests at fixed content boundaries for everyone, not triggered by distraction; several questions per segment. Restudy breaks without testing did not give the same benefit, which suggests the active question matters more than the pause. | That a single question triggered mid-segment gives a similar benefit; that it works for children with ADHD. |
| Roediger, Agarwal, McDaniel & McDermott (2011) | 6th-grade social-studies students, suburban US middle school | Low-stakes multiple-choice quizzes on course content | Chapter and semester exam performance | Typically developing children, general learning | Supports short quizzes for children in the general age range. Not distraction-triggered; scheduled. | Effects for children with ADHD; effect of a single repeated question. |
| Knouse, Rawson, Vaughn & Dunlosky (2016) | 25 college students with ADHD, 75 without | Practice tests vs. restudy on word lists | Recall 2 days later (testing effect d ≈ 0.50–0.57 in both groups) | Adults with ADHD | Shows retrieval practice is not weaker with ADHD, in adults and with word lists. | Transfer to children and to lesson content. |
| Hutt et al. (2021), see B1 | | Question about the current content after detected mind wandering | | Adolescents | Closest detection-triggered analogue. Its questions were about the content being discussed at that moment. | Luma's question is the module's first checkpoint item, not the content just watched. |

### B3. Pacing pause

| Study | Participants | What was delivered | Outcome measured | Population | Match to Luma | Still an assumption |
|---|---|---|---|---|---|---|
| Rey, Beege, Nebel, Wirzberger, Schmitt & Schneider (2019) | Meta-analysis, 56 studies, 88 comparisons | Multimedia lessons split into meaningful segments, learner- or system-paced | Retention (d = 0.32), transfer (d = 0.36), cognitive load, learning time | Mostly adults/students, general learning | Weak. Segments are cut at meaningful content boundaries; Luma pauses wherever distraction is detected. | That a pause at an arbitrary point helps; that an emoji check-in adds anything. |
| Szpunar et al. (2013), see B2 | | Breaks between segments filled with restudy or arithmetic | | | Counter-evidence for a pause alone: breaks without questions did not reduce mind wandering. | |

### B4. Hint

| Study | Participants | What was delivered | Outcome measured | Population | Match to Luma | Still an assumption |
|---|---|---|---|---|---|---|
| Aleven, Roll, McLaren & Koedinger (2016) | Review of help-seeking research with the Geometry Cognitive Tutor (high-school classrooms) and later studies | On-demand, step-specific hints; feedback on help-seeking | Help-seeking behaviour; domain learning | Adolescents, general learning | Weak. Hints were requested by the student and specific to the step; benefits mainly for students with intermediate skill. Luma's hint is pushed, generic, and triggered by visual distraction. | That distraction during a quiz means difficulty; that a generic hint helps. |
| Mills, Gregg, Bixler & D'Mello (2021), Eye-Mind Reader | Readers in a lab study with a yoked control (sample details to confirm from the paper) | When gaze indicated mind wandering: prompt to self-explain; if the explanation was weak, prompt to re-read specific text | Comprehension immediately and after one week (better at one week, d ≈ 0.31–0.35) | Adults, general learning | Luma's hint text ("skim the heading…") resembles a re-reading prompt, but is not targeted to specific text and is not conditional on the child's response. | Same as above. |

### B5. Pace reduction

| Study | Participants | What was delivered | Outcome measured | Population | Match to Luma | Still an assumption |
|---|---|---|---|---|---|---|
| Murphy, Hoover, Agadzhanyan, Kuehn & Castel (2022) | Adult participants (university-based studies) | Lecture videos at 1×, 1.5×, 2×, 2.5× | Immediate and 1-week comprehension | Adults, general learning | Does not test slower than normal; finds little cost up to 2×. Provides no support for slowing below 1×. | That slower playback helps anyone. |
| Rey et al. (2019), see B3 | | | | | "More processing time" is one of several candidate explanations for segmenting. Indirect only. | |
| Zentall (1975); Zentall & Zentall (1983) | Theoretical reviews | Optimal-stimulation theory | | Children with hyperactivity | Possible counter-argument: if under-stimulation contributes to inattention in ADHD, slowing content could make it worse. Theory, not a test. | Whether slowing helps or harms; whether the cause is overload at all (the webcam cannot tell). |

### B6. Suggested break

| Study | Participants | What was delivered | Outcome measured | Population | Match to Luma | Still an assumption |
|---|---|---|---|---|---|---|
| Mahar et al. (2006) | 243 K–4 students; on-task observed in 62 third- and fourth-graders (age 8–11) | Teacher-led 10-min classroom physical-activity breaks (Energizers) daily for 12 weeks | Steps; observed on-task behaviour after the break (+8%; +20% in least on-task) | Typically developing children | Weak. Physical, 10 min, scheduled, teacher-led. Luma's break is 60 s, seated breathing, triggered by distraction. | That a 60 s seated break has any comparable effect. |
| Pontifex, Saliba, Raine, Picchietti & Hillman (2013) | 20 children age 8–10 with ADHD, 20 matched controls | Single 20-min moderate treadmill bout vs. seated reading | Attention task accuracy, brain responses, reading and arithmetic | Children with ADHD | Weak. Exercise, 20 min, laboratory. | Same as above. |
| Ariga & Lleras (2011) | Adult participants | Two brief task switches during a 40-min vigilance task | Vigilance performance over time | Adults | Supports brief disengagement and re-engagement in principle; very different task and population. | Transfer to children and to learning. |

### B7. Timing and escalation order

No study found supports Luma's thresholds (5/10/20/40 s), its 30 s gap, or the order cue → quiz → slow-down → break. Points relevant to review:

- Self-monitoring cues in the ADHD studies were scheduled (every ~45 s on average, or every minute and lengthened later) and preceded by training. They were not escalated.
- The classroom attention-aware system (Hutt et al., 2021) used a 90 s minimum gap, probabilistic triggering because detection is imperfect, and delivered about 1.2 interventions per session. Luma can deliver four or more in about 100 s.
- Prompt hierarchies from special education (least-to-most prompting) are a possible conceptual model for escalation, but they are used to teach skills, with a trained adult judging each step. They do not justify escalating because time has passed.
- **The central limitation:** the webcam estimates that visible attention has drifted; it cannot tell boredom, confusion, fatigue, a necessary glance away (for example writing notes), or a model error apart. Each later tier assumes a different cause (confusion → hint/slow-down; fatigue → break). Escalating only because time has passed therefore needs justification and expert review.

---

## Part C. Defining re-engagement

| Observation | What it establishes | Does Luma record it today? |
|---|---|---|
| Child clicks a button on the prompt | Acknowledgement | Yes. Every non-skip click, and the break timer running out, is stored as `reengaged`; `reengaged_in_seconds` is time to click. |
| Webcam verdict changes to FOCUSED | System-estimated return of visible focus | Partly: the distraction episode's end time is stored, but it is not linked to the intervention or checked for being sustained. |
| Child resumes a relevant learning action | Behavioural return to the task | No. The video resumes automatically after most prompts, so "playing again" is not a child action. |
| Child answers a relevant question or completes an activity | Participation or understanding | Partly: quiz correctness is stored for the brief quiz. Later quiz or lesson performance is not linked to interventions. |

Consequences:

- What Luma's analytics currently call "re-engagement" is acknowledgement. In the thesis, report it as "acknowledged" or "responded", not "re-engaged".
- A future evaluation should record, per intervention: time to a sustained FOCUSED verdict (for example ≥ 10 s); time to a child-initiated learning action (requires turning off auto-resume or logging the child's own play/scroll/answer); participation and performance in the following minutes; skip rates and child/parent ratings of how irritating or unnecessary prompts were; and how many prompts fired when a human coder judged the child to be on task.
- Attributing any improvement to the interventions needs a comparison: for example monitoring-only sessions versus intervention sessions in an alternating single-case design, or a yoked control (as in Mills et al., 2021) where a child receives the same prompts at times unrelated to their attention.

---

## Part D. Implementation points to raise in the review (or fix before it)

These are not research findings but they affect what the doctor is reviewing. Each is a candidate change rather than something already decided.

1. "I'm here", every emoji, a submitted answer, the hint button, and the break timer expiring are all logged as `reengaged`.
2. The emoji self-report (including "Tough") is discarded and never changes what happens next.
3. The pacing pause is effectively unreachable within one episode; the real order is cue → quiz → slow-down → repeated breaks.
4. A child who ignores the first cue gets no further prompts; a child who responds is escalated quickly.
5. The quiz always uses the module's first checkpoint question, unrelated to the part just watched.
6. The hint is generic and not linked to the current quiz question.
7. Slow-down is applied before the child chooses, persists for the whole video, cannot be undone, and is shown even when there is no video.
8. Breaks can repeat back-to-back, and the video resumes when the break timer ends even if the child is away.
9. Wording assumes the detection is correct ("Let's refocus together!") and praises regardless of context ("Great effort!"). There is no option for "I was already paying attention".
10. The 30 s gap is a third of the gap used in the closest classroom study.

---

## References

Aleven, V., Roll, I., McLaren, B. M., & Koedinger, K. R. (2016). Help helps, but only so much: Research on help seeking with intelligent tutoring systems. *International Journal of Artificial Intelligence in Education, 26*(1), 205–223. https://doi.org/10.1007/s40593-015-0089-1

Amato-Zech, N. A., Hoff, K. E., & Doepke, K. J. (2006). Increasing on-task behavior in the classroom: Extension of self-monitoring strategies. *Psychology in the Schools, 43*(2), 211–221. https://doi.org/10.1002/pits.20137

Ariga, A., & Lleras, A. (2011). Brief and rare mental "breaks" keep you focused: Deactivation and reactivation of task goals preempt vigilance decrements. *Cognition, 118*(3), 439–443. https://doi.org/10.1016/j.cognition.2010.12.007

D'Mello, S., Olney, A., Williams, C., & Hays, P. (2012). Gaze tutor: A gaze-reactive intelligent tutoring system. *International Journal of Human-Computer Studies, 70*(5), 377–398. https://doi.org/10.1016/j.ijhcs.2012.01.004

Harris, K. R., Friedlander, B. D., Saddler, B., Frizzelle, R., & Graham, S. (2005). Self-monitoring of attention versus self-monitoring of academic performance: Effects among students with ADHD in the general education classroom. *The Journal of Special Education, 39*(3), 145–156. https://doi.org/10.1177/00224669050390030201

Hutt, S., Krasich, K., Brockmole, J. R., & D'Mello, S. K. (2021). Breaking out of the lab: Mitigating mind wandering with gaze-based attention-aware technology in classrooms. In *Proceedings of the 2021 CHI Conference on Human Factors in Computing Systems* (Article 52). https://doi.org/10.1145/3411764.3445269

Knouse, L. E., Rawson, K. A., Vaughn, K. E., & Dunlosky, J. (2016). Does testing improve learning for college students with attention-deficit/hyperactivity disorder? *Clinical Psychological Science, 4*(1), 136–143. https://doi.org/10.1177/2167702614565175

Mahar, M. T., Murphy, S. K., Rowe, D. A., Golden, J., Shields, A. T., & Raedeke, T. D. (2006). Effects of a classroom-based program on physical activity and on-task behavior. *Medicine & Science in Sports & Exercise, 38*(12), 2086–2094. https://doi.org/10.1249/01.mss.0000235359.16685.a3

Mills, C., Gregg, J., Bixler, R., & D'Mello, S. K. (2021). Eye-Mind reader: An intelligent reading interface that promotes long-term comprehension by detecting and responding to mind wandering. *Human–Computer Interaction, 36*(4), 306–332. https://doi.org/10.1080/07370024.2020.1716762

Murphy, D. H., Hoover, K. M., Agadzhanyan, K., Kuehn, J. C., & Castel, A. D. (2022). Learning in double time: The effect of lecture video speed on immediate and delayed comprehension. *Applied Cognitive Psychology, 36*(1), 69–82. https://doi.org/10.1002/acp.3899

Pontifex, M. B., Saliba, B. J., Raine, L. B., Picchietti, D. L., & Hillman, C. H. (2013). Exercise improves behavioral, neurocognitive, and scholastic performance in children with attention-deficit/hyperactivity disorder. *The Journal of Pediatrics, 162*(3), 543–551. https://doi.org/10.1016/j.jpeds.2012.08.036

Reid, R., Trout, A. L., & Schartz, M. (2005). Self-regulation interventions for children with attention deficit/hyperactivity disorder. *Exceptional Children, 71*(4), 361–377.

Rey, G. D., Beege, M., Nebel, S., Wirzberger, M., Schmitt, T. H., & Schneider, S. (2019). A meta-analysis of the segmenting effect. *Educational Psychology Review, 31*(2), 389–419. https://doi.org/10.1007/s10648-018-9456-4

Roediger, H. L., III, Agarwal, P. K., McDaniel, M. A., & McDermott, K. B. (2011). Test-enhanced learning in the classroom: Long-term improvements from quizzing. *Journal of Experimental Psychology: Applied, 17*(4), 382–395. https://doi.org/10.1037/a0026252

Szpunar, K. K., Khan, N. Y., & Schacter, D. L. (2013). Interpolated memory tests reduce mind wandering and improve learning of online lectures. *Proceedings of the National Academy of Sciences, 110*(16), 6313–6317. https://doi.org/10.1073/pnas.1221764110

Zentall, S. (1975). Optimal stimulation as theoretical basis of hyperactivity. *American Journal of Orthopsychiatry, 45*(4), 549–563. https://doi.org/10.1111/j.1939-0025.1975.tb01185.x

Zentall, S. S., & Zentall, T. R. (1983). Optimal stimulation: A model of disordered activity and performance in normal and deviant children. *Psychological Bulletin, 94*(3), 446–471. https://doi.org/10.1037/0033-2909.94.3.446

Verification notes: participants, procedures and results above were checked against the papers or their abstracts on 24 Oct 2026. Before final thesis submission, confirm the Mahar et al. full author list, the Mills et al. sample, and the Murphy et al. sample description from the full texts.
