import os
import sys
import pickle

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.config import settings


def train_diabetes_model():
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score
    import numpy as np

    np.random.seed(42)
    n_samples = 2000

    age = np.random.uniform(20, 80, n_samples)
    bmi = np.random.uniform(18, 45, n_samples)
    glucose = np.random.uniform(70, 200, n_samples)
    bp = np.random.uniform(90, 180, n_samples)
    exercise = np.random.uniform(0, 60, n_samples)
    sleep = np.random.uniform(4, 10, n_samples)

    risk = (
        (age > 45) * 0.15 +
        (bmi > 30) * 0.20 +
        (glucose > 126) * 0.30 +
        (bp > 140) * 0.10 +
        (exercise < 15) * 0.15 +
        (sleep < 6) * 0.10
    )
    y = (risk > 0.35).astype(int)

    X = np.column_stack([age, bmi, glucose, bp, exercise, sleep])
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42)
    model.fit(X_train, y_train)

    y_pred_proba = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_pred_proba)
    print(f"  Diabetes model AUC: {auc:.3f}")
    return model


def train_heart_disease_model():
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score
    import numpy as np

    np.random.seed(42)
    n_samples = 2000

    age = np.random.uniform(30, 80, n_samples)
    bp_sys = np.random.uniform(90, 180, n_samples)
    bp_dia = np.random.uniform(60, 110, n_samples)
    cholesterol = np.random.uniform(120, 300, n_samples)
    glucose = np.random.uniform(70, 200, n_samples)
    bmi = np.random.uniform(18, 45, n_samples)
    smoker = np.random.binomial(1, 0.2, n_samples)
    heart_rate = np.random.uniform(50, 110, n_samples)
    exercise = np.random.uniform(0, 60, n_samples)

    risk = (
        (age > 55) * 0.15 +
        (bp_sys > 140) * 0.15 +
        (cholesterol > 240) * 0.15 +
        (glucose > 126) * 0.10 +
        (bmi > 30) * 0.10 +
        smoker * 0.20 +
        (exercise < 15) * 0.10 +
        (heart_rate > 90) * 0.05
    )
    y = (risk > 0.35).astype(int)

    X = np.column_stack([age, bp_sys, bp_dia, cholesterol, glucose, bmi, smoker, heart_rate, exercise])
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = GradientBoostingClassifier(n_estimators=150, max_depth=5, random_state=42)
    model.fit(X_train, y_train)

    y_pred_proba = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_pred_proba)
    print(f"  Heart disease model AUC: {auc:.3f}")
    return model


def train_ckd_model():
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score
    import numpy as np

    np.random.seed(42)
    n_samples = 2000

    age = np.random.uniform(20, 85, n_samples)
    bp_sys = np.random.uniform(90, 180, n_samples)
    glucose = np.random.uniform(70, 200, n_samples)
    bmi = np.random.uniform(18, 45, n_samples)
    hemoglobin = np.random.uniform(8, 18, n_samples)
    albumin = np.random.uniform(2.0, 5.0, n_samples)
    sodium = np.random.uniform(125, 155, n_samples)

    risk = (
        (age > 60) * 0.15 +
        (bp_sys > 140) * 0.15 +
        (glucose > 126) * 0.10 +
        (hemoglobin < 12) * 0.20 +
        (albumin < 3.5) * 0.20 +
        (bmi > 30) * 0.10 +
        (sodium < 135) * 0.10
    )
    y = (risk > 0.30).astype(int)

    X = np.column_stack([age, bp_sys, glucose, bmi, hemoglobin, albumin, sodium])
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42)
    model.fit(X_train, y_train)

    y_pred_proba = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_pred_proba)
    print(f"  CKD model AUC: {auc:.3f}")
    return model


def train_stroke_model():
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score
    import numpy as np

    np.random.seed(42)
    n_samples = 2000

    age = np.random.uniform(20, 85, n_samples)
    bp_sys = np.random.uniform(90, 180, n_samples)
    glucose = np.random.uniform(70, 200, n_samples)
    bmi = np.random.uniform(18, 45, n_samples)
    smoker = np.random.binomial(1, 0.2, n_samples)
    heart_rate = np.random.uniform(50, 110, n_samples)
    exercise = np.random.uniform(0, 60, n_samples)
    sleep = np.random.uniform(4, 10, n_samples)

    risk = (
        (age > 65) * 0.20 +
        (bp_sys > 140) * 0.20 +
        (glucose > 126) * 0.10 +
        smoker * 0.15 +
        (bmi > 30) * 0.10 +
        (exercise < 15) * 0.10 +
        (sleep < 6) * 0.10 +
        (heart_rate > 90) * 0.05
    )
    y = (risk > 0.30).astype(int)

    X = np.column_stack([age, bp_sys, glucose, bmi, smoker, heart_rate, exercise, sleep])
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = GradientBoostingClassifier(n_estimators=150, max_depth=5, random_state=42)
    model.fit(X_train, y_train)

    y_pred_proba = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_pred_proba)
    print(f"  Stroke model AUC: {auc:.3f}")
    return model


def train_all():
    models_dir = settings.MODELS_DIR
    os.makedirs(models_dir, exist_ok=True)

    print("Training risk prediction models...")

    print("\n1. Diabetes Risk Model")
    diabetes_model = train_diabetes_model()
    with open(os.path.join(models_dir, "diabetes_model.pkl"), "wb") as f:
        pickle.dump(diabetes_model, f)

    print("\n2. Heart Disease Risk Model")
    heart_model = train_heart_disease_model()
    with open(os.path.join(models_dir, "heart_disease_model.pkl"), "wb") as f:
        pickle.dump(heart_model, f)

    print("\n3. CKD Risk Model")
    ckd_model = train_ckd_model()
    with open(os.path.join(models_dir, "ckd_model.pkl"), "wb") as f:
        pickle.dump(ckd_model, f)

    print("\n4. Stroke Risk Model")
    stroke_model = train_stroke_model()
    with open(os.path.join(models_dir, "stroke_model.pkl"), "wb") as f:
        pickle.dump(stroke_model, f)

    print(f"\nAll models saved to {models_dir}/")
    print("  - diabetes_model.pkl")
    print("  - heart_disease_model.pkl")
    print("  - ckd_model.pkl")
    print("  - stroke_model.pkl")


if __name__ == "__main__":
    train_all()
