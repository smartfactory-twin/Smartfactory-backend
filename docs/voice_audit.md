# Audit de l’assistant vocal — SmartFactory Twin

Audit statique du dépôt au 20 novembre 2026. Aucun appel réseau à l’application ni aucune mesure de taille de réponse en production n’a été effectué. Les tailles indiquées ci-dessous sont donc des ordres de grandeur déduits des sérialiseurs et de la pagination, pas des mesures observées.

## 1. Fichiers liés à l’assistant vocal

| Fichier | Rôle actuel |
|---|---|
| `Smartfactory-frontend/src/pages/vocal/VocalPage.jsx` | Écran, Web Speech API, NLU par expressions régulières, appels métier, confirmation locale, dictée de rapport et synthèse vocale. Il n’existe pas de hook vocal séparé. |
| `Smartfactory-frontend/src/services/voiceService.js` | Lit et enregistre l’historique via `/auth/vocal/commands/`. |
| `Smartfactory-frontend/src/services/api.js` | Axios partagé ; ajoute le JWT d’accès dans `Authorization: Bearer …` et renouvelle le token après un 401. |
| `Smartfactory-frontend/src/routes/AppRouter.jsx` | Déclare `/assistant-vocal` derrière `ProtectedRoute` (utilisateur authentifié, tous rôles). |
| `Smartfactory-frontend/src/context/AuthContext.jsx` | Fournit le rôle et le profil utilisés par l’écran vocal. |
| `Smartfactory-frontend/src/components/layout/AdminLayout.jsx` | Conteneur affiché à l’administrateur. |
| `Smartfactory-frontend/src/components/layout/TechnicianLayout.jsx` | Conteneur affiché au technicien. |
| `Smartfactory-frontend/src/components/layout/OperatorLayout.jsx` | Conteneur affiché à l’opérateur. |
| `Smartfactory-backend/apps/accounts/models.py` | Modèles `VocalCommand` et utilisateur ; l’historique ne conserve pas l’audio. |
| `Smartfactory-backend/apps/accounts/serializers.py` | Champs exposés et validation du journal vocal. |
| `Smartfactory-backend/apps/accounts/views.py` | `VocalCommandHistoryView` : lecture privée, lecture globale ADMIN, création d’une entrée pour l’utilisateur connecté. |
| `Smartfactory-backend/apps/accounts/urls.py` | Route `vocal/commands/`. |
| `Smartfactory-backend/apps/accounts/migrations/0006_vocal_command_history.py` | Création de la table et de l’index par utilisateur/date. |
| `Smartfactory-backend/apps/accounts/middleware.py` | Journalise les mutations API, sans stocker le corps de requête. |
| `Smartfactory-backend/apps/accounts/tests/test_audit_log.py` | Vérifie notamment l’audit d’un POST vers l’historique vocal et l’absence du corps de requête dans le journal d’audit. Ce n’est pas un test de compréhension vocale. |
| `Smartfactory-backend/core/urls.py` | Monte `/api/auth/`, les API métier et les routes de prédiction utilisées par les outils vocaux actuels ou proposés. |
| `Smartfactory-backend/apps/equipements/urls.py` | Routes machines, capteurs, mesures et ordres de travail. |
| `Smartfactory-backend/apps/alertes/urls.py` | Routes alertes et notifications. |
| `Smartfactory-backend/apps/equipements/permissions.py` | Contrôle des rôles et des périmètres `UserScope` pour équipements, mesures et ordres de travail. |
| `Smartfactory-backend/apps/alertes/permissions.py` | Rôles et périmètres des alertes. |
| `Smartfactory-backend/apps/equipements/ai_prediction_views.py` | Endpoints d’anomalie statistique, What-if et statut des modèles. |
| `Smartfactory-backend/apps/equipements/predictive_views.py` | Endpoint RUL C-MAPSS. |
| `Smartfactory-backend/apps/equipements/ml_serializers.py` | Contrat d’entrée C-MAPSS : cycle et historique de lignes de 24 valeurs. |
| `Smartfactory-backend/apps/accounts/tests/test_auth.py` | Tests généraux d’authentification et de permissions ; aucun test dédié au NLU vocal n’y est identifié. |

