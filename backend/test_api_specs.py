import pytest
import requests
from pytest_bdd import scenarios, given, when, then

# Définition de l'URL de base pour les tests locaux
BASE_URL = "http://localhost:8000"

# Charger toutes les spécifications du dossier features
scenarios("features/api.feature")

@given("le serveur API est en cours d'exécution")
def api_server_running():
    # Ce test suppose que vous avez lancé `python backend/server.py` dans un autre terminal
    pass

@when("je demande la liste des éléments en production", target_fixture="response")
def request_production_items():
    # Effectue une requête HTTP réelle vers l'API
    return requests.get(f"{BASE_URL}/api/production")

@then("le code de statut de la réponse doit être 200")
def check_status_code(response):
    # Vérifie que la réponse de l'API est un succès
    assert response.status_code == 200

def test_search_fallback():
    # 1. Se connecter pour récupérer un jeton de session
    login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@prosartisan.ci",
        "password": "admin123"
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["token"]
    
    # 2. Lancer une recherche hybride avec des tags inexistants pour déclencher le fallback
    headers = {"Authorization": f"Bearer {token}"}
    search_resp = requests.post(f"{BASE_URL}/api/search", json={
        "tags": ["non_existent_tag_for_fallback_testing"],
        "filters": {}
    }, headers=headers)
    
    assert search_resp.status_code == 200
    results = search_resp.json()
    assert len(results) == 1
    fallback_item = results[0]
    
    # Vérifications de la structure du fallback
    assert "metadata" in fallback_item
    assert fallback_item["metadata"]["is_llm_fallback"] is True
    assert fallback_item["metadata"]["generated_for"] == "admin@prosartisan.ci"
    
    assert "alternative_prosartisan" in fallback_item
    pitch = fallback_item["alternative_prosartisan"]["bouclier_autorite"]
    
    # Vérification de l'intégration socio-anthropologique
    assert any(term in pitch for term in ["Chef de chantier", "Vieux Père", "Boss", "Tonton"])

def test_search_fallback_anonymous():
    # Lancer une recherche sans en-tête Authorization
    search_resp = requests.post(f"{BASE_URL}/api/search", json={
        "tags": ["non_existent_tag_for_fallback_testing"],
        "filters": {}
    })
    
    assert search_resp.status_code == 200
    results = search_resp.json()
    assert len(results) == 1
    fallback_item = results[0]
    
    assert fallback_item["metadata"]["is_llm_fallback"] is True
    assert fallback_item["metadata"]["generated_for"] == "Anonyme"

def test_chat_endpoint():
    # Test chat endpoint without relying on specific Gemini behavior,
    # just checking that it returns a 200 OK and a response string.
    chat_resp = requests.post(f"{BASE_URL}/api/chat", json={
        "message": "Bonjour, comment faire une arase ?"
    })
    
    assert chat_resp.status_code == 200
    results = chat_resp.json()
    assert "response" in results
    assert isinstance(results["response"], str)
    assert "sources" in results
    assert isinstance(results["sources"], list)