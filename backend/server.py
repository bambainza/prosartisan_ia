#!/usr/bin/env python3
"""
server.py
Serveur API REST et serveur de fichiers statiques pour ProsArtisan IA.
Utilise PostgreSQL (SGBD local) pour stocker les fiches de staging et de production.
"""

import http.server
import socketserver
import json
import psycopg2
import psycopg2.extras
import os
import re
from urllib.parse import urlparse
from datetime import datetime
from google import genai
from google.genai import types


PORT = int(os.environ.get("PORT", 8000))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

FILESHARE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fileshare")
os.makedirs(FILESHARE_DIR, exist_ok=True)

# --- CONFIGURATION DE CONNEXION POSTGRESQL ---
PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", 5432))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "postgres")
PG_DB = os.environ.get("PG_DB", "prosartisan")

# --- CONFIGURATION ET INITIALISATION DE LA BASE DE DONNÉES ---

def init_database():
    print(f"Vérification de la base de données PostgreSQL: {PG_DB} sur {PG_HOST}:{PG_PORT}")
    
    # 1. Vérifier si la base prosartisan existe, sinon la créer
    conn = None
    try:
        # Tenter une connexion directe
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            dbname=PG_DB
        )
        print(f"La base de données '{PG_DB}' existe déjà.")
    except psycopg2.OperationalError as e:
        # Code d'erreur SQLSTATE 3D000 ou textes linguistiques
        is_missing_db = (
            (hasattr(e, 'pgcode') and e.pgcode == '3D000') or 
            "does not exist" in str(e) or 
            "n'existe pas" in str(e) or 
            "3D000" in str(e)
        )
        if is_missing_db:
            print(f"La base '{PG_DB}' n'existe pas. Création en cours...")
            sys_conn = None
            try:
                # Se connecter à la base système 'postgres'
                sys_conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname="postgres"
                )
                sys_conn.autocommit = True
                with sys_conn.cursor() as cursor:
                    cursor.execute(f"CREATE DATABASE {PG_DB};")
                print(f"Base de données '{PG_DB}' créée avec succès.")
            except Exception as create_err:
                print(f"Erreur lors de la création de la base de données : {create_err}")
                raise create_err
            finally:
                if sys_conn:
                    sys_conn.close()
        else:
            print(f"Erreur de connexion PostgreSQL : {e}")
            print("Assurez-vous que votre SGBD PostgreSQL local est bien lancé sur le port 5432.")
            raise e
    finally:
        if conn:
            conn.close()

    # 2. Initialiser les tables
    conn = None
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            dbname=PG_DB
        )
        with conn.cursor() as cursor:
            # Table de staging (avec JSONB pour les dosages et structures)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS staging_items (
                id VARCHAR(50) PRIMARY KEY,
                raw_pdf_source VARCHAR(255) NOT NULL,
                original_extracted_text TEXT NOT NULL,
                generated_json JSONB NOT NULL,
                status VARCHAR(50) DEFAULT 'PENDING',
                reviewer_notes TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
                validated_at TIMESTAMP WITH TIME ZONE
            );
            """)

            # Table de production (simule l'index Qdrant avec JSONB)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS production_items (
                id VARCHAR(50) PRIMARY KEY,
                generated_json JSONB NOT NULL,
                tags TEXT NOT NULL
            );
            """)

            # Table d'historique des importations
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS import_history (
                id VARCHAR(100) PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                file_size INTEGER NOT NULL,
                imported_at VARCHAR(100) NOT NULL,
                status VARCHAR(50) NOT NULL,
                vlm_extracted BOOLEAN DEFAULT FALSE,
                llm_downscaled BOOLEAN DEFAULT FALSE
            );
            """)

            # Table des utilisateurs
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                email VARCHAR(255) PRIMARY KEY,
                password_hash VARCHAR(255) NOT NULL,
                reset_token VARCHAR(255),
                reset_token_expiry TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL
            );
            """)

            # Table des fichiers joints
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                id VARCHAR(100) PRIMARY KEY,
                original_filename VARCHAR(255) NOT NULL,
                extension VARCHAR(20) NOT NULL,
                file_link VARCHAR(500) NOT NULL,
                uploaded_by VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE NOT NULL
            );
            """)

            # Tables pour la configuration des métiers, catégories et contextes
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS professions (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id VARCHAR(50) PRIMARY KEY,
                profession_id VARCHAR(50) REFERENCES professions(id),
                name VARCHAR(255) NOT NULL,
                description TEXT
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS contexts (
                id VARCHAR(50) PRIMARY KEY,
                category_id VARCHAR(50) REFERENCES categories(id),
                tags TEXT NOT NULL,
                title VARCHAR(255) NOT NULL,
                source VARCHAR(255) NOT NULL,
                execution TEXT NOT NULL,
                pitch TEXT NOT NULL,
                dosages JSONB,
                materials JSONB,
                price VARCHAR(255),
                justification TEXT,
                type_ouvrage VARCHAR(255)
            );
            """)

            # Insertion de l'utilisateur admin par défaut si la table est vide
            cursor.execute("SELECT COUNT(*) FROM users;")
            if cursor.fetchone()[0] == 0:
                print("Insertion de l'utilisateur admin par défaut dans PostgreSQL...")
                import hashlib
                salt = "prosartisan_secure_salt_2026"
                default_password_hash = hashlib.sha256(("admin123" + salt).encode('utf-8')).hexdigest()
                now_str = datetime.utcnow().isoformat() + "Z"
                cursor.execute(
                    "INSERT INTO users (email, password_hash, created_at) VALUES (%s, %s, %s);",
                    ("admin@prosartisan.ci", default_password_hash, now_str)
                )

            conn.commit()

            # --- JEU DE DONNÉES INITIAL (SEEDS) ---
            cursor.execute("SELECT COUNT(*) FROM staging_items;")
            if cursor.fetchone()[0] == 0:
                print("Insertion des données de démo initiales dans PostgreSQL (Staging)...")
                
                stage1_json = {
                    "id": "stage-101",
                    "norme_origine": {
                        "source": "LBTP",
                        "reference_article": "SECTION 4.2",
                        "titre_original": "Étanchéité des murs enterrés et soubassements",
                        "texte_brut": "L'arase étanche doit être réalisée au niveau de la coupure de capillarité à l'aide d'une membrane bitumineuse conforme à la norme NF EN 13969 soudée à chaud..."
                    },
                    "alternative_prosartisan": {
                        "titre_vulgarise": "Réalisation d'une coupure de capillarité (arase étanche) sur parpaings de 15",
                        "methode_execution": "Nettoyer parfaitement la tête de la fondation (pas de terre). Poser un mortier de ciment dosé à 350kg/m3 mélangé avec un sachet d'hydrofuge de masse SikaCim par sac de ciment. Le mortier doit être appliqué sur une épaisseur de 2 cm minimum. Bien lisser à la taloche. Poser le premier rang de parpaings pendant que le mortier est encore frais. Pour un traitement curatif de mur existant : piquer l'enduit abîmé sur 50 cm de hauteur, brosser les joints, et refaire un enduit serré au ciment CPJ 42.5 hydrofugé au SikaCim.",
                        "dosages_recommandes": [
                            { "element": "Ciment CPJ 42.5 (CIMAF / LafargeHolcim)", "ratio": "1 sac (50kg)", "unite_mesure_locale": "Sac" },
                            { "element": "Sable de carrière propre (non salé)", "ratio": "2 brouettes de 60L rases", "unite_mesure_locale": "Brouette (60L)" },
                            { "element": "Adjuvant SikaCim (ou Super Sikalite)", "ratio": "1 sachet (ou 1 pot de 1kg)", "unite_mesure_locale": "Sac" }
                        ],
                        "materiaux_recommandes": [
                            { "nom": "Ciment CPJ 42.5", "substitut_acceptable": "CPJ 32.5 (Moins recommandé)", "disponibilite": "Quincaillerie" },
                            { "nom": "Hydrofuge de masse SikaCim", "substitut_acceptable": "Super Sikalite en poudre", "disponibilite": "Quincaillerie" },
                            { "nom": "Sable de carrière", "substitut_acceptable": "Sable de lagune lavé", "disponibilite": "Quincaillerie" }
                        ]
                    },
                    "cout_estime_local": {
                        "gamme_prix": "Faible",
                        "estimation_m2_fcfa": "4 500 - 6 000 FCFA par mètre linéaire",
                        "justification_economique": "L'achat d'un sachet de SikaCim (environ 1 500 FCFA) évite au client de devoir refaire la peinture de sa maison chaque année. C'est un argument de vente solide pour convaincre le client d'acheter le produit."
                    },
                    "metadata": {
                        "tags_pathologies": ["remontee_capillaire", "humidite_bas", "salpetre"],
                        "type_ouvrage": "Etancheite"
                    }
                }
                
                stage2_json = {
                    "id": "stage-102",
                    "norme_origine": {
                        "source": "BNETD",
                        "reference_article": "SECTION 7.8",
                        "titre_original": "Ferraillage des éléments porteurs (Linteaux)",
                        "texte_brut": "Tout linteau franchissant une ouverture supérieure à 1.20m doit posséder une armature de chaînage minimale constituée de 4 cadres filants HA 12..."
                    },
                    "alternative_prosartisan": {
                        "titre_vulgarise": "Ferraillage et coulage de linteau pour ouverture (> 1.20m)",
                        "methode_execution": "Façonner l'armature avec 4 barres de fer de 10 (HA 10) filantes. Lier ces barres avec des cadres en fer de 6 (HA 6) espacés de 15 cm. Veiller à ce que l'armature soit calée à 3 cm du coffrage bois en utilisant des cales en mortier (pas de contact direct métal-bois pour éviter la rouille). Utiliser exclusivement du ciment CPJ 42.5 pour le béton de structure. Mélanger vigoureusement et piquer le béton fraîchement coulé avec une barre de fer pour éliminer les bulles d'air (vibration manuelle). Laisser sécher 14 jours minimum avant de décoffrer.",
                        "dosages_recommandes": [
                            { "element": "Ciment CPJ 42.5 (CIMAF / LafargeHolcim)", "ratio": "1 sac (50kg)", "unite_mesure_locale": "Sac" },
                            { "element": "Sable de carrière propre", "ratio": "1.5 brouettes de 60L", "unite_mesure_locale": "Brouette (60L)" },
                            { "element": "Gravier 15/25 de concassage", "ratio": "2.5 brouettes", "unite_mesure_locale": "Brouette (60L)" },
                            { "element": "Fers à béton HA 10 et HA 6", "ratio": "Selon longueur de l'ouverture + 40cm d'ancrage de chaque côté", "unite_mesure_locale": "Pelle" }
                        ],
                        "materiaux_recommandes": [
                            { "nom": "Ciment CPJ 42.5", "substitut_acceptable": "Aucun substitut pour éléments porteurs structuraux", "disponibilite": "Quincaillerie" },
                            { "nom": "Fers de construction HA 10 et HA 6", "substitut_acceptable": "Fers importés certifiés", "disponibilite": "Quincaillerie" },
                            { "nom": "Gravier concassé 15/25", "substitut_acceptable": "Gravier de lagune lavé", "disponibilite": "Zone Industrielle" }
                        ]
                    },
                    "cout_estime_local": {
                        "gamme_prix": "Moyen",
                        "estimation_m2_fcfa": "15 000 - 25 000 FCFA par linteau standard",
                        "justification_economique": "Le coût est justifié par l'achat de ciment CPJ 42.5 haute résistance et le ferraillage de 10 mm. Expliquer au client que poser du fer de 8 mm ou du ciment CPJ 32.5 entraînera des fissures structurelles et l'effondrement à terme de sa maçonnerie."
                    },
                    "metadata": {
                        "tags_pathologies": ["fissure_structure", "linteau_beton", "ferraillage"],
                        "type_ouvrage": "Poteau-Poutre"
                    }
                }

                now_str = datetime.utcnow().isoformat() + "Z"
                cursor.execute(
                    "INSERT INTO staging_items (id, raw_pdf_source, original_extracted_text, generated_json, status, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s);",
                    ("stage-101", "LBTP-GUIDE-BTP-2022.pdf", "SECTION 4.2: ÉTANCHÉITÉ DES MURS ENTERRÉS ET SOUBASSEMENTS...", psycopg2.extras.Json(stage1_json), "PENDING", now_str, now_str)
                )
                cursor.execute(
                    "INSERT INTO staging_items (id, raw_pdf_source, original_extracted_text, generated_json, status, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s);",
                    ("stage-102", "BNETD-STRUCT-BÉTON-2021.pdf", "SECTION 7.8: FERRAILLAGE DES ÉLÉMENTS PORTEURS...", psycopg2.extras.Json(stage2_json), "PENDING", now_str, now_str)
                )
                conn.commit()

            # Vérifier et insérer les données de démo initiales dans PostgreSQL (Production)
            cursor.execute("SELECT id FROM production_items;")
            existing_prod_ids = [r[0] for r in cursor.fetchall()]

            # prod-101 (humidité)
            if "prod-101" not in existing_prod_ids:
                print("Insertion du jeu de données prod-101 (Humidité) dans PostgreSQL (Production)...")
                prod101_json = {
                    "id": "prod-101",
                    "norme_origine": {
                        "source": "LBTP",
                        "reference_article": "SECTION 4.2",
                        "titre_original": "Étanchéité des murs enterrés et soubassements",
                        "texte_brut": "L'arase étanche doit être réalisée au niveau de la coupure de capillarité à l'aide d'une membrane bitumineuse conforme à la norme NF EN 13969 soudée à chaud..."
                    },
                    "alternative_prosartisan": {
                        "titre_vulgarise": "Réalisation d'une coupure de capillarité (arase étanche) sur parpaings de 15",
                        "methode_execution": "Nettoyer parfaitement la tête de la fondation (pas de terre). Poser un mortier de ciment dosé à 350kg/m3 mélangé avec un sachet d'hydrofuge de masse SikaCim par sac de ciment. Le mortier doit être appliqué sur une épaisseur de 2 cm minimum. Bien lisser à la taloche. Poser le premier rang de parpaings pendant que le mortier est encore frais. Pour un traitement curatif de mur existant : piquer l'enduit abîmé sur 50 cm de hauteur, brosser les joints, et refaire un enduit serré au ciment CPJ 42.5 hydrofugé au SikaCim.",
                        "dosages_recommandes": [
                            { "element": "Ciment CPJ 42.5 (CIMAF / LafargeHolcim)", "ratio": "1 sac (50kg)", "unite_mesure_locale": "Sac" },
                            { "element": "Sable de carrière propre (non salé)", "ratio": "2 brouettes de 60L rases", "unite_mesure_locale": "Brouette (60L)" },
                            { "element": "Adjuvant SikaCim (ou Super Sikalite)", "ratio": "1 sachet (ou 1 pot de 1kg)", "unite_mesure_locale": "Sac" }
                        ],
                        "materiaux_recommandes": [
                            { "nom": "Ciment CPJ 42.5", "substitut_acceptable": "CPJ 32.5 (Moins recommandé)", "disponibilite": "Quincaillerie" },
                            { "nom": "Hydrofuge de masse SikaCim", "substitut_acceptable": "Super Sikalite en poudre", "disponibilite": "Quincaillerie" },
                            { "nom": "Sable de carrière", "substitut_acceptable": "Sable de lagune lavé", "disponibilite": "Quincaillerie" }
                        ]
                    },
                    "cout_estime_local": {
                        "gamme_prix": "Faible",
                        "estimation_m2_fcfa": "4 500 - 6 000 FCFA par mètre linéaire",
                        "justification_economique": "L'achat d'un sachet de SikaCim (environ 1 500 FCFA) évite au client de devoir refaire la peinture de sa maison chaque année. C'est un argument de vente solide pour convaincre le client d'acheter le produit."
                    },
                    "metadata": {
                        "tags_pathologies": ["remontee_capillaire", "humidite_bas", "salpetre"],
                        "type_ouvrage": "Etancheite"
                    }
                }
                cursor.execute(
                    "INSERT INTO production_items (id, generated_json, tags) VALUES (%s, %s, %s);",
                    ("prod-101", psycopg2.extras.Json(prod101_json), "remontee_capillaire,humidite_bas,salpetre")
                )

            # prod-102 (linteau)
            if "prod-102" not in existing_prod_ids:
                print("Insertion du jeu de données prod-102 (Linteau) dans PostgreSQL (Production)...")
                prod102_json = {
                    "id": "prod-102",
                    "norme_origine": {
                        "source": "BNETD",
                        "reference_article": "SECTION 7.8",
                        "titre_original": "Ferraillage des éléments porteurs (Linteaux)",
                        "texte_brut": "Tout linteau franchissant une ouverture supérieure à 1.20m doit posséder une armature de chaînage minimale constituée de 4 cadres filants HA 12..."
                    },
                    "alternative_prosartisan": {
                        "titre_vulgarise": "Ferraillage et coulage de linteau pour ouverture (> 1.20m)",
                        "methode_execution": "Façonner l'armature avec 4 barres de fer de 10 (HA 10) filantes. Lier ces barres avec des cadres en fer de 6 (HA 6) espacés de 15 cm. Veiller à ce que l'armature soit calée à 3 cm du coffrage bois en utilisant des cales en mortier (pas de contact direct métal-bois pour éviter la rouille). Utiliser exclusivement du ciment CPJ 42.5 pour le béton de structure. Mélanger vigoureusement et piquer le béton fraîchement coulé avec une barre de fer pour éliminer les bulles d'air (vibration manuelle). Laisser sécher 14 jours minimum avant de décoffrer.",
                        "dosages_recommandes": [
                            { "element": "Ciment CPJ 42.5 (CIMAF / LafargeHolcim)", "ratio": "1 sac (50kg)", "unite_mesure_locale": "Sac" },
                            { "element": "Sable de carrière propre", "ratio": "1.5 brouettes de 60L", "unite_mesure_locale": "Brouette (60L)" },
                            { "element": "Gravier 15/25 de concassage", "ratio": "2.5 brouettes", "unite_mesure_locale": "Brouette (60L)" },
                            { "element": "Fers à béton HA 10 et HA 6", "ratio": "Selon longueur de l'ouverture + 40cm d'ancrage de chaque côté", "unite_mesure_locale": "Pelle" }
                        ],
                        "materiaux_recommandes": [
                            { "nom": "Ciment CPJ 42.5", "substitut_acceptable": "Aucun substitut pour éléments porteurs structuraux", "disponibilite": "Quincaillerie" },
                            { "nom": "Fers de construction HA 10 et HA 6", "substitut_acceptable": "Fers importés certifiés", "disponibilite": "Quincaillerie" },
                            { "nom": "Gravier concassé 15/25", "substitut_acceptable": "Gravier de lagune lavé", "disponibilite": "Zone Industrielle" }
                        ]
                    },
                    "cout_estime_local": {
                        "gamme_prix": "Moyen",
                        "estimation_m2_fcfa": "15 000 - 25 000 FCFA par linteau standard",
                        "justification_economique": "Le coût est justifié par l'achat de ciment CPJ 42.5 haute résistance et le ferraillage de 10 mm. Expliquer au client que poser du fer de 8 mm ou du ciment CPJ 32.5 entraînera des fissures structurelles et l'effondrement à terme de sa maçonnerie."
                    },
                    "metadata": {
                        "tags_pathologies": ["fissure_structure", "linteau_beton", "ferraillage"],
                        "type_ouvrage": "Poteau-Poutre"
                    }
                }
                cursor.execute(
                    "INSERT INTO production_items (id, generated_json, tags) VALUES (%s, %s, %s);",
                    ("prod-102", psycopg2.extras.Json(prod102_json), "fissure_structure,linteau_beton,ferraillage")
                )

            # prod-201 (infiltration)
            if "prod-201" not in existing_prod_ids:
                print("Insertion du jeu de données prod-201 (Infiltration) dans PostgreSQL (Production)...")
                prod201_json = {
                    "id": "prod-201",
                    "norme_origine": {
                        "source": "RE-CIM",
                        "reference_article": "GUIDE EN-1996-1",
                        "titre_original": "Protection contre les infiltrations en terrasse",
                        "texte_brut": "L'étanchéité des toitures-terrasses non accessibles doit comporter un pare-vapeur bitumineux, un panneau isolant thermique, et une membrane d'étanchéité élastomère soudée en deux couches croisées avec protection lourde gravillonnée."
                    },
                    "alternative_prosartisan": {
                        "titre_vulgarise": "Étanchéité liquide de toit-terrasse (Système SEL manuel accessible)",
                        "methode_execution": "Nettoyer et brosser la dalle béton (enlever toute poussière et mousse). Réparer les fissures au mortier hydrofugé. Appliquer une première couche de résine d'étanchéité liquide acrylique (ex: Sika Lanko étanchéité ou similaire) au rouleau. Poser immédiatement une bande d'armature en fibre de verre (toile) sur la résine fraîche en marouflant bien. Laisser sécher 12h. Appliquer une deuxième couche de résine croisée sur la toile. Laisser sécher 12h, puis appliquer la troisième couche de finition. Assurer une pente de 2% vers les évacuations d'eau.",
                        "dosages_recommandes": [
                            { "element": "Résine d'étanchéité liquide (Lanko ou Sika)", "ratio": "1.5 kg par m² (au total pour les 3 passes)", "unite_mesure_locale": "Seau de maçon (10L)" },
                            { "element": "Armature fibre de verre (toile)", "ratio": "1.1 m² par m² de terrasse", "unite_mesure_locale": "Sac" }
                        ],
                        "materiaux_recommandes": [
                            { "nom": "Résine d'étanchéité liquide SEL", "substitut_acceptable": "Peinture routière avec résine additionnée (Moins durable)", "disponibilite": "Zone Industrielle" },
                            { "nom": "Toile de renfort en fibre de verre", "substitut_acceptable": "Treillis de jute fin (Moins durable)", "disponibilite": "Zone Industrielle" }
                        ]
                    },
                    "cout_estime_local": {
                        "gamme_prix": "Eleve",
                        "estimation_m2_fcfa": "8 000 - 12 000 FCFA par m²",
                        "justification_economique": "Bien que le coût initial soit élevé, expliquez au propriétaire que cela évite la dégradation des fers à béton dans la dalle (qui rouillent et font éclater le béton sous le plafond). Une dalle qui coule détruit les meubles et la peinture intérieure, ce qui coûte 5 fois plus cher à réparer."
                    },
                    "metadata": {
                        "tags_pathologies": ["infiltration_dalle", "toit_terrasse", "etancheite_defaillante"],
                        "type_ouvrage": "Etancheite"
                    }
                }
                cursor.execute(
                    "INSERT INTO production_items (id, generated_json, tags) VALUES (%s, %s, %s);",
                    ("prod-201", psycopg2.extras.Json(prod201_json), "infiltration_dalle,toit_terrasse,etancheite_defaillante")
                )
            conn.commit()

            # --- SEEDS POUR LES PROFESSIONS, CATEGORIES ET CONTEXTES ---
            cursor.execute("SELECT COUNT(*) FROM professions;")
            if cursor.fetchone()[0] == 0:
                print("Insertion des données de démo initiales pour métiers et contextes...")
                
                # Professions
                cursor.execute("INSERT INTO professions (id, name, description) VALUES (%s, %s, %s);", ("prof-1", "Maçonnerie", "Travaux de maçonnerie générale et gros oeuvre."))
                cursor.execute("INSERT INTO professions (id, name, description) VALUES (%s, %s, %s);", ("prof-2", "Mécanique", "Entretien et réparation de véhicules."))
                
                # Categories
                cursor.execute("INSERT INTO categories (id, profession_id, name, description) VALUES (%s, %s, %s, %s);", ("cat-mac-1", "prof-1", "Humidité et Etanchéité", "Traitement des remontées capillaires et infiltrations."))
                cursor.execute("INSERT INTO categories (id, profession_id, name, description) VALUES (%s, %s, %s, %s);", ("cat-mac-2", "prof-1", "Structure et Elévation", "Linteaux, poteaux, poutres, murs."))
                cursor.execute("INSERT INTO categories (id, profession_id, name, description) VALUES (%s, %s, %s, %s);", ("cat-mec-1", "prof-2", "Moteur", "Diagnostic et réparation moteur."))
                cursor.execute("INSERT INTO categories (id, profession_id, name, description) VALUES (%s, %s, %s, %s);", ("cat-mec-2", "prof-2", "Freinage", "Système de freinage."))
                
                # Contextes
                # Context 1: Arase (Maçonnerie)
                cursor.execute("""
                    INSERT INTO contexts (id, category_id, tags, title, source, execution, pitch, dosages, materials, price, justification, type_ouvrage)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    "ctx-1", "cat-mac-1", "remontee_capillaire,humidite_bas,salpetre,humidite,arase,soubassement",
                    "Traitement des remontées d'humidité et salpêtre (Arase Hydrofuge)",
                    "Norme LBTP / RE-CIM Section 5.4 - Barrière d'étanchéité",
                    "1. Piquer l'enduit abîmé ou contaminé sur 50 cm au-dessus des traces de salpêtre.\n2. Laver le mur à l'eau douce pour enlever le sel capillaire.\n3. Mouiller abondamment le mur en parpaings avant d'appliquer le gobetis pour éviter les décollements ('enduit brûlé').\n4. Préparer un mortier de ciment CPJ 42.5 dosé à 350 kg/m³ (1 sac de 50 kg pour 2 brouettes de sable de carrière propre).\n5. Incorporer 1 sachet de SikaCim (ou Super Sikalite) par sac de ciment dans l'eau de gâchage.\n6. Appliquer l'enduit serré en deux passes croisées de 10 mm d'épaisseur.",
                    "« Vieux Père, le bas du mur est en train de gâter à cause de l'humidité qui monte du sol. C'est comme la pluie : si on ne met pas de chapeau, on est mouillé. Le mur a besoin d'un bouclier. Selon la norme LBTP pour la sécurité de la maison, il faut faire une coupure de capillarité. Si on repeint directement sans arase étanche avec hydrofuge SikaCim, la peinture va encore sauter dans 3 mois et ce sera de l'argent jeté. Pour honorer votre investissement et protéger la famille, voici le dosage et la méthode certifiée. Que Dieu bénisse le travail de nos mains. »",
                    psycopg2.extras.Json([{"element": "Ciment CPJ 42.5 (CIMAF/Lafarge)", "ratio": "1 sac (50kg)", "unite_mesure_locale": "Sac"}, {"element": "Sable de carrière propre", "ratio": "2 brouettes de 60L", "unite_mesure_locale": "Brouette (60L)"}, {"element": "Adjuvant hydrofuge SikaCim", "ratio": "1 sachet (1kg)", "unite_mesure_locale": "Sachet (1kg)"}]),
                    psycopg2.extras.Json([{"nom": "Ciment CPJ 42.5", "substitut_acceptable": "Aucun substitut pour arase", "disponibilite": "Quincaillerie"}, {"nom": "SikaCim", "substitut_acceptable": "Super Sikalite", "disponibilite": "Quincaillerie"}, {"nom": "Sable de carrière", "substitut_acceptable": "Sable de lagune lavé", "disponibilite": "Quincaillerie"}]),
                    "4 500 - 6 500 FCFA par mètre linéaire",
                    "L'achat d'un sachet d'hydrofuge (environ 1 500 FCFA) protège la peinture et le plâtre intérieur. En Côte d'Ivoire, les pluies de juin sont très fortes. Ne pas faire d'arase étanche, c'est s'exposer à refaire les enduits chaque année, ce qui coûte 5 fois plus cher.",
                    "Arase"
                ))
                
                # Context 2: Structure (Maçonnerie)
                cursor.execute("""
                    INSERT INTO contexts (id, category_id, tags, title, source, execution, pitch, dosages, materials, price, justification, type_ouvrage)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    "ctx-2", "cat-mac-2", "fissure_structure,linteau_beton,ferraillage,poteau,dalle,fissure",
                    "Ferraillage de renfort et bétonnage de linteau (HA 10)",
                    "CCT BNETD - Règles de calcul des ouvrages en béton armé",
                    "1. Façonner l'armature avec 4 cadres HA 10 filants.\n2. Lier les cadres avec des épingles HA 6 espacées de 15 cm.\n3. Assurer un enrobage de 3 cm minimum avec des cales en mortier.\n4. Utiliser du ciment CPJ 42.5 de structure dosé à 350 kg/m³.\n5. Piquer le béton frais à la barre de fer.\n6. Laisser sécher sous coffrage humide pendant 14 jours minimum.",
                    "« Boss, le linteau c'est comme le pilier de la famille. S'il y a une fissure structurelle au-dessus de la porte, c'est que le fer ou le ciment utilisé était trop faible. La norme BNETD exige du fer HA 10 et du ciment CPJ 42.5. Si on met du fer de 8 ou du ciment CPJ 32.5, le mur va se fendre. Faisons un ouvrage propre qui va durer. »",
                    psycopg2.extras.Json([{"element": "Ciment CPJ 42.5", "ratio": "1 sac", "unite_mesure_locale": "Sac"}, {"element": "Gravier 15/25", "ratio": "2.5 brouettes", "unite_mesure_locale": "Brouette (60L)"}]),
                    psycopg2.extras.Json([{"nom": "Ciment CPJ 42.5", "substitut_acceptable": "Aucun", "disponibilite": "Quincaillerie"}, {"nom": "Fers HA 10", "substitut_acceptable": "Fers certifiés", "disponibilite": "Quincaillerie"}]),
                    "15 000 - 25 000 FCFA par linteau standard",
                    "Le coût s'explique par la qualité mécanique requise.",
                    "Poteau-Poutre"
                ))

                # Context 3: Moteur (Mécanique)
                cursor.execute("""
                    INSERT INTO contexts (id, category_id, tags, title, source, execution, pitch, dosages, materials, price, justification, type_ouvrage)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    "ctx-3", "cat-mec-1", "moteur,vidange,huile,filtre",
                    "Vidange Moteur et Remplacement Filtre",
                    "Manuel du Constructeur Automobile",
                    "1. Mettre le véhicule sur pont élévateur.\n2. Vidanger l'huile usagée à chaud.\n3. Remplacer le filtre à huile et le joint de bouchon de carter.\n4. Remplir avec l'huile recommandée (ex: 5W40 synthétique).\n5. Vérifier le niveau d'huile et l'absence de fuites.",
                    "« Boss, le moteur c'est le coeur de la voiture. Si on ne change pas l'huile à temps, les pièces vont s'user très vite et le moteur risque de couler. Mettre de l'huile de bonne qualité et un filtre neuf, c'est la garantie de rouler sans panne sur la route de Yamoussoukro. Un bon entretien évite les grosses factures. »",
                    psycopg2.extras.Json([{"element": "Huile Moteur 5W40", "ratio": "5 Litres", "unite_mesure_locale": "Bidon (5L)"}]),
                    psycopg2.extras.Json([{"nom": "Huile Synthétique 5W40", "substitut_acceptable": "10W40 (selon km)", "disponibilite": "Station Service ou Boutique Pièces"}, {"nom": "Filtre à huile", "substitut_acceptable": "Aucun", "disponibilite": "Boutique Pièces"}]),
                    "25 000 - 45 000 FCFA",
                    "Le coût inclut l'huile de synthèse et un filtre de qualité pour préserver la durée de vie du moteur.",
                    "Entretien Moteur"
                ))
                
                # Context 4: Freinage (Mécanique)
                cursor.execute("""
                    INSERT INTO contexts (id, category_id, tags, title, source, execution, pitch, dosages, materials, price, justification, type_ouvrage)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    "ctx-4", "cat-mec-2", "frein,plaquette,disque,bruit_freinage",
                    "Remplacement Plaquettes de Frein",
                    "Normes de Sécurité Routière",
                    "1. Démonter la roue.\n2. Repousser le piston de l'étrier.\n3. Remplacer les plaquettes usées par des neuves.\n4. Vérifier l'état du disque.\n5. Pomper sur la pédale de frein avant de rouler.",
                    "« Tonton, avec les freins, on ne blague pas. Si les plaquettes sont finies, ça va rayer le disque et vous n'allez pas pouvoir vous arrêter en cas d'urgence. Des plaquettes neuves, c'est l'assurance pour vous et votre famille sur l'autoroute. »",
                    psycopg2.extras.Json([]),
                    psycopg2.extras.Json([{"nom": "Jeu de Plaquettes", "substitut_acceptable": "Aucun (Sécurité)", "disponibilite": "Boutique Pièces"}]),
                    "15 000 - 30 000 FCFA",
                    "Il est crucial d'utiliser des plaquettes certifiées pour éviter les accidents et l'usure prématurée du disque de frein.",
                    "Sécurité - Freinage"
                ))

                conn.commit()
    except Exception as err:
        print(f"Erreur d'initialisation de la base de données : {err}")
        raise err
    finally:
        if conn:
            conn.close()

