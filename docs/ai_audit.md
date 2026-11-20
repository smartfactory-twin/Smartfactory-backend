# Audit IA — SmartFactory Twin

**Type d’audit :** lecture seule du code, des artefacts présents, des migrations et des tests.
**Périmètre :** backend Django REST et frontend React présents dans le dépôt. Aucun test d’inférence ni entraînement n’a été déclenché pour cet audit.

## 1. Fichiers liés à l’IA

### Backend — code, configuration et données

| Fichier | Rôle |
|---|---|
| `apps/equipements/ai_prediction_views.py` | Endpoints du score statistique d’anomalie, simulation What-if et catalogue d’état des modèles. |
| `apps/equipements/predictive_views.py` | Endpoint authentifié d’état et de prédiction RUL C-MAPSS. |
| `apps/equipements/cmapss_ml.py` | Préparation des fenêtres C-MAPSS, chargement mis en cache du régresseur, prédiction et état de l’artefact. |
| `apps/equipements/ml_serializers.py` | Validation des entrées RUL (cycle et séries de 24 valeurs). |
| `apps/equipements/metropt_ml.py` | Entraînement, évaluation et lecture de statut du benchmark MetroPT-3. L’API ne prédit pas sur les mesures SmartFactory avec ce modèle. |
| `apps/equipements/skab_ml.py` | Pipeline SKAB : fenêtres temporelles, séparation par fichiers, validation croisée, entraînement/évaluation, statut d’artefact. Le statut n’est pas raccordé à une vue API. |
| `apps/equipements/vision_ai.py` | Interface de service de vision, implémentation YOLO et implémentation mock déterministe. |
| `apps/equipements/views.py` | Actions REST de création, analyse, annotation et consultation des inspections; les alertes et ordres de travail ont aussi leurs ViewSets ici. |
| `apps/equipements/serializers.py` | Sérialisation des capteurs, mesures, inspections, alertes consommées par l’application, et ordres de travail. |
| `apps/equipements/models.py` | Modèles Machine, Sensor, Reading, InspectionVisuelle, OrdreTravail et périmètres d’accès. |
| `apps/alertes/engine.py` | Détection des dépassements de seuils min/max d’un capteur et création/résolution des alertes. |
| `apps/alertes/signals.py` | Branche l’évaluation des seuils aux nouvelles mesures `Reading`. |
| `apps/alertes/models.py` | Modèles persistants Alerte et Notification; le champ de score IA d’alerte est réservé et non alimenté par le score actuel. |
| `apps/alertes/views.py` | API des alertes, acquittement/résolution et action explicite de préparation d’un ordre de travail depuis une alerte. |
| `apps/accounts/models.py` | `VocalCommand`, journal textuel des commandes vocales associé à l’utilisateur (aucun audio stocké). |
| `apps/accounts/serializers.py` | Sérialiseur du journal vocal : texte, intention, confiance, résultat et utilisateur. |
| `apps/accounts/views.py` | GET/POST de l’historique vocal; l’admin peut consulter le journal global, les autres utilisateurs leur propre historique. |
| `apps/accounts/urls.py` | Route `/api/auth/vocal/commands/`. |
| `apps/equipements/urls.py` | Routes des inspections, capteurs, mesures et ordres de travail via DRF router. |
| `core/urls.py` | Routes `/api/ai-predictions/*`, `/api/predictive-maintenance/`, inspections et alias de lecture. |
| `core/settings.py` | Configuration du backend Vision (`mock` par défaut, chemin YOLO et seuil de confiance) et chemin de modèle C-MAPSS. |
| `apps/equipements/apps.py` | Connecte le signal de création des mesures à la diffusion temps réel; ce n’est pas une inférence IA. |
| `apps/accounts/migrations/0006_vocal_command_history.py` | Création de la table du journal vocal. |
| `apps/equipements/migrations/0002_sensor_reading.py` | Création des tables Sensor et Reading. |
| `apps/equipements/migrations/0003_inspectionvisuelle.py`, `0004_inspectionvisuelle_confidence_and_more.py`, `0008_inspection_gallery_annotations_and_video.py` | Évolutions du modèle d’inspection, résultats, annotations et galerie. |
| `apps/equipements/migrations/0009_work_orders_and_recurring_maintenance.py` | Création des ordres de travail et maintenances récurrentes. |
| `apps/alertes/migrations/0001_initial.py` | Schéma initial des alertes et notifications. |
| `requirements-ml.txt` | Dépendances Python des modèles et traitements ML. |
| `requirements-vision.txt` | Dépendances optionnelles du backend de vision YOLO. |

