import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

def plot_gaze(output_dir):
    df = pd.read_csv("data/processed/model1_gaze/train.csv")
    plt.figure(figsize=(8, 6))
    sns.countplot(data=df, x='label_name', palette='viridis')
    plt.title('Gaze Dataset: Class Distribution')
    plt.savefig(output_dir / 'gaze_distribution.png', bbox_inches='tight')
    plt.close()

def plot_pose(output_dir):
    try:
        df = pd.read_csv("data/processed/model2_pose/train.csv")
        angle_cols = [c for c in df.columns if 'rad' in c or 'deg' in c or c in ['yaw', 'pitch', 'roll', 'yaw_deg', 'pitch_deg', 'roll_deg']]
        
        if angle_cols:
            plt.figure(figsize=(10, 6))
            for col in angle_cols:
                # Force numeric to handle corrupt rows like 'natural'
                clean_data = pd.to_numeric(df[col], errors='coerce').dropna()
                sns.kdeplot(data=clean_data, label=col, fill=True)
            plt.title('Head Pose Dataset: Angle Distributions')
            plt.legend()
            plt.savefig(output_dir / 'pose_distribution.png', bbox_inches='tight')
            plt.close()
    except Exception as e:
        print(f"Pose plot failed: {e}")

def plot_engagement(output_dir):
    try:
        try:
            df = pd.read_csv("data/processed/model4_engagement/labeled.csv")
        except:
            df = pd.read_csv("data/processed/model4_engagement/features.csv")
        numeric_df = df.select_dtypes(include=['number', 'float', 'int'])
        if not numeric_df.empty:
            plt.figure(figsize=(12, 10))
            sns.heatmap(numeric_df.corr(), annot=False, cmap='coolwarm', fmt=".2f")
            plt.title('Engagement Dataset: Feature Correlation')
            plt.savefig(output_dir / 'engagement_correlation.png', bbox_inches='tight')
            plt.close()
    except Exception as e:
        print(f"Engagement plot failed: {e}")

def plot_fusion(output_dir):
    try:
        df = pd.read_csv("data/processed/model5_fusion/train.csv")
        numeric_df = df.select_dtypes(include=['number', 'float', 'int'])
        plt.figure(figsize=(12, 10))
        sns.heatmap(numeric_df.corr(), annot=True, cmap='coolwarm', fmt=".2f")
        plt.title('Fusion Dataset: Feature vs Verdict Correlation')
        plt.savefig(output_dir / 'fusion_correlation.png', bbox_inches='tight')
        plt.close()
        
        if 'y' in df.columns:
            plt.figure(figsize=(6, 4))
            sns.countplot(data=df, x='y', palette='Set2', hue='y', legend=False)
            plt.title('Fusion Dataset: Distracted (1) vs Focused (0)')
            plt.savefig(output_dir / 'fusion_distribution.png', bbox_inches='tight')
            plt.close()
    except Exception as e:
        print(f"Fusion plot failed: {e}")

def main():
    sns.set_theme(style="whitegrid")
    output_dir = Path("outputs/dataset_visualizations")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("Generating Gaze visualizations...")
    plot_gaze(output_dir)
    print("Generating Pose visualizations...")
    plot_pose(output_dir)
    print("Generating Engagement visualizations...")
    plot_engagement(output_dir)
    print("Generating Fusion visualizations...")
    plot_fusion(output_dir)
    
    print(f"All visualizations saved to {output_dir.absolute()}")

if __name__ == "__main__":
    main()
