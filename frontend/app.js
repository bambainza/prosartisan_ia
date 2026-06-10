/**
 * app.js
 * Logique métier principale et simulateur de pipelines d'IA (VLM, Downscaling, Hybrid RAG, Offline Queue).
 */

import { dbInstance, INITIAL_PATHOLOGY_PRESETS } from "./db.js";

// Documents techniques institutionnels prédéfinis pour la démo d'ingestion
export const MOCK_INSTITUTIONAL_DOCS = [
  {
    id: "doc-1",
    title: "Guide LBTP 2023 - Spécifications Dalles Béton",
    raw_text: "SECTION 3.1: DOSAGE DES BÉTONS DE STRUCTURE. Le béton destiné aux ouvrages porteurs (dalles, poteaux, poutres) doit impérativement être dosé à 350 kg/m³ de ciment Portland Pur de classe CEM I 42.5 R ou CEM II/A 42.5. Le malaxage mécanique à tambour rotatif est obligatoire pendant une durée minimale de 180 secondes. L'ajout d'eau en cours de prise pour améliorer la maniabilité est formellement interdit sous peine de chute drastique de la résistance mécanique sous 28 jours.",
    markdown_tables: `| Composant | Dosage par m³ de béton | Spécification |
| :--- | :--- | :--- |
| Ciment | 350 kg | CEM I ou II 42.5 R |
| Sable sec | 400 L | Sable siliceux lavé |
| Gravier | 800 L | Gravier concassé 15/25 |
| Eau max | 175 L | Eau propre (pH > 6) |`
  },
  {
    id: "doc-2",
    title: "Norme BNETD - Enduits extérieurs de protection",
    raw_text: "PROT-402: MÉTHODOLOGIE DE L'ENDUIT TRADITIONNEL. Les maçonneries en blocs de ciment doivent recevoir un enduit de protection appliqué en 3 couches successives : 1. Gobetis d'accrochage d'épaisseur 3 à 5 mm dosé à 500 kg/m³ de ciment de classe CEM II 32.5 R. 2. Corps d'enduit de dressage d'épaisseur 10 à 15 mm dosé à 350 kg/m³. 3. Couche de finition talochée d'épaisseur 5 mm dosée à 250 kg/m³.",
    markdown_tables: `| Couche d'Enduit | Épaisseur | Dosage Ciment / m³ | Utilisation |
| :--- | :--- | :--- | :--- |
| 1. Gobetis | 3 - 5 mm | 500 kg (CEM II 32.5) | Accrochage rugueux |
| 2. Corps d'enduit | 10 - 15 mm | 350 kg | Dressage et planéité |
| 3. Finition | 5 mm | 250 kg | Lissage esthétique |`
  }
];

class AppManager {
  constructor() {
    this.currentNetworkState = "wifi"; // "wifi", "3g", "offline"
    this.offlineQueue = [];
    this.logCallbacks = [];
  }

  // --- Outil de journalisation (Logs) pour afficher ce que fait l'IA sous le capot ---
  addLogListener(callback) {
    this.logCallbacks.push(callback);
  }

  log(category, message, details = "") {
    const timestamp = new Date().toLocaleTimeString();
    const logItem = { timestamp, category, message, details };
    console.log(`[${category.toUpperCase()}] ${message}`, details);
    this.logCallbacks.forEach(cb => cb(logItem));
  }

  setNetworkState(state) {
    this.currentNetworkState = state;
    this.log("system", `État du réseau modifié : ${state.toUpperCase()}`);

    // Si on repasse en ligne, vider la file d'attente (synchronisation)
    if (state !== "offline" && this.offlineQueue.length > 0) {
      this.syncOfflineQueue();
    }
  }

  // --- PIPELINE 1 : Ingestion & Déclassement (PISL) ---

  /**
   * Simule la conversion d'un PDF technique en Markdown sémantique (LlamaParse)
   */
  async simulateVlmExtraction(docId) {
    const doc = MOCK_INSTITUTIONAL_DOCS.find(d => d.id === docId);
    if (!doc) return null;

    this.log("vlm", "Lancement du traitement LlamaParse (Extraction de tables)...");

    // Simuler le délai d'appel API VLM
    await new Promise(resolve => setTimeout(resolve, 800));

    this.log("vlm", `Extraction réussie. Table sémantique récupérée pour : "${doc.title}"`);
    return {
      title: doc.title,
      raw_text: doc.raw_text,
      markdown: doc.markdown_tables
    };
  }