### Backend — commandes d’entraînement et artefacts présents

| Fichier | Rôle |
|---|---|
| `ml/train_cmapss.py` | Commande d’entraînement du régresseur RUL C-MAPSS. |
| `ml/train_metropt.py` | Commande du benchmark MetroPT-3. |
| `ml/train_skab.py` | Commande du benchmark SKAB. |
| `ml/train_yolo.py` | Outil d’entraînement YOLO; le chargement en production dépend des poids `.pt` externes configurés. |
| `ml/artifacts/cmapss_rul.joblib` | Artefact HistGradientBoostingRegressor appelé par l’endpoint RUL. |
| `ml/artifacts/cmapss_training_report.json` | Rapport de données/métriques du modèle C-MAPSS. |
| `ml/artifacts/metropt3_anomaly_detector.joblib` | Détecteur IsolationForest lu par le statut de benchmark, mais non appliqué aux machines dans l’API. |
| `ml/artifacts/metropt3_status_classifier.joblib` | Classifieur conservé dans les artefacts; aucune référence de chargement/usage API trouvée dans le code parcouru. |
| `ml/artifacts/metropt3_training_report.json` | Rapport du benchmark MetroPT-3. |
| `ml/artifacts/skab_anomaly_detector.joblib` | Artefact contenant les modèles comparés et le modèle sélectionné; aucune route API ne le charge ni ne l’infère actuellement. |
| `ml/artifacts/skab_training_report.json` | Rapport de séparation, sélection et métriques SKAB. |
| `ml/data/SKAB/` | Copie locale du jeu SKAB, de sa documentation et des ressources amont; données de benchmark, pas des capteurs SmartFactory. |
| `ml/data/metropt3/` | Emplacement prévu pour les données d’entraînement MetroPT-3. |
| `ml/data/C-MAPSS/` | Emplacement des fichiers C-MAPSS consommés par le pipeline d’entraînement. |

### Frontend — pages et services

| Fichier | Rôle |
|---|---|
| `src/pages/ai/PredictionsIaPage.jsx` | Interface de score statistique, RUL, What-if et présentation des modèles/benchmarks. |
| `src/pages/ai/PredictionsIaPage.css` | Présentation responsive de la page IA. |
| `src/services/aiPredictionService.js` | Appels frontend pour anomalies, What-if et catalogue des modèles. |
| `src/services/predictiveMaintenanceService.js` | Appels d’état et de prédiction RUL. |
| `src/pages/inspections/InspectionsPage.jsx` | Parcours d’inspection visuelle, historique et comparaison. |
| `src/components/inspections/MachineSelector.jsx` | Sélection de la machine à inspecter. |
| `src/components/inspections/ImageUploadDropzone.jsx` | Téléversement/capture des images d’inspection. |
| `src/components/inspections/InspectionResultCard.jsx` | Affichage du résultat et de la confiance de l’analyse. |
| `src/components/inspections/InspectionHistoryTable.jsx` | Tableau d’historique des inspections. |
| `src/components/inspections/InspectionDetailModal.jsx` | Détail d’une inspection. |
| `src/components/inspections/InspectionAnnotationEditor.jsx` | Annotation manuelle et sauvegarde de l’image annotée. |
| `src/components/inspections/InspectionComparison.jsx` | Comparaison des images d’inspections avant/après. |
| `src/services/inspectionService.js` | Appels REST de création, analyse, annotation, détail et suppression. |
| `src/pages/vocal/VocalPage.jsx` | Reconnaissance/synthèse navigateur, règles NLU, confirmations de commandes, orchestration des lectures/actions vocales et dictée de rapport. |
| `src/services/voiceService.js` | Lecture et enregistrement du journal textuel vocal côté API. |
| `src/pages/alertes/AlertesPage.jsx` | Affichage/traitement des alertes et déclenchement éventuel de préparation d’OT. |
| `src/services/alertService.js` | Appels API pour alertes, acquittement, résolution et préparation d’OT. |
| `src/pages/maintenance/WorkOrdersPage.jsx` | Consultation et gestion des ordres de travail. |
| `src/services/workOrderService.js` | Appels API de création, lecture, mise à jour d’OT et dépôt de rapport. |
| `src/services/sensorService.js` | Lecture des capteurs et mesures utilisée notamment par What-if et l’assistant vocal. |

