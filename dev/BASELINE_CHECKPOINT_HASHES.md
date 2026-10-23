# Baseline checkpoint hashes (pre Phase-1 fixes)

Recorded 2026-10-23 from the local working tree. Checkpoints are **not** committed to git (see root `.gitignore`). Do not overwrite these files during Phase 1.

Paths relative to `models/`.

| Asset | Path | SHA-256 | Bytes | File time (local) |
|-------|------|---------|-------|-------------------|
| Gaze M1 (deployed) | `outputs/checkpoints/model1_gaze/best.pt` | `8127a926c74a21b41f4398d43f8a662c653f61e31f2dd62302cd995b442eba32` | 27089538 | 2026-10-21 07:34:17 |
| Gaze M1 last (same bytes) | `outputs/checkpoints/model1_gaze/last.pt` | `8127a926c74a21b41f4398d43f8a662c653f61e31f2dd62302cd995b442eba32` | 27089538 | 2026-10-21 07:34:17 |
| Gaze M1 epoch-15 backup | `outputs/checkpoints/model1_gaze/last_epoch15_96_backup.pt` | `8127a926c74a21b41f4398d43f8a662c653f61e31f2dd62302cd995b442eba32` | 27089538 | 2026-10-21 07:34:17 |
| Gaze M1 epoch-2 best backup | `outputs/checkpoints/model1_gaze/best_epoch2_backup.pt` | `a3e1f4ed22dba22319705c7417470c77d5bdaedffec431bebbe7062e38b6c58d` | 9143300 | 2026-07-01 |
| Gaze M1 epoch-2 last backup | `outputs/checkpoints/model1_gaze/last_epoch2_backup.pt` | `fbe931d3961f258aa5a43a48879d4fe915ea7892a5e37d273a557b043ae07d69` | 27087810 | 2026-07-01 |
| Pose M2 | `outputs/checkpoints/model2_pose/best.pt` | `a91162707d5eff172e21f16cac93feeec9b57306dac1ca78531efd4e8050f629` | 134253858 | 2026-02-16 09:09:31 |
| Pose M2 last | `outputs/checkpoints/model2_pose/last.pt` | `61104a6df32837d4f1a0fdd8bb35d61c61a3688442e14f0f7cf46bb43a695962` | 134253858 | 2026-02-16 09:11:03 |
| Engagement M4 | `outputs/checkpoints/model4_engagement/model.pkl` | `d39b5f16d3e78653c06fdead842518e2d6add967194474de6f632373beb237e9` | 2419 | 2026-07-22 06:50:55 |
| Fusion M5 | `outputs/checkpoints/model5_fusion/model.pkl` | `b465e0c48af9067b9417a696a7c510ddf34ac98779d6aea6adba94e7d42020e6` | 1853 | 2026-07-26 15:08:42 |
| MediaPipe lite | `src/model4_engagement/pose_landmarker_lite.task` | `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a` | 5777746 | 2026-02-16 10:12:18 |

Gaze `best.pt` metadata (torch): epoch 15, `img_size` 96, `best_f1` 0.569808 (validation peak from earlier epoch).  
Fusion pickle metadata: 9 features, threshold 0.5, tuning disabled.

Historical evaluation reports under `models/reports/` and `models/*_out.txt` are preserved in place and must not be overwritten by Phase 1 work.
