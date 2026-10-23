import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

def generate_fusion_scatterplots(output_dir):
    try:
        df = pd.read_csv("data/processed/model5_fusion/train.csv")
        if 'y' not in df.columns:
            return
            
        sns.set_theme(style="darkgrid", rc={"axes.facecolor": "#1c1c2b", "figure.facecolor": "#1c1c2b", "text.color": "white", "axes.labelcolor": "white", "xtick.color": "white", "ytick.color": "white"})
        
        # Plot 1: Gaze Away Ratio vs Yaw Mean
        plt.figure(figsize=(10, 7))
        sns.scatterplot(data=df, x='gaze_away_ratio', y='yaw_mean', hue='y', palette=['#00ffcc', '#ff3333'], alpha=0.7, s=60)
        plt.title('Why ML for Fusion? Class Separation\n(Gaze Away vs Head Movement)', fontsize=16, weight='bold', pad=15)
        plt.xlabel('Gaze Away Ratio (0.0 to 1.0)', fontsize=12)
        plt.ylabel('Yaw Mean (Head Position)', fontsize=12)
        
        # Custom legend
        handles, _ = plt.gca().get_legend_handles_labels()
        if len(handles) >= 2:
            plt.legend(handles=handles, labels=['Focused (0)', 'Distracted (1)'], title="Verdict", frameon=True, facecolor='#1c1c2b', edgecolor='white')
            
        plt.savefig(output_dir / 'fusion_scatter_gaze_yaw.png', bbox_inches='tight', dpi=300)
        plt.close()

        # Plot 2: Engagement vs Gaze
        plt.figure(figsize=(10, 7))
        sns.scatterplot(data=df, x='engagement_prob_mean', y='gaze_away_ratio', hue='y', palette=['#00ffcc', '#ff3333'], alpha=0.7, s=60)
        plt.title('Why ML for Fusion? Class Separation\n(Body Engagement vs Eye Gaze)', fontsize=16, weight='bold', pad=15)
        plt.xlabel('Engagement Probability (Body active)', fontsize=12)
        plt.ylabel('Gaze Away Ratio', fontsize=12)
        
        if len(handles) >= 2:
            plt.legend(handles=handles, labels=['Focused (0)', 'Distracted (1)'], title="Verdict", frameon=True, facecolor='#1c1c2b', edgecolor='white')

        plt.savefig(output_dir / 'fusion_scatter_eng_gaze.png', bbox_inches='tight', dpi=300)
        plt.close()

    except Exception as e:
        print(f"Fusion scatterplot failed: {e}")

def generate_gaze_scatterplots(output_dir):
    try:
        df = pd.read_csv("data/processed/model1_gaze/train.csv")
        if len(df) > 3000:
            df = df.sample(n=3000, random_state=42)
        plt.figure(figsize=(10, 7))
        sns.scatterplot(data=df, x='gaze_x', y='gaze_y', hue='label_name', alpha=0.6, s=40)
        plt.title('Gaze Dataset: 2D Gaze Vector Cluster', fontsize=16, weight='bold', pad=15)
        # Custom legend safely
        try:
            plt.legend(title="Gaze Class", frameon=True, facecolor='#1c1c2b', edgecolor='white')
        except: pass
        plt.savefig(output_dir / 'gaze_scatter.png', bbox_inches='tight', dpi=300)
        plt.close()
    except Exception as e:
        print(f"Gaze scatter failed: {e}")

def generate_pose_scatterplots(output_dir):
    try:
        df = pd.read_csv("data/processed/model2_pose/train.csv")
        # Try finding yaw and pitch columns
        y_col = 'yaw_deg' if 'yaw_deg' in df.columns else ('yaw_rad' if 'yaw_rad' in df.columns else None)
        p_col = 'pitch_deg' if 'pitch_deg' in df.columns else ('pitch_rad' if 'pitch_rad' in df.columns else None)
        
        if y_col and p_col:
            df[y_col] = pd.to_numeric(df[y_col], errors='coerce')
            df[p_col] = pd.to_numeric(df[p_col], errors='coerce')
            df = df.dropna(subset=[y_col, p_col])
            if len(df) > 5000: df = df.sample(n=5000, random_state=42)
                
            plt.figure(figsize=(10, 7))
            sns.scatterplot(data=df, x=y_col, y=p_col, alpha=0.5, s=30, color='#38bdf8')
            plt.title('Head Pose Dataset: Yaw vs Pitch', fontsize=16, weight='bold', pad=15)
            plt.savefig(output_dir / 'pose_scatter.png', bbox_inches='tight', dpi=300)
            plt.close()
    except Exception as e:
        print(f"Pose scatter failed: {e}")

def generate_engagement_scatterplots(output_dir):
    try:
        df = pd.read_csv("data/processed/model4_engagement/labeled.csv")
        if 'active_work' in df.columns and 'lw_speed_mean' in df.columns and 'nose_jitter' in df.columns:
            plt.figure(figsize=(10, 7))
            sns.scatterplot(data=df, x='lw_speed_mean', y='nose_jitter', hue='active_work', palette=['#ff3333', '#00ffcc'], alpha=0.7, s=60)
            plt.title('Engagement Dataset: Wrist Speed vs Head Jitter', fontsize=16, weight='bold', pad=15)
            
            handles, _ = plt.gca().get_legend_handles_labels()
            if len(handles) >= 2:
                plt.legend(handles=handles, labels=['Passive (0)', 'Active Work (1)'], title="Engagement", frameon=True, facecolor='#1c1c2b', edgecolor='white')
                
            plt.savefig(output_dir / 'engagement_scatter.png', bbox_inches='tight', dpi=300)
            plt.close()
    except Exception as e:
        print(f"Engagement scatter failed: {e}")

def main():
    output_dir = Path("outputs/dataset_visualizations")
    output_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="darkgrid", rc={"axes.facecolor": "#1c1c2b", "figure.facecolor": "#1c1c2b", "text.color": "white", "axes.labelcolor": "white", "xtick.color": "white", "ytick.color": "white"})
    print("Generating defense scatterplots...")
    generate_fusion_scatterplots(output_dir)
    generate_gaze_scatterplots(output_dir)
    generate_pose_scatterplots(output_dir)
    generate_engagement_scatterplots(output_dir)
    print("Done!")

if __name__ == "__main__":
    main()
