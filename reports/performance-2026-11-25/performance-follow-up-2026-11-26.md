# Analyse et suivi de performance — 26 novembre 2026

## Lecture de la campagne du 25 novembre

La campagne a exécuté 2 193 requêtes sous 20 utilisateurs, sans erreur HTTP, sur 50 machines et 500 capteurs synthétiques. Elle établit ces constats :

- Les P95 des endpoints machines, capteurs et alertes sont tous proches, entre 1,4 et 1,6 s. Cette similarité indique une pression générale de l'environnement ou de la base pendant la charge ; elle ne désigne pas à elle seule un endpoint comme cause unique.
- Le login a un P95 de 6,2 s. Chaque utilisateur Locust se connecte au démarrage, ce qui concentre le coût d'authentification pendant la montée en charge et peut affecter les autres requêtes. Cette campagne ne sépare pas cet effet d'une saturation CPU ou base de données.
- Le dashboard lance cinq appels de données initiaux, puis un appel de hiérarchie pour chaque usine. Les réponses par composant ont des médianes d'environ 0,5 à 0,6 s, et la hiérarchie d'environ 1,2 s. Leur composition explique une part importante du délai dashboard, sans expliquer à elle seule le P95 navigateur de 14,135 s.
- La hiérarchie imbriquée (usine → zones → lignes → machines → composants) était sérialisée sans préchargement des relations. Cela créait des requêtes répétées à chaque niveau. La liste machine préchargeait également composants et documents alors que son serializer de liste ne les renvoie pas.

Ces observations localisent une amplification de requêtes dans la hiérarchie et un coût superflu de la liste machine. Elles ne suffisent pas à identifier la cause complète des latences sous charge. Le rapport initial ne contient pas les caractéristiques matérielles ni de profil CPU, mémoire ou requêtes SQL pendant la campagne.

## Corrections appliquées

- Préchargement des relations imbriquées pour l'endpoint de hiérarchie.
- Calcul de `zones_count` par annotation SQL dans la liste des usines, au lieu d'une requête de comptage par usine.
- Préchargement des composants et documents uniquement pour les actions machine qui les exposent, pas pour la liste.
- Ajout d'un test de régression SQL : une hiérarchie de quatre zones, sept lignes et treize machines est renvoyée avec au plus cinq requêtes SQL. Le test et les tests de hiérarchie et pagination associés passent (**3/3**).

## Vérification après correction

- Suite backend complète : **466 réussis, 0 échec**, en 197,57 s.
- Avertissements : pagination des usines sans ordre explicite (résultats potentiellement instables entre pages) et classe SKAB de deux exemples pour cinq plis.
- La campagne de charge après correction **n'a pas été exécutée**. Aucun nouveau P95 API, dashboard ou WebSocket n'est donc disponible.

La tentative de vérifier le candidat Docker a échoué car le moteur Docker Desktop n'était pas démarré :

```text
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine;
check if the path is correct and if the daemon is running:
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

Les mesures du 25 novembre restent le seul résultat de charge valide et ne doivent pas être présentées comme des résultats après optimisation. La comparaison doit être refaite sur l'environnement candidat, avec les mêmes 20 utilisateurs et 500 capteurs, plus le chronométrage navigateur et WebSocket, et en archivant les versions et caractéristiques matérielles.

## Mesures de suivi après correction — 26 novembre 2026

Cette section complète et remplace l'affirmation précédente selon laquelle aucune campagne après correction n'avait été exécutée. La campagne répétée a utilisé l'instance de recette isolée `smartfactory_load`, avec 20 utilisateurs Locust, montée en charge à 5 utilisateurs/seconde, 120 secondes, 50 machines et 500 capteurs synthétiques. Aucun échec n'a été enregistré sur 2 857 requêtes.

| Mesure | Résultat après correction | Cible | Verdict |
| --- | ---: | ---: | --- |
| GET machines, P95 Locust | 920 ms (519 requêtes) | < 300 ms | Non atteint |
| GET capteurs, P95 Locust | 950 ms (408 requêtes) | < 300 ms | Non atteint |
| GET alertes, P95 Locust | 720 ms (278 requêtes) | < 300 ms | Non atteint |
| Composition API dashboard, P95 | 3 600 ms (202 compositions) | < 3 000 ms | Non atteint |
| Chargement navigateur dashboard, P95 | 2 615 ms (30 navigations Chromium headless; médiane 766 ms) | < 3 000 ms | Atteint sur cette campagne |
| WebSocket mesure → événement, P95 | 1 430,47 ms (30 essais réussis) | < 2 000 ms | Atteint |

La campagne du 25 novembre et celle du 26 novembre ne doivent pas être confondues : après optimisation, les P95 machines/capteurs/alertes sont respectivement 920/950/720 ms contre 1 500/1 600/1 400 ms. La composition API dashboard est passée de 15 000 à 3 600 ms. Elle manque encore la cible API. Le navigateur a atteint 2 615 ms au P95 sur 30 itérations. La mesure initiale de 10 itérations (P95 13 901 ms) est conservée comme observation distincte, mais la série à 30 itérations est la campagne de suivi retenue. Le WebSocket reste sous 2 s mais son P95 est moins bon que les 493,16 ms du 25 novembre.

Les statistiques Locust sont approximatives selon l'estimateur de percentiles de Locust. Les mesures ne sont pas une preuve de production : elles caractérisent la machine de développement et une base de recette locale. Les caractéristiques CPU/RAM de l'hôte n'ont pas pu être lues depuis cette session, et aucun environnement candidat de déploiement distinct n'était fourni. Une campagne sur cet environnement candidat reste nécessaire avant de conclure sur les objectifs ISO du déploiement.

Preuves du 26 novembre : `../performance-2026-11-26/iso25010-load-20261126_stats.csv`, `../performance-2026-11-26/iso25010-load-20261126_stats_history.csv`, `../performance-2026-11-26/iso25010-load-20261126_failures.csv`, `../performance-2026-11-26/iso25010-load-20261126_exceptions.csv`, `../performance-2026-11-26/dashboard-load-run-30.json`, `../performance-2026-11-26/websocket-latency-run.json`.
