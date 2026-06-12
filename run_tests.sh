#!/bin/bash

# Configuration
PORT=8000
SERVER_PID=""

# Fonction de nettoyage pour tuer le serveur à la fin
cleanup() {
    if [ -n "$SERVER_PID" ]; then
        echo "=================================================="
        echo "Arrêt du serveur API (PID: $SERVER_PID)..."
        kill "$SERVER_PID" 2>/dev/null
        wait "$SERVER_PID" 2>/dev/null
    fi
}

# S'assurer que le nettoyage est exécuté à la sortie du script
trap cleanup EXIT

echo "=================================================="
echo "🚀 Démarrage du pipeline de tests ProsArtisan IA"
echo "=================================================="

# --- ÉTAPE 1 : TESTS DU BACKEND API ---
echo -e "\n🔹 Étape 1 : Tests du Backend API (Python)"
echo "--------------------------------------------------"

# 1. Vérifier si le port 8000 est déjà occupé
if lsof -i :$PORT >/dev/null 2>&1; then
    echo "❌ Erreur : Le port $PORT est déjà utilisé par un autre processus."
    exit 1
fi

# 2. Démarrer le serveur API en arrière-plan
echo "Démarrage du serveur API..."
./.venv/bin/python3 backend/server.py > backend_server.log 2>&1 &
SERVER_PID=$!

# 3. Attendre que le serveur soit prêt
echo "Attente du démarrage du serveur..."
MAX_ATTEMPTS=15
ATTEMPT=0
READY=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl -s http://localhost:$PORT/api/production >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 1
    ATTEMPT=$((ATTEMPT + 1))
done

if [ $READY -ne 1 ]; then
    echo "❌ Erreur : Le serveur n'a pas démarré à temps. Voir backend_server.log pour les détails."
    exit 1
fi

echo "✅ Serveur démarré avec succès."

# 4. Exécuter les tests pytest
echo "Lancement des tests avec pytest..."
./.venv/bin/pytest backend/test_api_specs.py
BACKEND_EXIT_CODE=$?

if [ $BACKEND_EXIT_CODE -eq 0 ]; then
    echo "✅ Tests backend passés avec succès !"
else
    echo "❌ Échec des tests backend."
fi

# Arrêter le serveur API
cleanup
SERVER_PID=""

# --- ÉTAPE 2 : TESTS DE L'APPLICATION MOBILE ---
echo -e "\n🔹 Étape 2 : Tests de l'Application Mobile (Flutter)"
echo "--------------------------------------------------"

if command -v flutter >/dev/null 2>&1; then
    echo "Lancement des tests widget avec flutter test..."
    (cd mobile && flutter test)
    MOBILE_EXIT_CODE=$?
    if [ $MOBILE_EXIT_CODE -eq 0 ]; then
        echo "✅ Tests mobiles passés avec succès !"
    else
        echo "❌ Échec des tests mobiles."
    fi
else
    echo "⚠️ Flutter n'est pas installé ou n'est pas dans le PATH. Les tests mobiles ont été ignorés."
    MOBILE_EXIT_CODE=0
fi

# --- SYNTHÈSE DES RÉSULTATS ---
echo -e "\n=================================================="
echo "📊 Synthèse des Tests :"
echo "=================================================="
if [ $BACKEND_EXIT_CODE -eq 0 ]; then
    echo "  Backend API   : ✅ SUCCÈS"
else
    echo "  Backend API   : ❌ ÉCHEC"
fi

if [ $MOBILE_EXIT_CODE -eq 0 ]; then
    echo "  Mobile Widget : ✅ SUCCÈS"
else
    echo "  Mobile Widget : ❌ ÉCHEC"
fi
echo "=================================================="

# Exit avec le code d'erreur s'il y en a un
if [ $BACKEND_EXIT_CODE -ne 0 ]; then
    exit $BACKEND_EXIT_CODE
fi

if [ $MOBILE_EXIT_CODE -ne 0 ]; then
    exit $MOBILE_EXIT_CODE
fi

exit 0