  /**
   * Simule l'appel au LLM de Déclassement (Downscaling LLM)
   * Traduit les prescriptions brutes en alternatives réalistes pour Yopougon/Koumassi.
   */
  async simulateLLMDownscaling(docTitle, rawText, markdown) {
    this.log("llm-downscale", "Envoi des données brutes + tableaux de dosages au LLM de déclassement...");

    await new Promise(resolve => setTimeout(resolve, 1200));

    // Générer un JSON adapté au type de document
    let generatedJson = {};

    if (docTitle.includes("Dalles Béton")) {
      generatedJson = {
        id: "stage-" + Math.floor(Math.random() * 1000 + 200),
        norme_origine: {
          source: "LBTP",
          reference_article: "SECTION 3.1",
          titre_original: "Dosage des bétons de structure (Dalles)",
          texte_brut: rawText
        },
        alternative_prosartisan: {
          titre_vulgarise: "Mélange et coulage manuel de béton de structure (dalles & poteaux)",
          methode_execution: "Effectuer un gâchage manuel méticuleux uniquement sur une aire propre et plane (plaque de tôle d'acier ou dalle béton nettoyée) pour éviter d'incorporer de la terre ou des débris organiques. Mélanger d'abord le ciment, le sable et le gravier à sec. Retourner le tas au moins 3 fois jusqu'à obtenir une couleur grise homogène. Ajouter l'eau au centre du cratère de manière progressive. Gâcher vigoureusement. Piquer le béton frais à la barre de fer après coulage pour chasser les bulles d'air. Maintenir humide l'ouvrage (arrosage matinal doux) pendant les 7 premiers jours.",
          dosages_recommandes: [
            { element: "Ciment CPJ 42.5 (CIMAF / LafargeHolcim / Dangote)", ratio: "1 sac (50kg)", unite_mesure_locale: "Sac" },
            { element: "Sable de carrière propre (grains moyens)", ratio: "1.5 brouettes de 60L", unite_mesure_locale: "Brouette (60L)" },
            { element: "Gravier concassé type 15/25", ratio: "2.5 brouettes de 60L", unite_mesure_locale: "Brouette (60L)" },
            { element: "Eau propre du robinet", ratio: "22 Litres (environ 2 seaux de maçon de 10L)", unite_mesure_locale: "Seau de maçon (10L)" }
          ],
          materiaux_recommandes: [
            { nom: "Ciment CPJ 42.5", substitut_acceptable: "CPJ 32.5 (FORMELLEMENT INTERDIT POUR LES DALLES PORTEUSES)", disponibilite: "Quincaillerie" },
            { nom: "Sable de carrière", substitut_acceptable: "Sable de lagune (doit être lavé à l'eau douce avant usage)", disponibilite: "Quincaillerie" },
            { nom: "Gravier 15/25 concassé", substitut_acceptable: "Gravier roulé de rivière trié", disponibilite: "Zone Industrielle" }
          ]
        },
        cout_estime_local: {
          gamme_prix: "Moyen",
          estimation_m2_fcfa: "12 000 - 18 000 FCFA par m² de dalle coulée",
          justification_economique: "Le choix du ciment CPJ 42.5 est non négociable pour la sécurité structurelle. Le coût s'explique par la qualité mécanique requise. Expliquez au client que rogner sur la qualité du ciment mettra sa famille en danger de mort en cas d'effondrement."
        },
        metadata: {
          tags_pathologies: ["fissure_structure", "infiltration_dalle", "fissure_dalle"],
          type_ouvrage: "Dallage"
        }
      };
    } else if (
      docTitle.toLowerCase().includes("arase") ||
      docTitle.toLowerCase().includes("soubassement") ||
      rawText.toLowerCase().includes("arase") ||
      rawText.toLowerCase().includes("soubassement") ||
      rawText.toLowerCase().includes("sikacim")
    ) {
      generatedJson = {
        id: "stage-" + Math.floor(Math.random() * 1000 + 200),
        norme_origine: {
          source: docTitle.includes("LBTP") ? "LBTP" : "Norme Importée",
          reference_article: "SECTION 5.4",
          titre_original: "Spécifications des arases étanches",
          texte_brut: rawText
        },
        alternative_prosartisan: {
          titre_vulgarise: "Réalisation d'arase étanche de soubassement contre le salpêtre",
          methode_execution: "1. Préparer la surface du mur de soubassement en nettoyant les débris. 2. Gâcher un mortier dosé à 350 kg/m³ de ciment CPJ 42.5 (environ 1 sac pour 2 brouettes de sable de carrière propre). 3. Ajouter l'adjuvant hydrofuge de masse SikaCim à raison de 1 sachet de 1 kg par sac de ciment directement dans l'eau de gâchage. 4. Appliquer le mortier hydrofuge sur une épaisseur uniforme de 20 mm pour créer la coupure capillaire étanche.",
          dosages_recommandes: [
            { element: "Ciment CPJ 42.5 (CIMAF / LafargeHolcim / Dangote)", ratio: "1 sac (50kg)", unite_mesure_locale: "Sac" },
            { element: "Sable de carrière propre (grains moyens)", ratio: "2 brouettes de 60L", unite_mesure_locale: "Brouette (60L)" },
            { element: "Hydrofuge de masse SikaCim (sachet 1kg)", ratio: "1 sachet par sac de ciment", unite_mesure_locale: "Sachet (1kg)" },
            { element: "Eau propre", ratio: "22 Litres (environ 2 seaux de maçon de 10L)", unite_mesure_locale: "Seau de maçon (10L)" }
          ],
          materiaux_recommandes: [
            { nom: "Ciment CPJ 42.5", substitut_acceptable: "CPJ 32.5 (FORMELLEMENT DÉCONSEILLÉ POUR LES ARASES)", disponibilite: "Quincaillerie" },
            { nom: "Sable de carrière", substitut_acceptable: "Sable de lagune bien lavé", disponibilite: "Quincaillerie" },
            { nom: "Hydrofuge de masse SikaCim", substitut_acceptable: "Super Sikalite ou adjuvant équivalent certifié", disponibilite: "Quincaillerie" }
          ]
        },
        cout_estime_local: {
          gamme_prix: "Faible",
          estimation_m2_fcfa: "4 500 - 6 500 FCFA par mètre linéaire",
          justification_economique: "L'arase étanche est le bouclier d'autorité qui protège définitivement les murs de la maison contre le salpêtre et la remontée capillaire. Expliquez au propriétaire qu'investir quelques milliers de francs aujourd'hui évite de devoir refaire toutes les peintures du bas des murs chaque année."
        },
        metadata: {
          tags_pathologies: ["remontee_capillaire", "humidite_bas", "salpetre"],
          type_ouvrage: "Arase"
        }
      };
    } else {
      // Enduits extérieurs
      generatedJson = {
        id: "stage-" + Math.floor(Math.random() * 1000 + 200),
        norme_origine: {
          source: "BNETD",
          reference_article: "PROT-402",
          titre_original: "Méthodologie de l'enduit traditionnel",
          texte_brut: rawText
        },
        alternative_prosartisan: {
          titre_vulgarise: "Réalisation d'enduits muraux extérieurs résistants au décollement",
          methode_execution: "1. Préparation du support : Mouiller abondamment le mur en parpaings creux avant application. Si le support est trop sec, il absorbera l'eau du mortier et l'enduit se décollera ('brûlera'). 2. Gobetis (accrochage) : Appliquer un mortier fluide (dosé à 1 sac de ciment CPJ 32.5 pour 1.5 brouettes de sable fin) jeté vigoureusement à la truelle pour former une texture rugueuse. Laisser sécher 24h. 3. Corps d'enduit : Appliquer une couche de 1.5 cm d'épaisseur dosée à 1 sac de ciment pour 2 brouettes de sable de lagune. Dresser à la règle de maçon. Laisser sécher 48h. 4. Finition : Enduit fin dosé à 1 sac pour 3 brouettes de sable, lissé finement à la taloche mousse.",
          dosages_recommandes: [
            { element: "Ciment CPJ 32.5 (CIMAF / SOCIM)", ratio: "1 sac (50kg) pour le corps d'enduit", unite_mesure_locale: "Sac" },
            { element: "Sable de lagune (grains fins) ou sable fin", ratio: "2 brouettes de 60L", unite_mesure_locale: "Brouette (60L)" },
            { element: "Eau propre", ratio: "20 Litres", unite_mesure_locale: "Seau de maçon (10L)" }
          ],
          materiaux_recommandes: [
            { nom: "Ciment CPJ 32.5", substitut_acceptable: "CPJ 42.5 (Possible mais plus cher et risque de faïençage si mal dosé)", disponibilite: "Quincaillerie" },
            { nom: "Sable de lagune fin", substitut_acceptable: "Sable de carrière tamisé fin", disponibilite: "Quincaillerie" }
          ]
        },
        cout_estime_local: {
          gamme_prix: "Faible",
          estimation_m2_fcfa: "3 500 - 5 000 FCFA par m²",
          justification_economique: "L'enduit est un élément de protection indispensable. Expliquez au propriétaire qu'un enduit réalisé sans arrosage préalable du mur va fissurer et s'écailler en moins d'une saison des pluies, l'obligeant à tout gratter et repeindre."
        },
        metadata: {
          tags_pathologies: ["salpetre", "humidite_bas", "fissure_structure"],
          type_ouvrage: "Enduit"
        }
      };
    }

    // Insérer dans la base de staging
    const stagingItem = {
      id: generatedJson.id,
      raw_pdf_source: docTitle,
      original_extracted_text: rawText,
      status: "PENDING",
      created_at: new Date().toISOString(),
      generated_json: generatedJson
    };

    const res = await dbInstance.addStagingItem(stagingItem);
    if (!res || res.error) {
      this.log("llm-downscale", `Échec de la création de la fiche en staging.`);
      return null;
    }
    this.log("llm-downscale", `Fiche créée dans la Staging DB avec succès sous l'ID : ${stagingItem.id}`, JSON.stringify(generatedJson, null, 2));

    return stagingItem;
  }

