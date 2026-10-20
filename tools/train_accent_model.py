"""Train/evaluate the optional accent-classifier adapter from labelled feature CSV data.

Expected CSV columns:
  accent,pitch_median_hz,rms_dbfs,spectral_centroid_hz,spectral_rolloff_hz,zero_crossing_rate

This is an educational baseline, not a reliable accent-recognition system. Use only
consented data, prevent speaker leakage across splits, and evaluate on speakers that
were not used for training before using results in a robot.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = [
    "pitch_median_hz",
    "rms_dbfs",
    "spectral_centroid_hz",
    "spectral_rolloff_hz",
    "zero_crossing_rate",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_csv", help="CSV containing labelled voice features")
    parser.add_argument("--model-out", default="models/accent_classifier.joblib")
    parser.add_argument("--test-size", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    dataset_path = Path(args.dataset_csv)
    if not dataset_path.is_file():
        parser.error(f"CSV file not found: {dataset_path}")
    data = pd.read_csv(dataset_path)
    required = FEATURES + ["accent"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        parser.error("Missing required CSV columns: " + ", ".join(missing))
    data = data[required].dropna()
    if data["accent"].nunique() < 2:
        parser.error("At least two accent labels are required")
    counts = data["accent"].value_counts()
    if counts.min() < 4:
        parser.error("Each label needs at least 4 usable examples for a stratified train/test split")
    if args.test_size <= 0.0 or args.test_size >= 1.0:
        parser.error("--test-size must be greater than 0 and less than 1")

    X = data[FEATURES].astype(float)
    y = data["accent"].astype(str)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.seed, stratify=y
    )
    classifier = Pipeline([
        ("scale", StandardScaler()),
        ("classifier", RandomForestClassifier(
            n_estimators=300,
            class_weight="balanced",
            random_state=args.seed,
            min_samples_leaf=2,
        )),
    ])
    classifier.fit(X_train, y_train)
    predictions = classifier.predict(X_test)

    print(f"Rows: {len(data)} | classes: {sorted(y.unique())}")
    print(f"Hold-out accuracy (descriptive only): {accuracy_score(y_test, predictions):.3f}")
    print(classification_report(y_test, predictions, zero_division=0))
    print("Confusion matrix (label order follows sorted labels):")
    labels = sorted(y.unique())
    print(confusion_matrix(y_test, predictions, labels=labels))
    print("WARNING: use a speaker-independent holdout split in serious evaluations; random utterance splits may overstate generalisation.")

    # Refit on all available labelled examples only after reporting the hold-out evaluation.
    classifier.fit(X, y)
    output = Path(args.model_out)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(classifier, output)
    print(f"Saved model: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
