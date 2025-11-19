from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    classification_report,
    precision_recall_fscore_support,
    roc_auc_score,
)


# -----------------------------
# 1) 数据准备
# -----------------------------
def prepare_dataset(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    join_keys: List[str] = ["ad_id", "date"],
    y_col: str = "y",
    sort_by: str = "date",
) -> pd.DataFrame:
    """合并特征与标签、去除无效 y、排序并重置索引。"""
    df = features.merge(labels, on=join_keys, how="inner")
    df = df[~df[y_col].isna()].sort_values(sort_by).reset_index(drop=True)
    return df


# -----------------------------
# 2) 分层划分（按 ad_id）
# -----------------------------
def split_by_ad_id(
    df: pd.DataFrame,
    ad_col: str = "ad_id",
    test_ratio: float = 0.2,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """按广告ID分层随机划分数据集。"""
    unique_ad_ids = df[ad_col].unique()
    rng = np.random.RandomState(random_state)
    rng.shuffle(unique_ad_ids)
    split_idx = int(len(unique_ad_ids) * (1 - test_ratio))
    train_ad_ids = unique_ad_ids[:split_idx]
    test_ad_ids = unique_ad_ids[split_idx:]
    tr = df[df[ad_col].isin(train_ad_ids)]
    va = df[df[ad_col].isin(test_ad_ids)]
    return tr, va


# -----------------------------
# 3) 选择特征列
# -----------------------------
def get_feature_columns(
    df: pd.DataFrame,
    exclude: Optional[set] = None,
) -> List[str]:
    """排除非特征列，得到用于训练的列名。"""
    exclude = exclude or {
        "ad_id",
        "date",
        "y",
        "roas_future_7d",
        "rev_future_7d",
        "spend_future_7d",
    }
    return [c for c in df.columns if c not in exclude]


# -----------------------------
# 4) 模型构建
# -----------------------------
def build_hgbt(
    random_state: int = 42,
    class_weight=None,
    **overrides,
) -> HistGradientBoostingClassifier:
    """构建 HistGradientBoostingClassifier，可用 overrides 覆盖默认超参。"""
    params = dict(
        max_depth=10,
        learning_rate=0.06,
        max_iter=600,
        min_samples_leaf=20,
        l2_regularization=0.05,
        random_state=random_state,
        class_weight=class_weight,
    )
    params.update(overrides)
    return HistGradientBoostingClassifier(**params)


# -----------------------------
# 4.1) 模型保存
# -----------------------------
def save_model(model, path):
    """保存模型。"""
    import joblib

    return joblib.dump(model, path)


def load_model(path) -> HistGradientBoostingClassifier:
    """加载模型。"""
    import joblib

    return joblib.load(path)


# -----------------------------
# 5) 训练与预测
# -----------------------------
def fit_predict_proba(
    clf: HistGradientBoostingClassifier,
    X_tr: pd.DataFrame,
    y_tr: pd.Series,
    X_va: pd.DataFrame,
) -> Tuple[np.ndarray, np.ndarray]:
    """拟合模型并返回 train/val 的正类概率。"""
    clf.fit(X_tr, y_tr)
    proba_tr = clf.predict_proba(X_tr)[:, 1]
    proba_va = clf.predict_proba(X_va)[:, 1]
    return proba_tr, proba_va


# -----------------------------
# 6) 阈值搜索
# -----------------------------
def select_best_threshold(
    y_true: np.ndarray,
    proba: np.ndarray,
    thresholds: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    """在给定阈值集合上以 F1 最大为准选择最佳阈值，并返回主要指标。"""
    if thresholds is None:
        thresholds = np.linspace(0.1, 0.9, 17)
    best = {"thr": 0.5, "f1": -1.0, "precision": 0.0, "recall": 0.0}
    for thr in thresholds:
        pred = (proba >= thr).astype(int)
        p, r, f1, _ = precision_recall_fscore_support(
            y_true, pred, average="binary", zero_division=0
        )
        if f1 > best["f1"]:
            best = {
                "thr": float(thr),
                "f1": float(f1),
                "precision": float(p),
                "recall": float(r),
            }
    return best


# -----------------------------
# 7) 评估（AUC + 报告）
# -----------------------------
def compute_auc(y_true: np.ndarray, proba: np.ndarray) -> Optional[float]:
    """安全计算 AUC；若标签只有1类则返回 None。"""
    return float(roc_auc_score(y_true, proba)) if len(np.unique(y_true)) > 1 else None


def make_report(
    y_true: np.ndarray,
    proba: np.ndarray,
    threshold: float,
) -> Dict[str, Any]:
    """基于固定阈值得到分类报告。"""
    pred = (proba >= threshold).astype(int)
    return classification_report(y_true, pred, output_dict=True, zero_division=0)


# -----------------------------
# 8) 包装主流程
# -----------------------------
def train_model(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    random_state: int = 42,
    class_weight=None,
    exclude_cols: Optional[set] = None,
    model_overrides: Optional[Dict[str, Any]] = None,
    test_ratio: float = 0.2,
) -> Dict[str, Any]:
    # 准备数据
    df = prepare_dataset(
        features, labels, join_keys=["ad_id", "date"], y_col="y", sort_by="date"
    )

    # 划分
    tr, va = split_by_ad_id(
        df, ad_col="ad_id", test_ratio=test_ratio, random_state=random_state
    )

    # 特征列
    X_cols = get_feature_columns(tr, exclude=exclude_cols)

    # 构造矩阵
    X_tr, y_tr = tr[X_cols].fillna(0), tr["y"].astype(int)
    X_va, y_va = va[X_cols].fillna(0), va["y"].astype(int)

    # 建模
    clf = build_hgbt(
        random_state=random_state, class_weight=class_weight, **(model_overrides or {})
    )
    proba_tr, proba_va = fit_predict_proba(clf, X_tr, y_tr, X_va)

    # 阈值选择（基于验证集）
    best = select_best_threshold(y_va.values, proba_va)

    # 评估
    auc_tr = compute_auc(y_tr.values, proba_tr)
    auc_va = compute_auc(y_va.values, proba_va)
    report_tr = make_report(y_tr.values, proba_tr, best["thr"])
    report_va = make_report(y_va.values, proba_va, best["thr"])

    # 结果打包（与原版保持一致）
    return {
        "model": clf,
        "feature_names": X_cols,
        # 验证集
        "val_auc": auc_va,
        "best_threshold": best,
        "val_report": report_va,
        "val_table": va[["ad_id", "date", "y", "roas_future_7d"]].assign(
            p_stop=proba_va
        ),
        "va": va[["rev_future_7d", "spend_future_7d", "y"]],
        "proba_va": proba_va,
        # 训练集
        "train_auc": auc_tr,
        "train_report": report_tr,
        "train_table": tr[["ad_id", "date", "y", "roas_future_7d"]].assign(
            p_stop=proba_tr
        ),
        "proba_tr": proba_tr,
    }


if __name__ == "__main__":
    import pandas as pd

    feat = pd.read_feather("models/feat.feather")
    labels = pd.read_feather("models/labels.feather")

    train_result = train_model(
        feat,
        labels[
            ["ad_id", "date", "y", "roas_future_7d", "rev_future_7d", "spend_future_7d"]
        ],
    )
    print(train_result.keys())
    print(train_result.get("val_auc"))
    path_list = save_model(train_result["model"], "models/model.feather")
    print(path_list)

    model = load_model(path_list[0])
    feat_clip = feat.iloc[:10]
    print(feat_clip)
    pred_proba = model.predict_proba(feat_clip.drop(columns=["ad_id", "date"]))
    print(pred_proba)
