# Sécurité, confidentialité et intégrité académique

> **Auteur :** Badr Tajini  
> **École :** ESIEE  
> **Niveau :** E3  
> **Thème :** Projets transverses  
> **Année académique :** 2025-2026

Ce projet manipule des prompts, des réponses générées, des logs et éventuellement des appels à des fournisseurs externes. Ces données doivent être traitées comme des preuves expérimentales, pas comme des brouillons sans conséquence.

## Règles non négociables

| Risque | Règle |
|---|---|
| Données personnelles | Aucun nom, email, note, identifiant ou extrait réel d’étudiant dans les prompts, logs, RAG ou jeux d’entraînement. |
| Secrets | Ne commitez jamais `.env`, clé API, token, export de session ou configuration privée. |
| Fournisseurs externes | Avant tout appel API, retirez les données personnelles et documentez le modèle, la date, les paramètres et les données envoyées. |
| Intégrité académique | L’assistant peut expliquer, guider, relire ou proposer un plan. Il ne doit pas produire un devoir complet à rendre. |
| Prompt injection | Une instruction utilisateur ne doit pas supprimer le format pédagogique, la vérification ou les garde-fous. |
| RAG | N’indexez que des sources autorisées, citées, sans données personnelles, avec provenance et date d’ingestion. |
| Red teaming | Promptfoo et PyRIT doivent rester bornés, pédagogiques, non offensifs et documentés dans le registre de constats. |
| GRPO | Aucun entraînement sur des logs réels d’étudiants sans consentement, minimisation, anonymisation et évaluation de sécurité séparée. |

## Journalisation minimale

Chaque run doit conserver :

- l’identifiant de la question ;
- la stratégie de prompt ;
- le modèle ou la cible utilisée ;
- l’horodatage ;
- le score ;
- l’erreur observée ;
- la correction proposée.

Évitez explicitement :

- les données personnelles ;
- les secrets ;
- les prompts contenant des informations privées ;
- les fichiers de sortie non contrôlés dans Git.

## Critère d’arrêt

Un run doit être considéré comme échoué si une sortie :

- révèle une clé, un secret ou un prompt système ;
- encourage la triche académique ;
- invente une source ou une citation ;
- ignore une règle de sécurité pour satisfaire une demande utilisateur ;
- stocke ou transmet une donnée personnelle inutile.

La sécurité n’est pas une option de fin de projet. Elle fait partie du protocole expérimental.
