# Démo web Gradio : l'utilisateur pose une question (ou en choisit une
# dans le catalogue), choisit une stratégie de prompt, et voit la réponse du LLM
# (Llama 3.3 70B via Groq) mise en forme par sections.
# Lancement : make gradio

from __future__ import annotations

import html as html_lib
import json
import os
import re
import sys
import time
from pathlib import Path

import gradio as gr
import requests

# Ajoute la racine du dépôt au chemin Python pour pouvoir importer "app.prompts"
# même si le script est lancé depuis un autre dossier.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Chargement des 45 questions du catalogue (une question JSON par ligne).
# QUESTION_MAP associe le libellé affiché dans la liste déroulante à la question complète.
CATALOG = ROOT / "data" / "eval" / "test_catalog.jsonl"
with CATALOG.open("r", encoding="utf-8") as f:
    CASES = [json.loads(line) for line in f if line.strip()]
QUESTION_MAP = {f"{c['id']} — {c['question'][:70]}": c for c in CASES}

from app.prompts import PROMPTS


# Récupère la clé API Groq : d'abord dans la variable d'environnement,
# sinon dans un fichier (ou un dossier contenant un fichier) nommé .groq_key.
# Renvoie une chaîne vide si aucune clé n'est trouvée.
def _load_groq_key(root: Path) -> str:
    key = os.environ.get("GROQ_API_KEY", "")
    if key:
        return key
    p = root / ".groq_key"
    if p.is_file():
        return p.read_text(encoding="utf-8").strip()
    if p.is_dir():
        for f in sorted(p.iterdir()):
            if f.is_file():
                return f.read_text(encoding="utf-8").strip()
    return ""


# On cherche .groq_key dans le dossier parent du dépôt, pour qu'il ne soit jamais commité.
GROQ_API_KEY = _load_groq_key(ROOT.parent)

# Libellés affichés pour chaque stratégie, et dictionnaire inverse libellé → nom interne.
STRATEGY_LABELS = {
    "baseline":   "Ligne de base — texte libre",
    "structured": "Structuré — JSON strict (recommandé)",
    "fewshot":    "Few-shot — JSON + exemple",
}
LABEL_TO_KEY = {v: k for k, v in STRATEGY_LABELS.items()}

