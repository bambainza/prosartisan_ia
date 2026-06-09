Feature: Spécifications de l'API ProsArtisan

  Scenario: Récupération des fiches de production
    Given le serveur API est en cours d'exécution
    When je demande la liste des éléments en production
    Then le code de statut de la réponse doit être 200