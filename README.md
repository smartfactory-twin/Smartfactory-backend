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

Le superuser de démonstration est créé automatiquement :
- **Email** : `admin@smartfactory.dz`
- **Mot de passe** : `Admin@2024!`

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
