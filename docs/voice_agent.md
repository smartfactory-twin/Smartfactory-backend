# Assistant vocal SmartFactory Twin — backend (phases 1 à 4b-1)

## Architecture et flux

`POST /api/voice/agent/` reçoit un texte avec JWT obligatoire. `POST /api/voice/agent/stream/` expose le même traitement par Server-Sent Events. Django garde l'identité, transmet au fournisseur LLM uniquement le prompt, l'historique borné et la liste JSON des outils. Le LLM ne reçoit ni JWT ni connexion à la base. Quand il demande un outil, Django exécute la route DRF existante dans le processus avec le JWT de l'appelant ; authentification, permissions, périmètre `UserScope`, sérialisation et throttling restent donc ceux de cette API. Les outils ne modifient aucune donnée ; `simulate_what_if` appelle le calcul existant sans persistance. Le résultat est borné et renvoyé au modèle comme donnée non fiable.

Les conversations sont identifiées par UUID, isolées par utilisateur, gardent au plus 12 messages et expirent après 30 minutes d'inactivité. Une demande autorise au plus 4 appels d'outils, 5 échanges LLM, 700 tokens de sortie par échange et 45 secondes au total. La limite par défaut est 20 demandes/minute/utilisateur. Un fournisseur absent ou en erreur produit HTTP 503 ; le mode règles existant du frontend reste le repli.

Chaque demande authentifiée est enregistrée dans `VoiceAgentRequest` : utilisateur, texte assaini, outils et paramètres assainis, résumé, durée totale, délai serveur jusqu'à la première phrase, mode d'interaction, statut et code d'erreur. Aucun audio, JWT ou clé de fournisseur n'est enregistré. `VocalCommand` n'a pas été réutilisé : son schéma correspond aux commandes du mode règles existant, sans conversation, appels d'outils, paramètres ni durée; l'étendre aurait mêlé deux formats d'audit. La migration `voice.0001_initial` crée les modèles dédiés ; `voice.0003_voiceagentrequest_premiere_phrase_ms` ajoute la mesure du délai.

Les champs libres (noms, identifiants, messages, commentaires, rapports) sont renvoyés dans des objets `{"kind":"untrusted_data","value":"..."}`, limités à 240 caractères. Le prompt système précise que ces contenus sont des données non fiables, jamais des instructions. Les réponses d'outils sont plafonnées à 12 Ko ; les listes indiquent `truncated` et `incomplete`.

## Outils de lecture

Chaque outil utilise les permissions de son endpoint associé, et non une nouvelle matrice de rôles. Les listes sont limitées et indiquent si elles sont incomplètes.

Les champs optionnels du schéma LLM acceptent `null`, car certains fournisseurs renvoient explicitement `null` au lieu d'omettre un paramètre. Django traite ces valeurs comme absentes et conserve les valeurs par défaut des outils.

