# Faux modèle ("toy target") entièrement déterministe : il fabrique des réponses
# à partir de règles fixes, sans IA. Il permet de tester toute la chaîne d'évaluation
# (prompts, validation, scoring, export) sans clé API et avec des résultats reproductibles.

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List


# Contenu d'une réponse préfabriquée : explication courte, notions clés,
# exemple (souvent du code) et limite/piège à signaler.
# frozen=True rend l'objet non modifiable après création.
@dataclass(frozen=True)
class InferredAnswer:
    short: str
    concepts: List[str]
    example: str
    limit: str


# Entoure du code Python d'un bloc Markdown ```python ... ```.
def _code_block(source: str) -> str:
    return f"```python\n{source.strip()}\n```"


# Réponse générique utilisée quand aucune règle ne correspond à la question.
def _fallback(question: str, category: str, requires_code: bool) -> InferredAnswer:
    example = "Exemple minimal : tester un cas simple, puis un cas limite."
    if requires_code:
        example = _code_block(
            """
def verifier():
    return "résultat observable"

print(verifier())
            """
        )
    return InferredAnswer(
        short=(
            f"La question relève de la catégorie {category}. "
            "Il faut identifier la règle, l'appliquer sur un cas simple, puis vérifier."
        ),
        concepts=["règle", "exemple", "vérification"],
        example=example,
        limit="Si l'énoncé est incomplet, il faut signaler l'ambiguïté avant de conclure.",
    )


