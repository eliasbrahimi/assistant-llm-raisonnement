# Tableau de bord Streamlit : affiche les résultats du benchmark
# (45 questions × 3 stratégies) à partir du CSV produit par l'évaluation.
# Lancement : make dashboard

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

# Chemins : ROOT = racine du dépôt (dossier parent de app/).
# Attention : CSV pointe vers ../resultats/, hors du dépôt. Les résultats versionnés
# ici sont dans results/eval_results.csv : adapter ce chemin si le fichier est introuvable.
ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT.parent / "resultats" / "eval_results.csv"
CATALOG = ROOT / "data" / "eval" / "test_catalog.jsonl"

# Configuration de la page et titre.
st.set_page_config(page_title="Dashboard RL/GRPO — ESIEE", layout="wide")
st.title("Dashboard — Assistant Pédagogique RL/GRPO")
st.caption("ESIEE Paris 2025/2026 — Projet E3 | Benchmark 45 questions × 3 stratégies")

# Arrêt propre si le fichier de résultats n'existe pas encore.
if not CSV.exists():
    st.error(f"CSV introuvable : {CSV}\nLance d'abord `python run_local_eval.py` depuis la racine du projet.")
    st.stop()

# Chargement des résultats ; les retours à la ligne avaient été stockés
# sous la forme "\n" (2 caractères) dans le CSV, on les remet en vrais sauts de ligne.
df = pd.read_csv(CSV, encoding="utf-8")
df["response_text"] = df["response_text"].str.replace("\\n", "\n", regex=False)

# Ordre d'affichage des stratégies et couleur associée à chacune.
ORDER = ["baseline", "structured", "fewshot"]
COLORS = {"baseline": "#6c757d", "structured": "#0d6efd", "fewshot": "#198754"}

# ── métriques globales ────────────────────────────────────────────────────────
st.subheader("Métriques globales")
cols = st.columns(4)
cols[0].metric("Questions", df["id"].nunique())
cols[1].metric("Réponses totales", len(df))
# Stratégie ayant le meilleur score moyen, et ce score.
best_strat = df.groupby("strategy")["overall"].mean().idxmax()
best_score = df.groupby("strategy")["overall"].mean().max()
cols[2].metric("Meilleure stratégie", best_strat, f"{best_score:.2f}/3")
# Taux de réponses au format valide, hors baseline (qui n'est pas censée produire du JSON).
json_pct = df[df.strategy != "baseline"]["valid_format"].mean() * 100
cols[3].metric("JSON valide (structured+fewshot)", f"{json_pct:.1f}%")

# ── tableau comparatif ────────────────────────────────────────────────────────
st.subheader("Comparaison par stratégie")
# Une ligne par stratégie : nombre de réponses et moyennes de chaque critère.
summary = (df.groupby("strategy")
           .agg(N=("overall", "count"),
                Score_moyen=("overall", "mean"),
                JSON_valide=("valid_format", "mean"),
                Exactitude=("correctness", "mean"),
                Structure=("structure", "mean"),
                Verification=("verification", "mean"),
                Latence_moy_ms=("latency_ms", "mean"))
           .round(3)
           .reindex(ORDER))
# Mise en forme : taux en pourcentage, latence arrondie à la milliseconde.
summary["JSON_valide"] = (summary["JSON_valide"] * 100).round(1).astype(str) + "%"
summary["Latence_moy_ms"] = summary["Latence_moy_ms"].round(0).astype(int)

# Couleur de fond selon le score : vert ≥ 2,5 / jaune ≥ 1,5 / rouge en dessous.
def color_score(val):
    try:
        v = float(str(val).replace("%", ""))
        if v >= 2.5: return "background-color: #d4edda"
        if v >= 1.5: return "background-color: #fff3cd"
        return "background-color: #f8d7da"
    except Exception:
        return ""

st.dataframe(summary.style.applymap(color_score, subset=["Score_moyen"]), use_container_width=True)

