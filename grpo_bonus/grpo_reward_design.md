# GRPO bonus — conception de récompense

## Objectif réaliste

Le bonus GRPO ne doit pas viser à battre un grand modèle propriétaire. Il doit montrer que les étudiants comprennent la chaîne expérimentale : prompts, générations multiples, récompenses, entraînement, validation et analyse des effets secondaires.

## Récompenses proposées

| Récompense | Idée | Risque |
|---|---|---|
| format_reward | Vérifier les quatre sections | Le modèle peut apprendre le format sans être correct |
| verification_reward | Récompenser une vérification concrète | Vérifications génériques répétées |
| concept_reward | Couvrir les concepts attendus | Surapprentissage lexical |
| length_reward | Garder une réponse concise | Réponses trop courtes |
| refusal_reward | Gérer les demandes hors périmètre | Refus excessifs |

## Split recommandé

- Dev : questions utilisées pour concevoir prompts et récompenses.
- Test : questions non vues avant le benchmark final.
- Robustesse : questions ambiguës, pièges et injections bénignes.

## Conclusion attendue

Une conclusion acceptable : « Le mini-GRPO améliore le respect du format mais ne prouve pas une amélioration robuste de l’exactitude. » Cette conclusion est scientifiquement plus solide qu’une affirmation excessive.