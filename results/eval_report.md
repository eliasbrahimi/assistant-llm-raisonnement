# Rapport d'evaluation - Assistant RL/GRPO

> Genere le 2026-06-04 12:55 UTC  
> Modele : llama-3.3-70b-versatile | 45 questions | 3 strategies

## Resultats globaux

| Strategie | N | Score moyen | Format valide | Latence moy. |
|-----------|---|-------------|---------------|--------------|
| baseline | 45 | 1.58/3 | 0.0% | 1856 ms |
| structured | 45 | 1.94/3 | 88.9% | 877 ms |
| fewshot | 45 | 1.52/3 | 68.9% | 888 ms |

## GO/NO-GO

### structured
- Score : 1.94/3 FAIL (cible >= 2.5)
- Format JSON : 88.9% FAIL (cible >= 95%)
- Latence P95 : 1115ms OK (cible < 8000ms)

### fewshot
- Score : 1.52/3 FAIL (cible >= 2.5)
- Format JSON : 68.9% FAIL (cible >= 95%)
- Latence P95 : 1437ms OK (cible < 8000ms)