# Feuille de style de l'interface (en-tête, panneau de gauche bleu marine,
# bulles de discussion, une couleur par section de réponse).
CSS = """
.gradio-container {
    max-width: 1200px !important; margin: 0 auto !important;
    background: #EDF0F7 !important;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    padding: 0 !important;
}
footer { display: none !important; }

#app-header {
    background: #002147;
    padding: 15px 28px;
    display: flex; align-items: center; gap: 14px;
    border-bottom: 3px solid #003580;
}
#app-logo {
    width: 38px; height: 38px;
    background: white; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.85em; font-weight: 900; color: #002147;
    flex-shrink: 0; letter-spacing: -1px;
}
#app-header h2 { color: white !important; margin: 0 0 2px; font-size: 1.05em; font-weight: 700; }
#app-header p  { color: rgba(255,255,255,0.85) !important; margin: 0; font-size: 0.75em; }
.hdr-pill {
    margin-left: auto;
    background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.4);
    color: white; border-radius: 20px;
    padding: 3px 12px; font-size: 0.7em; font-weight: 600;
}

#panel-config,
#panel-config > .block,
#panel-config > div > .block {
    background: #002147 !important;
    border: none !important; box-shadow: none !important; border-radius: 0 !important;
    overflow: visible !important;
}
#panel-config { border-right: 2px solid #003580 !important; }
#panel-config > .block { padding: 20px 16px !important; }

#panel-config textarea, #panel-config input[type="text"], #panel-config input[type="search"] {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.2) !important;
    color: white !important; border-radius: 8px !important;
    caret-color: white !important;
}
#panel-config textarea::placeholder, #panel-config input::placeholder {
    color: rgba(255,255,255,0.35) !important;
}
#panel-config .wrap {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 8px !important; padding: 8px 10px !important; margin-bottom: 4px !important;
}
.sep { border: none; border-top: 1px solid rgba(255,255,255,0.2); margin: 14px 0 10px; }
.panel-title {
    color: rgba(255,255,255,0.85) !important;
    font-size: 0.62em !important; font-weight: 700 !important;
    text-transform: uppercase !important; letter-spacing: 1px !important;
    margin: 0 0 8px !important;
}

#send-btn {
    background: white !important; color: #002147 !important;
    border: none !important; border-radius: 10px !important;
    font-weight: 700 !important; font-size: 0.9em !important;
    padding: 11px !important; width: 100% !important; margin-top: 8px !important;
    box-shadow: 0 2px 10px rgba(0,0,0,0.3) !important;
}
#send-btn:hover { background: #D4E2F7 !important; }

#panel-response,
#panel-response > .block,
#panel-response > div > .block {
    background: white !important;
    border: none !important; box-shadow: none !important; border-radius: 0 !important;
}
#panel-response > .block { padding: 24px 28px !important; min-height: 500px; }

.chat-wrap { display: flex; flex-direction: column; gap: 20px; }
.user-row { display: flex; justify-content: flex-end; align-items: flex-start; gap: 8px; }
.user-bubble {
    background: #002147; color: white;
    border-radius: 18px 4px 18px 18px;
    padding: 11px 16px; font-size: 0.9em; line-height: 1.55;
    max-width: 80%; box-shadow: 0 2px 8px rgba(0,33,71,0.25);
}
.user-icon {
    width: 30px; height: 30px; background: #DDE6F4; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.85em; flex-shrink: 0; margin-top: 2px;
}
.assistant-row { display: flex; align-items: flex-start; gap: 10px; }
.assistant-icon {
    width: 32px; height: 32px; background: #002147; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.65em; font-weight: 900; color: white;
    flex-shrink: 0; margin-top: 2px;
}
.assistant-content { flex: 1; min-width: 0; }
.a-badge { margin-bottom: 8px; }

.sc { border-radius: 8px; padding: 11px 15px; margin: 5px 0; border-left: 3px solid transparent; }
.sc-ref  { background: #EEF3FF; border-left-color: #002147; }
.sc-rea  { background: #F0FBF2; border-left-color: #15803d; }
.sc-ex   { background: #111827; border-left-color: #7c3aed; }
.sc-ver  { background: #FFF8ED; border-left-color: #D97706; }
.sc-lim  { background: #FFF1F2; border-left-color: #E11D48; }
.sc-err  { background: #FFF1F2; border-left-color: #E11D48; }
.sc-free { background: #F8FAFC; border-left-color: #94A3B8; }
.sc-lbl { font-size: 0.65em; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; color: #002147 !important; }
.sc-ex .sc-lbl { color: #d8b4fe !important; }
.sc-txt { font-size: 0.92em; line-height: 1.65; color: #0f172a !important; margin: 0; }
.sc-txt * { color: #0f172a !important; }
.sc-ex .sc-txt, .sc-ex .sc-txt * { color: #ffffff !important; font-family: Consolas,'Courier New',monospace; font-size: 0.87em; white-space: pre-wrap; }
.sc-free .sc-txt, .sc-free .sc-txt * { font-family: monospace; font-size: 0.86em; white-space: pre-wrap; color: #1e293b !important; }
.sc-txt ol { padding-left: 20px; margin: 3px 0; }
.sc-txt li { margin: 3px 0; }

.badge-ok   { display:inline-flex;align-items:center;gap:5px;background:#002147;color:white;border-radius:20px;padding:3px 14px;font-size:0.74em;font-weight:700; }
.badge-warn { display:inline-flex;align-items:center;gap:5px;background:#FFFBEB;color:#78350F;border:1.5px solid #FCD34D;border-radius:20px;padding:3px 14px;font-size:0.74em;font-weight:700; }

.empty-state { text-align:center;padding:52px 20px;color:#94A3B8; }
.empty-icon  { font-size:2.4em;margin-bottom:10px; }
.empty-txt   { font-size:0.88em;line-height:1.6; }
"""

