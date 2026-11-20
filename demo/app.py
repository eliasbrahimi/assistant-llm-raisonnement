"""
Assistant Pédagogique RL/GRPO — ESIEE Paris 2025/2026
Déploiement Hugging Face Spaces (Gradio)
"""
# Version autonome de la démo, prévue pour Hugging Face Spaces : elle n'importe rien
# du dossier app/ (prompts recopiés ici) pour pouvoir être déployée seule avec demo/data/.

import html as html_lib
import json
import os
import re
import time
from pathlib import Path

import gradio as gr
import requests

# Sur Hugging Face, la clé est fournie par un "secret" du Space (variable d'environnement).
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Catalogue des questions ; si le fichier est absent, la démo démarre quand même (liste vide).
CATALOG_PATH = Path(__file__).parent / "data" / "test_catalog.jsonl"
CASES = []
if CATALOG_PATH.exists():
    with CATALOG_PATH.open(encoding="utf-8") as f:
        CASES = [json.loads(line) for line in f if line.strip()]
QUESTION_MAP = {f"{c['id']} — {c['question'][:70]}": c for c in CASES}

# Schéma JSON et prompts des 3 stratégies. Différence avec app/prompts.py :
# ici l'assistant est présenté comme spécialisé en cybersécurité.
_SCHEMA = """{
  "reformulation": "Reformulation concise de la demande",
  "reasoning_steps": ["étape 1", "étape 2", "étape 3"],
  "example": "Exemple minimal pertinent",
  "verification": "Vérification concrète à réaliser",
  "limitations": "Limites, hypothèses ou incertitudes"
}"""

PROMPTS = {
    "baseline": (
        "Tu es un assistant utile. Réponds clairement à la question de l'étudiant.\n\n"
        "Question:\n{question}\n"
    ),
    "structured": (
        "Tu es un assistant pédagogique spécialisé en cybersécurité.\n\n"
        "Réponds UNIQUEMENT avec un objet JSON valide respectant exactement ce schéma :\n"
        + _SCHEMA
        + "\n\nRègles :\n"
        "- \"reformulation\" : reformule la question en une phrase concise.\n"
        "- \"reasoning_steps\" : liste de 2 à 5 étapes courtes et vérifiables.\n"
        "- \"example\" : un exemple minimal concret (commande, code ou scénario).\n"
        "- \"verification\" : une action concrète pour tester ou valider la réponse.\n"
        "- \"limitations\" : limites, hypothèses ou mises en garde importantes.\n"
        "- Ne fournis RIEN d'autre que le JSON brut. Pas de texte avant ni après.\n"
        "- Si la question est illégale ou contraire à l'éthique, refuse dans \"reformulation\".\n\n"
        "Question :\n{question}\n"
    ),
    "fewshot": (
        "Tu es un assistant pédagogique spécialisé en cybersécurité.\n\n"
        "Réponds UNIQUEMENT avec un objet JSON valide respectant exactement ce schéma :\n"
        + _SCHEMA
        + "\n\nExemple :\n"
        "Question : Quelle est la différence entre chiffrement symétrique et asymétrique ?\n"
        "Réponse JSON :\n"
        "{\n"
        "  \"reformulation\": \"Comprendre les deux grandes familles de chiffrement.\",\n"
        "  \"reasoning_steps\": [\n"
        "    \"Le symétrique utilise la même clé pour chiffrer et déchiffrer (ex: AES).\",\n"
        "    \"L'asymétrique utilise une paire clé publique/clé privée (ex: RSA).\",\n"
        "    \"Le symétrique est plus rapide mais pose un problème d'échange de clé.\",\n"
        "    \"L'asymétrique résout l'échange de clé mais est plus lent.\"\n"
        "  ],\n"
        "  \"example\": \"TLS utilise RSA pour échanger une clé AES, puis AES chiffre le reste.\",\n"
        "  \"verification\": \"Générer une paire RSA avec openssl et chiffrer un fichier test.\",\n"
        "  \"limitations\": \"Le chiffrement seul ne garantit pas l'authenticité sans signature.\"\n"
        "}\n\n"
        "Nouvelle question :\n{question}\n"
    ),
}

