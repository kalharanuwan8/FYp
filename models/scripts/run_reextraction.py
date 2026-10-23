import subprocess
import sys
import time
from pathlib import Path

def run_step(idx: int, total: int, desc: str, cmd: list[str]):
    print(f"\n=======================================================")
    print(f"[{idx}/{total}] {desc}")
    print(f"Command: {' '.join(cmd)}")
    print(f"=======================================================", flush=True)
    t0 = time.time()
    res = subprocess.run(cmd)
    dt = time.time() - t0
    if res.returncode != 0:
        print(f"\n[ERROR] Step {idx} failed with return code {res.returncode} after {dt:.1f}s!", flush=True)
        sys.exit(res.returncode)
    print(f"--> [OK] Step {idx} completed in {dt:.1f}s", flush=True)

def main():
    py = sys.executable
    raw_dir = Path("D:/uni/6th sem/IRP/Data collection/raw data/participant 1")
    distracted_vid = str(raw_dir / "distracted.mp4")
    focused_vid = str(raw_dir / "focused.mp4")
    
    steps = [
        # 1. Pose for distracted.mp4
        ("Extracting Model 2 Pose for distracted.mp4", [py, "-u", "-m", "src.model2_pose.infer", "--video", distracted_vid, "--out", "data/processed/model2_pose/window_pose_distracted.csv"]),
        
        # 2-4. Engagement for distracted.mp4
        ("Extracting Model 4 Engagement pose landmarks for distracted.mp4", [py, "-u", "-m", "src.model4_engagement.extractpose", "--video", distracted_vid, "--out", "data/processed/model4_engagement/pose_distracted.csv"]),
        ("Building Model 4 Engagement features for distracted.mp4", [py, "-u", "-m", "src.model4_engagement.buildfeatures", "--pose", "data/processed/model4_engagement/pose_distracted.csv", "--out", "data/processed/model4_engagement/features_distracted.csv"]),
        ("Running Model 4 Engagement inference for distracted.mp4", [py, "-u", "-m", "src.model4_engagement.infer", "--features", "data/processed/model4_engagement/features_distracted.csv", "--model", "outputs/checkpoints/model4_engagement/model.pkl", "--out", "data/processed/model4_engagement/pred_distracted.csv", "--video-id", "distracted"]),
        
        # 5-7. Engagement for focused.mp4 (saved as forced)
        ("Extracting Model 4 Engagement pose landmarks for focused.mp4", [py, "-u", "-m", "src.model4_engagement.extractpose", "--video", focused_vid, "--out", "data/processed/model4_engagement/pose_forced.csv"]),
        ("Building Model 4 Engagement features for focused.mp4", [py, "-u", "-m", "src.model4_engagement.buildfeatures", "--pose", "data/processed/model4_engagement/pose_forced.csv", "--out", "data/processed/model4_engagement/features_forced.csv"]),
        ("Running Model 4 Engagement inference for focused.mp4", [py, "-u", "-m", "src.model4_engagement.infer", "--features", "data/processed/model4_engagement/features_forced.csv", "--model", "outputs/checkpoints/model4_engagement/model.pkl", "--out", "data/processed/model4_engagement/preds_forced.csv", "--video-id", "forced"]),
        
        # 8-9. Model 5 Dataset Prep
        ("Running Model 5 dataset preparation (prep.py)", [py, "-u", "-m", "src.model5_fusion.prep"]),
        ("Running Model 5 dataset preparation (prepare.py)", [py, "-u", "-m", "src.model5_fusion.prepare"]),
        
        # 10. Train Model 5 Fusion
        ("Training Model 5 Fusion classifier", [py, "-u", "-m", "src.model5_fusion.train"])
    ]
    
    t_start = time.time()
    print(f"Starting feature re-extraction and Model 5 re-training pipeline ({len(steps)} steps)...", flush=True)
    
    for i, (desc, cmd) in enumerate(steps, 1):
        run_step(i, len(steps), desc, cmd)
        
    total_time = time.time() - t_start
    print(f"\n=======================================================")
    print(f"[SUCCESS] Whole pipeline finished successfully in {total_time/60:.2f} minutes!")
    print(f"=======================================================", flush=True)

if __name__ == "__main__":
    main()
