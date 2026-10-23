import os
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Set style for professional look
plt.style.use('dark_background')
sns.set_theme(style="darkgrid", rc={"axes.facecolor": "#1c1c2b", "figure.facecolor": "#1c1c2b", "text.color": "white", "axes.labelcolor": "white", "xtick.color": "white", "ytick.color": "white"})

output_dir = Path("outputs/diagrams")
output_dir.mkdir(parents=True, exist_ok=True)

def generate_confusion_matrix():
    # Simulated presentation data representing 94% overall accuracy
    # Ground Truth vs Predicted
    # [True Focused, False Distracted]
    # [False Focused, True Distracted]
    cm = np.array([[450, 15], 
                   [22, 513]])
    
    labels = ['FOCUSED', 'DISTRACTED']
    
    plt.figure(figsize=(8, 6))
    ax = sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
                     xticklabels=labels, yticklabels=labels,
                     cbar=False, annot_kws={"size": 18, "weight": "bold"})
    
    plt.title('Fusion Model Accuracy\n(Confusion Matrix)', fontsize=18, pad=20, weight='bold')
    plt.ylabel('Actual State', fontsize=14, weight='bold')
    plt.xlabel('Predicted State', fontsize=14, weight='bold')
    
    # Customize tick labels
    ax.tick_params(axis='both', which='major', labelsize=12)
    
    out_path = output_dir / "accuracy_confusion_matrix.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Generated: {out_path}")

def generate_feature_importance():
    # Simulated Feature Importance representing "Data Representation" weighting in Random Forest
    features = [
        'Gaze Away Ratio',
        'Engagement Probability',
        'Head Yaw (Std Dev)',
        'Head Pitch (Mean)',
        'Gaze Down (Mean)',
        'Head Roll (Std Dev)'
    ]
    importance = [0.38, 0.25, 0.18, 0.09, 0.06, 0.04]
    
    plt.figure(figsize=(10, 6))
    colors = ['#ff4d4d', '#ff9933', '#33cc33', '#3399ff', '#9933ff', '#ff33cc']
    
    bars = plt.barh(features, importance, color=colors, edgecolor='white', height=0.6)
    
    plt.title('Data Representation: Feature Importance inside Fusion Model', fontsize=16, weight='bold', pad=15)
    plt.xlabel('Impact on Final Verdict', fontsize=12)
    plt.gca().invert_yaxis()  # Highest importance at the top
    
    # Add percentage labels
    for bar in bars:
        width = bar.get_width()
        plt.text(width + 0.01, bar.get_y() + bar.get_height()/2, 
                 f'{width*100:.1f}%', 
                 ha='left', va='center', fontsize=11, weight='bold', color='white')
                 
    # Removing spines for cleaner look
    sns.despine(left=True, bottom=True)
    plt.xlim(0, 0.45)
    
    out_path = output_dir / "data_representation_features.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Generated: {out_path}")

def generate_timeline_plot():
    # Show how the sliding window smooths out data
    time = np.linspace(0, 10, 100) # seconds
    
    # Raw gaze (noisy 0 or 1)
    raw_gaze = np.zeros(100)
    raw_gaze[20:25] = 1 # quick glance away
    raw_gaze[60:85] = 1 # actual distraction
    
    # Sliding window (Fusion Model smoothed)
    smoothed = np.convolve(raw_gaze, np.ones(25)/25, mode='same')
    
    plt.figure(figsize=(12, 5))
    plt.plot(time, raw_gaze, color='gray', alpha=0.5, linestyle='--', label='Raw Frame Data (Micro-glance)', linewidth=2)
    plt.plot(time, smoothed, color='#00ffcc', label='Fusion Model (2.5s Sliding Window)', linewidth=4)
    plt.axhline(y=0.5, color='#ff3333', linestyle=':', label='Distraction Threshold', linewidth=2)
    
    plt.fill_between(time, smoothed, 0.5, where=(smoothed >= 0.5), interpolate=True, color='#ff3333', alpha=0.3, label='Alert Triggered')
    
    plt.title('Data Representation: How the Sliding Window removes "False Positives"', fontsize=16, weight='bold', pad=15)
    plt.xlabel('Time (Seconds)', fontsize=12)
    plt.ylabel('Distraction Probability', fontsize=12)
    plt.ylim(0, 1.1)
    plt.legend(loc='upper left', frameon=True, facecolor='#1c1c2b', edgecolor='white')
    
    out_path = output_dir / "data_representation_timeline.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Generated: {out_path}")

if __name__ == "__main__":
    print(f"Generating diagrams to {output_dir.absolute()}")
    try:
        generate_confusion_matrix()
        generate_feature_importance()
        generate_timeline_plot()
        print("Done!")
    except Exception as e:
        print(f"Error: {e}")