| Outil | Paramètres | API réutilisée | Accès |
|---|---|---|---|
| `search_machines` | `query` (1–100), `limit` (1–10) | `GET /api/equipements/machines/?search=...` | Permissions MachineViewSet et UserScope |
| `get_machine` | `machine_ref` (nom ou identifiant exact, 1–100) | liste de recherche puis détail machine | idem ; objet hors périmètre absent/404 |
| `list_sensors` | `machine_id`, `limit` (1–20) | `GET /api/equipements/capteurs/` | Permissions capteur et UserScope |
| `get_sensor_readings` | `sensor_id`, dates ISO-8601 optionnelles ensemble, `limit` (1–50) | `GET /api/equipements/readings/` | Permissions lecture des mesures et UserScope |
| `list_alerts` | filtres optionnels `machine_id`, `niveau`, `statut`, période, `limit` (1–20) | `GET /api/alertes/` | `AlerteAccessPermission`, UserScope |
| `get_alert` | `alert_ref` (ID numérique ou référence, max 40) | recherche/liste puis détail alerte | `AlerteAccessPermission`, UserScope; détail hors périmètre masqué |
| `get_alerts_by_machine` | `date_debut`, `date_fin` ISO-8601 avec fuseau (max 366 jours), `limit` (1–50) | `GET /api/alertes/aggregation/par-machine/` | `AlerteAccessPermission`, UserScope; agrégation SQL |
| `list_work_orders` | `machine_id`, `statut`, dates ISO-8601 optionnelles ensemble, `export_format` (`csv`/`pdf`), `limit` (1–100) | `GET /api/equipements/ordres-travail/` | `WorkOrderRolePermission`, UserScope; la période est filtrée sur la date de création |
| `export_user_actions` | `export_format` (`csv`/`pdf`), `user_id` ou `search` facultatifs | `GET /api/auth/users/list/` puis `GET /api/auth/users/{id}/activity/` | ADMIN seulement, les deux API existantes imposent les permissions |
| `get_work_order` | `work_order_id` | `GET /api/equipements/ordres-travail/{id}/` | idem |
| `get_anomaly_summary` | `machine_id` | `GET /api/ai-predictions/anomalies/?machine_id=...` | Permissions et scope de l'API de prédiction |
| `simulate_what_if` | `sensor_id`, `variation_percent` (-100 à +300) | `POST /api/ai-predictions/what-if/` (simulation sans écriture) | Permissions existantes de l'API What-if |
| `get_model_availability` | `machine_id` optionnel, `limit` (1–20) | `GET /api/ai/readiness/` | ADMIN et TECHNICIEN, périmètre identique à readiness |
| `get_rul_status` | `machine_ref` optionnel (max 100) | réponse indisponible déterministe | RUL toujours « non disponible pour cette machine » tant qu'aucun modèle SmartFactory valide n'existe |

L'agrégation d'alertes accepte seulement `date_debut`, `date_fin` et `limit`. Elle renvoie le nombre d'alertes par machine visible, le total de groupes, la période et `truncated`. Elle ne parcourt pas les pages d'alertes.