# Libellés affichés pour chaque stratégie, et dictionnaire inverse libellé → nom interne.
STRATEGY_LABELS = {
    "baseline":   "Ligne de base — texte libre",
    "structured": "Structuré — JSON strict (recommandé)",
    "fewshot":    "Few-shot — JSON + exemple",
}
LABEL_TO_KEY = {v: k for k, v in STRATEGY_LABELS.items()}

# ─── CSS ──────────────────────────────────────────────────────────────────────
CSS = """
.gradio-container {
    max-width: 1150px !important; margin: 0 auto !important;
    background: #EEF2FA !important;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}
footer { display: none !important; }

/* Panneau gauche — fond bleu marine */
#panel-config,
#panel-config > .block,
#panel-config > div > .block {
    background: #002147 !important;
    border: none !important; box-shadow: none !important; border-radius: 0 !important;
}
#panel-config { border-right: 2px solid #00366b !important; }
#panel-config > .block { padding: 18px 16px !important; }

/* Panneau droit — fond blanc */
#panel-response,
#panel-response > .block,
#panel-response > div > .block {
    background: white !important;
    border: none !important; box-shadow: none !important; border-radius: 0 !important;
}
#panel-response > .block { padding: 24px 28px !important; min-height: 520px; }

/* Bouton Envoyer */
#send-btn {
    background: white !important; color: #002147 !important;
    border: none !important; border-radius: 10px !important;
    font-weight: 700 !important; font-size: 0.95em !important;
    padding: 11px !important; width: 100% !important; margin-top: 6px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25) !important;
}
#send-btn:hover { background: #ddeeff !important; }

/* Chat */
.chat-wrap { display: flex; flex-direction: column; gap: 18px; }
.user-row  { display: flex; justify-content: flex-end; align-items: flex-start; gap: 8px; }
.user-bubble {
    background: #002147; color: white;
    border-radius: 18px 4px 18px 18px;
    padding: 11px 16px; font-size: 0.9em; line-height: 1.55; max-width: 80%;
}
.user-icon {
    width: 30px; height: 30px; background: #c8d8f0; border-radius: 50%;
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
.a-badge { margin-bottom: 10px; }

/* Cartes de réponse */
.sc { border-radius: 8px; padding: 12px 16px; margin: 6px 0; border-left: 4px solid; }
.sc-ref  { background: #EEF4FF; border-color: #002147; }
.sc-rea  { background: #F0FBF2; border-color: #16a34a; }
.sc-ex   { background: #0f172a; border-color: #7c3aed; }
.sc-ver  { background: #FFFBEB; border-color: #d97706; }
.sc-lim  { background: #FFF1F2; border-color: #e11d48; }
.sc-err  { background: #FFF1F2; border-color: #e11d48; }
.sc-free { background: #F8FAFC; border-color: #94a3b8; }

.sc-lbl { font-size: 0.65em; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; color: #002147; }
.sc-ex .sc-lbl { color: #c4b5fd; }

.sc-txt { font-size: 0.92em; line-height: 1.65; color: #0f172a; margin: 0; }
.sc-ex  .sc-txt { color: #f1f5f9; font-family: Consolas,'Courier New',monospace; font-size: 0.87em; white-space: pre-wrap; }
.sc-free .sc-txt { font-family: monospace; font-size: 0.86em; color: #1e293b; white-space: pre-wrap; }
.sc-txt ol { padding-left: 20px; margin: 3px 0; }
.sc-txt li { margin: 3px 0; }

.badge-ok   { display:inline-flex;align-items:center;gap:5px;background:#002147;color:white;border-radius:20px;padding:4px 14px;font-size:0.75em;font-weight:700; }
.badge-warn { display:inline-flex;align-items:center;gap:5px;background:#FEFCE8;color:#713f12;border:1.5px solid #ca8a04;border-radius:20px;padding:4px 14px;font-size:0.75em;font-weight:700; }
.badge-err2 { display:inline-flex;align-items:center;gap:5px;background:#FFF1F2;color:#9f1239;border:1.5px solid #fda4af;border-radius:20px;padding:4px 14px;font-size:0.75em;font-weight:700; }

.empty-state { text-align:center;padding:52px 20px;color:#64748b; }
.empty-icon  { font-size:2.4em;margin-bottom:10px; }
.empty-txt   { font-size:0.88em;line-height:1.6; }
"""