  // --- PIPELINE 2 : Interface de Staging & Ingestion en Production ---

  async approveItem(id) {
    const item = await dbInstance.approveStagingItem(id);
    if (item && !item.error) {
      this.log("staging-db", `Fiche approuvée par l'expert technique. Indexation vectorielle déclenchée pour l'ID : ${id}`);
      this.log("vector-db", `Vecteurs générés et poussés dans la production (Collection Qdrant) pour la fiche : "${item.generated_json.alternative_prosartisan.titre_vulgarise}"`);
      return true;
    }
    return false;
  }

  async rejectItem(id, notes) {
    const item = await dbInstance.rejectStagingItem(id, notes);
    if (item && !item.error) {
      this.log("staging-db", `Fiche rejetée. Statut mis à REJECTED pour l'ID : ${id}. Notes : ${notes}`);
      return true;
    }
    return false;
  }

  async updateItemContent(id, updatedJson) {
    const item = await dbInstance.updateStagingItem(id, updatedJson);
    if (item && !item.error) {
      this.log("staging-db", `Fiche modifiée et mise à jour en staging pour l'ID : ${id}`);
      return true;
    }
    return false;
  }

  // --- PIPELINE 3 : Workflow Utilisateur (Vision to RAG) & Simulateur mobile ---

  /**
   * Simule la prise de photo par le maçon, l'envoi de la photo et l'analyse de vision.
   * Gère la simulation de compression d'image pour optimiser la 3G.
   */
  async processUserPhotoAndRAG(pathologyPreset, userFilters = {}) {
    const startTime = Date.now();
    this.log("mobile-app", `Début du traitement de l'image de pathologie : "${pathologyPreset.title}"`);

    // 1. Simuler la compression locale sur le mobile
    this.log("mobile-app", "Simulation de la compression native de l'image...");
    await new Promise(resolve => setTimeout(resolve, 300));

    const sizeOriginal = "4.2 Mo (PNG brut)";
    const sizeCompressed = "38 Ko (WebP progressif 800x800, Q=70)";
    this.log("mobile-app", `Compression terminée : ${sizeOriginal} -> ${sizeCompressed}`);

    // 2. Simuler la latence réseau selon l'état choisi
    let uploadDelay = 400; // Wifi par défaut
    if (this.currentNetworkState === "3g") {
      uploadDelay = 2200; // Latence 3G dégradée
      this.log("network", "Connexion 3G lente : Envoi progressif des paquets d'image...");
    } else if (this.currentNetworkState === "offline") {
      // Gestion du mode hors-ligne
      this.log("network", "Mode Hors-ligne : Impossible de joindre le cloud ProsArtisan.");
      return await this.executeLocalFallback(pathologyPreset, userFilters);
    }

    await new Promise(resolve => setTimeout(resolve, uploadDelay));
    this.log("api-gateway", `Requête reçue sur le serveur cloud (Latence réseau : ${uploadDelay}ms)`);

    // 3. Appel du modèle de vision (simulé)
    this.log("vision-model", "Appel du modèle de vision de pathologie du bâtiment...");
    await new Promise(resolve => setTimeout(resolve, 500));

    const detectedTags = pathologyPreset.tags;
    this.log("vision-model", `Pathologie classifiée avec succès. Tags détectés : [${detectedTags.join(", ")}]`);

    // 4. Recherche hybride dans la Vector DB (Qdrant)
    this.log("vector-db", `Requête de recherche vectorielle hybride lancée... Tags : [${detectedTags.join(", ")}]`);

    // Récupérer les fiches correspondantes
    const searchResults = await dbInstance.hybridSearch(detectedTags, userFilters);

    if (searchResults.length === 0) {
      this.log("vector-db", "Aucun résultat trouvé dans la Vector DB pour ces critères.");
      this.log("llm-fallback", "Consultation du LLM génératif associé au compte (Intégration socio-anthropologique)...");

      const fallbackData = this.generateLLMFallbackPitch(pathologyPreset, userFilters);
      const fallbackDuration = ((Date.now() - startTime) / 1000).toFixed(1);

      return {
        status: "success",
        source: "llm_fallback",
        duration: fallbackDuration,
        tags: detectedTags,
        data: fallbackData
      };
    }

    this.log("vector-db", `${searchResults.length} document(s) trouvé(s) et renvoyé(s) pour enrichissement.`);

    // 5. Génération finale du Bouclier d'Autorité (LLM RAG)
    this.log("llm-rag", "Génération de l'argumentaire et de la solution par le LLM ProsArtisan...");
    await new Promise(resolve => setTimeout(resolve, 1000));

    const finalResponse = this.generatePersuasivePitch(searchResults[0], pathologyPreset, userFilters);

    const totalDuration = ((Date.now() - startTime) / 1000).toFixed(1);
    this.log("system", `Workflow terminé avec succès en ${totalDuration}s.`);

    return {
      status: "success",
      source: "cloud",
      duration: totalDuration,
      tags: detectedTags,
      data: finalResponse
    };
  }

