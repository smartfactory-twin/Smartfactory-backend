# SmartFactory Twin — Backend Django

Module d'authentification (Sprint 1) — JWT, rôles, Docker.

## Structure du projet

```
Smartfactory-backend/
├── core/                   ← Configuration Django (settings, urls, wsgi)
├── apps/
│   └── accounts/           ← Auth, Utilisateurs, Rôles
│       ├── models.py       ← Modèle Utilisateur (AbstractBaseUser)
│       ├── serializers.py  ← Serializers (register, login, reset, me)
│       ├── views.py        ← Views (register, login, logout, reset, me)
│       ├── urls.py         ← Routes /api/auth/
│       ├── permissions.py  ← IsAdmin
│       ├── admin.py        ← Admin Django
│       └── tests/          ← Tests pytest
├── manage.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## Démarrage rapide (Docker)

```powershell
# 1. Copier le fichier d'environnement
copy .env.example .env

# 2. Lancer les conteneurs (base + backend + migrations + superuser démo)
docker compose up --build

# 3. Accéder à Swagger
# http://localhost:8000/api/docs/
```

Le compte de démonstration est `admin@smartfactory.com` avec le mot de passe initial `Admin@2026!`. Au premier accès, il doit compléter son nom, son prénom, son adresse e-mail et choisir un nouveau mot de passe. Change ces identifiants après le premier lancement. Pour envoyer les e-mails, configure `EMAIL_HOST_USER`, `DEFAULT_FROM_EMAIL` et un vrai `EMAIL_HOST_PASSWORD` SMTP dans `.env` ; Gmail nécessite un mot de passe d’application.

## Démarrage local (sans Docker)

```powershell
# 1. Créer l'environnement virtuel
python -m venv venv
venv\Scripts\activate

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configurer l'environnement
copy .env.example .env

# 4. Créer la base de données PostgreSQL
# CREATE DATABASE smartfactory_db;

# 5. Appliquer les migrations
python manage.py migrate

# 6. Créer un superuser
python manage.py createsuperuser

# 7. Lancer le serveur
python manage.py runserver
```

## Tests

```powershell
# Tous les tests
pytest

# Avec couverture
pytest --cov=apps.accounts

# Un fichier spécifique
pytest apps/accounts/tests/test_auth.py
```

## Endpoints

| Méthode | URL | Description |
|---------|-----|-------------|
| POST | `/api/auth/register/` | Inscription |
| POST | `/api/auth/login/` | Connexion → JWT |
| POST | `/api/auth/logout/` | Déconnexion (blacklist refresh) |
| POST | `/api/auth/token/refresh/` | Refresh du token |
| POST | `/api/auth/password-reset/` | Demande de réinitialisation |
| POST | `/api/auth/password-reset/confirm/` | Confirmation de réinitialisation |
| GET  | `/api/auth/me/` | Profil utilisateur connecté |
| GET  | `/api/docs/` | Swagger UI |
| GET  | `/api/schema/` | Schéma OpenAPI |

## Scénario de test Swagger

1. **POST /register** — Créer un utilisateur
   ```json
   {
     "nom": "Dupont",
     "prenom": "Jean",
     "email": "jean.dupont@example.com",
     "password": "MonMotDePasse123",
     "password_confirm": "MonMotDePasse123"
   }
   ```

2. **POST /login** — Se connecter
   ```json
   {
     "email": "jean.dupont@example.com",
     "password": "MonMotDePasse123"
   }
   ```
   Copier le `access` token.

3. **Authorize** — Cliquer sur "Authorize" en haut à droite, saisir le token, valider.

4. **GET /me** — Vérifier que le profil s'affiche.

5. **POST /password-reset** — Demander une réinitialisation
   ```json
   {
     "email": "jean.dupont@example.com"
   }
   ```
   Copier le `uid` et le `token` depuis le lien affiché dans les logs du conteneur :
   ```powershell
   docker compose logs backend
   ```

6. **POST /password-reset/confirm** — Confirmer la réinitialisation
   ```json
   {
     "uid": "...",
     "token": "...",
     "new_password": "NouveauMotDePasse123",
     "new_password_confirm": "NouveauMotDePasse123"
   }
   ```

7. **POST /login** — Se connecter avec le nouveau mot de passe.

8. **POST /logout** — Se déconnecter avec le refresh token.

9. **POST /token/refresh** — Tenter de rafraîchir avec l'ancien refresh token (doit être refusé).

## Sécurité

- Mots de passe hachés avec **bcrypt** (BCryptSHA256PasswordHasher)
- JWT avec rotation et blacklist des refresh tokens
- Throttling : login 5/min, password-reset 3/heure
- CORS configurable via `.env`
- Variables sensibles dans `.env` (jamais en dur)

## Rôles

| Rôle | Description |
|------|-------------|
| ADMIN | Administrateur — accès total |
| TECHNICIEN | Technicien terrain |
| OPERATEUR | Opérateur (par défaut à l'inscription) |

## Assistant vocal — agent texte (phase 1)

`POST /api/voice/agent/` nécessite un JWT et accepte `{ "message": "…", "conversation_id": "…" }`.
La réponse contient `reply`, `conversation_id` et `tools_called`. La phase 1 n'expose que des outils de lecture ; `simulate_what_if` est un calcul sans persistance. Le RUL répond qu'il n'est pas disponible pour une machine SmartFactory.

Les outils appellent les routes DRF existantes au nom du demandeur : leurs rôles et périmètres restent appliqués par ces API. Le JWT n'est pas transmis au fournisseur LLM. Les conversations expirent après 30 minutes et sont isolées par utilisateur ; le point d'accès est limité à 20 demandes par minute et par utilisateur.

Configure dans `.env` les cinq variables suivantes pour un endpoint OpenAI-compatible : `LLM_PROVIDER`, `LLM_BASE_URL` (base URL se terminant par `/v1`, sans `/chat/completions`), `LLM_MODEL`, `LLM_API_KEY` et `LLM_TIMEOUT_SECONDS`. Pour `ollama` ou `local`, la clé peut être vide. En cas d'absence ou d'indisponibilité du fournisseur, l'API répond 503 ; le mode règles du frontend reste utilisable.

La liste d'outils, leurs paramètres et limites se trouve dans `docs/voice_agent.md`.
# Disponibilité des données pour l’IA

`GET /api/ai/readiness/` (ADMIN et TECHNICIEN, restreint au périmètre UserScope)
indique si chaque machine dispose d’un historique exploitable. Les critères par
défaut sont `AI_READINESS_MIN_HISTORY_DAYS=7`,
`AI_READINESS_MIN_VALID_MEASURES=1000` et `AI_READINESS_MAX_MISSING_RATE=5.0`
(pourcentage). Ils peuvent être surchargés par variables d’environnement et
sont renvoyés dans `criteria`. Le taux de valeurs manquantes est `null` si la
période d’échantillonnage est inconnue. Ces indicateurs de disponibilité ne
garantissent pas à eux seuls la qualité ou la validité industrielle d’un modèle.