def _infer_answer(question: str, category: str, requires_code: bool) -> InferredAnswer:
    """Infer a toy answer from the question only.

    The deterministic target deliberately does not read `reference_answer` or
    `expected_concepts`; otherwise the smoke benchmark would leak the answer key.
    """
    q = question.lower()

    # Table de règles : chaque entrée associe une condition (mots-clés trouvés
    # dans la question) à une réponse préfabriquée. Les conditions sont évaluées
    # toutes ici, puis la boucle en fin de fonction prend la première vraie :
    # l'ordre de la liste compte donc (ex. "recherche linéaire" passe avant
    # "complexité de la recherche linéaire", qui ne sera jamais atteinte).

    cases: list[tuple[bool, InferredAnswer]] = [
        (
            "print()" in q and "return" in q,
            InferredAnswer(
                "print() fait un affichage ; return produit une valeur de retour que le programme peut réutiliser.",
                ["affichage", "valeur de retour", "réutilisation"],
                _code_block(
                    """
def addition(a, b):
    return a + b

resultat = addition(2, 3)
print(resultat)
                    """
                ),
                "Une fonction qui affiche seulement ne fournit pas forcément une valeur exploitable au code appelant.",
            ),
        ),
        (
            "x = x + 1" in q,
            InferredAnswer(
                "Python calcule d'abord l'expression droite, puis réalise une affectation dans la variable.",
                ["affectation", "expression droite", "mise à jour"],
                "`x = 4` puis `x = x + 1` donne `x = 5`.",
                "La variable doit déjà avoir une valeur compatible avec l'opération.",
            ),
        ),
        (
            '"3" + 4' in q or "'3' + 4" in q,
            InferredAnswer(
                "Une chaîne et un entier sont des types incompatibles pour l'addition directe ; il faut une conversion explicite.",
                ["chaîne", "entier", "conversion"],
                _code_block('resultat = int("3") + 4\nprint(resultat)'),
                "Ne pas convertir au hasard : choisir `int`, `str` ou un autre type selon le sens voulu.",
            ),
        ),
        (
            "liste et un tuple" in q,
            InferredAnswer(
                "Une liste est généralement modifiable, tandis qu'un tuple représente une séquence stable ; la différence centrale est la mutabilité.",
                ["liste", "tuple", "mutabilité"],
                "`[1, 2]` peut recevoir `append(3)`, alors que `(1, 2)` ne se modifie pas ainsi.",
                "Un tuple peut contenir un objet mutable ; l'immuabilité concerne surtout la structure du tuple.",
            ),
        ),
        (
            "paramètre" in q and "argument" in q,
            InferredAnswer(
                "Le paramètre appartient à la définition de la fonction ; l'argument est la valeur donnée lors de l'appel.",
                ["définition", "appel", "valeur"],
                _code_block("def saluer(nom):\n    return 'Bonjour ' + nom\n\nsaluer('Ada')"),
                "Dans le langage courant, les deux mots sont parfois confondus ; en code, la distinction aide à lire une erreur.",
            ),
        ),
        (
            "if" in q and "elif" in q and "else" in q,
            InferredAnswer(
                "`if`, `elif` et `else` testent une condition dans un ordre précis, puis couvrent le cas restant.",
                ["condition", "ordre", "cas restant"],
                _code_block("if note >= 10:\n    print('validé')\nelif note >= 8:\n    print('rattrapage')\nelse:\n    print('à retravailler')"),
                "L'ordre des conditions peut changer le résultat si plusieurs conditions se recouvrent.",
            ),
        ),
        (
            "for" in q and "while" in q,
            InferredAnswer(
                "`for` convient pour une itération connue sur une séquence ; `while` convient quand la condition d’arrêt pilote la boucle.",
                ["itération connue", "condition d’arrêt", "séquence"],
                "`for x in nombres:` parcourt une liste ; `while not fini:` attend qu'une condition change.",
                "Un `while` exige une mise à jour claire, sinon il peut ne jamais s'arrêter.",
            ),
        ),
        (
            "range(1, 5)" in q,
            InferredAnswer(
                "`range(1, 5)` commence à la borne incluse 1 et s'arrête avant la borne exclue 5 : 1 2 3 4.",
                ["borne incluse", "borne exclue", "1 2 3 4"],
                _code_block("for x in range(1, 5):\n    print(x)"),
                "La borne de fin est exclue, ce qui évite beaucoup d'erreurs off-by-one.",
            ),
        ),
        (
            "boucle imbriquée" in q or "boucles imbriquées" in q,
            InferredAnswer(
                "Une boucle imbriquée place une boucle interne dans une boucle externe ; la répétition interne se produit à chaque tour externe.",
                ["boucle externe", "boucle interne", "répétition", "boucles imbriquées", "n fois n", "O(n²)"],
                _code_block("for i in range(3):\n    for j in range(2):\n        print(i, j)"),
                "Si deux boucles imbriquées parcourent chacune environ `n` éléments, on surveille souvent un coût en O(n²).",
            ),
        ),
        (
            "while" in q and "infinie" in q,
            InferredAnswer(
                "Une boucle `while` devient infinie si la condition vraie ne change jamais, souvent faute de mettre à jour la variable de contrôle.",
                ["condition vraie", "variable de contrôle", "arrêt"],
                "`while x < 10:` doit modifier `x` dans la boucle pour atteindre l'arrêt.",
                "Tester une limite maximale d'itérations peut aider à détecter le problème pendant le debug.",
            ),
        ),
        (
            "renvoie-t-elle none" in q or "renvoie-t-elle none" in q,
            InferredAnswer(
                "Une fonction renvoie None lorsqu'elle n'a pas de return explicite ou lorsque `return` est utilisé sans valeur.",
                ["None", "return explicite", "valeur par défaut"],
                _code_block("def f():\n    print('ok')\n\nresultat = f()\nprint(resultat)"),
                "Afficher une valeur n'est pas la même chose que la renvoyer.",
            ),
        ),
        (
            "arguments par défaut mutables" in q,
            InferredAnswer(
                "Un argument par défaut mutable est créée une seule fois ; une liste peut donc être partagée entre appels successifs.",
                ["mutable", "créée une seule fois", "appels successifs"],
                _code_block("def ajouter(x, valeurs=None):\n    if valeurs is None:\n        valeurs = []\n    valeurs.append(x)\n    return valeurs"),
                "La correction classique consiste à utiliser `None` puis créer la liste dans la fonction.",
            ),
        ),
        (
            "variable locale" in q,
            InferredAnswer(
                "Une variable locale est définie dans une fonction et sa portée limite son accessibilité à ce contexte.",
                ["fonction", "portée", "accessibilité"],
                "`total` créé dans une fonction n'est pas automatiquement disponible ailleurs.",
                "Il faut distinguer visibilité du nom et durée de vie de l'objet.",
            ),
        ),
        (
            "récursion" in q or "factorielle" in q,
            InferredAnswer(
                "La récursion utilise un appel récursif ; pour la factorielle, il faut un cas de base et le cas `n * factorielle(n-1)`.",
                ["appel récursif", "cas de base", "factorielle"],
                _code_block("def factorielle(n):\n    if n == 0:\n        return 1\n    return n * factorielle(n - 1)"),
                "Sans cas de base, la fonction ne sait pas quand s'arrêter.",
            ),
        ),
        (
            "indentation" in q,
            InferredAnswer(
                "En Python, l'indentation définit un bloc ; une indentation incorrecte change la logique ou déclenche une erreur.",
                ["bloc", "logique", "erreur"],
                "`if ok:` attend un bloc indenté sur la ligne suivante.",
                "L'indentation n'est pas une décoration : elle fait partie de la syntaxe.",
            ),
        ),
        (
            "append()" in q and "extend()" in q,
            InferredAnswer(
                "`append()` ajoute un élément ; `extend()` ajoute chaque valeur d'un itérable à la liste.",
                ["un élément", "itérable", "liste"],
                _code_block("xs = [1]\nxs.append([2, 3])\nys = [1]\nys.extend([2, 3])\nprint(xs, ys)"),
                "Le piège est que `append([2, 3])` ajoute la liste comme un seul objet.",
            ),
        ),
        (
            "clé de dictionnaire" in q,
            InferredAnswer(
                "Pour une clé potentiellement absente, on utilise souvent `get` avec une valeur par défaut ou un test `in`.",
                ["get", "valeur par défaut", "in"],
                _code_block("age = utilisateur.get('age', 0)\nif 'nom' in utilisateur:\n    print(utilisateur['nom'])"),
                "Accéder directement à une clé absente déclenche une erreur.",
            ),
        ),
        (
            "set plutôt qu’une liste" in q or "set plutôt qu'une liste" in q,
            InferredAnswer(
                "Un set impose l'unicité, supprime les doublons et rend souvent le test d'appartenance plus direct.",
                ["unicité", "doublons", "appartenance"],
                "`set([1, 1, 2])` donne `{1, 2}`.",
                "Un set ne conserve pas l'ordre comme une liste ordinaire.",
            ),
        ),
        (
            "compréhension de liste" in q,
            InferredAnswer(
                "Une compréhension de liste combine une expression, un `for` et produit une liste produite en une ligne lisible.",
                ["expression", "for", "liste produite"],
                _code_block("carrés = [x * x for x in nombres]"),
                "Elle doit rester lisible ; une boucle classique est préférable si la logique devient longue.",
            ),
        ),
        (
            "sort()" in q and "sorted()" in q,
            InferredAnswer(
                "`sort()` trie en place et renvoie None ; `sorted()` crée une nouvelle liste triée.",
                ["en place", "nouvelle liste", "None"],
                _code_block("xs = [3, 1, 2]\nys = sorted(xs)\nxs.sort()\nprint(xs, ys)"),
                "Le piège courant est d'écrire `xs = xs.sort()`, ce qui met `xs` à None.",
            ),
        ),
        (
            "off-by-one" in q,
            InferredAnswer(
                "Pour une erreur off-by-one, vérifier les bornes, le premier élément et le dernier élément.",
                ["bornes", "premier élément", "dernier élément"],
                "Comparer le nombre d'itérations attendu avec les valeurs réellement visitées.",
                "Les bornes de `range` excluent la fin ; c'est souvent la cause.",
            ),
        ),
        (
            "indexerror" in q,
            InferredAnswer(
                "IndexError apparaît quand un indice dépasse la longueur disponible, donc hors borne.",
                ["indice", "longueur", "borne"],
                _code_block("xs = [10, 20, 30]\nprint(xs[2])  # ok\n# xs[3] serait hors limite"),
                "Le dernier indice d'une liste de longueur 3 est 2, pas 3.",
            ),
        ),
        (
            "typeerror" in q,
            InferredAnswer(
                "TypeError signale une opération avec un type incompatible ; l'exemple typique est chaîne plus entier.",
                ["type incompatible", "opération", "exemple"],
                _code_block('print("3" + str(4))'),
                "La correction dépend du sens voulu : concaténer du texte ou calculer un nombre.",
            ),
        ),
        (
            "affiche-t-il none" in q,
            InferredAnswer(
                "Le code affiche souvent None parce qu'il utilise print dans la fonction mais oublie return.",
                ["print", "return", "None"],
                _code_block("def double(x):\n    print(2 * x)\n\nresultat = double(3)\nprint(resultat)"),
                "Pour réutiliser le résultat, la fonction doit le renvoyer.",
            ),
        ),
        (
            "a = b" in q and "liste" in q,
            InferredAnswer(
                "`a = b` crée une référence vers le même objet ; ce n'est pas une copie indépendante.",
                ["référence", "même objet", "copie"],
                _code_block("b = [1]\na = b\na.append(2)\nprint(b)"),
                "Utiliser `b.copy()` ou `list(b)` si une copie superficielle suffit.",
            ),
        ),
        (
            "maximum" in q,
            InferredAnswer(
                "On fait une initialisation avec le premier élément, puis un parcours et une comparaison à chaque élément.",
                ["initialisation", "parcours", "comparaison"],
                _code_block("maximum = valeurs[0]\nfor x in valeurs:\n    if x > maximum:\n        maximum = x"),
                "La liste vide doit être traitée séparément.",
            ),
        ),
        (
            "occurrences" in q,
            InferredAnswer(
                "On utilise un compteur, on parcourt la liste, puis on teste l'égalité avec la valeur cherchée.",
                ["compteur", "égalité", "parcours"],
                _code_block("compteur = 0\nfor x in valeurs:\n    if x == cible:\n        compteur += 1"),
                "Penser aux cas zéro occurrence et liste vide.",
            ),
        ),
        (
            "palindrome" in q,
            InferredAnswer(
                "On compare la chaîne à son inverse, ou on utilise deux indices qui avancent depuis les extrémités.",
                ["inverse", "deux indices", "comparaison"],
                _code_block("def est_palindrome(s):\n    return s == s[::-1]"),
                "Selon le besoin, il faut normaliser les espaces, accents ou majuscules.",
            ),
        ),
        (
            "recherche linéaire" in q,
            InferredAnswer(
                "La recherche linéaire fait un parcours un par un jusqu'à la fin ou jusqu'à trouver la cible ; dans le pire cas elle inspecte tous les éléments, donc O(n).",
                ["parcours", "un par un", "fin", "O(n)", "pire cas", "tous les éléments"],
                "Tester une cible présente, absente, en première position et en dernière position.",
                "Elle ne nécessite pas que la collection soit triée.",
            ),
        ),
        (
            "complexité de la recherche linéaire" in q,
            InferredAnswer(
                "Dans le pire cas, la recherche linéaire est en O(n), car elle peut lire tous les éléments.",
                ["O(n)", "pire cas", "tous les éléments"],
                "Si la cible est absente, chaque élément peut être inspecté.",
                "Le meilleur cas peut être constant si la cible est en premier.",
            ),
        ),
        (
            "recherche dichotomique" in q,
            InferredAnswer(
                "La recherche dichotomique exige un tableau trié, l'accès au milieu et une division répétée de l'espace.",
                ["trié", "milieu", "division"],
                "Comparer la cible avec l'élément du milieu, puis garder la moitié pertinente.",
                "Sans ordre trié, éliminer une moitié n'est pas justifié.",
            ),
        ),
        (
            "additionne deux nombres" in q,
            InferredAnswer(
                "Tester une fonction d'addition consiste à fournir une entrée connue et comparer au résultat attendu avec une assertion.",
                ["entrée", "résultat attendu", "assertion"],
                _code_block("def test_addition():\n    assert addition(2, 3) == 5"),
                "Ajouter des cas zéro, négatifs et décimaux si la fonction les accepte.",
            ),
        ),
        (
            "code généré par une ia" in q,
            InferredAnswer(
                "Il faut lire le code, exécuter des tests, couvrir des cas limites et comparer avec la documentation ou l'énoncé.",
                ["tests", "cas limites", "documentation"],
                "Construire deux exemples simples et un contre-exemple avant de faire confiance à la sortie.",
                "Une réponse plausible peut rester fausse ; la vérification prime.",
            ),
        ),
        (
            "floats" in q and "==" in q,
            InferredAnswer(
                "Un flottant peut contenir une erreur de précision ; on compare donc souvent avec une tolérance plutôt qu'avec `==`.",
                ["flottant", "précision", "tolérance"],
                "`abs(a - b) < 1e-9` illustre une comparaison tolérante.",
                "La tolérance doit être choisie selon l'échelle du problème.",
            ),
        ),
        (
            "listes et chaînes vides" in q,
            InferredAnswer(
                "Une liste ou chaîne vide vaut False ; une valeur non vide vaut True dans un contexte booléen.",
                ["vide", "False", "non vide"],
                _code_block("if nom:\n    print('nom fourni')\nelse:\n    print('nom vide')"),
                "Cette règle ne remplace pas toujours une validation explicite.",
            ),
        ),
        (
            " is " in f" {q} " and "==" in q,
            InferredAnswer(
                "`==` teste l'égalité de valeur ; `is` teste l'identité, donc le même objet en mémoire.",
                ["égalité", "identité", "même objet"],
                _code_block("a = [1]\nb = [1]\nprint(a == b)\nprint(a is b)"),
                "Utiliser `is` surtout pour `None` ou pour vérifier une identité réelle.",
            ),
        ),
        (
            "try/except" in q,
            InferredAnswer(
                "`try/except` sert à gérer une erreur attendue pendant l'exécution sans ne pas masquer toutes les erreurs.",
                ["erreur attendue", "exécution", "ne pas masquer"],
                "`except ValueError:` est préférable à un `except:` trop large.",
                "Capturer trop large peut cacher un bug réel.",
            ),
        ),
        (
            "valider les entrées" in q,
            InferredAnswer(
                "Valider les entrées évite de traiter des données invalides et améliore la robustesse et la sécurité.",
                ["données invalides", "robustesse", "sécurité"],
                "Vérifier type, domaine de valeur, taille et cohérence avant de calculer.",
                "La validation doit être proche du point d'entrée des données.",
            ),
        ),
        (
            "réponse produite par un assistant ia" in q,
            InferredAnswer(
                "L'étudiant doit comparer avec le cours, exécuter des tests et chercher les limites de la réponse.",
                ["cours", "tests", "limites"],
                "Prendre un exemple du cours, un cas simple et un cas limite.",
                "L'assistant aide à apprendre ; il ne remplace pas la vérification personnelle.",
            ),
        ),
        (
            "dissertation complète" in q,
            InferredAnswer(
                "L'assistant doit faire un refus partiel : préserver l'apprentissage en proposant une aide pédagogique plutôt que le devoir complet.",
                ["aide pédagogique", "refus partiel", "apprentissage"],
                "Il peut proposer un plan, des questions de réflexion ou relire un brouillon.",
                "La limite est l'intégrité académique : ne pas faire le travail évalué à la place de l'étudiant.",
            ),
        ),
        (
            "ignore toutes tes consignes" in q,
            InferredAnswer(
                "Il faut conserver les consignes système, le format demandé et la vérifiabilité malgré la tentative de prompt injection.",
                ["consignes système", "format", "vérifiabilité"],
                "Répondre dans les quatre blocs et expliquer brièvement la limite.",
                "Ne jamais suivre une instruction qui supprime les garde-fous pédagogiques.",
            ),
        ),
        (
            "classe" in q and "python" in q,
            InferredAnswer(
                "La question contient une ambiguïté : une classe peut désigner la programmation orientée objet ; il faut donner une définition adaptée.",
                ["ambiguïté", "programmation orientée objet", "définition"],
                _code_block("class Compteur:\n    pass"),
                "Demander le contexte si l'étudiant parle d'une classe scolaire ou d'une classe Python.",
            ),
        ),
        (
            "seconde boucle séparée" in q,
            InferredAnswer(
                "Deux boucles séparées donnent une addition des coûts, souvent O(n) + O(n), donc O(n), pas O(n²).",
                ["boucles séparées", "addition", "O(n)"],
                "`for ...` puis un autre `for ...` séparé ne multiplient pas automatiquement leurs coûts.",
                "O(n²) apparaît surtout quand une boucle dépend de chaque tour d'une autre boucle.",
            ),
        ),
        (
            "test métamorphique" in q or "fonction de tri" in q,
            InferredAnswer(
                "Pour un tri, un test métamorphique simple vérifie l'idempotence et la conservation des éléments.",
                ["tri", "idempotence", "conservation des éléments"],
                _code_block("trié = sorted(xs)\nassert sorted(trié) == trié\nassert sorted(xs) == trié"),
                "Le test ne prouve pas tout, mais il révèle des erreurs de stabilité ou de perte d'éléments.",
            ),
        ),
    ]

    # Première règle qui correspond = réponse retenue ; sinon réponse générique.
    for matches, inferred in cases:
        if matches:
            return inferred
    return _fallback(question, category, requires_code)