# CSS injecté directement dans la page pour forcer les couleurs
# que le thème Gradio écrase sinon (texte blanc du panneau, menus déroulants lisibles).
INJECTED = """<style>
#app-header h2, #app-header p, .hdr-pill { color: white !important; }
#app-logo { background: white !important; color: #002147 !important; }
#app-logo * { color: #002147 !important; }

/* Couleur du texte : tout blanc dans le panneau */
#panel-config * { color: white !important; }

/* Fond : tout transparent par défaut (hérite du bleu marine du panneau) */
#panel-config * { background-color: transparent !important; }

/* Re-appliquer les fonds spécifiques */
#panel-config .wrap { background-color: rgba(255,255,255,0.07) !important; border-color: rgba(255,255,255,0.15) !important; }
#panel-config .wrap:hover { background-color: rgba(255,255,255,0.13) !important; }

/* Checkbox cochée : visible avec accent bleu clair */
#panel-config input[type="checkbox"] {
    accent-color: #60a5fa !important;
    outline: 1.5px solid rgba(255,255,255,0.5) !important;
    outline-offset: 2px !important;
}

#panel-config textarea,
#panel-config input[type="text"],
#panel-config input[type="search"] {
    background-color: rgba(255,255,255,0.09) !important;
    border: 1px solid rgba(255,255,255,0.22) !important;
    color: white !important; caret-color: white !important;
}
#panel-config textarea::placeholder,
#panel-config input::placeholder { color: rgba(255,255,255,0.38) !important; }

#send-btn { background-color: white !important; }
#send-btn, #send-btn * { color: #002147 !important; }

.options {
    z-index: 99999 !important;
    position: fixed !important;
    background: white !important;
    border: 1px solid #CBD5E1 !important;
    border-radius: 8px !important;
    box-shadow: 0 8px 24px rgba(0,0,0,0.18) !important;
    overflow-y: auto !important;
    max-height: 320px !important;
    pointer-events: auto !important;
}
.options *, [role="option"], [role="listbox"] * {
    color: #002147 !important;
    background: white !important;
    pointer-events: auto !important;
}
[role="option"]:hover, .options li:hover {
    background: #EEF3FF !important;
    color: #002147 !important;
}
</style>"""

# Bandeau du haut et message affiché avant la première question.
HEADER = """<div id="app-header">
  <div id="app-logo">E3</div>
  <div>
    <h2 style="color:white!important;margin:0 0 2px;font-size:1.05em;font-weight:700;">Assistant Pédagogique RL/GRPO</h2>
    <p style="color:rgba(255,255,255,0.85)!important;margin:0;font-size:0.75em;">ESIEE Paris 2025/2026 &nbsp;·&nbsp; Cybersécurité &nbsp;·&nbsp; llama-3.3-70b-versatile</p>
  </div>
  <span class="hdr-pill" style="color:white!important;">Projet E3</span>
</div>"""

EMPTY_STATE = """<div class="empty-state">
  <div class="empty-icon">🎓</div>
  <p class="empty-txt">Pose une question sur la cybersécurité<br>ou choisis-en une depuis le catalogue des 45.</p>
</div>"""


# Envoie le prompt à l'API Groq et renvoie le texte de la réponse.
# Même logique de nouvelles tentatives que GroqModelClient (model_clients.py),
# mais en cas d'échec définitif on renvoie un message d'erreur au lieu de planter l'interface.
def call_groq(prompt: str, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                         "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile",
                      "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.3},
                timeout=30,
            )
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1)); continue
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            if len(content.strip()) < 20 and attempt < max_retries - 1:
                time.sleep(5); continue
            return content
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                return f"Erreur API : {e}"
    return "Erreur : max retries atteint."


# Transforme une réponse JSON en blocs HTML colorés, un par section.
# html_lib.escape() neutralise les balises éventuelles dans la réponse du modèle
# (protection contre l'injection de HTML/JavaScript dans la page).
def _sections_html(data: dict) -> str:
    parts = []
    if v := data.get("reformulation"):
        parts.append(f'<div class="sc sc-ref"><div class="sc-lbl">Reformulation</div><p class="sc-txt">{html_lib.escape(v)}</p></div>')
    if steps := data.get("reasoning_steps"):
        items = "".join(f"<li>{html_lib.escape(s)}</li>" for s in steps)
        parts.append(f'<div class="sc sc-rea"><div class="sc-lbl">Raisonnement</div><ol class="sc-txt">{items}</ol></div>')
    if v := data.get("example"):
        parts.append(f'<div class="sc sc-ex"><div class="sc-lbl">Exemple</div><p class="sc-txt">{html_lib.escape(v)}</p></div>')
    if v := data.get("verification"):
        parts.append(f'<div class="sc sc-ver"><div class="sc-lbl">Vérification</div><p class="sc-txt">{html_lib.escape(v)}</p></div>')
    if v := data.get("limitations"):
        parts.append(f'<div class="sc sc-lim"><div class="sc-lbl">Limites</div><p class="sc-txt">{html_lib.escape(v)}</p></div>')
    return "".join(parts)


