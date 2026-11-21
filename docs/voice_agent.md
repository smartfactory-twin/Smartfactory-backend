# Assistant vocal — phase 1 (agent texte, lecture seule)

## Architecture et flux

`POST /api/voice/agent/` reçoit un texte avec JWT obligatoire. Django garde l'identité, transmet au fournisseur LLM uniquement le prompt, l'historique borné et la liste JSON des outils. Le LLM ne reçoit ni JWT ni connexion à la base. Quand il demande un outil, Django exécute la route DRF existante dans le processus avec le JWT de l'appelant ; authentification, permissions, périmètre `UserScope`, sérialisation et throttling restent donc ceux de cette API. Les outils ne modifient aucune donnée ; `simulate_what_if` appelle le calcul existant sans persistance. Le résultat est borné et renvoyé au modèle comme donnée non fiable.

Les conversations sont identifiées par UUID, isolées par utilisateur, gardent au plus 12 messages et expirent après 30 minutes d'inactivité. Une demande autorise au plus 4 appels d'outils, 5 échanges LLM, 700 tokens de sortie par échange et 45 secondes au total. La limite par défaut est 20 demandes/minute/utilisateur. Un fournisseur absent ou en erreur produit HTTP 503 ; le mode règles existant du frontend reste le repli.

Chaque demande authentifiée est enregistrée dans `VoiceAgentRequest` : utilisateur, texte assaini, outils et paramètres assainis, résumé, durée, statut et code d'erreur. Aucun audio, JWT ou clé de fournisseur n'est enregistré. `VocalCommand` n'a pas été réutilisé : son schéma correspond aux commandes du mode règles existant, sans conversation, appels d'outils, paramètres ni durée; l'étendre aurait mêlé deux formats d'audit. La migration `voice.0001_initial` crée les modèles dédiés.

Les champs libres (noms, identifiants, messages, commentaires, rapports) sont renvoyés dans des objets `{"kind":"untrusted_data","value":"..."}`, limités à 240 caractères. Le prompt système précise que ces contenus sont des données non fiables, jamais des instructions. Les réponses d'outils sont plafonnées à 12 Ko ; les listes indiquent `truncated` et `incomplete`.

## Outils de lecture

Chaque outil utilise les permissions de son endpoint associé, et non une nouvelle matrice de rôles. Les listes sont limitées et indiquent si elles sont incomplètes.

| Outil | Paramètres | API réutilisée | Accès |
|---|---|---|---|
| `search_machines` | `query` (1–100), `limit` (1–10) | `GET /api/equipements/machines/?search=...` | Permissions MachineViewSet et UserScope |
| `get_machine` | `machine_ref` (nom ou identifiant exact, 1–100) | liste de recherche puis détail machine | idem ; objet hors périmètre absent/404 |
| `list_sensors` | `machine_id`, `limit` (1–20) | `GET /api/equipements/capteurs/` | Permissions capteur et UserScope |
| `get_sensor_readings` | `sensor_id`, dates ISO-8601 optionnelles ensemble, `limit` (1–50) | `GET /api/equipements/readings/` | Permissions lecture des mesures et UserScope |
| `list_alerts` | filtres optionnels `machine_id`, `niveau`, `statut`, période, `limit` (1–20) | `GET /api/alertes/` | `AlerteAccessPermission`, UserScope |
| `get_alert` | `alert_ref` (ID numérique ou référence, max 40) | recherche/liste puis détail alerte | `AlerteAccessPermission`, UserScope; détail hors périmètre masqué |
| `get_alerts_by_machine` | `date_debut`, `date_fin` ISO-8601 avec fuseau (max 366 jours), `limit` (1–50) | `GET /api/alertes/aggregation/par-machine/` | `AlerteAccessPermission`, UserScope; agrégation SQL |
| `list_work_orders` | `machine_id`, `statut`, `limit` (1–20) | `GET /api/equipements/ordres-travail/` | `WorkOrderRolePermission`, UserScope |
| `get_work_order` | `work_order_id` | `GET /api/equipements/ordres-travail/{id}/` | idem |
| `get_anomaly_summary` | `machine_id` | `GET /api/ai-predictions/anomalies/?machine_id=...` | Permissions et scope de l'API de prédiction |
| `simulate_what_if` | `sensor_id`, `variation_percent` (-100 à +300) | `POST /api/ai-predictions/what-if/` (simulation sans écriture) | Permissions existantes de l'API What-if |
| `get_model_availability` | `machine_id` optionnel, `limit` (1–20) | `GET /api/ai/readiness/` | ADMIN et TECHNICIEN, périmètre identique à readiness |
| `get_rul_status` | `machine_ref` optionnel (max 100) | réponse indisponible déterministe | RUL toujours « non disponible pour cette machine » tant qu'aucun modèle SmartFactory valide n'existe |

L'agrégation d'alertes accepte seulement `date_debut`, `date_fin` et `limit`. Elle renvoie le nombre d'alertes par machine visible, le total de groupes, la période et `truncated`. Elle ne parcourt pas les pages d'alertes.

## Configuration

Définir dans l'environnement (ou `.env`, jamais dans le code) :

| Variable | Rôle |
|---|---|
| `LLM_PROVIDER` | Nom du fournisseur compatible OpenAI ; `ollama`/`local` autorisent une clé vide |
| `LLM_BASE_URL` | Base HTTPS se terminant par `/v1` ; HTTP permis uniquement pour localhost/127.0.0.1 |
| `LLM_MODEL` | Identifiant du modèle |
| `LLM_API_KEY` | Clé du fournisseur ; jamais incluse dans les erreurs ou journaux |
| `LLM_TIMEOUT_SECONDS` | Timeout fournisseur positif, plafonné par le délai restant de la requête |

Le client appelle `{LLM_BASE_URL}/chat/completions` avec tool calling, température zéro et `max_tokens=700`. `.env.example` donne les emplacements sans valeur secrète.

## Limites connues

- Phase texte uniquement : aucune transcription Whisper, interface, synthèse vocale, confirmation d'écriture ou outil d'écriture.
- Le résultat statistique/benchmark et la disponibilité RUL ne deviennent pas des diagnostics industriels ; la RUL est explicitement indisponible pour les machines SmartFactory.
- Le nettoyage des conversations expirées n'est pas planifié : les conversations expirées ne sont plus utilisables, mais restent stockées jusqu'à une politique de purge ultérieure.
- La liste d'alertes d'un opérateur reste soumise aux permissions de lecture historiques ; l'assistant ne surélève pas les droits.
- Le journal conserve le texte de demande et un résumé de réponse assainis ; prévoir une politique de rétention et de purge avant déploiement industriel.
- Le plafond de temps borne le nombre de tours et les timeouts LLM. Les appels synchrones aux API internes restent limités à des endpoints locaux, mais le serveur HTTP d'application n'est pas conçu ici comme un ordonnanceur asynchrone.