  /**
   * Génère l'argumentaire final (Bouclier d'Autorité)
   */
  generatePersuasivePitch(knowledgeItem, pathologyPreset, filters) {
    const alt = knowledgeItem.alternative_prosartisan;
    const cost = knowledgeItem.cout_estime_local;

    // Traduction de la gamme de prix
    const prixBadge = { "Faible": "🟢 Économique", "Moyen": "🟡 Modéré", "Eleve": "🔴 Investissement" }[cost.gamme_prix];

    return {
      titre: alt.titre_vulgarise,
      type_ouvrage: knowledgeItem.metadata.type_ouvrage,
      pathologie_detectee: pathologyPreset.title,
      budget_categorie: prixBadge,
      estimation_fcfa: cost.estimation_m2_fcfa,

      // Bouclier d'autorité (Persuasion client)
      argumentaire_client: alt.bouclier_autorite || `« Propriétaire, votre mur présente des remontées d'humidité qui proviennent du sol (capillarité). Si nous refaisons simplement la peinture, elle va cloquer et tomber d'ici la fin de la saison des pluies. Selon les règles de construction de l'État (norme LBTP), il est obligatoire de créer une arase étanche ou barrière de coupure pour stopper l'eau. En appliquant la méthode ProsArtisan avec du ciment CPJ 42.5 et un hydrofuge de masse SikaCim, nous protégeons durablement votre mur et votre investissement. C'est l'assurance d'avoir un bâtiment sain sans avoir à refaire les travaux chaque année. »`,

      // Fiche technique pour le maçon
      instructions_techniques: alt.methode_execution,

      // Matériaux à acheter
      dosages: alt.dosages_recommandes,
      materiaux: alt.materiaux_recommandes,
      justification_prix: cost.justification_economique,
      
      // Indication Fallback LLM
      is_llm_fallback: knowledgeItem.metadata.is_llm_fallback || false,
      generated_for: knowledgeItem.metadata.generated_for || null
    };
  }