### Tests pertinents

| Fichier | Couverture observée |
|---|---|
| `apps/equipements/tests/test_skab_ml.py` | Découpage par fichier, plis groupés, fenêtrage temporel irrégulier et règles de détection/manqué. |
| `apps/equipements/tests/test_inspections.py` | API d’inspection, permissions, analyse simulée/erreurs, champs de résultat et annotations. |
| `apps/equipements/tests/test_sensors_readings.py` | API des capteurs/mesures et imports utilisés comme source des calculs statistiques. |
| `apps/equipements/tests/test_readings_websocket.py` | Abonnement WebSocket authentifié aux mesures; pas un test du score IA. |
| `apps/accounts/tests/test_auth.py` | Authentification, comptes et rôles; ne teste pas le raisonnement vocal. |
| `apps/accounts/tests/test_audit_log.py` | Journal d’audit et contrôle des mutations, incluant l’endpoint vocal comme mutation HTTP. |
| `src/tests/pages/InspectionsPage.test.jsx` | Comportements de la page d’inspections. |
| `src/tests/components/InspectionResultCard.test.jsx` | Rendu des résultats de vision. |
| `src/tests/components/InspectionHistoryTable.test.jsx` | Rendu de l’historique visuel. |
| `src/tests/components/ImageUploadDropzone.test.jsx` | Téléversement d’images côté interface. |

Aucun test backend dédié à l’API `AnomalyAnalysisAPIView`, `WhatIfAPIView`, au chargement/inférence C-MAPSS ou à l’API de catalogue des modèles n’a été trouvé dans les chemins de tests parcourus. Aucun test frontend dédié à `PredictionsIaPage.jsx` ou au pipeline vocal n’a été trouvé.

## 2. Flux de données par fonction IA

### Score statistique d’anomalie

`Machine sélectionnée` → capteurs actifs visibles dans le périmètre + mesures valides sur les dernières 24 h → `_score()` utilise les seuils capteur et la dispersion/statistiques récentes → `GET /api/ai-predictions/anomalies/?machine_id=…` → `getAnomalyAnalysis()` → `PredictionsIaPage.jsx` (courbe, score, contributeurs, historique des alertes).

Le score est calculé à la volée; il ne charge pas un modèle entraîné et ne crée pas d’alerte IA. L’historique rendu par le même endpoint provient des alertes persistées.

### Prédiction RUL C-MAPSS

`Fichier C-MAPSS choisi et moteur sélectionné` → parsing du fichier texte dans React, extraction de l’historique des dernières lignes → validation du cycle et des matrices de 24 nombres → features de fenêtre dans `cmapss_ml.py` → modèle `cmapss_rul.joblib` → `POST /api/predictive-maintenance/` → `predictiveMaintenanceService.js` → `PredictionsIaPage.jsx` affiche les cycles estimés et l’état de santé.

Le fichier importé dans l’interface est le jeu de test NASA, pas une série de mesures SmartFactory. Le backend ne convertit pas automatiquement les capteurs de l’usine en entrées C-MAPSS.

### Simulation What-if

`Capteur choisi + variation %` → dernière mesure valide et jusqu’à 500 valeurs récentes du capteur → calcul du score statistique avant/après sur la valeur modifiée en mémoire → `POST /api/ai-predictions/what-if/` → `simulateWhatIf()` → carte d’impact What-if dans `PredictionsIaPage.jsx`.

La simulation ne persiste pas la valeur et ne prédit pas le RUL.

### Inspection visuelle

`Machine + image importée` → ligne `InspectionVisuelle` avec image et utilisateur → `POST /api/equipements/inspections/{id}/analyze/` (alias `/api/inspections/{id}/analyze/`) → sélection de `mock` ou `yolo` via `VISION_AI_BACKEND` → résultat sauvegardé dans `resultat_analyse`, champs de défaut/confiance/observation → `inspectionService.js` → historique, détail et carte de résultat dans `InspectionsPage.jsx`.

Le backend `mock` est déterministe à partir du hash du fichier, mais ne fait pas de vision. Le backend YOLO charge les poids pointés par `VISION_AI_MODEL_PATH`, détecte des classes et retourne boîtes/localisation; aucun poids YOLO n’est présent dans `ml/artifacts/` listé.