Recherche effectuée dans `src/tests` et les tests backend : aucun test frontend dédié à `VocalPage`/`voiceService`, à la reconnaissance vocale, aux intentions, aux confirmations vocales ou aux actions déclenchées par la voix n’a été trouvé. Le test d’audit ci-dessus ne couvre que le journal API.

## 2. Flux vocal actuel et commandes reconnues

### Flux

1. **Micro ou saisie** : le bouton micro utilise `window.SpeechRecognition` ou `window.webkitSpeechRecognition`. La saisie texte passe directement au même traitement.
2. **Transcription** : reconnaissance du navigateur configurée en `fr-FR`, sans résultats intermédiaires, une alternative, une seule phrase. Le texte et le score de confiance renvoyés par le navigateur sont utilisés. Aucun fichier audio n’est envoyé à Django par l’écran.
3. **Filtre de confiance** : sous `0,7`, l’écran demande une reformulation et journalise ce résultat.
4. **NLU** : `nlu()` applique une suite ordonnée de regex/mots-clés dans `VocalPage.jsx`. Ce n’est ni un LLM ni un modèle entraîné.
5. **Lecture** : le frontend appelle les services machines, capteurs, mesures, alertes ou OT. L’API Django applique ses propres permissions et filtres de périmètre.
6. **Écriture** : l’écran affiche une confirmation locale. Après « oui », il envoie l’appel métier ; après « non », il annule l’état local. La dictée du rapport est recueillie dans un brouillon éditable puis sauvegardée via un formulaire.
7. **Réponse** : réponse texte ajoutée à la conversation. Si l’option est activée, `SpeechSynthesisUtterance` la lit avec `fr-FR`.
8. **Historique** : le frontend poste texte, intention, confiance et résultat à l’API d’historique. Aucun audio n’est sauvegardé.

La reconnaissance et la synthèse dépendent des capacités du navigateur et de sa plateforme. Le dépôt ne permet pas d’établir si le navigateur choisi traite l’audio localement ou via un fournisseur externe.

### Intentions, déclencheurs et limites exactes du code

| Intention interne | Déclencheur détecté / action réalisée |
|---|---|
| `yes` | Texte entier égal à `oui`, `confirm`, `ok`, `d'accord`, `vas-y` ou `vas y` (ponctuation finale tolérée par la seconde regex). N’exécute une action que si `pendingAction` existe dans l’écran. |
| `no` | Texte entier égal à `non`, `annule` ou `stop` (ponctuation finale tolérée). Annule seulement l’action en attente côté interface. |
| `ack_alert` | Toute présence de `acquitte`. Extraction numérique de l’alerte après le mot `alerte`; le reste est pris comme commentaire. Numéro et commentaire sont obligatoires avant confirmation dans l’interface. |
| `create_work_order` | Une phrase contenant `crée/créée`, `ouvre` ou `lance`, puis `ordre de travail` ou `OT`. Extrait la machine (`POMPE-001`, `M20`, etc.), le type (correctif/préventif/conditionnel) et la priorité (haute/moyenne/basse/urgent). Valeurs par défaut : correctif et moyenne. |
| `dictate_report` | Toute phrase contenant `dictée`. Extrait un identifiant si elle mentionne `OT 87` ou `ordre de travail 87`; après confirmation, lit l’OT, puis recueille le texte dans un brouillon. « terminer la dictée » ou « fin de dictée » arrête la collecte. |
| `set_work_order_status` | Une phrase avec `passe`, `mettre`, `change`, `changer` ou `avance`, un numéro d’OT, puis un statut reconnu : Assigné, En cours, En attente pièces, Rapport déposé, Validé ou Clôturé. Le backend impose également la séquence du workflow et réserve validation/clôture à ADMIN. |
| `get_rul` | Présence de `rul`, `combien d’heures`, `combien de cycles`, `durée de vie` ou `avant la panne`. Le code répond explicitement qu’il ne peut pas donner de RUL fiable pour une machine SmartFactory. |
| `get_sensor_value` | Présence de température, vibration, pression, courant, vitesse/RPM, débit ou bruit. Exige une machine reconnue, choisit le premier capteur dont nom/type contient le mot, puis lit la mesure la plus récente. |
| `list_alerts` | Présence de `alerte(s)`, renvoie au plus cinq alertes actives récentes ; filtre optionnel sur critique, avertissement, information, mineure ou majeure. |
| `get_machine_status` | Présence de état/état, statut ou santé et référence de machine ; lit le statut de la machine. |
| `unknown` | Toute autre demande ; demande une reformulation. |

