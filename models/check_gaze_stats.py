import pandas as pd

for split in ["train", "val", "test"]:
    df = pd.read_csv(f"data/processed/model1_gaze/{split}.csv")
    print(f"\n{split.upper()} samples: {len(df)}")
    print(df["label_name"].value_counts())