Annotation manuelle : `image + annotations JSON` → `POST .../{id}/annotate/` → image annotée et annotations sauvegardées sur l’inspection → éditeur/détail React. Cette annotation n’entraîne pas le modèle YOLO.

### Assistant vocal

`Micro ou saisie texte` → reconnaissance vocale du navigateur (`SpeechRecognition` / `webkitSpeechRecognition`) → texte → NLU à expressions régulières dans `VocalPage.jsx` → appels API REST de lecture (machines, capteurs, mesures, alertes), ou proposition d’action → confirmation oui/non → POST/PATCH d’acquittement, d’OT, de statut ou dépôt de rapport → réponse texte + synthèse vocale navigateur (`speechSynthesis`) → enregistrement séparé du texte/intention/confiance/résultat via `POST /api/auth/vocal/commands/`.

Le NLU et le pipeline sont côté client; il n’y a pas de modèle LLM ni de reconnaissance vocale backend. Pour les commandes de RUL, l’assistant répond explicitement qu’il ne peut pas fournir de valeur fiable à partir des capteurs d’usine et ne simule pas un résultat.

### Benchmarks MetroPT-3 et SKAB

MetroPT-3 : `CSV de benchmark` → `ml/train_metropt.py` / `metropt_ml.py` → modèle et rapport → lecture du statut/métriques depuis `AiModelsAPIView` → onglet « Modèles » de `PredictionsIaPage.jsx`. Aucun flux de mesures SmartFactory ne passe dans `metropt3_anomaly_detector.joblib` via cette vue.

SKAB : `CSV SKAB` → `ml/train_skab.py` / `skab_ml.py` → comparaison IF, HistGradientBoosting et référence médiane/MAD → `.joblib` + rapport JSON. Aucun endpoint n’appelle `skab_artifact_status()` ou le modèle; aucun écran ne reçoit actuellement ses métriques depuis l’API.

## 3. Modèles réellement chargés et utilisés par l’API

| Modèle/artefact | État d’utilisation API |
|---|---|
| `cmapss_rul.joblib` — HistGradientBoostingRegressor | **Chargé et utilisé pour la prédiction** via `POST /api/predictive-maintenance/`. Le chargement passe par un cache LRU dans `cmapss_ml.py`. Le statut RUL est également exposé par GET. |
| YOLO (`.pt` configuré à part) | **Chargé et utilisé seulement si** `VISION_AI_BACKEND=yolo` et `VISION_AI_MODEL_PATH` désigne des poids valides. Chargement caché. Le backend par défaut observé est `mock`; aucun poids YOLO n’a été listé sous `ml/artifacts/`. |
| Mock Vision | Appelé comme service configuré par défaut. **Ce n’est pas un modèle entraîné** : résultat déterministe fondé sur le hash des octets d’image. |
| `metropt3_anomaly_detector.joblib` — IsolationForest | **Lu pour le statut et les métriques** par `AiModelsAPIView`; pas d’inférence via API sur les capteurs de machines SmartFactory. Le statut effectue le chargement joblib à la demande, sans cache explicite. |
| `metropt3_status_classifier.joblib` | **Aucun chargement ni appel trouvé** dans le code applicatif audité; artefact non utilisé par l’API. |
| `skab_anomaly_detector.joblib` | **Non utilisé par l’API.** `skab_artifact_status()` existe, mais aucune vue ne l’appelle; la page ne présente pas le modèle SKAB dans son catalogue courant. |
| Score statistique | **Utilisé par l’API**, mais ce n’est pas un modèle entraîné/artefact : calcul dynamique `_score()` avec seuils et statistiques des lectures. |
| LSTM Autoencoder affiché | Marqué non entraîné; pas de service ni d’inférence active trouvé dans cette page API. |

## 4. Modèle de données des capteurs

### Machine

`Machine` contient notamment `nom`, `identifiant_interne` unique, numéro de série, type d’équipement, marque, modèle, date d’installation, position, statut, description et relation optionnelle `ligne_production` vers `LigneProduction` (qui mène à zone/usine). Une machine possède plusieurs capteurs par la relation inverse `Machine.capteurs`.

### Sensor

Champs présents :