La détection prend la première règle correspondante dans l’ordre du code. Elle ne comprend pas librement les paraphrases, les dates relatives, les comparaisons ou les demandes multi-étapes. Exemples de l’écran : état machine, RUL, alertes critiques, température, acquittement avec commentaire, création d’OT prioritaire, dictée d’OT.

## 3. Confirmations et droits

- **Interface** : les confirmations et les contrôles d’action sont dans `VocalPage.jsx`, avec un unique `pendingAction` en mémoire. L’état disparaît si la page est rechargée ou quittée ; aucune expiration serveur n’est associée à la proposition. L’opérateur est bloqué dans l’interface pour créer/modifier un OT ou dicter un rapport. Il peut acquitter une alerte.
- **Backend** : les endpoints métier vérifient indépendamment le JWT, le rôle et le périmètre `UserScope`. Un ADMIN a accès global ; techniciens et opérateurs voient les machines de leurs affectations. Les endpoints de mutation d’OT sont réservés à ADMIN/TECHNICIEN ; l’acquittement d’alerte est permis à ADMIN, TECHNICIEN et OPERATEUR, avec contrôle de périmètre et commentaire obligatoire.
- **Contourner les droits ?** Un appel sans JWT ou hors rôle/périmètre est refusé par le backend ; le contrôle n’est donc pas seulement visuel.
- **Contourner la confirmation ?** Oui. Les endpoints métier n’exigent ni identifiant de proposition ni preuve de confirmation. Un client authentifié autorisé peut appeler directement `POST /api/alertes/{id}/acquitter/`, créer/modifier un OT ou déposer un rapport sans passer par le dialogue vocal. La confirmation actuelle améliore l’UX, mais n’est pas une barrière backend.
- **Journal** : le middleware audite les mutations `/api/` (acteur, rôle, route, statut HTTP, IP, agent utilisateur) sans corps de requête. Cela ne constitue pas un journal de l’appel LLM : aucun LLM ni outil d’agent n’existe encore.

## 4. API existantes pouvant servir d’outils

Toutes les routes ci-dessous sont sous `http://localhost:8000` en local et nécessitent `Authorization: Bearer <JWT>`. Les tailles exactes n’ont pas été mesurées. Les tailles sont qualitatives et dérivées du schéma : objets individuels généralement petits, listes plus grandes et paginées (20 éléments par défaut, sauf mention). Le code d’un outil futur devrait sélectionner quelques champs utiles et limiter explicitement les lignes retournées.

