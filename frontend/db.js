/**
 * db.js
 * Client de base de données asynchrone pour le prototype ProsArtisan IA.
 * Communique avec le serveur API Python (server.py) connecté à la base SQLite.
 */

export const INITIAL_PATHOLOGY_PRESETS = [
  {
    id: "pathology-1",
    title: "Remontée capillaire sévère",
    image: "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?auto=format&fit=crop&w=400&q=80",
    description: "Humidité ascensionnelle qui fait sauter l'enduit et la peinture sur le bas des murs en parpaings creux de 15 cm.",
    tags: ["remontee_capillaire", "humidite_bas", "salpetre", "parpaing_creux"]
  },
  {
    id: "pathology-2",
    title: "Fissure de flexion sur linteau",
    image: "https://images.unsplash.com/photo-1590069261209-f8e9b8642343?auto=format&fit=crop&w=400&q=80",
    description: "Fissure horizontale ou oblique à la base d'un linteau en béton armé au-dessus d'une porte ou fenêtre.",
    tags: ["fissure_structure", "linteau_beton", "cisaillement", "ferraillage"]
  },
  {
    id: "pathology-3",
    title: "Infiltration sur dalle terrasse",
    image: "https://images.unsplash.com/photo-1504307651254-35680f356dfd?auto=format&fit=crop&w=400&q=80",
    description: "Infiltration d'eau de pluie à travers une dalle de toiture-terrasse non étanchéifiée ou fissurée.",
    tags: ["infiltration_dalle", "toit_terrasse", "etancheite_defaillante", "fissure_dalle"]
  }
];

class APIDatabaseClient {
  // --- STAGING DB ---
  async getStagingItems() {
    try {
      const res = await fetch("/api/staging");
      if (!res.ok) throw new Error("Erreur réseau");
      return await res.json();
    } catch (err) {
      console.error("Impossible de récupérer les fiches en staging:", err);
      return [];
    }
  }

  async addStagingItem(item) {
    try {
      const res = await fetch("/api/staging", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(item)
      });
      return await res.json();
    } catch (err) {
      console.error("Impossible d'ajouter la fiche en staging:", err);
      return null;
    }
  }

  async updateStagingItem(id, updatedJson) {
    try {
      const res = await fetch(`/api/staging/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updatedJson)
      });
      return await res.json();
    } catch (err) {
      console.error("Impossible de modifier la fiche en staging:", err);
      return null;
    }
  }

  async approveStagingItem(id) {
    try {
      const res = await fetch(`/api/staging/${id}/approve`, {
        method: "POST"
      });
      return await res.json();
    } catch (err) {
      console.error("Impossible d'approuver la fiche:", err);
      return null;
    }
  }

  async rejectStagingItem(id, reviewerNotes = "") {
    try {
      const res = await fetch(`/api/staging/${id}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reviewer_notes: reviewerNotes })
      });
      return await res.json();
    } catch (err) {
      console.error("Impossible de rejeter la fiche:", err);
      return null;
    }
  }

  // --- PRODUCTION VECTOR DB ---
  async getProductionItems() {
    try {
      const res = await fetch("/api/production");
      if (!res.ok) throw new Error("Erreur réseau");
      return await res.json();
    } catch (err) {
      console.error("Impossible de récupérer les fiches en production:", err);
      return [];
    }
  }

  /**
   * Effectue la recherche hybride sémantique + filtres via le serveur Python SQLite
   */
  async hybridSearch(queryTags, metadataFilters = {}) {
    try {
      const res = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tags: queryTags,
          filters: metadataFilters
        })
      });
      return await res.json();
    } catch (err) {
      console.error("Erreur de recherche hybride:", err);
      return [];
    }
  }

  async sendChatMessage(message, history = []) {
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: message,
          history: history
        })
      });
      return await res.json();
    } catch (err) {
      console.error("Erreur chatbot API:", err);
      return { error: err.message, response: "Désolé Boss, mon serveur de chat est inaccessible." };
    }
  }

  async getImportHistory() {
    try {
      const res = await fetch("/api/imports");
      if (!res.ok) throw new Error("Erreur réseau");
      return await res.json();
    } catch (err) {
      console.error("Impossible de récupérer l'historique des imports:", err);
      return [];
    }
  }

  async logImport(item) {
    try {
      const res = await fetch("/api/imports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(item)
      });
      return await res.json();
    } catch (err) {
      console.error("Impossible d'historiser l'importation:", err);
      return null;
    }
  }

  async updateImportStatus(id, updates) {
    try {
      const res = await fetch(`/api/imports/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates)
      });
      return await res.json();
    } catch (err) {
      console.error("Impossible de mettre à jour le statut de l'import:", err);
      return null;
    }
  }
}

export const dbInstance = new APIDatabaseClient();