- `identifiant` unique, `nom`, `type_capteur`;
- `machine` : ForeignKey obligatoire vers `Machine`, `related_name='capteurs'`;
- `unite`, `frequence_mesure` (en secondes), `seuil_min`, `seuil_max`;
- `actif`, `description`, `created_at`, `updated_at`.

Types codés : `TEMPERATURE`, `VIBRATION`, `PRESSION`, `COURANT`, `VITESSE_RPM`, `DEBIT`, `NIVEAU_SONORE`. La validation exige seuil minimum inférieur au maximum et fréquence positive.

### Reading (mesure)

Champs : ForeignKey `sensor` vers `Sensor` (`Sensor.lectures`), `valeur`, `timestamp`, `created_at`, `hors_plage`, `est_valide`, `interpolation`. Une mesure appartient donc indirectement à une machine par `Reading.sensor.machine`.

### Rôle capteur / plage nominale

Il n’existe **pas** de champ `rôle`/`position fonctionnelle` permettant de distinguer, par exemple, température moteur de température fluide ou vibration 1 de vibration 2. Il n’existe pas non plus de champ `plage_nominale` séparé. `seuil_min`/`seuil_max` sont des seuils opérationnels génériques; ils ne constituent pas une plage nominale certifiée ou une plage de validité du modèle SKAB. `unite` est librement stockée et ne garantit pas conversion ni conformité d’unité.

## 5. Relation entre anomalie, alertes et ordres de travail

- Le score statistique IA de l’endpoint anomalies est calculé à la demande et renvoyé avec ses contributeurs. Il ne crée pas de ligne `Alerte`.
- Les alertes automatiques actuelles viennent du signal `post_save` d’une **nouvelle mesure** et de `apps/alertes/engine.py`, qui compare sa valeur aux `seuil_min`/`seuil_max` du capteur.
- `Alerte.lecture` relie une alerte de seuil à la mesure déclenchante; `Alerte.capteur` et `Alerte.machine` gardent aussi les relations directes. `anomalie_ia_score` est nullable et documenté comme réservé; le score IA courant ne le renseigne pas.
- Une alerte peut être acquittée/résolue. La création d’un OT lié est une action explicite `preparer-ot` qui renseigne `OrdreTravail.from_alert` (identifiant d’alerte, pas ForeignKey). Elle n’est pas déclenchée automatiquement par le score IA.
- L’assistant vocal peut acquitter une alerte ou demander la création d’un OT après confirmation explicite. L’API et les rôles restent les barrières d’autorisation; l’opérateur ne peut pas créer/modifier un OT depuis ce flux.
- Les inspections sont reliées à une machine et à l’utilisateur, mais aucun lien ForeignKey vers une alerte ou un OT n’a été trouvé dans `InspectionVisuelle`.

## 6. Dettes techniques et risques

1. **Interopérabilité des capteurs non démontrée :** types génériques, unités libres, absence de rôle et plages nominales. Un modèle benchmark ne peut pas être appliqué sans mapping explicite, contrôles d’unités et validation des plages.
2. **Résultats de référence transposés abusivement :** C-MAPSS est un turbofan simulé; MetroPT-3 un compresseur ferroviaire; SKAB un banc de pompe/circuit. Leurs scores ne mesurent pas les performances sur les équipements SmartFactory.
3. **Valeurs codées en dur :** seuil d’anomalie `0.65`, fenêtre récente de 24 h, limites de lectures, pondérations/formule `_score`, variations What-if `−100 % à +300 %`, seuils de santé RUL (30/80 cycles), et logique mock de vision (~60 % selon hash). Elles sont dans le code ou la configuration, pas dans un registre de politiques/versionné.
4. **Modèle d’alerte IA inachevé :** le type `ANOMALIE_IA` et le champ `anomalie_ia_score` existent mais le moteur d’alertes ne les renseigne pas. Aucun événement du score statistique, C-MAPSS, YOLO ou benchmark ne crée aujourd’hui une alerte unifiée.
5. **Chaîne OT partiellement couplée :** la relation `from_alert` est un entier nullable plutôt qu’une ForeignKey; le lien inspection/prédiction→alerte→OT n’est pas normalisé ni généralisé.
6. **Versionnage/traçabilité modèles :** les artefacts sont des fichiers `.joblib` locaux; le code ne montre pas de registre de modèles/versions déployées, empreinte de l’artefact, provenance attachée à chaque prédiction, ni stratégie d’activation/rollback. Les rapports JSON de benchmark sont distincts des prédictions opérationnelles.
7. **Chargement hétérogène :** C-MAPSS utilise un cache par chemin/mtime; YOLO un cache local; MetroPT relit l’artefact pour le statut; SKAB n’est pas branché. Il faut harmoniser cycle de vie, erreurs d’indisponibilité et health check.
8. **Pas de journal persistant des prédictions génériques :** l’inspection persiste ses résultats et l’assistant vocal persiste le texte/résultat, mais le score statistique, What-if et RUL ne créent pas d’enregistrement métier horodaté avec modèle/version, entrée/référence, résultat et décision.
9. **Assistant vocal à règles côté navigateur :** couverture NLU limitée aux motifs prévus, dépendance aux APIs du navigateur, reconnaissance et synthèse non portables partout; l’historique stocke texte de commande et résultat (données potentiellement sensibles), sans audio.
10. **Tests IA déséquilibrés :** tests présents sur pipeline SKAB, inspections/mock et mesures; tests dédiés absents pour endpoints statistiques/What-if/catalogue, chargement/cache et prédiction C-MAPSS, inference YOLO réelle, pipeline NLU vocal et permissions/intégration complètes de commandes vocales.
11. **Contrôle des données en entrée :** l’API RUL valide la forme numérique, mais les valeurs sont principalement bornées très largement; aucune validation sémantique de capteur ou de distribution machine n’est réalisée.
12. **Artefacts benchmark potentiellement non reproductibles côté clone :** leur présence locale ne garantit pas présence dans le dépôt ou environnement déployé; la disponibilité dépend des fichiers ignorés/localement installés et de leur compatibilité de versions Python/scikit-learn/joblib.