| Fonction / méthode et URL | Permission et périmètre | Entrée / filtres | Réponse et taille indicative |
|---|---|---|---|
| Machines — `GET /api/equipements/machines/`, `GET /api/equipements/machines/{id}/` | Tous rôles authentifiés en lecture ; ADMIN global, TECHNICIEN/OPERATEUR limité à `UserScope`. | `search` cherche nom, identifiant interne, numéro de série ; filtres statut/type/ligne/zone/usine ; détail par ID. | Liste paginée, env. 20 objets par défaut ; détail contient statut, ligne, dernière mesure et documents/composants : objet de quelques KB selon ces listes. |
| Capteurs — `GET /api/equipements/capteurs/`, `GET /api/equipements/capteurs/{id}/` | Tous rôles en lecture, dans le périmètre machine. Écriture différente : ADMIN complet, TECHNICIEN PUT/PATCH, OPERATEUR lecture seule. | `machine`, `type_capteur`, `actif`, `search` (identifiant/nom/machine). | Liste paginée d’objets de capteurs ; détail inclut unité, seuils et métadonnées IA ; tailles faibles par capteur, variables pour les pages. |
| Mesures — `GET /api/equipements/readings/` (alias métier `GET /api/readings/`) | ADMIN lecture ; TECHNICIEN lecture/ingestion/modification ; OPERATEUR lecture. Périmètre capteur-machine appliqué au backend. | `sensor`, `sensor__machine`, `timestamp__gte/lte/gt/lt`, `ordering`; pagination propre : 25 par défaut, `page_size` jusqu’à 200. | Champs mesure, valeur, horodatage, validité et capteur. Taille croît avec `page_size`; outil conseillé : ≤20 lignes et champs minimaux. |
| Alertes — `GET /api/alertes/`, `GET /api/alertes/{id}/` | ADMIN/TECHNICIEN lecture et actions ; OPERATEUR lecture ; toujours limitées aux machines du périmètre. | filtres `niveau`, `statut`, `type_alerte`, `machine`, `capteur`, dates ; `search` sur référence/message/machine/capteur ; `ordering`. | Liste paginée (20 par défaut), liste compacte ; détail ajoute contexte de mesure et acquittement. Taille d’un élément dépend notamment du texte libre `message`. |
| Acquitter — `POST /api/alertes/{id}/acquitter/` | ADMIN, TECHNICIEN, OPERATEUR si alerte dans son périmètre ; alerte encore acquittable. | JSON `{"commentaire":"…"}` obligatoire et non vide. | Détail de l’alerte après mutation, objet compact mais avec message libre. L’API ne demande pas de confirmation préalable. |
| Préparer OT depuis alerte — `POST /api/alertes/{id}/preparer-ot/` | ADMIN/TECHNICIEN ; opérateur refusé ; périmètre alerte vérifié. | ID d’alerte dans l’URL, pas de corps requis. | Résumé d’alerte et objet OT ; crée ou retrouve l’OT. C’est une écriture à confirmer si exposée à un agent. |
| Ordres de travail — `GET /api/equipements/ordres-travail/`, `GET /api/equipements/ordres-travail/{id}/` | Tous les rôles en lecture ; scope par machine. | `machine`, `statut`, `type_ordre`, `priorite`; `search` sur titre/machine/assigné; tri/pagination. | Liste paginée, détail contient aussi historique et rapport JSON libre ; taille peut croître avec historique/rapport. |
| Créer OT — `POST /api/equipements/ordres-travail/` | ADMIN/TECHNICIEN seulement, périmètre machine revérifié. | `machine_id`, `type` (optionnel), `priorite`, `titre`, `assigne`, `statut`, `echeance`, `from_alert` selon sérialiseur. Le vocal actuel envoie machine, type, priorité, titre, assigné. | Sérialiseur d’un OT. Écriture à confirmation backend nécessaire. |
| Modifier OT — `PATCH /api/equipements/ordres-travail/{id}/` | ADMIN/TECHNICIEN seulement, scope vérifié sur l’OT et la machine. | Champs partiels, dont `statut`; changement de statut doit suivre l’étape suivante. Validation/clôture réservées ADMIN. | Sérialiseur OT, dont historique. Le vocal envoie actuellement `{statut: …}`. |
| Rapport d’intervention — `POST /api/equipements/ordres-travail/{id}/rapport/` | ADMIN/TECHNICIEN seulement ; OT dans le périmètre et statut En cours/En attente pièces. | `travaux`, `duree`, `observations`, `pieces`, `signataire`. Dépose le rapport et passe l’OT à Rapport déposé. | Sérialiseur OT incluant le rapport. Les chaînes libres doivent être bornées avant modèle et journal. |
| Anomalies — `GET /api/ai-predictions/anomalies/?machine_id={id}` | Authentifié ; machine/capteurs filtrés au périmètre. | `machine_id`. | Score statistique, jusqu’à 60 points d’historique, contributeurs et jusqu’à 30 alertes des dernières 24 h ; résultat plus volumineux qu’un objet métier. |
| What-if — `POST /api/ai-predictions/what-if/` | Authentifié ; capteur filtré au périmètre. | `sensor_id`, `variation_percent` entre −100 et +300. | Petit résumé avant/après ; simulation statistique, ne modifie aucune mesure et ne prédit pas le RUL. |
| Statut modèles — `GET /api/ai-predictions/models/` | Tout utilisateur authentifié. | Aucun. | Liste courte des modèles et métadonnées/benchmarks. |
| RUL C-MAPSS — `POST /api/predictive-maintenance/` | Authentifié ; le schéma d’entrée ne porte pas de machine et la vue n’applique pas de scope machine. | `cycle` et `history`, matrice de 1 à 500 lignes de 24 valeurs numériques (3 réglages + 21 capteurs C-MAPSS). | Résultat RUL C-MAPSS. Ce n’est pas une RUL de machine SmartFactory. Outil proposé : répondre « non disponible pour cette machine » tant qu’un modèle et une correspondance valides ne sont pas établis. |
| Santé machine — `GET /api/reports/health/?machine_id={id}&days=30` | Authentifié ; contrôle de périmètre effectué dans la vue. | `machine_id` obligatoire ; `days` vaut 7 ou 30 (30 par défaut). | Agrégat par capteur, compteurs OT/alertes et indice santé nullable ; petite réponse par machine, taille dépend du nombre de capteurs. |

