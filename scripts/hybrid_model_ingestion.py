import os
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

try:
    import torch
except ModuleNotFoundError:  # pragma: no cover
    torch = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = PROJECT_ROOT / "data" / "multimodal_hybrid_dataset"
CSV_PATH = DATASET_DIR / "multimodal_hybrid_dataset.csv"
XLSX_PATH = DATASET_DIR / "multimodal_hybrid_dataset.xlsx"


def load_dataset(csv_path=CSV_PATH):
    df = pd.read_csv(csv_path)
    df = df.sort_values(["region", "year"]).reset_index(drop=True)
    return df


def build_feature_matrix(df, target_col="target_yield_kg_ha"):
    feature_cols = [
        c for c in df.columns
        if c not in {"region", "year", "target_yield_kg_ha"}
    ]
    X = df[feature_cols].copy()
    y = df[target_col].astype(float)
    X = X.fillna(X.median(numeric_only=True))
    X = X.replace([np.inf, -np.inf], np.nan).fillna(X.median(numeric_only=True))

    cat_cols = X.select_dtypes(include=["object"]).columns.tolist()
    if cat_cols:
        X = pd.get_dummies(X, columns=cat_cols, drop_first=True)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    return X_scaled, y.to_numpy(dtype=np.float32), list(X.columns), scaler


def make_sequences(X, y, seq_len=3):
    if len(X) < seq_len:
        return np.array([X]), np.array([y])
    seqs, targets = [], []
    for i in range(len(X) - seq_len + 1):
        seqs.append(X[i:i + seq_len])
        targets.append(y[i + seq_len - 1])
    return np.asarray(seqs, dtype=np.float32), np.asarray(targets, dtype=np.float32)


def to_tensor_batch(X, y):
    if torch is None:
        raise ImportError("PyTorch n'est pas installé. Installez-le avec: pip install torch")
    return torch.tensor(X, dtype=torch.float32), torch.tensor(y, dtype=torch.float32).unsqueeze(1)


def prepare_for_model(model_name, X, y, seq_len=3):
    if model_name in {"transformer", "lstm", "cnn", "mlp"}:
        if model_name in {"transformer", "lstm", "cnn"}:
            X_seq, y_seq = make_sequences(X, y, seq_len=seq_len)
            return to_tensor_batch(X_seq, y_seq)
        if model_name == "mlp":
            return torch.tensor(X, dtype=torch.float32), torch.tensor(y, dtype=torch.float32).unsqueeze(1)
    raise ValueError(f"Unknown model: {model_name}")


def example_transformer_model(input_dim, seq_len):
    import torch.nn as nn

    class TransformerRegressor(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = nn.TransformerEncoder(
                nn.TransformerEncoderLayer(d_model=input_dim, nhead=4, dim_feedforward=128, batch_first=True),
                num_layers=2,
            )
            self.head = nn.Linear(input_dim, 1)

        def forward(self, x):
            x = self.encoder(x)
            x = x[:, -1, :]
            return self.head(x)

    return TransformerRegressor()


def example_cnn_model(input_dim, seq_len):
    import torch.nn as nn

    class CNNRegressor(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = nn.Conv1d(in_channels=seq_len, out_channels=16, kernel_size=3, padding=1)
            self.pool = nn.AdaptiveAvgPool1d(1)
            self.head = nn.Linear(16, 1)

        def forward(self, x):
            x = x.transpose(1, 2)
            x = self.conv(x)
            x = torch.relu(x)
            x = self.pool(x).squeeze(-1)
            return self.head(x)

    return CNNRegressor()


def example_lstm_model(input_dim, seq_len):
    import torch.nn as nn

    class LSTMRegressor(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(input_size=input_dim, hidden_size=64, num_layers=2, batch_first=True)
            self.head = nn.Linear(64, 1)

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.head(out[:, -1, :])

    return LSTMRegressor()


def example_mlp_model(input_dim):
    import torch.nn as nn

    class MLPRegressor(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_dim, 128),
                nn.ReLU(),
                nn.Linear(128, 64),
                nn.ReLU(),
                nn.Linear(64, 1),
            )

        def forward(self, x):
            return self.net(x)

    return MLPRegressor()


def build_model(model_name, input_dim, seq_len):
    if model_name == "transformer":
        return example_transformer_model(input_dim, seq_len)
    if model_name == "cnn":
        return example_cnn_model(input_dim, seq_len)
    if model_name == "lstm":
        return example_lstm_model(input_dim, seq_len)
    if model_name == "mlp":
        return example_mlp_model(input_dim)
    raise ValueError(f"Unsupported model name: {model_name}")


def train_example(model_name="lstm", epochs=5):
    if torch is None:
        raise ImportError("PyTorch n'est pas installé. Installez-le avec: pip install torch")
    df = load_dataset()
    X, y, feature_names, scaler = build_feature_matrix(df)
    X_t, y_t = prepare_for_model(model_name, X, y, seq_len=3)
    model = build_model(model_name, X_t.shape[-1], X_t.shape[1])
    criterion = torch.nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    for epoch in range(epochs):
        optimizer.zero_grad()
        pred = model(X_t)
        loss = criterion(pred, y_t)
        loss.backward()
        optimizer.step()
        print(f"Epoch {epoch+1}/{epochs} - Loss: {loss.item():.6f}")

    print(f"Model '{model_name}' trained successfully.")
    return model, feature_names, scaler


if __name__ == "__main__":
    print("Dataset exists:", CSV_PATH.exists())
    train_example(model_name="lstm", epochs=2)
