"""Same training logic as the Colab notebook. Saves model_rf / model_nn, scaler, labels and winner."""
import pandas as pd, joblib, simulate
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import f1_score, classification_report

simulate.make_dataset().to_csv("fault_data.csv", index=False)
df = pd.read_csv("fault_data.csv")
X = df[["voltage", "current", "leakage_ma", "power_factor"]].values
le = LabelEncoder(); y = le.fit_transform(df.label)
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

rf = RandomForestClassifier(n_estimators=200, random_state=42).fit(Xtr, ytr)
rf_f1 = f1_score(yte, rf.predict(Xte), average="macro"); nn_f1 = -1
print(f"RF macro-F1: {rf_f1:.4f}\n", classification_report(yte, rf.predict(Xte), target_names=le.classes_))
joblib.dump(rf, "model_rf.joblib"); joblib.dump(le, "labels.joblib")
try:
    import tensorflow as tf
    sc = StandardScaler().fit(Xtr)
    nn = tf.keras.Sequential([tf.keras.layers.Input(shape=(4,)), tf.keras.layers.Dense(16, activation="relu"),
        tf.keras.layers.Dense(8, activation="relu"), tf.keras.layers.Dense(len(le.classes_), activation="softmax")])
    nn.compile("adam", "sparse_categorical_crossentropy", metrics=["accuracy"])
    nn.fit(sc.transform(Xtr), ytr, epochs=30, batch_size=32, verbose=0)
    nn_f1 = f1_score(yte, nn.predict(sc.transform(Xte)).argmax(1), average="macro")
    print(f"NN macro-F1: {nn_f1:.4f}"); nn.save("model_nn.keras"); joblib.dump(sc, "scaler.joblib")
except ImportError:
    print("TensorFlow not installed: using Random Forest only. pip install tensorflow to compare.")
joblib.dump("nn" if nn_f1 > rf_f1 else "rf", "winner.joblib"); print("Winner:", "nn" if nn_f1 > rf_f1 else "rf")
