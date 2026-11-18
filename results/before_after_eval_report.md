# Rapport automatique avant/après

> Cible utilisée : API Groq (llama-3.3-70b-versatile)

| Stratégie | N | Score moyen | Format valide | Vérification moyenne |
|---|---:|---:|---:|---:|
| baseline | 45 | 1.77 | 0.00% | 1.47 |
| fewshot | 45 | 2.57 | 97.78% | 3.00 |
| structured | 45 | 2.54 | 97.78% | 2.93 |

## Lecture par split

| Split | Stratégie | N | Score moyen |
|---|---|---:|---:|
| dev | baseline | 24 | 1.79 |
| dev | fewshot | 24 | 2.53 |
| dev | structured | 24 | 2.56 |
| test | baseline | 21 | 1.74 |
| test | fewshot | 21 | 2.61 |
| test | structured | 21 | 2.51 |

## Utilisation attendue

1. Lancer sans GROQ_API_KEY pour tester le pipeline (toy target).
2. Lancer avec GROQ_API_KEY pour une évaluation réelle du modèle.
3. Conserver exactement le même catalogue de questions.
4. Comparer baseline, prompt structuré et few-shot.
5. Documenter les erreurs dans le findings register.