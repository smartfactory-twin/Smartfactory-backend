# Campagne de performance ISO/IEC 25010 — 25 novembre 2026

## Environnement et méthode

- API Django locale en mode recette (`core.settings_load`), base isolée `smartfactory_load`.
- Jeu de données synthétique vérifié avant l’essai : 50 machines et 500 capteurs `PERF-*`.
- Locust 2.47.0 : 20 utilisateurs, arrivée à 5 utilisateurs/seconde, 120 secondes.
- Dashboard : Chromium headless, 10 navigations vers `/admin/dashboard`, API de recette réelle.
- WebSocket : Daphne local, 30 envois de mesure puis attente de l’événement correspondant sur `PERF-SENSOR-001-01`.
- Résultats précédents invalides exclus. Aucun serveur ni base de production n’a été utilisé.

## Résultats

| Critère | Mesure observée | Cible | Verdict |
| --- | ---: | ---: | --- |
| Requêtes API sous 20 utilisateurs | 2 193 requêtes, 0 échec; débit moyen 18,55 req/s | aucun taux d’erreur toléré pour cet essai | 0 échec observé |
| API `GET machines` | P95 1 500 ms (242 requêtes) | < 300 ms | Non atteint |
| API `GET capteurs` | P95 1 600 ms (177 requêtes) | < 300 ms | Non atteint |
| API `GET alertes` | P95 1 400 ms (166 requêtes) | < 300 ms | Non atteint |
| Composition des appels API du dashboard | P95 15 000 ms (87 compositions) | < 3 000 ms | Non atteint |
| Chargement navigateur du dashboard | médiane 794 ms; P95 14 135 ms; min 692 ms (10 navigations) | < 3 000 ms | Non atteint au P95 |
| Livraison mesure → WebSocket | médiane 99,43 ms; P95 493,16 ms; max 951,60 ms (30 essais réussis) | < 2 000 ms | Atteint |
| Capacité de fixture | 50 machines; 500 capteurs | 50 machines; 500 capteurs | Atteint pour le jeu de recette |

Locust a également mesuré `GET profil` (P95 1 400 ms), l’authentification (P95 6 200 ms), les statistiques et la hiérarchie; les détails complets sont dans le CSV. Le temps « composition dashboard » cumule les appels API utilisés par le tableau de bord; il ne représente pas le rendu navigateur.

## Interprétation et limites

La campagne est techniquement exploitable (zéro erreur HTTP enregistrée), mais les cibles API et dashboard ne sont pas satisfaites sous cette charge locale. Le temps médian navigateur du dashboard est inférieur à 3 s, mais le P95 de 14,135 s échoue nettement. Le canal WebSocket respecte la cible mesurée.

Ces mesures caractérisent uniquement cette machine de développement, ce serveur Django local et des données synthétiques. Elles ne prouvent pas les performances en production ni une capacité industrielle. Les caractéristiques matérielles, le profil de déploiement candidat et la charge réseau industrielle n’ont pas été consignés; une nouvelle campagne sur l’environnement de déploiement reste nécessaire.

## Fichiers de preuve

- [Statistiques Locust](iso25010-load-20261125_stats.csv)
- [Historique Locust](iso25010-load-20261125_stats_history.csv)
- [Échecs Locust](iso25010-load-20261125_failures.csv)
- [Exceptions Locust](iso25010-load-20261125_exceptions.csv)
- Procédures et scripts : `tests/performance/README.md`, `tests/performance/locustfile.py`, `tests/performance/dashboard-load.mjs`, `tests/performance/websocket_latency.py`.