# --- REQUÊTES ET ROUTAGE API ---

import hashlib
import secrets

ACTIVE_SESSIONS = {}  # token -> email

def hash_password(password: str) -> str:
    salt = "prosartisan_secure_salt_2026"
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

def clean_and_parse_json(text: str):
    import json as json_lib
    text_clean = text.strip()
    if text_clean.startswith("```"):
        lines = text_clean.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text_clean = "\n".join(lines).strip()
    try:
        return json_lib.loads(text_clean)
    except Exception as first_err:
        start_idx = text_clean.find("{")
        end_idx = text_clean.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            try:
                return json_lib.loads(text_clean[start_idx:end_idx+1])
            except Exception:
                pass
        raise first_err

def generate_llm_fallback(query_tags, user_email):
    import time
    tags_str = ", ".join(query_tags)
    
    # Charger les contextes de notre base de données locale comme source d'information additionnelle
    db_contexts_summary = ""
    conn = None
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            dbname=PG_DB
        )
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM contexts;")
            db_rows = cursor.fetchall()
            for r in db_rows:
                db_contexts_summary += f"- Fiche: {r['title']} | Source: {r['source']} | Dosages: {r['dosages']} | Prix: {r['price']}\n"
    except Exception as e:
        print(f"Erreur lecture contextes pour generate_llm_fallback: {e}")
    finally:
        if conn:
            conn.close()

    # 1. Tenter d'utiliser Gemini avec Grounding de Recherche Google
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = f"""Tu es un expert en bâtiment et maçonnerie en Côte d'Ivoire (normes LBTP, BNETD).
Un maçon te demande une recommandation technique et un argumentaire commercial ('Bouclier Client') pour les tags de pathologies suivants : {tags_str}.

Voici les fiches de référence de la base de données locale du projet :
{db_contexts_summary}

Si l'argumentaire technique, les dosages, ou les spécifications correspondantes ne sont pas fournis ou ne correspondent pas aux fiches de la base de données locale ci-dessus, utilise obligatoirement l'outil Google Search pour trouver des spécifications externes à jour, des normes ivoiriennes pertinentes, des dosages ou des estimations de prix locales en FCFA. Indique clairement dans la source ('norme_origine.source') que l'information provient de cette recherche externe si c'est le cas.

Génère une fiche technique complète et structurée au format JSON.

Règles pour les champs :
1. Le ton du "Bouclier Client" (bouclier_autorite) doit être rédigé à la première personne en tant que chef de chantier ivoirien ("Vieux Père", "Boss de chantier") s'adressant à son client ("Grand-frère", "Tonton", "Maman", "Patron") avec grand respect, bienveillance et autorité technique pour justifier l'achat des bons matériaux et éviter les fausses économies.
2. Formate le résultat exclusivement en JSON valide avec cette structure :
{{
  "id": "llm-fallback-grounded-{int(time.time())}",
  "norme_origine": {{
    "source": "[LBTP ou BNETD ou Autre source externe identifiée par la recherche]",
    "reference_article": "[Référence de l'article ou section, ex: Section 4.2]",
    "titre_original": "[Titre officiel de la règle de l'art]",
    "texte_brut": "[Explication technique de la norme ou spécification trouvée]"
  }},
  "alternative_prosartisan": {{
    "titre_vulgarise": "[Nom clair et vulgarisé de l'ouvrage ou traitement]",
    "methode_execution": "[Étapes détaillées pour réaliser les travaux sur le chantier, adaptées aux tags : {tags_str}]",
    "dosages_recommandes": [
      {{ "element": "[Nom du matériau, ex: Ciment CPJ 42.5]", "ratio": "[ex: 1 sac (50kg) ou ratio précis]", "unite_mesure_locale": "[ex: Sac ou Brouette]" }}
    ],
    "materiaux_recommandes": [
      {{ "nom": "[Nom du matériau]", "substitut_acceptable": "[Substitut]", "disponibilite": "[ex: Quincaillerie]" }}
    ],
    "bouclier_autorite": "[L'argumentaire de vente client écrit dans le ton respectueux ivoirien décrit ci-dessus]"
  }},
  "cout_estime_local": {{
    "gamme_prix": "[Faible ou Moyen ou Eleve]",
    "estimation_m2_fcfa": "[Estimation des prix en FCFA en Côte d'Ivoire récupérée ou estimée par la recherche]",
    "justification_economique": "[Justification claire de l'investissement]"
  }},
  "metadata": {{
    "tags_pathologies": {json.dumps(query_tags)},
    "type_ouvrage": "[ex: Etancheite, Poteau-Poutre, Maconnerie]",
    "is_llm_fallback": true,
    "generated_for": "{user_email}"
  }}
}}
"""
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    response_mime_type="application/json"
                )
            )
            import json as json_lib
            result_json = clean_and_parse_json(response.text)
            return result_json
        except Exception as e:
            print(f"Erreur generate_llm_fallback avec grounding : {e}")

    # 2. Fallback de recherche locale standard
    conn = None
    matched_context = None
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            dbname=PG_DB
        )
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM contexts;")
            contexts = cursor.fetchall()
            
            # Simple matching by tag
            for ctx in contexts:
                ctx_tags = [t.strip().lower() for t in ctx["tags"].split(",") if t.strip()]
                if any(q.lower() in ctx_tags for q in [tag.lower() for tag in query_tags]):
                    matched_context = ctx
                    break
    except Exception as e:
        print(f"Erreur DB dans generate_llm_fallback: {e}")
    finally:
        if conn:
            conn.close()

    if matched_context:
        title = matched_context["title"]
        source = matched_context["source"]
        execution = matched_context["execution"]
        pitch = matched_context["pitch"]
        dosages = matched_context["dosages"] if matched_context["dosages"] else []
        mats = matched_context["materials"] if matched_context["materials"] else []
        price = matched_context["price"]
        justification = matched_context["justification"]
        type_ouvrage = matched_context["type_ouvrage"]
    else:
        title = "Dosage standardisé pour mortier et béton courants"
        source = "Recommandations Générales BNETD / LBTP"
        execution = "1. Délimiter une aire de gâchage propre et plane (plaque de tôle) pour ne pas mélanger de terre.\n2. Mélanger le ciment local et le sable à sec, puis incorporer les graviers.\n3. Ajouter l'eau propre progressivement sans excès pour ne pas affaiblir le mélange.\n4. Mettre en œuvre rapidement avant le début de prise."
        pitch = "« Chef de chantier, pour tous nos travaux, on doit suivre les dosages de l'État pour que le travail soit solide et propre. Le ciment CPJ 32.5 est bon pour monter les briques et crépir, mais pour tout ce qui porte le poids (linteaux, poteaux), le CPJ 42.5 est obligatoire. Faisons un dosage de confiance pour honorer notre nom. »"
        dosages = [
            { "element": "Ciment local (CPJ 32.5 ou 42.5)", "ratio": "1 sac (50kg)", "unite_mesure_locale": "Sac" },
            { "element": "Sable propre", "ratio": "2 brouettes de 60L", "unite_mesure_locale": "Brouette (60L)" }
        ]
        mats = [
            { "nom": "Ciment local", "substitut_acceptable": "Selon type d'ouvrage", "disponibilite": "Quincaillerie" }
        ]
        price = "Sur devis (Dosage standard)"
        justification = "Permet de respecter les ratios réglementaires ivoiriens tout en s'adaptant à la réalité du chantier."
        type_ouvrage = "Elevation"

    fallback_id = f"llm-fallback-{int(time.time())}"
    
    return {
        "id": fallback_id,
        "norme_origine": {
            "source": "LLM Génératif ProsArtisan",
            "reference_article": "ARTICLE 1.1",
            "titre_original": source,
            "texte_brut": f"Recommandations de l'assistant IA générées dynamiquement pour les critères : {tags_str}"
        },
        "alternative_prosartisan": {
            "titre_vulgarise": title,
            "methode_execution": execution,
            "dosages_recommandes": dosages,
            "materiaux_recommandes": mats,
            "bouclier_autorite": pitch
        },
        "cout_estime_local": {
            "gamme_prix": "Moyen",
            "estimation_m2_fcfa": price,
            "justification_economique": justification
        },
        "metadata": {
            "tags_pathologies": query_tags,
            "type_ouvrage": type_ouvrage,
            "is_llm_fallback": True,
            "generated_for": user_email
        }
    }