  generateLLMFallbackPitch(pathologyPreset, filters) {
    return {
      titre: `Diagnostic IA : ${pathologyPreset.title}`,
      type_ouvrage: "Général",
      pathologie_detectee: pathologyPreset.title,
      budget_categorie: "🟡 Modéré",
      estimation_fcfa: "Sur devis spécifique",

      // Bouclier d'autorité (Persuasion client)
      argumentaire_client: `« Grand-frère (ou Patron), la maison c'est le refuge de la famille. Face à ce problème de ${pathologyPreset.title.toLowerCase()}, mon devoir d'artisan est de vous conseiller la meilleure solution pour votre tranquillité. Un bon traitement aujourd'hui, avec de bons matériaux, vous évitera de jeter l'argent par la fenêtre demain. On va gérer ça proprement selon les règles. »`,

      // Fiche technique pour le maçon
      instructions_techniques: `🌟 Contexte Anthropologique Ivoirien :\n1. Posture : Parlez avec respect ("Grand-frère") mais restez le "Boss" (l'expert).\n2. Ne critiquez pas l'artisan précédent devant le client, préservez l'harmonie sociale.\n\n🛠️ Action Technique :\nUtilisez des matériaux adaptés (ex: CPJ 42.5 ou hydrofuge selon le cas) et respectez le temps de séchage.`,

      // Matériaux à acheter
      dosages: [
        { element: "Ciment adapté", ratio: "Selon norme", unite_mesure_locale: "Sac" },
        { element: "Sable de carrière propre", ratio: "Proportion standard", unite_mesure_locale: "Brouette (60L)" }
      ],
      materiaux: [
        { nom: "Matériaux de base", substitut_acceptable: "Selon arrivage", disponibilite: "Quincaillerie" }
      ],
      justification_prix: "L'IA conseille d'ajuster selon la quincaillerie locale. Rappelez que rogner sur la qualité crée des doubles dépenses ('Mougou-mougou coûte cher')."
    };
  }