### Synthèse : constat → risque → correction proposée

| Constat | Risque | Correction proposée |
|---|---|---|
| Modèle et type capteur ne partagent ni rôle explicite ni contrat d’unité | Mauvaise colonne injectée ou prédiction hors domaine | Ajouter un mapping de rôles par machine/capteur, dictionnaire d’unités/conversions contrôlées, validation bloquante et statut « données insuffisantes ». |
| Scores C-MAPSS/MetroPT-3/SKAB proviennent de domaines externes | Présenter un benchmark comme performance industrielle | Afficher source, domaine et avertissement; ne promouvoir un modèle qu’après validation machine/site sur jeu indépendant. |
| Score statistique est un calcul ad hoc avec constantes codées | Seuils opaques, variation de comportement difficile à auditer | Externaliser et versionner les paramètres; documenter/calibrer le score et tester ses cas limites. |
| Champ `anomalie_ia_score` réservé, non alimenté | Pas d’alerte IA traitable dans le workflow existant | Définir un contrat d’alerte IA (source, score, seuil, modèle/version, mesure), anti-duplication, acquittement et résolution. |
| `OrdreTravail.from_alert` est un entier et liens inspection/IA absents | Références orphelines, traçabilité faible | Remplacer par relations explicites et relier l’événement IA/inspection à l’alerte et à l’OT avec règles de création explicites. |
| RUL/What-if/anomalies ne sont pas journalisés | Résultat passé impossible à reproduire ou expliquer | Créer un journal de prédiction horodaté : source, modèle/version/hash, entrées/références, résultat, utilisateur et corrélation alerte/OT. |
| Artefacts lus avec stratégies différentes, modèles non versionnés | Démarrage fragile, rollback/débogage difficiles | Registre/version de modèle, vérification de hash/schéma/dépendances au démarrage, cache uniforme, health check et procédure de rollback. |
| Pas de tests dédiés pour plusieurs endpoints IA et la voix | Régression silencieuse et permissions non garanties | Ajouter tests unitaires/API sur valeurs manquantes, unités, erreurs artefact, rôle, seuils, confirmation et journal; tests YOLO conditionnels aux poids disponibles. |
| Assistant vocal fondé sur regex et APIs navigateur | Compréhension incomplète, compatibilité variable et confusion d’intention | Afficher les intentions prises en charge, seuil de confiance, confirmation pour actions, tests navigateurs et tests de sécurité par rôle. |
| Scores benchmark/test élevés mais échantillons limités et déséquilibrés | Fausse confiance, dérive et performances dégradées sur site | Évaluer sur données représentatives collectées en usine, split temporel par machine, suivi précision/rappel/FPR/délai et validation humaine avant exploitation. |
