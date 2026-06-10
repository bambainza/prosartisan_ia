# ProsArtisan IA 🏗️🤖

**ProsArtisan IA** est un prototype d'assistant BTP intelligent conçu pour accompagner les maçons et artisans de chantier (Côte d'Ivoire) dans l'aide à la décision technique, l'estimation des dosages et la démonstration de conformité réglementaire (BNETD, LBTP).

L'application intègre un pipeline de traitement sémantique localisé (RAG) et un simulateur d'application mobile autonome capable de fonctionner en mode hors-ligne avec file d'attente résiliente en 3G/Offline.

---

## 📁 Structure du Projet

Le projet est organisé selon une architecture séparée Frontend / Backend facilitant le déploiement sur les architectures de type **Hostinger** :

```text
prosartisan_ia/
├── frontend/                     # Application Client Statique
│   ├── index.html                # Portail d'Administration
│   ├── style.css                 # Design System & UI Admin
│   ├── ui.js                     # Contrôleur d'Interface Admin
│   ├── app.js                    # Logique métier principale (RAG, Offline, VLM)
│   ├── db.js                     # Client d'API de Base de Données
│   ├── client.html               # Application Mobile du Maçon (Simulateur)
│   ├── client.css                # Styles thématiques mobiles
│   └── client.js                 # Logique mobile et chatbot vocal nouchi
│
├── backend/                      # Serveur API de Données
│   ├── server.py                 # Serveur HTTP Python & Connecteur PostgreSQL
│   └── requirements.txt          # Dépendances Python
│
├── deployment/                   # Ressources de déploiement en production
│   └── deployment_guide.md       # Guide pas-à-pas de déploiement Hostinger (Nginx, systemd, PG)
│
└── README.md                     # Présentation générale du dépôt
```

---

## 🚀 Fonctionnalités Clés

1. **Ingestion Sémantique Localisée (PISL) :** Importation de documents de normes BTP (PDF, TXT, MD), extraction VLM par LlamaParse et normalisation LLM.
2. **Historisation PostgreSQL :** Suivi persistant de chaque document dans le pipeline (`import_history`) avec restauration dynamique de l'état de traitement.
3. **Staging / Human-In-The-Loop :** Interface de validation humaine permettant de vérifier et d'ajuster les dosages et estimations en FCFA avant l'indexation définitive.
4. **Diagnostic Mobile & Pitch Audio :** Génération de pitchs de conviction clients basés sur les normes locales de Côte d'Ivoire (dosages en ciment CPJ 42.5/32.5, sacs Lafarge/CIMAF, adjuvants SikaCim, sable de carrière) avec synthèse vocale (Text-To-Speech).
5. **Chatbot BTP Vocal (Nouchi) :** Chatbot intégré permettant de poser des questions de chantier à la voix ou à l'écrit, résilient hors-ligne.
6. **File d'Attente Offline :** Gestion de la latence réseau avec file d'attente de requêtes synchronisée dès le retour d'une connexion.

---

## 💻 Démarrage Local rapide

### Prérequis
* Python 3
* Un serveur PostgreSQL local démarré sur le port `5432` avec un utilisateur `postgres` (mot de passe par défaut : `postgres`).
* (Optionnel mais recommandé) Une clé d'API Gemini pour activer l'IA générative dans le chatbot.

### Lancement
1. Clonez ce dépôt.
2. Installez les dépendances :
   ```bash
   pip install -r backend/requirements.txt
   ```
3. Démarrez le serveur API (avec votre clé Gemini pour activer l'IA) :
   ```bash
   GEMINI_API_KEY="votre_cle_api" python3 backend/server.py
   ```
4. Ouvrez votre navigateur sur :
   * Le portail d'administration : **[http://localhost:8000](http://localhost:8000)**
   * L'application mobile maçon : **[http://localhost:8000/client](http://localhost:8000/client)**

---

## ☁️ Déploiement en Production

Consultez le [Guide de Déploiement Hostinger](file:///Users/i.bamba/Documents/prosartisan_ia/deployment/deployment_guide.md) dans le dossier `deployment/` pour configurer le service sur votre hébergement (VPS ou mutualisé).