**Regroupements non fournis directement par l’API :** « quelle machine a eu le plus d’alertes cette semaine ? » n’a pas d’agrégation par machine dédiée. `GET /api/alertes/statistiques/` compte par niveau/statut, pas par machine ; il faudrait parcourir les pages filtrées par dates avec un plafond et calculer côté outil, ou ajouter plus tard une API agrégée. Ne jamais prétendre avoir compté toutes les alertes si la pagination ou le plafond a tronqué le jeu.

## 5. Historique vocal et stockage

Modèle `VocalCommand` dans PostgreSQL (`apps/accounts/models.py`), table créée par `0006_vocal_command_history.py` :

- `id` : clé primaire ;
- `utilisateur` : clé étrangère vers l’utilisateur, suppression en cascade ;
- `texte` : texte utilisateur, maximum 1 000 caractères ;
- `intention` : chaîne, maximum 80 caractères ;
- `confiance` : flottant nullable, validé entre 0 et 1 ;
- `resultat` : chaîne, maximum 1 000 caractères ;
- `created_at` : date de création ; index par utilisateur et date.

Le GET renvoie au plus les 100 entrées les plus récentes : l’utilisateur voit ses entrées, ADMIN peut lire le journal global. Le POST authentifié attribue l’entrée à l’utilisateur connecté. Le frontend tronque les champs texte avant envoi. Le modèle ne conserve ni audio, ni transcription segmentée, ni outils appelés, paramètres, latence, identifiant de confirmation ou version du modèle. Un POST est aussi visible dans `AuditLog` comme mutation, mais le middleware exclut intentionnellement le corps.

## 6. Risques d’un agent LLM

- **Injection via données métier** : `Alerte.message`, noms/titres de machines et d’OT, commentaire d’acquittement, observations et rapport sont des données libres. Ils ne doivent jamais être fusionnés aux instructions système ni interprétés comme des consignes.
- **Données sensibles** : le fournisseur LLM pourrait recevoir des noms d’actifs, valeurs/horodatages, alarmes, rapports de maintenance, noms d’utilisateurs et commentaires. Ne transmettre que les champs strictement requis ; anonymiser les personnes et ne pas envoyer les credentials, JWT, pièces jointes ou secrets industriels.
- **Périmètre** : ne pas chercher l’objet en ORM avec des privilèges serveur globaux. Tout outil doit agir sous l’identité et les droits du demandeur. Les endpoints RUL C-MAPSS actuels ne sont pas liés à une machine réelle.
- **Confirmation non serveur** : une confirmation React seule est contournable par appel API direct ; chaque écriture agent doit passer par une proposition serveur à durée limitée, liée au demandeur et à une action immuable.
- **Limites de débit** : DRF a des plafonds génériques `anon=100/hour`, `user=1000/hour`, plus des limites dédiées login/réinitialisation. Aucun quota dédié à l’agent, au coût LLM ou à la transcription n’est défini. Ajouter throttling par utilisateur et garde-fous de coût/durée.
- **Journal d’outils absent** : l’audit HTTP générique consigne les mutations et leur statut, pas les appels de lecture ni les paramètres/résultats d’outils. Créer une trace agent dédiée, sans audio ni secrets, avec politique de conservation.
- **Réponses volumineuses** : alertes et OT contiennent des champs texte libres et pagination ; l’API d’anomalie peut inclure 60 points et 30 alertes. Whitelister les champs, limiter les lignes, les caractères et les tokens envoyés au modèle.
- **Données anciennes/incohérentes** : mesure courante, statut machine et état d’alerte doivent porter une date/heure et une source. L’agent doit dire qu’il ne sait pas si les API ne fournissent pas la donnée ou si le plafond est atteint.
- **Actions répétées** : une relance réseau ou un double clic peut créer plusieurs OT. Les écritures doivent être à usage unique/idempotentes ou détecter les doublons.
- **Absence de tests vocaux** : aucune couverture identifiée du NLU, des ambiguïtés, des droits par outil, des confirmations ou des injections.