# ── GO/NO-GO ─────────────────────────────────────────────────────────────────
st.subheader("Gate GO/NO-GO")
# Critères de validation d'une stratégie ("GO" si les 3 sont remplis) :
# score moyen ≥ 2,5, au moins 95 % de JSON valide (sauf baseline),
# et 95 % des réponses en moins de 8 s (latence P95).
gcols = st.columns(3)
for i, s in enumerate(ORDER):
    sub = df[df.strategy == s]
    score = sub["overall"].mean()
    fmt = sub["valid_format"].mean() * 100
    p95 = sub["latency_ms"].quantile(0.95)
    score_ok = score >= 2.5
    fmt_ok = fmt >= 95 or s == "baseline"
    lat_ok = p95 < 8000
    gcols[i].markdown(f"**{s.upper()}**")
    gcols[i].markdown(f"Score : `{score:.2f}` {'✅' if score_ok else '❌'} (cible ≥ 2.5)")
    gcols[i].markdown(f"JSON : `{fmt:.1f}%` {'✅' if fmt_ok else '❌'} (cible ≥ 95%)")
    gcols[i].markdown(f"P95 : `{p95:.0f}ms` {'✅' if lat_ok else '❌'} (cible < 8s)")

# ── heatmap par catégorie ─────────────────────────────────────────────────────
st.subheader("Score moyen par catégorie")
# Tableau croisé catégorie × stratégie, coloré du rouge (0) au vert (3).
cat_pivot = df.pivot_table(index="category", columns="strategy", values="overall", aggfunc="mean").round(2)
st.dataframe(cat_pivot.style.background_gradient(cmap="RdYlGn", vmin=0, vmax=3), use_container_width=True)

# ── analyse par difficulté ────────────────────────────────────────────────────
st.subheader("Score par difficulté")
# Même chose par niveau de difficulté, dans l'ordre facile → difficile.
diff_pivot = df.pivot_table(index="difficulty", columns="strategy", values="overall", aggfunc="mean").round(2)
st.dataframe(diff_pivot.reindex(["easy", "medium", "hard"]).style.background_gradient(cmap="RdYlGn", vmin=0, vmax=3), use_container_width=True)

# ── matrice d'évaluation ──────────────────────────────────────────────────────
st.subheader("Matrice d'évaluation (correct / mineur / majeur / invalide)")
# Classe chaque réponse : invalide (format non respecté), correct (≥ 2,5),
# erreur mineure (≥ 1,5) ou erreur majeure.
def classify(row):
    if row["valid_format"] == 0: return "invalide"
    if row["overall"] >= 2.5: return "correct"
    if row["overall"] >= 1.5: return "mineur"
    return "majeur"
df["matrice"] = df.apply(classify, axis=1)
# Nombre de réponses par stratégie et par classe.
mat = (df.groupby(["strategy", "matrice"]).size()
         .unstack(fill_value=0)
         .reindex(index=ORDER, columns=["correct", "mineur", "majeur", "invalide"], fill_value=0))
st.dataframe(mat, use_container_width=True)

# ── explorateur de réponses ───────────────────────────────────────────────────
st.subheader("Explorateur de réponses")
# Filtres : stratégie, catégorie et difficulté.
col_a, col_b, col_c = st.columns(3)
strat_sel = col_a.selectbox("Stratégie", ORDER)
cat_sel = col_b.selectbox("Catégorie", ["(toutes)"] + sorted(df["category"].unique().tolist()))
diff_sel = col_c.selectbox("Difficulté", ["(toutes)"] + ["easy", "medium", "hard"])

# Application des filtres choisis.
subset = df[df["strategy"] == strat_sel]
if cat_sel != "(toutes)":
    subset = subset[subset["category"] == cat_sel]
if diff_sel != "(toutes)":
    subset = subset[subset["difficulty"] == diff_sel]

if subset.empty:
    st.info("Aucune question pour ces filtres.")
else:
# Liste déroulante des questions filtrées ; on retrouve l'identifiant
# de la question choisie en coupant le libellé au séparateur " — ".
    choices = [f"{r['id']} — {r['question'][:70]}" for _, r in subset.iterrows()]
    choice = st.selectbox("Question", choices)
    qid = choice.split(" — ")[0]
    row = subset[subset["id"] == qid].iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Score", f"{row['overall']:.2f}/3")
    c2.metric("JSON valide", "Oui" if row["valid_format"] else "Non")
    c3.metric("Latence", f"{row['latency_ms']} ms")

# Affiche la réponse en JSON mis en forme si elle se parse, sinon en texte brut.
    text = row["response_text"].strip()
    try:
        data = json.loads(text)
        st.success("Format JSON valide")
        st.json(data)
    except Exception:
        st.warning("Format texte libre (non JSON)")
        st.text_area("Réponse brute", text, height=300)
