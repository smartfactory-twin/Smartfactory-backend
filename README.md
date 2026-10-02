# 🚀 SmartFactory Twin — Backend Django

## Structure du projet
```
Smartfactory-backend/
├── core/               ← Configuration Django (settings, urls, wsgi)
├── apps/
│   └── accounts/       ← Auth, Users, Rôles
├── manage.py
├── requirements.txt
└── .env
```

## Lancer le projet (PowerShell)

```powershell
# 1. Aller dans le dossier
cd C:\Users\lenovo\Desktop\gl5\smartfactory-twin\Smartfactory-backend

# 2. Créer l'environnement virtuel
python -m venv venv

# 3. Activer le venv
venv\Scripts\activate

# 4. Installer les dépendances
pip install -r requirements.txt

# 5. Créer la base de données PostgreSQL (dans pgAdmin ou psql)
# CREATE DATABASE smartfactory_db;

# 6. Appliquer les migrations
python manage.py makemigrations
python manage.py migrate

# 7. Créer un super admin
python manage.py createsuperuser

# 8. Lancer le serveur
python manage.py runserver
```

## Endpoints disponibles

| Méthode | URL | Description |
|---------|-----|-------------|
| POST | /api/v1/auth/login/ | Connexion → JWT |
| POST | /api/v1/auth/logout/ | Déconnexion |
| POST | /api/v1/auth/token/refresh/ | Refresh du token |
| POST | /api/v1/auth/register/ | Inscription |
| GET/PATCH | /api/v1/auth/me/ | Profil |
| POST | /api/v1/auth/change-password/ | Changer MDP |
| GET | /api/v1/auth/users/ | Liste users (Admin) |
| GET | /api/docs/ | Swagger UI |