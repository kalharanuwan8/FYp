# PLAN 4 annotation checklist (21 clips)

Use `venvpy312` and the fixed tool:

```
venvpy312\Scripts\python.exe models/scripts/annotate_clip.py --participant N --condition C
```

Protocol printed by the tool (`v4_distraction_spans`):
- Mark every distraction span ≥2 s (phone, looking away, talking, absent, drowsy, eyes off lesson).
- Glances <2 s are **not** distraction.
- **Distracted** clips: unmarked time = unlabelled (dropped at extract). Use `F` only for on-task islands.
- **Focused / natural** clips: unmarked time = focused. Natural = evaluation only.
- Keys: `D` start/end distract · `F` focused correction · `U` undo · `X` delete under cursor · `S` save · `Q` quit.

| # | Subject | Condition | Done |
|---|---------|-----------|------|
| 1 | S01 | focused | ☐ |
| 2 | S01 | distracted | ☐ |
| 3 | S01 | natural | ☐ |
| 4 | S02 | focused | ☐ |
| 5 | S02 | distracted | ☐ |
| 6 | S02 | natural | ☐ |
| 7 | S03 | focused | ☐ |
| 8 | S03 | distracted | ☐ |
| 9 | S03 | natural | ☐ |
| 10 | S04 | focused | ☐ |
| 11 | S04 | distracted | ☐ |
| 12 | S04 | natural | ☐ |
| 13 | S05 | focused | ☐ |
| 14 | S05 | distracted | ☐ |
| 15 | S05 | natural | ☐ |
| 16 | S06 | focused | ☐ |
| 17 | S06 | distracted | ☐ |
| 18 | S06 | natural | ☐ |
| 19 | S07 | focused | ☐ |
| 20 | S07 | distracted | ☐ |
| 21 | S07 | natural | ☐ |

Labels land next to each clip as `<stem>_labels.csv` (outside the repo raw tree).