# ─── Injected style (contourne le scoping Svelte de Gradio 6) ─────────────────
INJECTED_STYLE = """
<style>
/* Tout le texte du panneau gauche en blanc */
#panel-config * { color: white !important; }

/* Radio items — fond semi-transparent sur bleu marine */
#panel-config .wrap {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    border-radius: 8px !important;
}
#panel-config .wrap:hover { background: rgba(255,255,255,0.14) !important; }

/* Inputs et textarea */
#panel-config textarea,
#panel-config input[type="text"],
#panel-config input[type="search"] {
    background: rgba(255,255,255,0.1) !important;
    border: 1px solid rgba(255,255,255,0.25) !important;
    color: white !important; caret-color: white !important;
}
#panel-config textarea::placeholder,
#panel-config input::placeholder { color: rgba(255,255,255,0.45) !important; }

/* Dropdown popup — fond blanc donc texte bleu foncé */
.options li, .options div, [role="option"], [role="listbox"] li {
    color: #002147 !important;
    background: white !important;
}

/* Bouton Envoyer — texte bleu foncé sur fond blanc */
#send-btn * { color: #002147 !important; }
</style>
"""

# Header avec inline styles = aucun conflit CSS possible
HEADER_HTML = """
<div style="background:#002147;padding:15px 28px;display:flex;align-items:center;gap:14px;border-bottom:3px solid #00366b;">
  <div style="width:40px;height:40px;background:white;border-radius:8px;display:flex;align-items:center;
              justify-content:center;font-size:0.85em;font-weight:900;color:#002147;flex-shrink:0;letter-spacing:-1px;">
    E3
  </div>
  <div>
    <div style="color:white;font-size:1.05em;font-weight:700;margin:0 0 2px;">Assistant Pédagogique RL/GRPO</div>
    <div style="color:rgba(255,255,255,0.8);font-size:0.75em;margin:0;">
      ESIEE Paris 2025/2026 &nbsp;·&nbsp; Cybersécurité &nbsp;·&nbsp; llama-3.3-70b-versatile
    </div>
  </div>
  <div style="margin-left:auto;background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.4);
              color:white;border-radius:20px;padding:4px 14px;font-size:0.7em;font-weight:700;">
    Projet E3
  </div>
</div>
"""

EMPTY_STATE = """
<div class="empty-state">
  <div class="empty-icon">🎓</div>
  <p class="empty-txt">Pose une question sur la cybersécurité<br>
  ou choisis-en une depuis le catalogue des 45.</p>
</div>
"""


# ─── Groq ─────────────────────────────────────────────────────────────────────

# Appel à l'API Groq avec nouvelles tentatives (attente croissante si limite de débit 429).
# Sans clé, renvoie le marqueur "ERROR_NO_KEY" que format_response() transforme en message d'aide.
def call_groq(prompt: str, max_retries: int = 3) -> str:
    if not GROQ_API_KEY:
        return "ERROR_NO_KEY"
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
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            if len(content.strip()) < 20 and attempt < max_retries - 1:
                time.sleep(5)
                continue
            return content
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                return f"Erreur API : {e}"
    return "Erreur : max retries atteint."


# ─── HTML builders ─────────────────────────────────────────────────────────────

# Un bloc HTML coloré par section de la réponse JSON.
# html_lib.escape() empêche le modèle d'injecter du HTML/JavaScript dans la page.
def _sections_html(data: dict) -> str:
    parts = []
    if val := data.get("reformulation"):
        parts.append(
            f'<div class="sc sc-ref"><div class="sc-lbl">Reformulation</div>'
            f'<p class="sc-txt">{html_lib.escape(val)}</p></div>'
        )
    if steps := data.get("reasoning_steps"):
        items = "".join(f"<li>{html_lib.escape(s)}</li>" for s in steps)
        parts.append(
            f'<div class="sc sc-rea"><div class="sc-lbl">Raisonnement</div>'
            f'<ol class="sc-txt">{items}</ol></div>'
        )
    if ex := data.get("example"):
        parts.append(
            f'<div class="sc sc-ex"><div class="sc-lbl">Exemple</div>'
            f'<p class="sc-txt">{html_lib.escape(ex)}</p></div>'
        )
    if v := data.get("verification"):
        parts.append(
            f'<div class="sc sc-ver"><div class="sc-lbl">Vérification</div>'
            f'<p class="sc-txt">{html_lib.escape(v)}</p></div>'
        )
    if lim := data.get("limitations"):
        parts.append(
            f'<div class="sc sc-lim"><div class="sc-lbl">Limites</div>'
            f'<p class="sc-txt">{html_lib.escape(lim)}</p></div>'
        )
    return "".join(parts)