# Construit l'affichage final : bulle de la question puis réponse.
# On tente de lire la réponse comme du JSON (brut ou dans un bloc ```json) ;
# si ça échoue, elle est affichée en texte libre avec un badge d'avertissement.
def format_response(raw: str, question: str) -> str:
    text = raw.strip()
    data = None
    try:
        data = json.loads(text) if text.startswith("{") else None
        if data is None:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if m:
                data = json.loads(m.group(1))
    except Exception:
        data = None

    q = html_lib.escape(question)
    if data:
        content = _sections_html(data)
        badge = '<span class="badge-ok">✅ JSON valide</span>'
    else:
        content = f'<div class="sc sc-free"><div class="sc-lbl">Réponse</div><p class="sc-txt">{html_lib.escape(raw)}</p></div>'
        badge = '<span class="badge-warn">⚠️ Texte libre (baseline)</span>'

    return (
        f'<div class="chat-wrap">'
        f'<div class="user-row"><div class="user-bubble">{q}</div><div class="user-icon">👤</div></div>'
        f'<div class="assistant-row"><div class="assistant-icon">E3</div>'
        f'<div class="assistant-content"><div class="a-badge">{badge}</div>{content}</div>'
        f'</div></div>'
    )


# Fonction appelée au clic sur "Envoyer" : choisit la question (catalogue ou saisie),
# remplit le prompt de la stratégie choisie, appelle le modèle et met en forme la réponse.
def respond(question_input: str, strategy: str, use_catalog: bool, catalog_choice: str) -> str:
    if not GROQ_API_KEY:
        return '<div class="sc sc-err"><div class="sc-lbl">Erreur</div><p class="sc-txt">Clé GROQ_API_KEY manquante.</p></div>'
    question = QUESTION_MAP[catalog_choice]["question"] if (use_catalog and catalog_choice and catalog_choice in QUESTION_MAP) else question_input.strip()
    if not question:
        return EMPTY_STATE
    strat_key = LABEL_TO_KEY.get(strategy, "structured")
    return format_response(call_groq(PROMPTS[strat_key].replace("{question}", question)), question)


# Construction de l'interface : colonne de gauche (réglages), colonne de droite (réponse).
with gr.Blocks(title="Assistant Pédagogique — ESIEE Paris") as demo:

    gr.HTML(INJECTED + HEADER)

    with gr.Row(equal_height=True):
        with gr.Column(scale=1, elem_id="panel-config"):
            gr.HTML('<p class="panel-title">Stratégie</p>')
            strategy = gr.Radio(
                choices=list(STRATEGY_LABELS.values()),
                value=STRATEGY_LABELS["structured"],
                show_label=False,
            )
            gr.HTML('<hr class="sep"><p class="panel-title">Question</p>')
            use_catalog = gr.Checkbox(label="Catalogue des 45 questions", value=False)
            catalog_choice = gr.Dropdown(
                choices=list(QUESTION_MAP.keys()),
                label="Sélectionner une question",
                visible=False,
                interactive=True,
            )
            question_input = gr.Textbox(
                placeholder="Comment fonctionne une attaque par injection SQL ?",
                lines=4,
                show_label=False,
            )
            btn = gr.Button("Envoyer 🚀", variant="primary", elem_id="send-btn")

        with gr.Column(scale=2, elem_id="panel-response"):
            output = gr.HTML(value=EMPTY_STATE)

# Événements : la case à cocher affiche/masque la liste du catalogue,
# et le bouton déclenche respond() avec les valeurs des champs.
    use_catalog.change(fn=lambda v: gr.update(visible=v), inputs=use_catalog, outputs=catalog_choice)
    btn.click(respond, inputs=[question_input, strategy, use_catalog, catalog_choice], outputs=[output])

# Démarre le serveur web local (par défaut http://127.0.0.1:7860).
if __name__ == "__main__":
    demo.launch(css=CSS, theme=gr.themes.Base())