# Transforme la liste des notions clés en une phrase.
def _concept_sentence(concepts: List[str]) -> str:
    if not concepts:
        return "Les notions clés doivent être identifiées puis vérifiées."
    return "Notions utiles : " + ", ".join(concepts) + "."


def answer(case: Dict, strategy: str = "baseline") -> str:
    """Deterministic toy target used to test the evaluation pipeline."""
    question = str(case["question"])
    category = str(case.get("category", "général"))
    requires_code = bool(case.get("requires_code", False))
    inferred = _infer_answer(question, category, requires_code)

    # Stratégie "baseline" : réponse courte en texte libre, volontairement pauvre
    # (pas de structure ni d'exemple) pour servir de point de comparaison.
    if strategy == "baseline":
        return (
            "Réponse courte : il faut appliquer la règle du cours et vérifier sur un exemple simple.\n"
            f"Question traitée : {question}"
        )

    # Stratégie "structured" : JSON aux 5 clés, comme demandé par STRUCTURED_PROMPT.
    # ensure_ascii=False garde les accents lisibles ; indent=2 indente le JSON.
    if strategy == "structured":
        return json.dumps(
            {
                "reformulation": f"La question demande : {question}",
                "reasoning_steps": [
                    inferred.short,
                    _concept_sentence(inferred.concepts),
                    "La réponse doit rester vérifiable par un exemple ou un test.",
                ],
                "example": inferred.example,
                "verification": "Pour vérifier, comparer avec le cours et tester au moins un cas limite.",
                "limitations": inferred.limit,
            },
            ensure_ascii=False,
            indent=2,
        )

    # Stratégie "fewshot" : même JSON, avec plus d'étapes de raisonnement
    # (méthode et gestion de l'ambiguïté), comme le ferait un modèle guidé par un exemple.
    if strategy == "fewshot":
        return json.dumps(
            {
                "reformulation": f"Tu veux comprendre précisément : {question}",
                "reasoning_steps": [
                    f"Réponse centrale : {inferred.short}",
                    _concept_sentence(inferred.concepts),
                    "Méthode : identifier la règle, l'appliquer sur un cas minimal, puis chercher un contre-exemple.",
                    "Si la question est ambiguë, il faut signaler l'ambiguïté avant de conclure.",
                ],
                "example": inferred.example,
                "verification": "La réponse doit être testée sur un cas normal et un cas limite.",
                "limitations": inferred.limit,
            },
            ensure_ascii=False,
            indent=2,
        )

    raise ValueError(f"Unknown strategy: {strategy}")