def analyze_image_with_vlm(image_b64=None, image_url=None, query_tags=None, user_email="Anonyme"):
    if not GEMINI_API_KEY:
        return None
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Préparer le contenu de l'image
        contents = []
        if image_b64:
            import base64
            # Gérer les préfixes éventuels de data URI (ex: data:image/jpeg;base64,...)
            if "," in image_b64:
                image_b64 = image_b64.split(",")[1]
            img_bytes = base64.b64decode(image_b64)
            img_part = types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
            contents.append(img_part)
        elif image_url:
            import requests
            try:
                resp = requests.get(image_url, timeout=10)
                if resp.status_code == 200:
                    img_part = types.Part.from_bytes(data=resp.content, mime_type="image/jpeg")
                    contents.append(img_part)
            except Exception as e:
                print(f"Erreur téléchargement image preset : {e}")
        
        if not contents:
            return None
        
        # Charger les contextes de notre base de données locale comme source d'information additionnelle
        db_contexts_summary = ""
        conn = None
        try:
            conn = psycopg2.connect(
                host=PG_HOST,
                port=PG_PORT,
                user=PG_USER,
                password=PG_PASSWORD,
                dbname=PG_DB
            )
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM contexts;")
                db_rows = cursor.fetchall()
                for r in db_rows:
                    db_contexts_summary += f"- Fiche: {r['title']} | Source: {r['source']} | Dosages: {r['dosages']} | Prix: {r['price']}\n"
        except Exception as e:
            print(f"Erreur lecture contextes pour VLM: {e}")
        finally:
            if conn:
                conn.close()

        prompt = f"""Tu es un expert en diagnostic de pathologies du bâtiment et de maçonnerie en Côte d'Ivoire (normes LBTP, BNETD).
Analyse l'image fournie de manière très détaillée pour détecter la pathologie visible (remontée capillaire, fissure de flexion/cisaillement sur linteau/poteau, infiltration en terrasse, etc.).

Génère une fiche technique complète et structurée au format JSON.

Voici les règles pour les champs du JSON :
1. Les recommandations doivent être extrêmement pertinentes, actualisées et répondre aux critères modernes de construction en Côte d'Ivoire (ex: ciment CPJ 42.5 pour le béton de structure, adjuvants hydrofuges SikaCim ou Super Sikalite pour l'étanchéité, sable de carrière propre et lavé, membranes d'étanchéité bitumineuse NF EN 13969 ou résines SEL fluides modernes).
2. Le ton du "Bouclier Client" (bouclier_autorite) doit être rédigé à la première personne en tant que chef de chantier ivoirien ("Vieux Père", "Boss de chantier") s'adressant à son client ("Grand-frère", "Tonton", "Maman", "Patron") avec grand respect, bienveillance et autorité technique pour justifier l'achat des bons matériaux modernes et rejeter les fausses économies ("mougou-mougou") qui conduisent à des sinistres structurels ou d'étanchéité. Adapte spécifiquement l'argumentaire à ce qui est visible dans l'image.
3. Pour t'inspirer des dosages et normes de la base de données locale du projet, utilise ces fiches de référence s'il y a lieu :
{db_contexts_summary}
4. Si l'argumentaire technique, les dosages, ou les spécifications correspondantes ne sont pas fournis ou ne correspondent pas aux fiches de la base de données locale ci-dessus, utilise obligatoirement l'outil Google Search pour étendre ton analyse sur des spécifications depuis des sources externes (règles BNETD, normes LBTP de Côte d'Ivoire, documentations fabricants Sika/Lafarge/etc., prix locaux des matériaux, etc.). Indique clairement dans le champ source ('norme_origine.source') que l'information provient de cette recherche ou spécification externe.

Génère obligatoirement un JSON valide répondant exactement à cette structure (ne mets aucun texte autour, uniquement le JSON) :
{{
  "id": "vlm-analysis-{int(datetime.utcnow().timestamp())}",
  "norme_origine": {{
    "source": "[Nom de la norme, ex: LBTP ou BNETD]",
    "reference_article": "[Article spécifique, ex: Section 4.2 ou Section 7.8]",
    "titre_original": "[Titre officiel de la règle de l'art]",
    "texte_brut": "[Explication technique de la norme officielle]"
  }},
  "alternative_prosartisan": {{
    "titre_vulgarise": "[Nom clair et vulgarisé de l'ouvrage ou traitement, ex: Réalisation d'une coupure de capillarité (arase étanche)]",
    "methode_execution": "[Étapes claires, détaillées et professionnelles pour réaliser les travaux sur le chantier, adaptées à la pathologie observée sur l'image]",
    "dosages_recommandes": [
      {{ "element": "[ex: Ciment CPJ 42.5 (CIMAF / LafargeHolcim)]", "ratio": "[ex: 1 sac (50kg)]", "unite_mesure_locale": "[ex: Sac]" }}
    ],
    "materiaux_recommandes": [
      {{ "nom": "[ex: Adjuvant SikaCim]", "substitut_acceptable": "[ex: Super Sikalite]", "disponibilite": "[ex: Quincaillerie]" }}
    ],
    "bouclier_autorite": "[L'argumentaire de vente client écrit dans le ton ivoirien respectueux décrit ci-dessus, faisant explicitement référence à ce qui est visible sur l'image]"
  }},
  "cout_estime_local": {{
    "gamme_prix": "[Faible ou Moyen ou Eleve]",
    "estimation_m2_fcfa": "[ex: 4 500 - 6 000 FCFA par m2 ou par mètre linéaire]",
    "justification_economique": "[Justification économique claire pour le client: pourquoi investir dans ces matériaux modernes évite des dépenses répétées]"
  }},
  "metadata": {{
    "tags_pathologies": {json.dumps(query_tags or [])},
    "type_ouvrage": "[ex: Etancheite, Poteau-Poutre, Maconnerie]",
    "is_llm_fallback": true,
    "generated_for": "{user_email}"
  }}
}}
"""
        contents.append(prompt)
        
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                response_mime_type="application/json"
            )
        )
        
        import json as json_lib
        result_json = clean_and_parse_json(response.text)
        return result_json
    except Exception as e:
        print(f"Erreur analyze_image_with_vlm: {e}")
        return None

class ProsArtisanAPIHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def get_authenticated_user(self):
        auth_header = self.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ", 1)[1]
        return ACTIVE_SESSIONS.get(token)

    def translate_path(self, path):
        # Override translate_path to serve static assets from the frontend/ folder
        path = path.split('?', 1)[0]
        path = path.split('#', 1)[0]
        import posixpath
        path = posixpath.normpath(path)
        words = path.split('/')
        words = list(filter(None, words))
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        if words and words[0] == "fileshare":
            local_path = os.path.join(base_dir, "backend", "fileshare")
            for word in words[1:]:
                if os.path.dirname(word) or word in (os.curdir, os.pardir):
                    continue
                local_path = os.path.join(local_path, word)
            return local_path
            
        frontend_dir = os.path.join(base_dir, "frontend")
        
        local_path = frontend_dir
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                continue
            local_path = os.path.join(local_path, word)
        return local_path

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        # Redirect /docs or /swagger to /docs.html
        if path in ("/docs", "/swagger", "/api-docs"):
            self.send_response(301)
            self.send_header("Location", "/docs.html")
            self.end_headers()
            return

        # GET /api/auth/me
        if path == "/api/auth/me":
            user = self.get_authenticated_user()
            if not user:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Unauthorized"}).encode("utf-8"))
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"email": user}).encode("utf-8"))
            return

        # GET /api/staging
        elif path == "/api/staging":
            user = self.get_authenticated_user()
            if not user:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Unauthorized"}).encode("utf-8"))
                return
            conn = None
            try:
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM staging_items ORDER BY created_at DESC;")
                    rows = cursor.fetchall()
                
                result = []
                for r in rows:
                    result.append({
                        "id": r["id"],
                        "raw_pdf_source": r["raw_pdf_source"],
                        "original_extracted_text": r["original_extracted_text"],
                        "status": r["status"],
                        "reviewer_notes": r["reviewer_notes"],
                        "created_at": r["created_at"].isoformat() if isinstance(r["created_at"], datetime) else r["created_at"],
                        "updated_at": r["updated_at"].isoformat() if isinstance(r["updated_at"], datetime) else r["updated_at"],
                        "validated_at": r["validated_at"].isoformat() if r["validated_at"] else None,
                        "generated_json": r["generated_json"]
                    })
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode("utf-8"))
            except Exception as e:
                print(f"Erreur GET /api/staging : {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # GET /api/config/professions
        elif path == "/api/config/professions":
            conn = None
            try:
                conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DB)
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM professions;")
                    rows = cursor.fetchall()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(rows).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn: conn.close()
            return

        # GET /api/config/categories
        elif path == "/api/config/categories":
            conn = None
            try:
                conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DB)
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM categories;")
                    rows = cursor.fetchall()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(rows).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn: conn.close()
            return

        # GET /api/config/contexts
        elif path == "/api/config/contexts":
            conn = None
            try:
                conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DB)
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM contexts;")
                    rows = cursor.fetchall()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(rows).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn: conn.close()
            return

        # GET /api/production
        elif path == "/api/production":
            conn = None
            try:
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM production_items;")
                    rows = cursor.fetchall()
                
                result = []
                for r in rows:
                    result.append(r["generated_json"])
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode("utf-8"))
            except Exception as e:
                print(f"Erreur GET /api/production : {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # GET /api/imports
        elif path == "/api/imports":
            user = self.get_authenticated_user()
            if not user:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Unauthorized"}).encode("utf-8"))
                return
            conn = None
            try:
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM import_history ORDER BY imported_at DESC;")
                    rows = cursor.fetchall()
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(rows).encode("utf-8"))
            except Exception as e:
                print(f"Erreur GET /api/imports : {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # GET /client
        elif path == "/client":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            client_html_path = os.path.join(base_dir, "frontend", "client.html")
            with open(client_html_path, "rb") as f:
                self.wfile.write(f.read())
            return

        # Distribuer le fichier statique
        else:
            super().do_GET()

    def do_POST(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')

        public_post_paths = {
            "/api/auth/register",
            "/api/auth/login",
            "/api/auth/forgot-password",
            "/api/auth/reset-password",
            "/api/auth/oauth2/callback",
            "/api/search",
            "/api/chat"
        }
        
        if path not in public_post_paths:
            user = self.get_authenticated_user()
            if not user:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Unauthorized"}).encode("utf-8"))
                return

        # POST /api/auth/register
        if path == "/api/auth/register":
            try:
                data = json.loads(body)
                email = data.get("email", "").strip().lower()
                password = data.get("password", "")
                
                if not email or not password:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Email et mot de passe requis"}).encode("utf-8"))
                    return
                
                if "@" not in email:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Format d'email invalide"}).encode("utf-8"))
                    return
                
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor() as cursor:
                    cursor.execute("SELECT email FROM users WHERE email = %s;", (email,))
                    if cursor.fetchone():
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Cet utilisateur existe déjà"}).encode("utf-8"))
                        return
                    
                    hashed = hash_password(password)
                    now_str = datetime.utcnow().isoformat() + "Z"
                    cursor.execute(
                        "INSERT INTO users (email, password_hash, created_at) VALUES (%s, %s, %s);",
                        (email, hashed, now_str)
                    )
                    conn.commit()
                
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Utilisateur créé avec succès"}).encode("utf-8"))
            except Exception as e:
                print(f"Erreur d'inscription : {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # POST /api/auth/login
        elif path == "/api/auth/login":
            try:
                data = json.loads(body)
                email = data.get("email", "").strip().lower()
                password = data.get("password", "")
                
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("SELECT password_hash FROM users WHERE email = %s;", (email,))
                    row = cursor.fetchone()
                    
                    if not row or row["password_hash"] != hash_password(password):
                        self.send_response(401)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Identifiants incorrects"}).encode("utf-8"))
                        return
                    
                token = secrets.token_hex(24)
                ACTIVE_SESSIONS[token] = email
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "token": token, "email": email}).encode("utf-8"))
            except Exception as e:
                print(f"Erreur de connexion : {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # POST /api/auth/forgot-password
        elif path == "/api/auth/forgot-password":
            try:
                data = json.loads(body)
                email = data.get("email", "").strip().lower()
                
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor() as cursor:
                    cursor.execute("SELECT email FROM users WHERE email = %s;", (email,))
                    if not cursor.fetchone():
                        self.send_response(404)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Aucun utilisateur trouvé avec cet email"}).encode("utf-8"))
                        return
                    
                    reset_token = secrets.token_hex(4).upper()
                    from datetime import timedelta
                    expiry = datetime.utcnow() + timedelta(minutes=15)
                    expiry_str = expiry.isoformat() + "Z"
                    
                    cursor.execute(
                        "UPDATE users SET reset_token = %s, reset_token_expiry = %s WHERE email = %s;",
                        (reset_token, expiry_str, email)
                    )
                    conn.commit()
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "success", 
                    "message": "Un code de réinitialisation a été généré.",
                    "reset_token": reset_token
                }).encode("utf-8"))
            except Exception as e:
                print(f"Erreur mot de passe oublié : {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # POST /api/auth/reset-password
        elif path == "/api/auth/reset-password":
            try:
                data = json.loads(body)
                email = data.get("email", "").strip().lower()
                reset_token = data.get("reset_token", "").strip().upper()
                new_password = data.get("new_password", "")
                
                if not email or not reset_token or not new_password:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Champs requis manquants"}).encode("utf-8"))
                    return
                
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("SELECT reset_token, reset_token_expiry FROM users WHERE email = %s;", (email,))
                    row = cursor.fetchone()
                    
                    if not row or not row["reset_token"] or row["reset_token"] != reset_token:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Code de réinitialisation invalide"}).encode("utf-8"))
                        return
                    
                    expiry = row["reset_token_expiry"]
                    if isinstance(expiry, str):
                        expiry_clean = re.sub(r'Z$|\+00:00$', '', expiry)
                        expiry_dt = datetime.fromisoformat(expiry_clean)
                    else:
                        expiry_dt = expiry.replace(tzinfo=None) if expiry else datetime.utcnow()
                    
                    if expiry_dt < datetime.utcnow():
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Le code de réinitialisation a expiré"}).encode("utf-8"))
                        return
                    
                    hashed = hash_password(new_password)
                    cursor.execute(
                        "UPDATE users SET password_hash = %s, reset_token = NULL, reset_token_expiry = NULL WHERE email = %s;",
                        (hashed, email)
                    )
                    conn.commit()
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Votre mot de passe a été réinitialisé"}).encode("utf-8"))
            except Exception as e:
                print(f"Erreur réinitialisation : {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # POST /api/auth/oauth2/callback
        elif path == "/api/auth/oauth2/callback":
            try:
                data = json.loads(body)
                email = data.get("email", "").strip().lower()
                code = data.get("code", "")
                
                if not email or not code:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Email et code requis"}).encode("utf-8"))
                    return
                
                if not code.startswith("MOCK_AUTH_"):
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Code d'authentification invalide"}).encode("utf-8"))
                    return
                
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor() as cursor:
                    # Check if user already exists
                    cursor.execute("SELECT email FROM users WHERE email = %s;", (email,))
                    if not cursor.fetchone():
                        # Auto-register user since it's OAuth2 (first connection = registration)
                        now_str = datetime.utcnow().isoformat() + "Z"
                        # Placeholder password because it is authenticated via OAuth2
                        cursor.execute(
                            "INSERT INTO users (email, password_hash, created_at) VALUES (%s, %s, %s);",
                            (email, "OAUTH2_EXTERNAL_AUTHENTICATION", now_str)
                        )
                        conn.commit()
                        print(f"Nouvel utilisateur enregistré via OAuth2 (Google) : {email}")
                    
                # Create session
                token = secrets.token_hex(24)
                ACTIVE_SESSIONS[token] = email
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "token": token, "email": email}).encode("utf-8"))
            except Exception as e:
                print(f"Erreur OAuth2 Callback : {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # POST /api/config/professions
        elif path == "/api/config/professions":
            conn = None
            try:
                data = json.loads(body)
                import uuid
                item_id = data.get("id", f"prof-{uuid.uuid4().hex[:8]}")
                name = data.get("name")
                description = data.get("description", "")
                
                conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DB)
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO professions (id, name, description) VALUES (%s, %s, %s);",
                        (item_id, name, description)
                    )
                    conn.commit()
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "id": item_id}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn: conn.close()
            return

        # POST /api/config/categories
        elif path == "/api/config/categories":
            conn = None
            try:
                data = json.loads(body)
                import uuid
                item_id = data.get("id", f"cat-{uuid.uuid4().hex[:8]}")
                profession_id = data.get("profession_id")
                name = data.get("name")
                description = data.get("description", "")
                
                conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DB)
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO categories (id, profession_id, name, description) VALUES (%s, %s, %s, %s);",
                        (item_id, profession_id, name, description)
                    )
                    conn.commit()
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "id": item_id}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn: conn.close()
            return

        # POST /api/config/contexts
        elif path == "/api/config/contexts":
            conn = None
            try:
                data = json.loads(body)
                import uuid
                item_id = data.get("id", f"ctx-{uuid.uuid4().hex[:8]}")
                category_id = data.get("category_id")
                tags = data.get("tags", "")
                title = data.get("title", "")
                source = data.get("source", "")
                execution = data.get("execution", "")
                pitch = data.get("pitch", "")
                dosages = data.get("dosages", [])
                materials = data.get("materials", [])
                price = data.get("price", "")
                justification = data.get("justification", "")
                type_ouvrage = data.get("type_ouvrage", "")

                conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DB)
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO contexts (id, category_id, tags, title, source, execution, pitch, dosages, materials, price, justification, type_ouvrage)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """, (item_id, category_id, tags, title, source, execution, pitch, psycopg2.extras.Json(dosages), psycopg2.extras.Json(materials), price, justification, type_ouvrage))
                    conn.commit()
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "id": item_id}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn: conn.close()
            return

        # POST /api/staging
        elif path == "/api/staging":
            conn = None
            try:
                data = json.loads(body)
                item_id = data.get("id")
                raw_pdf_source = data.get("raw_pdf_source")
                original_extracted_text = data.get("original_extracted_text")
                generated_json = data.get("generated_json")
                status = data.get("status", "PENDING")
                
                now_str = datetime.utcnow().isoformat() + "Z"

                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO staging_items (id, raw_pdf_source, original_extracted_text, generated_json, status, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s);",
                        (item_id, raw_pdf_source, original_extracted_text, psycopg2.extras.Json(generated_json), status, now_str, now_str)
                    )
                    conn.commit()

                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "id": item_id}).encode("utf-8"))
            except Exception as e:
                print(f"Erreur POST /api/staging : {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # POST /api/staging/<id>/approve
        elif re.match(r"^/api/staging/[^/]+/approve$", path):
            item_id = path.split("/")[3]
            now_str = datetime.utcnow().isoformat() + "Z"

            conn = None
            try:
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    # 1. Mettre à jour staging
                    cursor.execute(
                        "UPDATE staging_items SET status = 'APPROVED', validated_at = %s WHERE id = %s RETURNING generated_json;",
                        (now_str, item_id)
                    )
                    row = cursor.fetchone()
                    
                    if not row:
                        self.send_response(404)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Item not found"}).encode("utf-8"))
                        return

                    generated_json = row["generated_json"]
                    
                    # 2. Extraire les tags
                    tags_list = generated_json.get("metadata", {}).get("tags_pathologies", [])
                    tags_str = ",".join(tags_list)

                    # 3. Pousser en production (UPSERT)
                    cursor.execute("""
                        INSERT INTO production_items (id, generated_json, tags) VALUES (%s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET 
                            generated_json = EXCLUDED.generated_json, 
                            tags = EXCLUDED.tags;
                    """, (item_id, psycopg2.extras.Json(generated_json), tags_str))
                    
                    conn.commit()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "promoted": item_id, "generated_json": generated_json}).encode("utf-8"))
            except Exception as e:
                print(f"Erreur approve: {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # POST /api/staging/<id>/reject
        elif re.match(r"^/api/staging/[^/]+/reject$", path):
            item_id = path.split("/")[3]
            data = json.loads(body)
            notes = data.get("reviewer_notes", "")
            now_str = datetime.utcnow().isoformat() + "Z"

            conn = None
            try:
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE staging_items SET status = 'REJECTED', reviewer_notes = %s, validated_at = %s WHERE id = %s;",
                        (notes, now_str, item_id)
                    )
                    conn.commit()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "rejected": item_id}).encode("utf-8"))
            except Exception as e:
                print(f"Erreur reject: {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # POST /api/search (Recherche Hybride)
        elif path == "/api/search":
            conn = None
            try:
                search_query = json.loads(body)
                query_tags = search_query.get("tags", [])
                filters = search_query.get("filters", {})
                image_b64 = search_query.get("image_b64")
                image_url = search_query.get("image_url")

                user_email = self.get_authenticated_user() or "Anonyme"
                
                # Si une image est fournie et que la clé Gemini est configurée, effectuer l'analyse VLM
                vlm_result = None
                if GEMINI_API_KEY and (image_b64 or image_url):
                    print(f"Lancement de l'analyse VLM pour l'image (utilisateur: {user_email})...")
                    vlm_result = analyze_image_with_vlm(image_b64, image_url, query_tags, user_email)

                if vlm_result:
                    matched_results = [vlm_result]
                else:
                    conn = psycopg2.connect(
                        host=PG_HOST,
                        port=PG_PORT,
                        user=PG_USER,
                        password=PG_PASSWORD,
                        dbname=PG_DB
                    )
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                        cursor.execute("SELECT * FROM production_items;")
                        rows = cursor.fetchall()

                    matched_results = []
                    for r in rows:
                        item_json = r["generated_json"]
                        item_tags = [t.strip() for t in r["tags"].split(",") if t.strip()]

                        # 1. Correspondance sémantique
                        has_tag_match = any(tag in item_tags for tag in query_tags)
                        if not has_tag_match:
                            continue

                        # 2. Filtre de Budget
                        if filters.get("maxBudget"):
                            max_budget = filters["maxBudget"]
                            item_budget = item_json.get("cout_estime_local", {}).get("gamme_prix")
                            budget_weights = { "Faible": 1, "Moyen": 2, "Eleve": 3 }
                            
                            max_weight = budget_weights.get(max_budget, 2)
                            item_weight = budget_weights.get(item_budget, 1)
                            
                            if item_weight > max_weight:
                                continue

                        # 3. Filtre Quincaillerie Locale
                        if filters.get("onlyHardwareStore") is True:
                            mats = item_json.get("alternative_prosartisan", {}).get("materiaux_recommandes", [])
                            has_only_local = all(m.get("disponibilite") == "Quincaillerie" for m in mats)
                            if not has_only_local:
                                continue

                        matched_results.append(item_json)

                    # Si aucune fiche de production ne correspond, consulter le LLM associé au compte
                    if not matched_results:
                        print(f"Fallback LLM pour l'utilisateur : {user_email}")
                        fallback_item = generate_llm_fallback(query_tags, user_email)
                        matched_results.append(fallback_item)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(matched_results).encode("utf-8"))
            except Exception as e:
                print(f"Erreur recherche hybride : {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # POST /api/chat (Chatbot BTP)
        elif path == "/api/chat":
            conn = None
            try:
                chat_data = json.loads(body)
                user_msg = chat_data.get("message", "").strip()
                
                # Récupérer les fiches de production pour le RAG localisé
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM production_items;")
                    rows = cursor.fetchall()

                # Recherche RAG
                rag_matches = []
                user_msg_lower = user_msg.lower()
                for r in rows:
                    item_json = r["generated_json"]
                    item_tags = [t.strip().lower() for t in r["tags"].split(",") if t.strip()]
                    title = item_json.get("alternative_prosartisan", {}).get("titre_vulgarise", "").lower()
                    
                    # Correspondance simple par tags ou titre
                    matched = False
                    for tag in item_tags:
                        if tag in user_msg_lower or user_msg_lower in tag:
                            matched = True
                            break
                    if title and (title in user_msg_lower or any(word in user_msg_lower for word in title.split() if len(word) > 4)):
                        matched = True
                        
                    if matched:
                        rag_matches.append(item_json)

                # Génération de la réponse
                response_text = ""
                sources = []
                
                context_texts = []
                if rag_matches:
                    for match in rag_matches:
                        alt = match["alternative_prosartisan"]
                        norme = match["norme_origine"]
                        cout = match.get("cout_estime_local", {})
                        
                        context_str = f"Titre: {alt['titre_vulgarise']}\nMéthode recommandée: {alt['methode_execution']}\nDosages: "
                        for d in alt["dosages_recommandes"]:
                            context_str += f"{d['element']} - {d['ratio']} ({d['unite_mesure_locale']}), "
                        if cout.get("estimation_m2_fcfa"):
                            context_str += f"\nCoût: {cout['estimation_m2_fcfa']}"
                        
                        context_texts.append(context_str)
                        sources.append({
                            "id": match["id"],
                            "title": alt["titre_vulgarise"],
                            "source_doc": norme["titre_original"]
                        })

                if GEMINI_API_KEY:
                    try:
                        client = genai.Client(api_key=GEMINI_API_KEY)
                        prompt = f"Tu es un assistant BTP expert ('Bouclier d'Autorité') pour la plateforme ProsArtisan en Côte d'Ivoire. Le maçon ('Boss') te demande: '{user_msg}'.\n"
                        if context_texts:
                            prompt += "\nUtilise les informations suivantes de notre base de données locale validée pour répondre de manière très professionnelle, valorisante et claire pour justifier les devis aux clients :\n"
                            prompt += "\n\n---\n".join(context_texts)
                            prompt += "\n\nFormate ta réponse de façon lisible avec des puces. Valide d'abord l'approche du maçon."
                        else:
                            prompt += "\nRéponds de manière professionnelle et adaptée au contexte de construction ivoirien (ciments CPJ 32.5/42.5, dosage, pathologies courantes). Si la question n'est pas liée au BTP ou à la maçonnerie, rappelle poliment ton rôle."
                        
                        response = client.models.generate_content(
                            model='gemini-1.5-flash',
                            contents=prompt
                        )
                        response_text = response.text
                    except Exception as gemini_err:
                        print(f"Erreur appel Gemini : {gemini_err}")
                        response_text = "Désolé Boss, mon cerveau d'intelligence artificielle est indisponible pour le moment. Veuillez vérifier ma connexion au réseau ou ma configuration."
                else:
                    if rag_matches:
                        match = rag_matches[0]
                        alt = match["alternative_prosartisan"]
                        response_text = f"**{alt['titre_vulgarise']}**\n\n*Méthode recommandée :*\n{alt['methode_execution']}\n\n*(L'IA conversationnelle est désactivée. Veuillez configurer GEMINI_API_KEY pour une explication complète)*"
                    else:
                        response_text = "Bonjour Boss ! Je suis l'assistant BTP. (Mode dégradé : Veuillez configurer GEMINI_API_KEY pour utiliser le chatbot)."

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"response": response_text, "sources": sources}).encode("utf-8"))
            except Exception as e:
                print(f"Erreur Chatbot : {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # POST /api/imports (Historiser l'importation)
        elif path == "/api/imports":
            conn = None
            try:
                data = json.loads(body)
                import_id = data.get("id")
                filename = data.get("filename")
                file_size = data.get("file_size")
                imported_at = data.get("imported_at")
                status = data.get("status", "PENDING_VLM")
                
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO import_history (id, filename, file_size, imported_at, status, vlm_extracted, llm_downscaled) VALUES (%s, %s, %s, %s, %s, %s, %s);",
                        (import_id, filename, file_size, imported_at, status, False, False)
                    )
                    conn.commit()

                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "id": import_id}).encode("utf-8"))
            except Exception as e:
                print(f"Erreur POST /api/imports : {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # POST /api/upload (Sauvegarde dans Fileshare et BD)
        elif path == "/api/upload":
            try:
                import base64
                import uuid
                data = json.loads(body)
                filename = data.get("filename", "")
                b64_content = data.get("content", "")
                
                if not filename or not b64_content:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "filename and content (base64) are required"}).encode("utf-8"))
                    return
                
                ext = ""
                if "." in filename:
                    ext = filename.split(".")[-1].lower()
                
                file_id = str(uuid.uuid4())
                safe_filename = f"{file_id}.{ext}" if ext else file_id
                file_path = os.path.join(FILESHARE_DIR, safe_filename)
                
                file_data = base64.b64decode(b64_content)
                with open(file_path, "wb") as f:
                    f.write(file_data)
                
                file_link = f"/fileshare/{safe_filename}"
                now_str = datetime.utcnow().isoformat() + "Z"
                
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO attachments (id, original_filename, extension, file_link, uploaded_by, created_at) VALUES (%s, %s, %s, %s, %s, %s);",
                        (file_id, filename, ext, file_link, user, now_str)
                    )
                    conn.commit()
                
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "id": file_id, "file_link": file_link}).encode("utf-8"))
            except Exception as e:
                print(f"Erreur upload : {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if 'conn' in locals() and conn:
                    conn.close()
            return

        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        user = self.get_authenticated_user()
        if not user:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Unauthorized"}).encode("utf-8"))
            return

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')

        # PUT /api/staging/<id>
        if re.match(r"^/api/staging/[^/]+$", path):
            item_id = path.split("/")[3]
            data = json.loads(body)
            now_str = datetime.utcnow().isoformat() + "Z"

            conn = None
            try:
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE staging_items SET generated_json = %s, updated_at = %s WHERE id = %s;",
                        (psycopg2.extras.Json(data), now_str, item_id)
                    )
                    conn.commit()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "updated": item_id}).encode("utf-8"))
            except Exception as e:
                print(f"Erreur PUT staging: {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        # PUT /api/imports/<id> (Mettre à jour l'état de l'importation)
        elif re.match(r"^/api/imports/[^/]+$", path):
            import_id = path.split("/")[3]
            data = json.loads(body)
            status = data.get("status")
            vlm_extracted = data.get("vlm_extracted")
            llm_downscaled = data.get("llm_downscaled")

            conn = None
            try:
                conn = psycopg2.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    dbname=PG_DB
                )
                
                # Construire dynamiquement le SET
                set_clauses = []
                params = []
                if status is not None:
                    set_clauses.append("status = %s")
                    params.append(status)
                if vlm_extracted is not None:
                    set_clauses.append("vlm_extracted = %s")
                    params.append(vlm_extracted)
                if llm_downscaled is not None:
                    set_clauses.append("llm_downscaled = %s")
                    params.append(llm_downscaled)
                
                if set_clauses:
                    sql = f"UPDATE import_history SET {', '.join(set_clauses)} WHERE id = %s;"
                    params.append(import_id)
                    with conn.cursor() as cursor:
                        cursor.execute(sql, tuple(params))
                        conn.commit()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "updated": import_id}).encode("utf-8"))
            except Exception as e:
                print(f"Erreur PUT /api/imports/{import_id} : {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            finally:
                if conn:
                    conn.close()
            return

        else:
            self.send_response(404)
            self.end_headers()

# --- LANCEMENT DU SERVEUR ---

if __name__ == "__main__":
    init_database()
    
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), ProsArtisanAPIHandler) as httpd:
        print(f"Serveur API ProsArtisan (PostgreSQL) démarré sur : http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nArrêt du serveur...")
            httpd.server_close()