En mode voix, les schémas transmis au fournisseur sont réduits aux outils correspondant à la demande pour diminuer les tokens consommés. Si Groq renvoie spécifiquement une limite TPM, quelques demandes de lecture simples (listes génériques et exports CSV/PDF associés, dates explicites simples, rapports d'OT sur trois mois) sont servies par les mêmes outils DRF sans appeler le fournisseur. Ce repli n'interprète pas de filtre de zone ou de machine lorsqu'il ne peut pas le déterminer sans ambiguïté, et n'exécute jamais une écriture. Les exports sont renvoyés au frontend comme pièce téléchargeable ; l'assistant ne prétend pas les avoir téléchargés.

Les demandes courantes reconnues (listes et exports de machines, capteurs, alertes et ordres de travail) sont aussi routées localement avant le LLM. Les commandes vocales explicites d'acquittement et de création d'OT peuvent préparer une proposition localement : elles ne réalisent pas l'écriture. Toute exécution conserve la confirmation et la revalidation serveur existantes. Si le LLM est indisponible et qu'aucune commande locale ne correspond, le backend répond avec les capacités disponibles et ne renvoie pas une erreur technique au chat.

Dans une session temps réel, si la transcription Whisper échoue, le frontend essaie `SpeechRecognition`/`webkitSpeechRecognition` en français lorsque le navigateur le fournit. Sans ce support, il garde la session active et indique que la saisie texte est disponible. Cela ne constitue pas un service hors ligne complet : les données doivent toujours être accessibles via Django et la base de données.

## Configuration

Définir dans l'environnement (ou `.env`, jamais dans le code) :

| Variable | Rôle |
|---|---|
| `LLM_PROVIDER` | Nom du fournisseur compatible OpenAI ; `ollama`/`local` autorisent une clé vide |
| `LLM_BASE_URL` | Base HTTPS se terminant par `/v1` ; HTTP permis uniquement pour localhost/127.0.0.1 |
| `LLM_MODEL` | Identifiant du modèle |
| `LLM_API_KEY` | Clé du fournisseur ; jamais incluse dans les erreurs ou journaux |
| `LLM_TIMEOUT_SECONDS` | Timeout fournisseur positif, plafonné par le délai restant de la requête |
| `LLM_USER_AGENT` | User-Agent HTTP utilisé par le LLM et la transcription ; valeur par défaut `SmartFactoryTwin/1.0` |
| `TRANSCRIPTION_MODEL` | Modèle Groq, défaut `whisper-large-v3-turbo` |
| `TRANSCRIPTION_LANGUAGE` | Langue ISO-639-1, défaut `fr` |
| `TRANSCRIPTION_PROMPT` | Contexte lexical métier (le prompt Groq accepte au plus 224 tokens) |
| `TRANSCRIPTION_API_KEY` | Clé dédiée facultative ; si vide, reprend `LLM_API_KEY` |
| `TRANSCRIPTION_BASE_URL` | Base d’API facultative ; si vide, reprend `LLM_BASE_URL` |
| `VOICE_MAX_AUDIO_BYTES` | Taille maximale reçue, défaut 20 MiB |
| `VOICE_MAX_AUDIO_SECONDS` | Durée WAV maximale contrôlée, défaut 120 secondes |

Le client appelle `{LLM_BASE_URL}/chat/completions` avec tool calling, température zéro et `max_tokens=700`. `.env.example` donne les emplacements sans valeur secrète.

## Phase 4b-1 : mode voix, SSE et durée de session

Quand `interaction_mode` vaut `voice`, le prompt ajoute des consignes de réponse orale courte, sans tableau ni liste Markdown. Le prompt texte reste identique. La réponse API garde `reply` inchangé et ajoute `speech`, calculé sans modèle par `apps/voice/speech.py` : nettoyage Markdown, conversion de références et de nombres en mots français, conversion d’unités courantes, et plafond de 1 200 caractères. La normalisation est déterministe ; elle ne remplace pas une vérification humaine de la prononciation de noms propres et d’unités rares.

`POST /api/voice/agent/stream/` exige le même JWT et réutilise le scope de quota `voice_agent`. Le client Groq compatible OpenAI est appelé avec `stream: true` sur chaque tour ; les fragments de texte et de tool calls sont assemblés conformément à l’exemple officiel de streaming tool use, puis les tool calls sont traités par la même boucle bornée. Le User-Agent `LLM_USER_AGENT` est conservé. Les événements SSE sont :

| Événement | Données envoyées |
|---|---|
| `tool` | `{ "name": "..." }`, uniquement le nom de l’outil exécuté, sans paramètres ni résultat |
| `sentence` | `{ "speech": "..." }`, une phrase normalisée prête à être lue |
| `proposal` | proposition complète créée par le même mécanisme que `/agent/` ; elle reste en attente |
| `done` | `{ "conversation_id", "reply", "tools_called" }` |
| `error` | `{ "code": "..." }`, code sans secret pour permettre le repli vers `/api/voice/agent/` |

La boucle et les résultats des outils restent cachés. Les tours du modèle contenant des appels d’outils ne produisent pas de phrases. Le texte final est normalisé, séparé en phrases et envoyé dans le flux ; `tool` expose seulement le nom exigé par le protocole. Une proposition ne peut pas être exécutée par ce flux : « oui » et « confirme » sont traités comme des messages ordinaires de non-confirmation ; l’exécution reste exclusivement sur `/proposals/{id}/confirm/`.

La documentation Groq consultée confirme le streaming de chat completions (`stream=True`) et présente un exemple de « Streaming Tool Use » qui assemble `delta.content` et `delta.tool_calls`, avec `openai/gpt-oss-120b`. Sources officielles : [Groq Local Tool Calling — Streaming Tool Use](https://console.groq.com/docs/tool-use/local-tool-calling#streaming-tool-use) et [Groq Text Generation — Streaming a Chat Completion](https://console.groq.com/docs/text-chat#streaming-a-chat-completion). Cela établit la compatibilité API générale ; le fournisseur et le modèle configurés restent à valider par un appel réel de l’environnement de déploiement.

Les sessions vocales disposent d’un quota de transcription séparé de l’endpoint historique : `POST /api/voice/session/transcribe/` est limité par `VOICE_TRANSCRIBE_RATE` (30/minute/utilisateur par défaut), tandis que `/api/voice/transcribe/` conserve son quota historique de 5/minute. Les deux contrôlent toujours le MIME et la taille ; la durée d’un fichier WAV reste limitée par `VOICE_MAX_AUDIO_SECONDS`. `GET /api/voice/session/config/` renvoie `max_seconds` à partir de `VOICE_SESSION_MAX_SECONDS` (300 secondes par défaut), afin que le client puisse borner la durée totale d’une session.

| Variable | Rôle |
|---|---|
| `VOICE_TRANSCRIBE_RATE` | quota du nouvel endpoint de transcription de session, défaut `30/min` |
| `VOICE_SESSION_MAX_SECONDS` | durée maximale annoncée d’une session vocale, défaut `300` secondes |

`VoiceAgentRequest.interaction_mode` stocke déjà le mode et reste renseigné pour les deux endpoints agent. `premiere_phrase_ms` mesure le délai côté serveur jusqu’à la disponibilité de la première phrase ; il ne mesure pas le délai réseau jusqu’au navigateur ni le début réel de la lecture audio.

## Écritures : propositions et confirmation explicite

Les outils `acknowledge_alert`, `create_work_order`, `update_work_order_status` et `submit_work_order_report` ne font qu'enregistrer une `VoiceActionProposal`. L'agent renvoie son identifiant, un résumé, l'aperçu complet et un `spoken_summary` de 250 caractères maximum. Le LLM n'a pas d'outil de confirmation. Répondre « oui » dans le chat vocal ou texte ne déclenche jamais l'écriture ; il faut appeler l'endpoint `POST /api/voice/proposals/{id}/confirm/` avec le JWT de l'utilisateur. `POST /api/voice/proposals/{id}/cancel/` annule ; `GET /api/voice/proposals/pending/` ne montre que les propositions de l'utilisateur connecté.

La proposition expire après `VOICE_PROPOSAL_TTL_SECONDS` (120 s par défaut). Une seule proposition en attente par utilisateur et conversation est conservée : une nouvelle remplace l'ancienne. La création est limitée par `VOICE_PROPOSAL_HOURLY_LIMIT` (10/h). La confirmation verrouille la ligne, vérifie son empreinte SHA-256, expire paresseusement, revalide rôle, périmètre, état et serializers existants, puis appelle l'endpoint métier avec le JWT du demandeur. Les actions sont journalisées avec l'acteur et les paramètres nécessaires ; aucun JWT, clé LLM ni audio n'est enregistré. `interaction_mode` (`text` ou `voice`) est conservé dans le journal, mais ne change jamais les règles.

Une commande `python manage.py purge_voice_proposals --days 30` supprime les propositions anciennes non en attente ; les propositions pending expirées sont d'abord passées à `expired`.

## Phase 3 : transcription vocale hébergée

Flux : navigateur (phase 4) -> `POST /api/voice/transcribe/` avec un JWT et un fichier multipart `audio` -> validation MIME/taille/durée WAV, puis limite de débit `voice_transcribe` -> envoi multipart vers `POST {TRANSCRIPTION_BASE_URL}/audio/transcriptions` chez Groq -> réponse `{text, engine, model, language, processing_ms}`. L’endpoint renvoie uniquement le texte reconnu ; il ne l’envoie pas à l’agent et ne déclenche aucune proposition ou écriture.

Le service utilise `TRANSCRIPTION_API_KEY` et `TRANSCRIPTION_BASE_URL` s’ils sont renseignés, sinon `LLM_API_KEY` et `LLM_BASE_URL`. Le `User-Agent` est celui de `LLM_USER_AGENT`. Le chemin et les champs multipart suivent la [documentation Groq Speech-to-Text](https://console.groq.com/docs/speech-to-text) : `file`, `model`, `language`, `prompt` et `response_format=json`. Le prompt de domaine reste inférieur à la limite documentée de 224 tokens. Le fournisseur reçoit l’audio uniquement pour traiter cette demande ; l’application ne l’enregistre pas en base ni dans son stockage média. Les uploads Django temporaires sont fermés dans un bloc `finally`. La durée peut être lue sans bibliothèque externe pour WAV ; elle n’est pas inspectée pour les autres formats.

La transcription elle-même n’est pas stockée par ce endpoint. Si un client envoie ensuite son texte à `/api/voice/agent/`, le texte devient alors une demande d’agent et est conservé selon la politique actuelle : dans `VoiceAgentRequest.texte` et, pour les échanges de conversation conservés, dans `VoiceConversation.messages`. `VocalCommand` n’est pas utilisé par le nouvel endpoint.

Formats admis : WebM, OGG, WAV, MP4/M4A et MPEG selon le type MIME déclaré. Taille par défaut : 20 MiB ; durée maximale WAV par défaut : 120 secondes. La limite de transcription est 5 requêtes/minute/utilisateur, contre 20/minute pour l’agent. Une erreur fournisseur renvoie 503 `transcription_unavailable` pour permettre au client de reprendre avec la reconnaissance navigateur.

Les variables de cette phase sont dans `.env.example`. Le prompt Groq reste du contexte lexical et n’ordonne jamais d’action. Le champ audio n’est jamais écrit dans le journal vocal ; le texte reçu de Groq n’est pas journalisé non plus. Les erreurs fournisseur sont journalisées côté serveur avec type, code HTTP et corps borné/assaini, jamais la clé, l’audio ou la transcription.

## Limites connues

- Le navigateur et l’interface n’intègrent pas encore cet endpoint (phase 4) ; aucune synthèse vocale serveur n’est ajoutée.
- La durée d’un fichier reçu est vérifiée uniquement pour WAV ; les autres formats ne sont pas décodés localement afin d’éviter une dépendance audio lourde. `VOICE_SESSION_MAX_SECONDS` annonce au frontend la durée totale de session ; le backend n’entretient pas d’état de session audio entre les requêtes.
- Les événements SSE sont assemblés côté serveur après réception des tours LLM ; le délai de première phrase consigné est une mesure serveur et non une mesure de latence réelle du navigateur ou du haut-parleur.
- Les réponses de transcription ne sont pas stockées et le backend ne transmet jamais automatiquement le texte transcrit à l’agent.
- Le résultat statistique/benchmark et la disponibilité RUL ne deviennent pas des diagnostics industriels ; la RUL est explicitement indisponible pour les machines SmartFactory.
- Le nettoyage des conversations expirées n'est pas planifié : les conversations expirées ne sont plus utilisables, mais restent stockées jusqu'à une politique de purge ultérieure.
- La liste d'alertes d'un opérateur reste soumise aux permissions de lecture historiques ; l'assistant ne surélève pas les droits.
- Le journal conserve le texte de demande et un résumé de réponse assainis ; prévoir une politique de rétention et de purge avant déploiement industriel.
- Le plafond de temps borne le nombre de tours et les timeouts LLM. Les appels synchrones aux API internes restent limités à des endpoints locaux, mais le serveur HTTP d'application n'est pas conçu ici comme un ordonnanceur asynchrone.
