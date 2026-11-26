# Recette de performance

Ces scénarios sont réservés à une base et à des comptes de recette dédiés. Ne jamais les lancer sur la production. Les scripts ne suppriment aucune donnée.

## Préparer la charge de données

1. Créer une base PostgreSQL dédiée nommée, par exemple, `smartfactory_load` et la renseigner dans `.env` (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`).
2. Démarrer PostgreSQL et appliquer les migrations avec les paramètres normaux de l'application.
3. Créer un compte ADMIN de recette. Il doit avoir accès aux machines PERF pour le test WebSocket.
4. Depuis `Smartfactory-backend`, en PowerShell :

```powershell
$env:PERFORMANCE_TEST_CONFIRM = 'YES'
python tests/performance/seed_load_data.py --settings core.settings_load
```

Le script refuse une base dont le nom ne contient pas `load`, `performance` ou `perf_test`. Il ajoute idempotemment 50 machines et 500 capteurs identifiés par le préfixe `PERF-`; aucun enregistrement n'est effacé. Les capteurs sont synthétiques et ne doivent pas être utilisés pour évaluer l'IA.

## Charge API et composition des données du dashboard

Installer les outils de recette avec `pip install -r requirements-dev.txt`, démarrer l'API avec le profil `core.settings_load`, puis lancer :

```powershell
$env:LOCUST_EMAIL = 'admin-load@example.test'
$env:LOCUST_PASSWORD = '<mot-de-passe-du-compte-de-recette>'
locust -f tests/performance/locustfile.py --host http://127.0.0.1:8000 --users 20 --spawn-rate 5 --run-time 2m --headless --csv reports/locust
```

Locust rapporte les latences par endpoint, taux d'erreurs et percentiles. La transaction `Dashboard composition (API, hors rendu navigateur)` suit les appels de données du tableau de bord ADMIN et mesure leur durée cumulée. Elle ne mesure pas le rendu visuel ni le chargement navigateur.

## Temps de chargement navigateur du dashboard

Depuis `Smartfactory-frontend`, avec Vite accessible et Playwright/Chromium installé :

```powershell
$env:PERF_APP_URL = 'http://127.0.0.1:5173'
$env:PERF_API_URL = 'http://127.0.0.1:8000'
$env:LOCUST_EMAIL = 'admin-load@example.test'
$env:LOCUST_PASSWORD = '<mot-de-passe-du-compte-de-recette>'
$env:DASHBOARD_ITERATIONS = '10'
node tests/performance/dashboard-load.mjs
```

Le chronomètre part de la navigation et s'arrête quand le panneau « État des équipements » est visible après chargement des données. Le script imprime min, médiane, P95 et max. La cible du cahier est < 3 s; conserver la sortie avec la version du navigateur et la configuration matérielle.

## Latence de diffusion WebSocket

Avec l'API ASGI/Daphne active, le compte ADMIN de recette et les capteurs PERF prêts :

```powershell
$env:LOCUST_EMAIL = 'admin-load@example.test'
$env:LOCUST_PASSWORD = '<mot-de-passe-du-compte-de-recette>'
python tests/performance/websocket_latency.py --iterations 30
```

Le script ouvre un WebSocket authentifié, crée une mesure sur le capteur PERF puis chronomètre jusqu'à réception de l'événement correspondant. Il affiche min, médiane, P95 et max; la cible est < 2 s. Les mesures sont conservées dans la base de charge.

## Interprétation

Une recette n'est concluante que si les fichiers Locust `*_stats.csv` et la sortie des scripts navigateur/WebSocket sont archivés avec l'horodatage, versions des composants, matériel, nombre d'utilisateurs et nombre de capteurs. Toute panne ou code HTTP en erreur invalide l'essai correspondant; ne pas transformer un objectif en résultat mesuré.
