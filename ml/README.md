# Benchmark MetroPT-3

Ce benchmark utilise `Group_14_Clean_Data.csv`, le dérivé nettoyé publié dans le dépôt [harveyphm/MetroPT-3-Anomaly-Detection](https://github.com/harveyphm/MetroPT-3-Anomaly-Detection), basé sur le [jeu MetroPT-3 de l’UCI](https://archive.ics.uci.edu/dataset/791/metropt+3+dataset). MetroPT-3 contient de la télémétrie réelle d’un compresseur ferroviaire. Le CSV dérivé contient 59 445 lignes et 15 signaux. Son champ `status` n’est pas utilisé.

Télécharger le CSV dérivé et le placer ici :

```text
ml/data/metropt3/Group_14_Clean_Data.csv
```

Entraîner le détecteur non supervisé sur février 2020, calibrer le seuil sur mars sans panne signalée (seuil au 5e percentile pour équilibrer rappel et fausses alertes), puis évaluer à partir d’avril sur les périodes de panne publiées par UCI :

```powershell
.\.venv\Scripts\python.exe ml\train_metropt.py
```

Le modèle et le rapport de métriques sont générés dans `ml/artifacts/`. Le CSV et les artefacts sont ignorés par Git; chaque clone doit télécharger le CSV puis réentraîner le modèle.

**Interprétation :** les quatre périodes de fuite de la fiche UCI sont la référence de test; `status` n’est pas pris comme vérité terrain. Les scores sont ceux de ce benchmark et ne valident pas les capteurs SmartFactory. Pour déployer sur une machine de l’usine, il faut recueillir ses signaux, confirmer leur correspondance physique et valider le modèle sur une période indépendante avant usage opérationnel.

## Pipeline SKAB (implémenté, entraînement manuel)

Le pipeline SKAB se trouve dans `apps/equipements/skab_ml.py`; la commande est `ml/train_skab.py`. Il lit les CSV présents dans `ml/data/SKAB/data/` : les fichiers étiquetés des dossiers `valve1/`, `valve2/` et `other/`, ainsi que `anomaly-free/anomaly-free.csv`.

Pour lancer explicitement l’entraînement et l’évaluation :

```powershell
.\.venv\Scripts\python.exe ml\train_skab.py
```

La commande produit `ml/artifacts/skab_anomaly_detector.joblib` et `ml/artifacts/skab_training_report.json`. Elle compare IsolationForest (appris sur des fenêtres normales), HistGradientBoostingClassifier (supervisé) et une référence médiane/MAD entraînée uniquement sur `anomaly-free.csv`. Cette dernière est une **référence statistique, pas le score live de l’application**. Le score live `_score` n’est pas reproduit : les CSV SKAB n’apportent pas de seuils opérationnels par capteur comparables à ceux de SmartFactory.

Les CSV sont séparés en groupes par fichier, de façon déterministe et stratifiée par dossier (environ 60/20/20). Les fenêtres utilisent 30 secondes calculées à partir de `datetime`, sans rééchantillonnage; le nom `Volume Flow RateRMS` est conservé. Une validation croisée stratifiée et groupée par fichier est calculée sur les fichiers d’entraînement. Les dossiers absents de chaque pli sont consignés. Le choix du modèle utilise le F1 moyen de validation croisée; en cas d’égalité, le F1 de calibration puis le taux moyen de faux positifs CV départagent. Le test final n’est ouvert qu’après cette sélection et ses métriques ne sont calculées qu’une fois.

Le rapport détaille les métriques globales, par dossier, type d’anomalie et fichier, le délai de détection, les faux positifs avant le premier changepoint et les fichiers manqués. Il indique la prévalence réelle des labels du test (attendue autour de 35 % sur le jeu fourni), ses 7 fichiers et les limites de l’évaluation. Un résultat SKAB reste un benchmark externe : il ne valide pas les capteurs ni les machines SmartFactory. Ce pipeline n’est pas branché à l’API et n’est pas entraîné automatiquement.
