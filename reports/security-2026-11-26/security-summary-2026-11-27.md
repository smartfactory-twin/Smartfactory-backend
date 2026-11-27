# Vérification SAST / SCA — 26–27 novembre 2026

## Résultats

| Contrôle | Outil et périmètre | Résultat | État |
| --- | --- | --- | --- |
| SAST Python | Bandit 1.9.4, apps/, seuil medium+ | 3 alertes medium B310, confiance élevée; aucune alerte high/critical rapportée | À trier |
| SCA backend runtime | pip-audit 2.10.1, Python 3.12.16, requirements.txt actuel | 57 dépendances résolues, 0 vulnérabilité connue | Réussi |
| SCA backend dev | pip-audit 2.10.1, Python 3.12.16, requirements-dev.txt actuel | 107 dépendances résolues, 0 vulnérabilité connue | Réussi |
| SCA frontend | npm audit connecté, package-lock.json actuel | 299 dépendances, 0 vulnérabilité connue | Réussi |
| DAST | OWASP ZAP Baseline sur Swagger de la recette isolée | Le serveur de recette a répondu HTTP 200 sur /api/docs/, mais l’image ZAP n’a pas fini de se télécharger depuis GHCR; aucun scan ni rapport ZAP produit | Non exécuté |

## Findings Bandit à examiner

Les trois alertes B310 concernent urllib.request.urlopen :

- apps/voice/llm.py:79 — requête stream du fournisseur LLM.
- apps/voice/llm.py:147 — requête LLM non-stream.
- apps/voice/transcription.py:91 — requête de transcription.

Le code limite actuellement les URL à HTTPS ou à certaines URL locales par startswith. Bandit signale que urlopen accepte aussi des schémas non attendus. La restriction actuelle réduit le risque, mais la validation de préfixe n’est pas une validation stricte de schéma et d’hôte. Examiner une validation avec urllib.parse.urlsplit, sans autoriser les schémas autres que HTTPS (et localhost strict uniquement si nécessaire). Ces findings n’ont pas été supprimés ni ignorés.

## Environnement, méthode et limites

- L’audit pip-audit tenté avec le Python local 3.10 n’a pas pu résoudre Pillow 13.0.0, qui requiert Python >= 3.11; cet essai n’est pas considéré comme un résultat.
- Les deux audits pip-audit valides ont été exécutés dans un conteneur jetable utilisant Python 3.12.16, avec les requirements actuels montés en lecture seule. Aucun paquet n’a été ajouté au conteneur applicatif.
- Django manage.py check a réussi avec core.settings_load et la base isolée smartfactory_load.
- Une instance Django temporaire de recette a été lancée uniquement sur un port local distinct et arrêtée après l’échec du téléchargement de l’image ZAP. Le port temporaire a ensuite été vérifié libre. Aucun scan n’a ciblé le backend de développement sur :8000.
- Le DAST manque encore : ZAP doit être disponible localement ou le téléchargement de ghcr.io/zaproxy/zaproxy:stable doit fonctionner. Le résultat prévu est un scan Baseline passif non authentifié de Swagger; il ne couvre donc pas encore les opérations d’API qui exigent un JWT.

## Rapports bruts

- bandit-apps.json — résultat complet Bandit (inclut les findings faibles).
- bandit-apps-medium-high.json — alertes medium et high.
- pip-audit-runtime.json — dépendances runtime.
- pip-audit-dev.json — dépendances de développement.
- npm-audit.json — audit frontend.
