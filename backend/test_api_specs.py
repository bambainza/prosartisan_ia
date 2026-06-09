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