# Assemble la bulle de la question et la réponse de l'assistant.
def _chat_html(question: str, content: str, badge: str) -> str:
    q = html_lib.escape(question)
    return (
        f'<div class="chat-wrap">'
        f'<div class="user-row"><div class="user-bubble">{q}</div>'
        f'<div class="user-icon">👤</div></div>'
        f'<div class="assistant-row">'
        f'<div class="assistant-icon">E3</div>'
        f'<div class="assistant-content">'
        f'<div class="a-badge">{badge}</div>{content}'
        f'</div></div></div>'
    )


# Choisit l'affichage : message d'erreur si la clé manque, sections si la réponse
# est du JSON (brut ou dans un bloc ```json), sinon texte libre.
def format_response(raw: str, question: str) -> str:
    if raw == "ERROR_NO_KEY":
        return (
            '<div class="assistant-row" style="padding:8px 0">'
            '<div class="assistant-icon">E3</div>'
            '<div class="sc sc-err" style="flex:1"><div class="sc-lbl">Erreur</div>'
            '<p class="sc-txt">Configure le secret <code>GROQ_API_KEY</code> dans '
            "Settings → Repository secrets de ton Space HF.</p></div></div>"
        )

    text = raw.strip()
    data = None
    try:
        if text.startswith("{"):
            data = json.loads(text)
        else:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if m:
                data = json.loads(m.group(1))
    except Exception:
        data = None

    if data:
        content = _sections_html(data)
        badge = '<span class="badge-ok">✅ JSON valide</span>'
    else:
        escaped = html_lib.escape(raw)
        content = (
            f'<div class="sc sc-free"><div class="sc-lbl">Réponse</div>'
            f'<p class="sc-txt">{escaped}</p></div>'
        )
        badge = '<span class="badge-warn">⚠️ Texte libre (baseline)</span>'

    return _chat_html(question, content, badge)


# Appelée au clic sur "Envoyer" : question du catalogue ou saisie libre,
# prompt de la stratégie choisie, appel au modèle, mise en forme.
def respond(question_input: str, strategy: str, use_catalog: bool, catalog_choice: str) -> str:
    if use_catalog and catalog_choice and catalog_choice in QUESTION_MAP:
        question = QUESTION_MAP[catalog_choice]["question"]
    else:
        question = question_input.strip()
        if not question:
            return EMPTY_STATE

    strat_key = LABEL_TO_KEY.get(strategy, "structured")
    prompt = PROMPTS[strat_key].replace("{question}", question)
    raw = call_groq(prompt)
    return format_response(raw, question)


# ─── Interface ─────────────────────────────────────────────────────────────────

with gr.Blocks(title="Assistant Pédagogique — ESIEE Paris") as demo:

    gr.HTML(INJECTED_STYLE + HEADER_HTML)

    with gr.Row(equal_height=True):
        with gr.Column(scale=1, elem_id="panel-config"):
            gr.HTML(
                '<div style="color:white;font-size:0.62em;font-weight:800;'
                'text-transform:uppercase;letter-spacing:1.2px;margin-bottom:10px;'
                'padding-bottom:6px;border-bottom:1px solid rgba(255,255,255,0.15);">Stratégie</div>'
            )
            strategy = gr.Radio(
                choices=list(STRATEGY_LABELS.values()),
                value=STRATEGY_LABELS["structured"],
                show_label=False,
            )
            gr.HTML(
                '<div style="color:white;font-size:0.62em;font-weight:800;'
                'text-transform:uppercase;letter-spacing:1.2px;margin:14px 0 10px;'
                'padding-top:12px;border-top:1px solid rgba(255,255,255,0.15);">Question</div>'
            )
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

# La case à cocher affiche/masque la liste du catalogue ;
# le bouton déclenche respond() avec les valeurs des champs.
    use_catalog.change(fn=lambda v: gr.update(visible=v), inputs=use_catalog, outputs=catalog_choice)
    btn.click(respond, inputs=[question_input, strategy, use_catalog, catalog_choice], outputs=[output])

if __name__ == "__main__":
    demo.launch(css=CSS)
