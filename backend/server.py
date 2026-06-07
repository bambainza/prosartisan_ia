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

PORT = int(os.environ.get("PORT", 8000))

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

            # Vérifier si Production est vide
            cursor.execute("SELECT COUNT(*) FROM production_items;")
            if cursor.fetchone()[0] == 0:
                print("Insertion des données de démo initiales dans PostgreSQL (Production)...")
                prod1_json = {
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
                    ("prod-201", psycopg2.extras.Json(prod1_json), "infiltration_dalle,toit_terrasse,etancheite_defaillante")
                )
                conn.commit()
    except Exception as err:
        print(f"Erreur d'initialisation de la base de données : {err}")
        raise err
    finally:
        if conn:
            conn.close()

# --- REQUÊTES ET ROUTAGE API ---

class ProsArtisanAPIHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def translate_path(self, path):
        # Override translate_path to serve static assets from the frontend/ folder
        path = path.split('?', 1)[0]
        path = path.split('#', 1)[0]
        import posixpath
        path = posixpath.normpath(path)
        words = path.split('/')
        words = filter(None, words)
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

        # GET /api/staging
        if path == "/api/staging":
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
        
        # POST /api/staging
        if path == "/api/staging":
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

                # Base de connaissances BTP locale (Ivoirienne)
                know_base = {
                    "dalle": "Pour le béton de structure (dalles, poteaux, poutres), le dosage standard LBTP/BNETD est de 350 kg/m³ de ciment de classe CPJ 42.5 (CEM II 42.5). Pour 1 m³ de béton, cela équivaut à 7 sacs de ciment de 50 kg, 400 L de sable de carrière propre et 800 L de gravier concassé 15/25, avec environ 175 à 180 L d'eau propre. Le gâchage manuel doit se faire sur une aire propre (plaque de tôle) pour éviter l'argile ou la terre.",
                    "poteau": "Pour les poteaux de structure, le ciment CPJ 42.5 est exigé avec un ferraillage d'acier HA (haute adhérence). Le béton doit être dosé à 350 kg/m³. Il est impératif de bien piquer le béton frais dans les coffrages à l'aide d'une barre de fer pour éliminer les bulles d'air ('nids de cailloux') avant le séchage.",
                    "béton": "Le béton se dose généralement à 350 kg/m³ pour la structure (dalles, poteaux) et 250 kg/m³ pour le béton de propreté. Utilisez du ciment CPJ 42.5 pour les structures porteuses et du CPJ 32.5 pour le béton non porteur.",
                    "enduit": "Les enduits extérieurs traditionnels s'appliquent en 3 couches successives : 1. Le gobetis d'accrochage (3-5 mm) très riche dosé à 500 kg/m³ de ciment CPJ 32.5. 2. Le corps d'enduit de dressage (10-15 mm) dosé à 350 kg/m³. 3. La finition talochée (5 mm) dosée à 250 kg/m³ de ciment fine.",
                    "crépir": "Le crépissage d'un mur extérieur nécessite un mortier dosé à 350 kg/m³ de ciment CPJ 32.5 et du sable de lagune fin. Mouillez abondamment le mur avant d'appliquer le gobetis pour éviter les décollements (enduit 'brûlé').",
                    "arase": "Pour bloquer les remontées capillaires d'eau et le salpêtre en bas des murs, l'arase étanche est obligatoire au-dessus du soubassement. Réalisez un mortier de ciment CPJ 42.5 dosé à 350 kg/m³ (soit 1 sac pour 2 brouettes de sable propre) enrichi d'un sachet d'hydrofuge de masse SikaCim de 1 kg par sac de ciment. Appliquez sur 20 mm d'épaisseur.",
                    "soubassement": "Le soubassement doit être étanchéifié avec un mortier hydrofuge ou un enduit multicouche contenant du SikaCim. Une arase étanche de coupure de capillarité de 20 mm d'épaisseur doit être coulée au-dessus du soubassement avant d'élever les murs de façade.",
                    "salpêtre": "Le salpêtre apparaît à cause de l'humidité ascensionnelle provenant du sol. La seule solution définitive est de réaliser une arase étanche hydrofuge au-dessus du soubassement. Si le mur est déjà construit, il faut injecter des résines hydrofuges ou gratter l'enduit gâté, appliquer un mortier d'arase hydrofuge et ré-enduire avec adjuvant.",
                    "humidité": "L'humidité en bas des murs est généralement causée par l'absence ou la mauvaise réalisation de l'arase étanche de coupure de capillarité. Pour régler cela, appliquez un mortier de ciment étanche additionné de SikaCim et assurez-vous de drainer les eaux pluviales à l'extérieur.",
                    "sikacim": "L'adjuvant hydrofuge de masse SikaCim (sachet de 1 kg) s'ajoute directement à l'eau de gâchage pour boucher les pores du mortier ou du béton. Il s'utilise à raison de 1 sachet par sac de ciment de 50 kg pour l'étanchéité des arases, soubassements, enduits extérieurs et piscines.",
                    "hydrofuge": "L'hydrofuge de masse (comme le SikaCim) permet d'étanchéifier le béton ou le mortier dans la masse en obturant les canaux capillaires. Il se dose généralement à 1% ou 2% du poids de ciment (soit 1 sachet de 1 kg par sac de 50 kg).",
                    "ciment": "En Côte d'Ivoire, nous utilisons principalement le CPJ 32.5 pour les maçonneries courantes, enduits et mortiers de pose, et le CPJ 42.5 pour les bétons armés de structure (dalles, poteaux, poutres) et arases étanches.",
                    "32.5": "Le ciment CPJ 32.5 (CEM II/B-L 32.5 R) convient pour les travaux courants de maçonnerie, enduits de dressage et lissage, et pose de parpaings. Il ne doit pas être utilisé pour couler des dalles porteuses ou des poteaux.",
                    "42.5": "Le ciment CPJ 42.5 (CEM II/A 42.5 R) est un ciment haute résistance obligatoire pour les ouvrages en béton armé (dalles, linteaux, escaliers) et les arases étanches de soubassement. Sa prise rapide offre une excellente résistance mécanique sous 28 jours.",
                    "sable": "Le sable de carrière propre (grains moyens/gros, sans argile) est idéal pour les bétons de structure et mortiers d'arase. Le sable de lagune fin convient pour la finition lisse des enduits mais doit être lavé s'il provient de lagunes salées."
                }

                if rag_matches:
                    match = rag_matches[0]
                    alt = match["alternative_prosartisan"]
                    norme = match["norme_origine"]
                    cout = match.get("cout_estime_local", {})
                    
                    response_text = f"**{alt['titre_vulgarise']}**\n\n"
                    response_text += f"*Méthode recommandée :*\n{alt['methode_execution']}\n\n"
                    response_text += "*Dosages locaux recommandés :*\n"
                    for d in alt["dosages_recommandes"]:
                        response_text += f"- **{d['element']}** : {d['ratio']} ({d['unite_mesure_locale']})\n"
                    
                    if cout.get("estimation_m2_fcfa"):
                        response_text += f"\n*Coût estimé localement :* {cout['estimation_m2_fcfa']}\n"
                    
                    response_text += f"\n*(Source RAG validée : {norme['source']} - {norme['titre_original']} - {norme['reference_article']} - Réf: {match['id']})*"
                    
                    sources.append({
                        "id": match["id"],
                        "title": alt["titre_vulgarise"],
                        "source_doc": norme["titre_original"]
                    })
                else:
                    matched_key = None
                    for key in know_base:
                        if key in user_msg_lower:
                            matched_key = key
                            break
                    
                    if matched_key:
                        response_text = know_base[matched_key]
                    else:
                        response_text = "Bonjour Boss ! Je suis votre assistant BTP ProsArtisan. Je peux vous renseigner sur le dosage des bétons de structure (ciment CPJ 42.5), des enduits (ciment CPJ 32.5), l'étanchéité des soubassements avec l'adjuvant SikaCim, ou les spécifications des sables. Posez-moi une question sur ces matériaux ou techniques de chantier !"

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

        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

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