  /**
   * Mode dégradé hors-ligne : utilise le cache local SQLite et le modèle de vision local
   */
  async executeLocalFallback(pathologyPreset, userFilters) {
    this.log("mobile-app", "Exécution du fallback local : Démarrage du modèle ONNX embarqué...");

    // Simuler le traitement du modèle de vision TFLite/ONNX local (plus rapide car pas d'envoi réseau)
    const detectedTags = pathologyPreset.tags;
    this.log("mobile-app", `Vision locale terminée. Tags de pathologie identifiés : [${detectedTags.join(", ")}]`);

    // Interroger la base locale (les fiches déjà stockées dans le cache SQLite du téléphone)
    this.log("mobile-app", "Recherche dans la base SQLite locale (Cache)...");
    const searchResults = await dbInstance.hybridSearch(detectedTags, userFilters);

    if (searchResults.length === 0) {
      this.log("mobile-app", "Aucune fiche correspondante trouvée dans le cache SQLite local.");
      return {
        status: "no_results_offline",
        message: "Vous êtes hors-ligne et cette pathologie n'est pas disponible dans votre cache local. La requête a été ajoutée à la file d'attente pour synchronisation ultérieure."
      };
    }

    // Formuler l'argumentaire à partir du modèle local
    this.log("mobile-app", "Génération locale de l'argumentaire (Modèle Edge)...");
    const localResult = this.generatePersuasivePitch(searchResults[0], pathologyPreset, userFilters);

    // Mettre en file d'attente pour synchro statistique d'usage plus tard
    this.offlineQueue.push({
      action: "log_diagnostic",
      timestamp: new Date().toISOString(),
      pathologyId: pathologyPreset.id,
      resolvedId: searchResults[0].id
    });
    this.log("mobile-app", "Diagnostic sauvegardé localement dans la file d'attente SQLite.");

    return {
      status: "success",
      source: "local_cache",
      duration: "0.2",
      tags: detectedTags,
      data: localResult
    };
  }

  /**
   * Simule la synchronisation des données de chantiers accumulées hors-ligne
   */
  async syncOfflineQueue() {
    this.log("network", `Réseau rétabli. Synchronisation de la queue locale (${this.offlineQueue.length} éléments en attente)...`);
    await new Promise(resolve => setTimeout(resolve, 1000));

    this.log("network", "Synchronisation terminée. Rapports d'analyse transmis au serveur cloud ProsArtisan.");
    this.offlineQueue = [];
  }
}

export const appInstance = new AppManager();
export { dbInstance };
