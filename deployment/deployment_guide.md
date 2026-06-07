# Guide de Déploiement Hostinger : ProsArtisan IA

Ce guide décrit la procédure de déploiement de l'application **ProsArtisan IA** sur les infrastructures Hostinger. 

---

## 🏗️ Architecture Globale de Déploiement

L'application est découpée en deux couches :
1. **Frontend (Statique) :** Le dossier `frontend/` contenant l'interface d'administration (`index.html`) et l'application mobile (`client.html`), ainsi que les styles et scripts JS.
2. **Backend (API) :** Le script `backend/server.py` qui gère le traitement sémantique, le RAG localisé, et le chatbot BTP en interagissant avec la base **PostgreSQL**.

---

## 🌐 Option 1 : Déploiement Unifié sur un VPS Hostinger (Recommandé)

Cette configuration utilise un **VPS Hostinger (Ubuntu 22.04 LTS)** pour héberger à la fois la base de données PostgreSQL, le serveur d'API Python, et distribuer l'interface statique via **Nginx**.

### Étape 1 : Installation des Dépendances Système sur le VPS

Connectez-vous à votre VPS en SSH et installez les paquets requis :
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv postgresql postgresql-contrib nginx git -y
```

### Étape 2 : Configuration de la base de données PostgreSQL

1. Connectez-vous à la console PostgreSQL :
   ```bash
   sudo -i -u postgres psql
   ```
2. Créez l'utilisateur et la base de données :
   ```sql
   CREATE DATABASE prosartisan;
   CREATE USER pros_user WITH PASSWORD 'VotreMotDePasseSecurise';
   GRANT ALL PRIVILEGES ON DATABASE prosartisan TO pros_user;
   \q
   ```
3. *(Optionnel)* Si PostgreSQL doit être accessible depuis l'extérieur (configuration hybride), modifiez `/etc/postgresql/14/main/postgresql.conf` pour écouter sur `listen_addresses = '*'` et configurez `/etc/postgresql/14/main/pg_hba.conf`.

### Étape 3 : Déploiement du Code et de l'Environnement Virtuel

1. Clonez ou transférez vos fichiers dans `/var/www/prosartisan` :
   ```bash
   sudo mkdir -p /var/www/prosartisan
   sudo chown -R $USER:$USER /var/www/prosartisan
   # Copiez les dossiers frontend/ et backend/ dans ce répertoire
   ```
2. Initialisez l'environnement virtuel Python :
   ```bash
   cd /var/www/prosartisan/backend
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

### Étape 4 : Configuration du Service systemd pour l'API Python

Pour exécuter le serveur API en arrière-plan et s'assurer qu'il redémarre automatiquement en cas de crash ou de redémarrage du VPS, créez un service systemd :

```bash
sudo nano /etc/systemd/system/prosartisan-api.service
```

Collez le contenu suivant (en adaptant les variables d'environnement si nécessaire) :

```ini
[Unit]
Description=ProsArtisan API Service
After=network.target postgresql.service

[Service]
User=root
WorkingDirectory=/var/www/prosartisan
Environment=PORT=8000
Environment=PG_HOST=localhost
Environment=PG_PORT=5432
Environment=PG_USER=pros_user
Environment=PG_PASSWORD=VotreMotDePasseSecurise
Environment=PG_DB=prosartisan
ExecStart=/var/www/prosartisan/backend/venv/bin/python3 /var/www/prosartisan/backend/server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Activez et démarrez le service :
```bash
sudo systemctl daemon-reload
sudo systemctl enable prosartisan-api
sudo systemctl start prosartisan-api
sudo systemctl status prosartisan-api
```

### Étape 5 : Configuration de Nginx pour distribuer le Site et faire Proxy API

Nginx va distribuer très rapidement les fichiers du dossier `frontend/` et rediriger les requêtes `/api/` vers notre service Python d'arrière-plan.

1. Créez un fichier de configuration de site Nginx :
   ```bash
   sudo nano /etc/nginx/sites-available/prosartisan
   ```
2. Ajoutez la configuration suivante :
   ```nginx
   server {
       listen 80;
       server_name votre-domaine.com; # Remplacez par votre domaine ou IP de VPS

       # Racine du projet statique (Frontend)
       root /var/www/prosartisan/frontend;
       index index.html;

       # Interface client mobile
       location /client {
           try_files /client.html =404;
       }

       # Routage vers les fichiers statiques (images, css, js)
       location / {
           try_files $uri $uri/ =404;
       }

       # Proxy inverse pour les requêtes API vers le serveur Python
       location /api/ {
           proxy_pass http://127.0.0.1:8000/api/;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection 'upgrade';
           proxy_set_header Host $host;
           proxy_cache_bypass $http_upgrade;
       }
   }
   ```
3. Activez le site et redémarrez Nginx :
   ```bash
   sudo ln -s /etc/nginx/sites-available/prosartisan /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   ```

---

## 🌐 Option 2 : Hébergement Hybride (Mutualisé + VPS)

Si vous possédez un **Hébergement Mutualisé Hostinger** pour vos sites et un VPS séparé (ou hébergeur externe) pour vos applications et bases de données :

### 1. Déploiement du Frontend (Hébergement Mutualisé Hostinger)
1. Ouvrez le **hPanel** d'Hostinger.
2. Allez dans le **Gestionnaire de fichiers** de votre site.
3. Téléversez tout le contenu du dossier `frontend/` directement dans le dossier `/public_html/`.
4. *Important :* Ouvrez `frontend/db.js` et configurez le client API pour pointer vers l'URL de votre serveur externe au lieu d'utiliser des chemins relatifs. 
   Par exemple, modifiez l'URL de base dans les requêtes `fetch` pour y mettre l'adresse IP/domaine publique de votre serveur API :
   `await fetch("http://vps-ip:8000/api/imports")` au lieu de `await fetch("/api/imports")`.

### 2. Déploiement du Backend (VPS Externe ou VPS Hostinger)
1. Installez PostgreSQL et Python sur votre VPS comme décrit dans l'Option 1.
2. Autorisez la connexion CORS : Le script `server.py` intègre déjà des en-têtes CORS universels (`Access-Control-Allow-Origin: *`), ce qui permet au frontend hébergé sur le serveur mutualisé de communiquer sans encombre avec le backend sur le VPS.
