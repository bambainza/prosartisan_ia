/**
 * config.js
 * Configuration dynamique des endpoints d'API pour ProsArtisan IA.
 * Détecte automatiquement l'environnement de running (Web standard vs Mobile Local Asset).
 */

(function() {
  // Par défaut, si l'application est chargée depuis le système de fichiers local (mobile)
  if (window.location.protocol === "file:") {
    // Adresse locale pour l'émulateur Android vers le serveur localhost de la machine hôte
    window.API_BASE_URL = "http://10.0.2.2:8000";
    console.log("ProsArtisan Mobile detected: using API_BASE_URL =", window.API_BASE_URL);
  } else {
    // En production web, les requêtes sont relatives au même domaine
    window.API_BASE_URL = "";
    console.log("ProsArtisan Web detected: using relative API paths.");
  }
})();