## 7. Déploiement actuel et place possible du service Whisper

`Smartfactory-backend/docker-compose.yml` déclare trois services :

1. `db` : PostgreSQL 16, port local 5432 et volume persistant `postgres_data` ;
2. `backend` : image Python 3.12, Django migré au démarrage, compte de démonstration initialisé, Daphne/ASGI sur le port 8000 ; dépend de la base saine ;
3. `frontend` : construit depuis `../Smartfactory-frontend`, publié sur 5173, dépend du backend.

Le backend reçoit `.env` et définit `DB_HOST=db` dans Compose. `.env.example` porte notamment configuration Django, PostgreSQL, URL/CORS, SMTP, vision, chemin du modèle C-MAPSS. Aucun service Whisper, endpoint audio, variable `WHISPER_*`/LLM, package `faster-whisper`, `openai`, `groq` ou `anthropic` n’est présent dans les fichiers de dépendances examinés. Le frontend possède seulement `VITE_API_BASE_URL` (défaut `/api`).

Place cohérente pour un futur conteneur : ajouter un service `transcription` dédié au Compose, isolé du réseau public, et faire appeler son API par Django (ou via un proxy authentifié). Seul Django devrait posséder les identifiants applicatifs et transmettre un fichier audio temporaire limité en durée/taille. Pour servir le frontend, préférer `POST /api/voice/transcribe/` côté Django qui relaie vers FastAPI, afin de ne pas exposer un port Whisper public ni une clé dans Vite. Ce service n’existe pas encore.

## 8. Constat → risque → correction proposée

| Constat | Risque | Correction proposée |
|---|---|---|
| NLU par regex dans le composant React | Demandes naturelles, négations et ambiguïtés mal classées. | Agent Django avec schémas d’outils stricts ; garder le NLU existant comme repli temporaire. |
| Web Speech API fournit micro et transcription | Disponibilité, qualité et traitement audio dépendent du navigateur. | Endpoint de transcription maîtrisé, limites de fichier, consentement et politique de rétention ; fallback explicitement indiqué. |
| Confirmation stockée uniquement en React | Un client autorisé peut exécuter l’écriture sans confirmation utilisateur. | Proposition backend à usage unique, TTL, utilisateur/action/payload liés, autorisation revérifiée au commit. |
| Backend valide rôle et périmètre | Le contexte de l’agent pourrait perdre le scope s’il utilise un compte technique privilégié. | Exécuter les outils au nom du JWT appelant ; ne jamais fournir la base ou un token au LLM. |
| Historique vocal minimal et POST contrôlable par client | Historique falsifiable ; pas de trace lisible des appels d’outils. | Distinguer message, transcription et trace backend ; générer intention/résultat d’outil côté serveur. |
| Audit API sans corps de requête | Bon pour éviter les secrets, mais ne permet pas de reconstituer l’action métier. | Trace métier dédiée avec paramètres assainis/résumé, identifiant de proposition et résultat, sans audio/secrets. |
| Rapports, alertes et commentaires sont du texte libre | Prompt injection, données sensibles, sorties énormes. | Marquer ces champs comme données non fiables, assainir/limiter le contenu et appliquer une liste blanche d’outils. |
| Outil vocal RUL dit déjà qu’il n’est pas fiable | Un agent pourrait malgré tout appeler le endpoint C-MAPSS ou inventer une RUL. | Outil RUL indisponible pour machine industrielle jusqu’à modèle validé et données admissibles. |
| Pas de throttling LLM/transcription dédié | Déni de service et coûts d’API incontrôlés. | Limites par utilisateur/IP, quota journalier, limites audio/tokens, timeouts et coupe-circuit fournisseur. |
| Pas de tests vocaux relevés | Régression silencieuse de compréhension, rôle ou sécurité. | Suite de tests déterministe pour outils, confirmations, scope, injections, hors-sujet et taux de succès. |
