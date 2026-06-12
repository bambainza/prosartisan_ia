/**
 * client.js
 * Logique client mobile autonome ProsArtisan IA.
 * Gère la communication API, la synthèse/reconnaissance vocale et les simulations offline/3G.
 */

import { dbInstance } from "./db.js";

// Presets de pathologies pour le simulateur
const PATHOLOGY_PRESETS = [
  {
    id: "preset-1",
    title: "Humidité bas de mur",
    image: "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?auto=format&fit=crop&w=200&q=80",
    tags: ["remontee_capillaire", "humidite_bas", "salpetre"],
    description: "L'humidité monte du sol et détruit le bas de la peinture."
  },
  {
    id: "preset-2",
    title: "Fissure linteau porte",
    image: "https://images.unsplash.com/photo-1590069261209-f8e9b8642343?auto=format&fit=crop&w=200&q=80",
    tags: ["fissure_structure", "linteau_beton", "ferraillage"],
    description: "Fissure structurelle au-dessus de la porte principale."
  },
  {
    id: "preset-3",
    title: "Infiltration dalle toit",
    image: "https://images.unsplash.com/photo-1504307651254-35680f356dfd?auto=format&fit=crop&w=200&q=80",
    tags: ["infiltration_dalle", "toit_terrasse", "etancheite_defaillante"],
    description: "L'eau traverse la dalle du salon lors des pluies d'Abidjan."
  }
];

class ClientAppManager {
  constructor() {
    this.networkState = "wifi"; // "wifi", "3g", "offline"
    this.selectedPreset = null;
    this.currentDoc = null; // Fiche active renvoyée par le RAG
    this.offlineQueue = [];
    this.recognition = null;
    this.speechUtterance = null;
    this.isRecording = false;
    this.isPlayingAudio = false;

    // Cache local simulé en localStorage
    this.localCache = {};
  }

  init() {
    this.setupCache();
    this.setupDOM();
    this.bindEvents();
    this.setupSpeechRecognition();
    this.drawMap();

    this.log("system", "Application ProsArtisan Mobile initialisée.");
  }

  // Initialisation du cache hors-ligne avec des données de démo par défaut
  setupCache() {
    const demoItems = [
      {
        id: "prod-201",
        metadata: { type_ouvrage: "Etancheite", tags_pathologies: ["infiltration_dalle", "toit_terrasse", "etancheite_defaillante"] },
        cout_estime_local: { gamme_prix: "Eleve", estimation_m2_fcfa: "8 000 - 12 000 FCFA par m²", justification_economique: "Évite l'oxydation des fers." },
        alternative_prosartisan: {
          titre_vulgarise: "Étanchéité liquide de toit-terrasse (SEL)",
          methode_execution: "Nettoyer la dalle, appliquer résine d'étanchéité, poser la toile en fibre de verre, puis deuxième couche de résine.",
          dosages_recommandes: [
            { element: "Résine d'étanchéité liquide", ratio: "1.5 kg par m²", unite_mesure_locale: "Seau de maçon (10L)" },
            { element: "Toile fibre de verre", ratio: "1.1 m² par m²", unite_mesure_locale: "Sac" }
          ],
          materiaux_recommandes: [
            { nom: "Résine SEL", substitut_acceptable: "Peinture routière", disponibilite: "Zone Industrielle" }
          ]
        }
      }
    ];
    localStorage.setItem("prosartisan_cache", JSON.stringify(demoItems));
  }

  setupDOM() {
    this.dom = {
      // Views
      screenHome: document.getElementById("screen-home"),
      screenResult: document.getElementById("screen-result"),
      loaderPanel: document.getElementById("loader-panel"),
      resultArea: document.getElementById("result-area"),

      // Inputs
      uploadInput: document.getElementById("image-upload"),
      uploadZone: document.getElementById("upload-zone"),
      presetContainer: document.getElementById("preset-container"),
      dictationInput: document.getElementById("dictation-input"),
      btnMic: document.getElementById("btn-mic"),
      btnDiagnose: document.getElementById("btn-diagnose"),
      btnBackHome: document.getElementById("btn-back-home"),
      btnSimulateVoice: document.getElementById("btn-simulate-voice"),

      // Compression
      compressIndicator: document.getElementById("compress-indicator"),
      compressBar: document.getElementById("compress-bar"),
      compressText: document.getElementById("compress-text"),

      // Navigation & Settings
      navDiag: document.getElementById("nav-diag"),
      navMap: document.getElementById("nav-map"),
      navSettings: document.getElementById("nav-settings"),
      btnClientLogout: document.getElementById("btn-client-logout"),
      badgeNetwork: document.getElementById("badge-network"),
      settingsModal: document.getElementById("settings-modal"),
      btnCloseSettings: document.getElementById("btn-close-settings"),
      selectNetwork: document.getElementById("setting-network"),

      // Interactive map
      mapCanvas: document.getElementById("quincaillerie-map"),
      mapView: document.getElementById("map-view"),
      btnBackMap: document.getElementById("btn-back-map"),

      // Chat BTP
      navChat: document.getElementById("nav-chat"),
      chatView: document.getElementById("chat-view"),
      btnBackChat: document.getElementById("btn-back-chat"),
      chatMessages: document.getElementById("chat-messages"),
      chatSuggestions: document.getElementById("chat-suggestions"),
      btnChatMic: document.getElementById("btn-chat-mic"),
      chatInput: document.getElementById("chat-input"),
      btnSendChat: document.getElementById("btn-send-chat"),

      // Console
      consoleLogs: document.getElementById("console-logs")
    };
  }

  bindEvents() {
    // Changement de réseau
    this.dom.selectNetwork.addEventListener("change", (e) => {
      this.setNetwork(e.target.value);
    });

    // Clic sur Paramètres
    this.dom.navSettings.addEventListener("click", () => {
      this.dom.settingsModal.classList.remove("hidden");
    });
    this.dom.btnCloseSettings.addEventListener("click", () => {
      this.dom.settingsModal.classList.add("hidden");
    });

    // Clic sur Déconnexion
    if (this.dom.btnClientLogout) {
      this.dom.btnClientLogout.addEventListener("click", () => {
        localStorage.removeItem("auth_token");
        localStorage.removeItem("user_email");
        window.location.href = "login.html?redirect=client.html";
      });
    }

    // Clic sur Carte
    this.dom.navMap.addEventListener("click", () => {
      this.dom.screenHome.classList.add("hidden");
      this.dom.screenResult.classList.add("hidden");
      this.dom.chatView.classList.add("hidden");
      this.dom.mapView.classList.remove("hidden");
      this.dom.navMap.classList.add("active");
      this.dom.navDiag.classList.remove("active");
      this.dom.navChat.classList.remove("active");
      this.drawMap();
    });
    this.dom.btnBackMap.addEventListener("click", () => {
      this.dom.mapView.classList.add("hidden");
      if (this.currentDoc) {
        this.dom.screenResult.classList.remove("hidden");
      } else {
        this.dom.screenHome.classList.remove("hidden");
      }
      this.dom.navDiag.classList.add("active");
      this.dom.navMap.classList.remove("active");
      this.dom.navChat.classList.remove("active");
    });

    // Navigation Diagnostic
    this.dom.navDiag.addEventListener("click", () => {
      this.dom.mapView.classList.add("hidden");
      this.dom.chatView.classList.add("hidden");
      if (this.currentDoc) {
        this.dom.screenHome.classList.add("hidden");
        this.dom.screenResult.classList.remove("hidden");
      } else {
        this.dom.screenResult.classList.add("hidden");
        this.dom.screenHome.classList.remove("hidden");
      }
      this.dom.navDiag.classList.add("active");
      this.dom.navMap.classList.remove("active");
      this.dom.navChat.classList.remove("active");
    });

    // Navigation Chat BTP
    this.dom.navChat.addEventListener("click", () => {
      this.dom.mapView.classList.add("hidden");
      this.dom.screenHome.classList.add("hidden");
      this.dom.screenResult.classList.add("hidden");
      this.dom.chatView.classList.remove("hidden");
      this.dom.navChat.classList.add("active");
      this.dom.navDiag.classList.remove("active");
      this.dom.navMap.classList.remove("active");
      this.initChat();
    });
    this.dom.btnBackChat.addEventListener("click", () => {
      this.dom.chatView.classList.add("hidden");
      if (this.currentDoc) {
        this.dom.screenResult.classList.remove("hidden");
      } else {
        this.dom.screenHome.classList.remove("hidden");
      }
      this.dom.navDiag.classList.add("active");
      this.dom.navChat.classList.remove("active");
      this.dom.navMap.classList.remove("active");
    });

    // Rendu des presets de pathologies
    this.renderPresets();

    // Importation de fichier photo
    this.dom.uploadZone.addEventListener("click", () => this.dom.uploadInput.click());
    this.dom.uploadInput.addEventListener("change", (e) => {
      this.handleImageSelect(e.target.files[0]);
      this.dom.uploadInput.value = "";
    });

    // Drag and drop photo
    this.dom.uploadZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      this.dom.uploadZone.style.borderColor = "var(--neon-cyan)";
    });
    this.dom.uploadZone.addEventListener("dragleave", () => {
      this.dom.uploadZone.style.borderColor = "rgba(255, 255, 255, 0.15)";
    });
    this.dom.uploadZone.addEventListener("drop", (e) => {
      e.preventDefault();
      this.dom.uploadZone.style.borderColor = "rgba(255, 255, 255, 0.15)";
      if (e.dataTransfer.files[0]) {
        this.handleImageSelect(e.dataTransfer.files[0]);
      }
    });

    // Lancer le diagnostic
    this.dom.btnDiagnose.addEventListener("click", () => this.runDiagnostic());

    // Retour à l'accueil
    this.dom.btnBackHome.addEventListener("click", () => {
      this.currentDoc = null;
      this.dom.screenResult.classList.add("hidden");
      this.dom.screenHome.classList.remove("hidden");
      // Réinitialiser la zone d'upload
      this.selectedPreset = null;
      this.selectedImageBase64 = null;
      this.renderPresets();
      this.dom.uploadInput.value = "";
      this.dom.uploadZone.innerHTML = `<span class="upload-icon">🧱</span>
                                      <div class="upload-text">Prendre une Photo / Choisir Image</div>
                                      <div class="upload-subtext">Glissez-déposez ou cliquez ici</div>`;
      this.dom.compressIndicator.classList.add("hidden");
      this.dom.dictationInput.value = "";
      this.dom.btnDiagnose.disabled = true;
    });

    // Simulation voix Nouchi
    this.dom.btnSimulateVoice.addEventListener("click", () => this.simulateNouchiDictation());
  }

  renderPresets() {
    this.dom.presetContainer.innerHTML = PATHOLOGY_PRESETS.map(p => `
      <div class="preset-thumb" data-id="${p.id}" id="preset-${p.id}">
        <img src="${p.image}" alt="${p.title}" />
        <span>${p.title}</span>
      </div>
    `).join("");

    // Rendre cliquable
    PATHOLOGY_PRESETS.forEach(p => {
      const card = document.getElementById(`preset-${p.id}`);
      card.addEventListener("click", () => {
        PATHOLOGY_PRESETS.forEach(pr => {
          document.getElementById(`preset-${pr.id}`).classList.remove("active");
        });
        card.classList.add("active");
        this.selectedPreset = p;
        this.dom.btnDiagnose.disabled = false;

        // Simuler la compression sur la sélection d'un preset
        this.simulateCompression(p.title + ".jpg");
      });
    });
  }

  // --- RECONNAISSANCE VOCALE (SpeechToText) ---
  setupSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      this.recognition = new SpeechRecognition();
      this.recognition.continuous = false;
      this.recognition.lang = "fr-FR";
      this.recognition.interimResults = false;

      this.recognition.onstart = () => {
        this.isRecording = true;
        this.dom.btnMic.classList.add("recording");
        this.log("voice", "Enregistrement vocal actif. Parlez...");
      };

      this.recognition.onresult = (e) => {
        const text = e.results[0][0].transcript;
        this.dom.dictationInput.value = text;
        this.log("voice", `Transcription vocale : "${text}"`);
      };

      this.recognition.onerror = (e) => {
        this.log("voice", `Erreur vocale : ${e.error}`);
        this.stopRecording();
      };

      this.recognition.onend = () => {
        this.stopRecording();
      };

      // Liaison clic bouton mic
      this.dom.btnMic.addEventListener("click", () => {
        if (this.isRecording) {
          this.recognition.stop();
        } else {
          this.recognition.start();
        }
      });
    } else {
      this.dom.btnMic.addEventListener("click", () => {
        alert("La reconnaissance vocale n'est pas supportée sur votre navigateur. Utilisez le lien de simulation Nouchi.");
      });
    }
  }

  stopRecording() {
    this.isRecording = false;
    this.dom.btnMic.classList.remove("recording");
  }

  simulateNouchiDictation() {
    const textPreset = "Le mur là est trop mouillé au salon, la peinture est en train de quitter dessus, le salpêtre a gâté tout le bas. On a besoin d'arase étanche propre avec hydrofuge SikaCim.";
    this.dom.dictationInput.value = "";
    let i = 0;

    this.log("voice", "Simulation de dictée vocale Nouchi...");
    this.dom.btnMic.classList.add("recording");

    const typingInterval = setInterval(() => {
      this.dom.dictationInput.value += textPreset[i];
      i++;
      if (i >= textPreset.length) {
        clearInterval(typingInterval);
        this.dom.btnMic.classList.remove("recording");
        this.log("voice", "Transcription terminée.");
      }
    }, 25);
  }

  // --- TRAITEMENT ET COMPRESSION D'IMAGE ---
  handleImageSelect(file) {
    if (!file) return;
    this.selectedPreset = {
      id: "custom-upload",
      title: file.name,
      tags: ["remontee_capillaire", "humidite_bas", "salpetre"], // Fallback par défaut
      description: "Image importée par l'utilisateur."
    };

    // Afficher l'aperçu de l'image dans la zone d'upload
    const reader = new FileReader();
    reader.onload = (e) => {
      this.dom.uploadZone.innerHTML = `<img src="${e.target.result}" class="w-full h-32 object-cover rounded-xl" alt="Aperçu" />
                                      <div class="text-[10px] text-cyan-400 mt-2 font-bold">${file.name}</div>`;
      this.selectedImageBase64 = e.target.result.split(',')[1];
    };
    reader.readAsDataURL(file);

    // Débloquer le bouton
    this.dom.btnDiagnose.disabled = false;
    this.simulateCompression(file.name, file.size);
  }

  simulateCompression(filename, originalSize = 3450000) {
    this.dom.compressIndicator.classList.remove("hidden");
    this.dom.compressBar.style.width = "0%";
    this.dom.compressText.textContent = "Traitement en cours...";

    const sizeMo = (originalSize / (1024 * 1024)).toFixed(1);

    let progress = 0;
    const interval = setInterval(() => {
      progress += 15;
      if (progress > 100) progress = 100;
      this.dom.compressBar.style.width = `${progress}%`;

      if (progress >= 100) {
        clearInterval(interval);
        // Taille compressée simulée (entre 20 et 50 Ko)
        const compressedSizeKb = Math.floor(Math.random() * 20 + 25);
        this.dom.compressText.innerHTML = `WebP Compressé : <strong>${sizeMo} Mo</strong> &rarr; <strong>${compressedSizeKb} Ko</strong> (Optimisé 3G)`;
        this.log("image", `Compression locale de ${filename} réussie (${sizeMo} Mo -> ${compressedSizeKb} Ko).`);
      }
    }, 80);
  }

  // --- REQUÊTE RAG ET DÉROULEMENT DU DIAGNOSTIC ---
  async runDiagnostic() {
    this.dom.screenHome.classList.add("hidden");
    this.dom.loaderPanel.classList.remove("hidden");

    let tags = this.selectedPreset ? [...this.selectedPreset.tags] : ["remontee_capillaire"];
    const textContext = this.dom.dictationInput.value;

    // Analyse du texte saisi par l'artisan pour orienter les tags de diagnostic RAG
    if (textContext) {
      const textLower = textContext.toLowerCase();
      const hasFissure = /fissur|linteau|poteau|poutre|fer|armature|béton|structure/i.test(textLower);
      const hasInfiltration = /infiltration|dalle|terrasse|toit|fuite|pluie|etanche/i.test(textLower);
      const hasHumidite = /humid|salpêtre|peinture|bas|capill|arase/i.test(textLower);

      if (this.selectedPreset && this.selectedPreset.id === "custom-upload") {
        const newTags = [];
        if (hasFissure) newTags.push("fissure_structure", "linteau_beton", "ferraillage");
        if (hasInfiltration) newTags.push("infiltration_dalle", "toit_terrasse", "etancheite_defaillante");
        if (hasHumidite || newTags.length === 0) newTags.push("remontee_capillaire", "humidite_bas", "salpetre");
        tags = newTags;
      }
    }

    let imageB64 = null;
    let imageUrl = null;
    if (this.selectedPreset) {
      if (this.selectedPreset.id === "custom-upload") {
        imageB64 = this.selectedImageBase64;
      } else {
        imageUrl = this.selectedPreset.image;
      }
    }

    // Simuler le délai réseau selon le mode sélectionné
    let delay = 400;
    if (this.networkState === "3g") {
      delay = 2400;
      this.log("network", "Envoi des données compressées sur réseau 3G (latence accrue)...");
    } else if (this.networkState === "offline") {
      delay = 150;
      this.log("network", "Mode Hors-ligne : Interrogation de la base cache SQLite locale...");
    }

    await new Promise(resolve => setTimeout(resolve, delay));

    try {
      let resultDoc = null;

      if (this.networkState === "offline") {
        // Mode offline : Charger du cache local (LocalStorage)
        const localCacheData = JSON.parse(localStorage.getItem("prosartisan_cache") || "[]");
        // Filtrer par tags
        resultDoc = localCacheData.find(item =>
          item.metadata.tags_pathologies.some(t => tags.includes(t))
        );

        // Si aucun match local, prendre la première fiche du cache
        if (!resultDoc && localCacheData.length > 0) {
          resultDoc = localCacheData[0];
        }

        // Enregistrer la requête dans la queue de synchro locale
        this.offlineQueue.push({
          timestamp: new Date().toISOString(),
          tags: tags,
          text: textContext,
          status: "pending_sync"
        });

        this.log("offline-queue", "Diagnostic sauvegardé localement dans la file d'attente.");
        this.renderConsoleLogs();
      } else {
        // Mode en ligne : Requête POST /api/search avec jeton
        const list = await dbInstance.hybridSearch(tags, {
          maxBudget: "Moyen",
          onlyHardwareStore: false
        }, imageB64, imageUrl);
        if (list && list.length > 0) {
          resultDoc = list[0];
        }
      }

      this.dom.loaderPanel.classList.add("hidden");
      this.dom.screenResult.classList.remove("hidden");

      if (resultDoc) {
        this.currentDoc = resultDoc;
        this.renderResult(resultDoc);
        this.log("rag", `Résultat du RAG récupéré pour la fiche : "${resultDoc.alternative_prosartisan.titre_vulgarise}"`);
      } else {
        this.log("llm", "Aucun résultat dans la base RAG. Interrogation du LLM (Contexte socio-anthropologique ivoirien)...");
        resultDoc = await this.fallbackToLLM(tags, textContext);
        this.currentDoc = resultDoc;
        this.renderResult(resultDoc);
        this.log("llm", "Diagnostic LLM de secours généré avec succès.");
      }

    } catch (err) {
      console.error(err);
      this.dom.loaderPanel.classList.add("hidden");
      this.dom.screenResult.classList.remove("hidden");
      this.dom.resultArea.innerHTML = `
        <div class="glass-card text-center py-6 border-red-500/30">
          <span class="text-2xl block mb-2">⚠️</span>
          <p class="text-sm font-semibold text-red-400">Erreur de connexion</p>
          <p class="text-xs text-slate-400 mt-2">Impossible de joindre le serveur API. Veuillez vérifier que server.py et PostgreSQL sont démarrés.</p>
        </div>
      `;
      this.log("system", `Erreur de communication : ${err.message}`);
    }
  }

  async fallbackToLLM(tags, textContext) {
    this.log("llm", "Génération de l'analyse avec contexte culturel (Solidarité, Respect des aînés)...");
    await new Promise(resolve => setTimeout(resolve, 1500));

    const detectedIssue = tags.length > 0 ? tags.join(", ").replace(/_/g, " ") : "Problème non spécifié";

    return {
      id: "llm-fallback-" + Date.now(),
      norme_origine: {
        source: "LLM Génératif ProsArtisan",
        titre_original: "Analyse experte générée par IA",
        reference_article: "N/A"
      },
      metadata: {
        type_ouvrage: "Général",
        tags_pathologies: tags
      },
      cout_estime_local: {
        gamme_prix: "Moyen",
        estimation_m2_fcfa: "Sur devis spécifique",
        justification_economique: "Le LLM recommande d'ajuster selon les prix de la quincaillerie locale. Rappelez au client que chercher trop de réduction entraîne un travail bâclé ('Mougou-mougou coûte cher')."
      },
      alternative_prosartisan: {
        titre_vulgarise: `Diagnostic IA : ${detectedIssue}`,
        methode_execution: `🌟 Approche Socio-Anthropologique (Côte d'Ivoire) :\n- Posture du Boss : En Afrique, le chef de chantier est garant de la sécurité familiale. Parlez au client avec respect ("Grand-frère", "Tonton") tout en assumant votre expertise technique.\n- Gestion du conflit : Ne critiquez jamais l'artisan précédent devant le client (préservez l'harmonie sociale), expliquez simplement que "les éléments ont travaillé".\n\n🛠️ Recommandation Technique :\n1. Traitez la zone touchée avec des dosages certifiés.\n2. Utilisez le sable de carrière bien lavé.\n3. Prenez le temps de faire le travail sans précipitation.`,
        bouclier_autorite: `« Grand-frère (ou Patron), la maison c'est le refuge de la famille. Aujourd'hui, on remarque un petit souci d'humidité ou de fissure. On ne va pas jeter la pierre à celui qui a fait avant, le bâtiment travaille. Mon devoir de Boss de chantier, c'est de vous conseiller la meilleure solution technique pour que vous ayez la paix de l'esprit. Un bon traitement aujourd'hui avec les bons matériaux, ça vous évite de jeter l'argent par la fenêtre demain. On va gérer ça proprement. »`,
        dosages_recommandes: [
          { element: "Ciment local adapté", ratio: "Selon norme", unite_mesure_locale: "Sac" },
          { element: "Sable propre", ratio: "Proportion standard", unite_mesure_locale: "Brouette (60L)" }
        ],
        materiaux_recommandes: [
          { nom: "Matériaux certifiés", substitut_acceptable: "Adaptation selon stock", disponibilite: "Quincaillerie" }
        ]
      }
    };
  }

  // --- RENDU DU RÉSULTAT RAG MOBILE ---
  renderResult(doc) {
    const alt = doc.alternative_prosartisan;
    const cost = doc.cout_estime_local;

    // Génération du Bouclier d'Autorité (Argumentaire Client localisé)
    let clientPitch = alt.bouclier_autorite || alt.bouclier_client || alt.pitch;
    
    if (!clientPitch) {
      const typeOuvrage = (doc.metadata && doc.metadata.type_ouvrage) ? doc.metadata.type_ouvrage.toLowerCase() : "";
      const tagsStr = (doc.metadata && doc.metadata.tags_pathologies) ? doc.metadata.tags_pathologies.join(" ") : "";
      
      if (typeOuvrage === "etancheite" || tagsStr.includes("infiltration") || tagsStr.includes("terrasse")) {
        clientPitch = `« Tonton, quand la dalle du toit coule pendant la saison des pluies, l'eau s'infiltre dans le béton et fait rouiller les fers de la structure. À la longue, le béton éclate et le plafond risque de s'effondrer. Repeindre le salon ne sert à rien si on ne bloque pas l'eau par le haut. Selon les règles de l'art, il faut appliquer une étanchéité liquide SEL multicouche armée en fibre de verre. C'est le seul moyen de protéger définitivement votre investissement et votre famille. »`;
      } else if (typeOuvrage === "poteau-poutre" || tagsStr.includes("fissure") || tagsStr.includes("linteau")) {
        clientPitch = `« Boss, le linteau c'est comme le pilier de la famille. S'il y a une fissure structurelle au-dessus de la porte, c'est que le fer ou le ciment utilisé était trop faible. La norme BNETD exige du fer HA 10 et du ciment CPJ 42.5. Si on met du fer de 8 ou du ciment CPJ 32.5, le mur va se fendre. Faisons un ouvrage propre qui va durer pour la sécurité de votre foyer. »`;
      } else {
        clientPitch = `« Propriétaire, le mur présente des remontées d'humidité qui proviennent directement du sol. Si nous remettons simplement de la peinture, elle va cloquer et tomber d'ici la fin de la saison des pluies. Selon les normes de construction de l'État (Règles LBTP), il est obligatoire de créer une arase étanche pour stopper l'eau à la base. En posant un mortier dosé à 350kg avec un adjuvant hydrofuge SikaCim, nous assurons l'étanchéité complète. Votre bâtiment sera protégé de façon définitive sans avoir à refaire la peinture l'année prochaine. »`;
      }
    }

    this.dom.resultArea.innerHTML = `
      <!-- En-tête de la pathologie -->
      <div class="result-header-panel">
        <div class="result-tag">Pathologie : ${this.selectedPreset ? this.selectedPreset.title : "Humidité"}</div>
        <div class="source-tag font-bold ${doc.metadata && doc.metadata.is_llm_fallback ? 'text-purple-400' : ''}">
          ${doc.metadata && doc.metadata.is_llm_fallback ? `Assistant LLM (${doc.metadata.generated_for || 'Anonyme'})` : (this.networkState === "offline" ? "Source : Cache SQLite" : "Source : Qdrant (PG)")}
        </div>
      </div>

      <!-- BOUCLIER D'AUTORITÉ -->
      <div class="authority-shield-card">
        <div class="shield-badge">
          <span>🛡️</span> Bouclier Client
        </div>
        <div class="pitch-text">
          ${clientPitch}
        </div>
        
        <!-- Widget audio (TTS) -->
        <div class="audio-player-widget mt-3" id="audio-widget">
          <button class="audio-play-btn" id="btn-play-audio">▶</button>
          <div class="audio-wave-sim">
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
          </div>
          <span class="text-[9px] text-cyan-400 font-bold">ÉCOUTER</span>
        </div>

        <div class="copy-action-row">
          <button class="icon-btn" id="btn-copy-pitch">
            <span>📋</span> Copier le texte
          </button>
        </div>
      </div>

      <!-- RECETTE TECHNIQUE -->
      <div class="glass-card neon-purple-border mt-3">
        <div class="card-title">
          <span>🛠️</span> Recette Technique du Boss
        </div>
        <p class="text-xs leading-relaxed text-slate-300 whitespace-pre-line">
          ${alt.methode_execution}
        </p>
      </div>

      <!-- CALCULATEUR DE DOSAGE DE CHANTIER DYNAMIQUE -->
      <div class="calculator-box mt-3">
        <div class="card-title text-xs">
          <span>📊</span> Calculateur de Dosages de Chantier
        </div>
        
        <div class="calc-input-row">
          <span class="calc-label">Surface à traiter (m² ou m linéaire) :</span>
          <div class="calc-input-wrapper">
            <input type="number" id="calc-area-input" value="10" min="1" max="500" class="calc-input" />
            <span class="calc-unit">Unité</span>
          </div>
        </div>

        <!-- Ratios de dosages calculés -->
        <div class="dosage-checklist" id="dosage-checklist">
          <!-- Rempli dynamiquement par recalculateDosages -->
        </div>
        
        <!-- Estimation de Coût total -->
        <div class="mt-3 pt-2 border-t border-white/5 flex justify-between items-center text-xs">
          <span class="text-slate-400">Coût estimé total :</span>
          <span class="font-bold text-yellow-400" id="calc-total-price">-- FCFA</span>
        </div>
      </div>
    `;

    // Lier les écouteurs du résultat
    document.getElementById("btn-copy-pitch").addEventListener("click", () => {
      navigator.clipboard.writeText(clientPitch);
      alert("Argumentaire copié dans le presse-papiers !");
      this.log("system", "Argumentaire copié.");
    });

    // Écouteur de lecture audio (Synthese Vocale)
    document.getElementById("btn-play-audio").addEventListener("click", () => this.toggleAudioPitch(clientPitch));

    // Écouteur du calculateur dynamique
    const areaInput = document.getElementById("calc-area-input");
    areaInput.addEventListener("input", () => this.recalculateDosages(areaInput.value, alt, cost));

    // Premier calcul initial pour 10m²
    this.recalculateDosages(10, alt, cost);
  }

  // --- SYNTHÈSE VOCALE (TextToSpeech) ---
  toggleAudioPitch(text) {
    if (this.isPlayingAudio) {
      window.speechSynthesis.cancel();
      this.setAudioState(false);
    } else {
      this.speechUtterance = new SpeechSynthesisUtterance(text);
      this.speechUtterance.lang = "fr-FR";
      this.speechUtterance.rate = 0.95; // Un peu plus lent et articulé

      this.speechUtterance.onstart = () => {
        this.setAudioState(true);
        this.log("voice", "Lecture audio de l'argumentaire en cours...");
      };

      this.speechUtterance.onend = () => {
        this.setAudioState(false);
        this.log("voice", "Lecture audio terminée.");
      };

      this.speechUtterance.onerror = (e) => {
        this.log("voice", `Erreur audio : ${e.error}`);
        this.setAudioState(false);
      };

      window.speechSynthesis.speak(this.speechUtterance);
    }
  }

  setAudioState(playing) {
    this.isPlayingAudio = playing;
    const widget = document.getElementById("audio-widget");
    const btn = document.getElementById("btn-play-audio");
    if (widget && btn) {
      if (playing) {
        widget.classList.add("playing");
        btn.textContent = "■";
      } else {
        widget.classList.remove("playing");
        btn.textContent = "▶";
      }
    }
  }

  // --- CALCULATEUR DE DOSAGE DE CHANTIER EN DIRECT ---
  recalculateDosages(area, altData, costData) {
    const factor = parseFloat(area) / 10.0; // Le dosage initial est donné pour ~10m²

    const listContainer = document.getElementById("dosage-checklist");
    if (!listContainer) return;

    // Recalculer chaque dosage
    listContainer.innerHTML = altData.dosages_recommandes.map((d, idx) => {
      // Extraire le nombre du ratio
      const numMatch = d.ratio.match(/^([0-9.]+)/);
      let newRatio = d.ratio;

      if (numMatch) {
        const value = parseFloat(numMatch[1]);
        const calculatedValue = (value * factor).toFixed(1);
        newRatio = d.ratio.replace(/^[0-9.]+/, calculatedValue);
      }

      return `
        <div class="checklist-item" id="chk-item-${idx}">
          <div class="checklist-check">✓</div>
          <span class="item-name">${d.element}</span>
          <span class="item-qty">${newRatio}</span>
        </div>
      `;
    }).join("");

    // Rendre la checklist interactive
    altData.dosages_recommandes.forEach((d, idx) => {
      const item = document.getElementById(`chk-item-${idx}`);
      item.addEventListener("click", () => {
        item.classList.toggle("checked");
      });
    });

    // Recalculer le prix en FCFA
    // Extraire les prix minimum et maximum du texte d'estimation
    const priceMatch = costData.estimation_m2_fcfa.match(/([0-9\s]+)-\s*([0-9\s]+)/);
    let calculatedCostText = "Selon devis";

    if (priceMatch) {
      const minPrice = parseInt(priceMatch[1].replace(/\s/g, ""));
      const maxPrice = parseInt(priceMatch[2].replace(/\s/g, ""));

      const calcMin = Math.round(minPrice * factor);
      const calcMax = Math.round(maxPrice * factor);

      calculatedCostText = `${calcMin.toLocaleString()} - ${calcMax.toLocaleString()} FCFA`;
    } else {
      // Si format diffèrent (ex: 8000 - 12000 FCFA par m²)
      const singlePriceMatch = costData.estimation_m2_fcfa.match(/([0-9\s]+)\s*FCFA/);
      if (singlePriceMatch) {
        const val = parseInt(singlePriceMatch[1].replace(/\s/g, ""));
        calculatedCostText = `${Math.round(val * factor).toLocaleString()} FCFA`;
      }
    }

    document.getElementById("calc-total-price").textContent = calculatedCostText;
  }

  // --- CONFIGURATION DE LA LATENCE ET OFFLINE ---
  setNetwork(state) {
    this.networkState = state;

    // Style du badge réseau
    this.dom.badgeNetwork.classList.remove("offline", "latency-3g");
    this.dom.badgeNetwork.textContent = state.toUpperCase();

    if (state === "offline") {
      this.dom.badgeNetwork.classList.add("offline");
      this.dom.badgeNetwork.textContent = "OFFLINE";
      this.log("network", "Réseau déconnecté. Passage en cache local SQLite.");
    } else if (state === "3g") {
      this.dom.badgeNetwork.classList.add("latency-3g");
      this.dom.badgeNetwork.textContent = "3G LENTE";
      this.log("network", "Réseau restreint. Activation de la latence 3G dégradée.");

      // Essayer de synchroniser la queue si on repasse en ligne
      this.syncQueue();
    } else {
      this.log("network", "Fibre optique/WiFi active. Connexion cloud établie.");
      this.syncQueue();
    }
  }

  async syncQueue() {
    if (this.offlineQueue.length === 0) return;

    this.log("network", `Réseau rétabli. Synchronisation de ${this.offlineQueue.length} diagnostics cumulés hors-ligne...`);
    await new Promise(resolve => setTimeout(resolve, 1500));

    this.offlineQueue = [];
    this.log("network", "Synchronisation avec le cloud réussie.");
    this.renderConsoleLogs();
  }

  // --- DESSIN DE LA CARTE DES QUINCAILLERIES ---
  drawMap() {
    const canvas = this.dom.mapCanvas;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    // Ajuster taille logique
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;

    const w = canvas.width;
    const h = canvas.height;

    // Fond sombre bleuâtre
    ctx.fillStyle = "#0c1222";
    ctx.fillRect(0, 0, w, h);

    // Tracer des quadrillages
    ctx.strokeStyle = "rgba(255, 255, 255, 0.03)";
    ctx.lineWidth = 1;
    for (let x = 0; x < w; x += 30) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
    for (let y = 0; y < h; y += 30) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }

    // Tracer des cercles concentriques de radar/recherche
    ctx.strokeStyle = "rgba(6, 182, 212, 0.15)";
    ctx.beginPath();
    ctx.arc(w / 2, h / 2, 40, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(w / 2, h / 2, 90, 0, Math.PI * 2);
    ctx.stroke();

    // Tracer les routes principales fictives de Yopougon / Koumassi
    ctx.strokeStyle = "rgba(255,255,255,0.06)";
    ctx.lineWidth = 6;
    ctx.lineCap = "round";
    // Route 1
    ctx.beginPath();
    ctx.moveTo(20, h / 2 - 20);
    ctx.lineTo(w - 20, h / 2 + 30);
    ctx.stroke();
    // Route 2
    ctx.beginPath();
    ctx.moveTo(w / 3, 15);
    ctx.lineTo(w * 2 / 3, h - 15);
    ctx.stroke();

    // Placer les quincailleries sous forme de pins
    const stores = [
      { name: "Quincaillerie Siporex (Yopougon)", x: w / 2 - 40, y: h / 2 - 30, stock: "En Stock (CIMAF CPJ 42.5)", color: "var(--neon-cyan)" },
      { name: "Quincaillerie de la Gare (Koumassi)", x: w / 2 + 60, y: h / 2 + 20, stock: "En Stock (SikaCim)", color: "var(--neon-purple)" },
      { name: "Dépôt Ciment Zone Ind.", x: w / 2 - 80, y: h / 2 + 30, stock: "CPJ 42.5 & 32.5", color: "var(--neon-emerald)" }
    ];

    stores.forEach(s => {
      // Effet de halo clignotant
      ctx.fillStyle = s.color === "var(--neon-cyan)" ? "rgba(6, 182, 212, 0.2)" : (s.color === "var(--neon-purple)" ? "rgba(168, 85, 247, 0.2)" : "rgba(16, 185, 129, 0.2)");
      ctx.beginPath();
      ctx.arc(s.x, s.y, 10, 0, Math.PI * 2);
      ctx.fill();

      // Pin central
      ctx.fillStyle = s.color === "var(--neon-cyan)" ? "#06b6d4" : (s.color === "var(--neon-purple)" ? "#a855f7" : "#10b981");
      ctx.beginPath();
      ctx.arc(s.x, s.y, 4, 0, Math.PI * 2);
      ctx.fill();

      // Texte du magasin
      ctx.fillStyle = "#f8fafc";
      ctx.font = "bold 8px sans-serif";
      ctx.fillText(s.name, s.x + 8, s.y + 2);
      ctx.fillStyle = "#94a3b8";
      ctx.font = "6px sans-serif";
      ctx.fillText(s.stock, s.x + 8, s.y + 10);
    });

    // Point utilisateur (Maçon)
    ctx.fillStyle = "rgba(239, 68, 68, 0.3)";
    ctx.beginPath();
    ctx.arc(w / 2, h / 2, 12, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#ef4444";
    ctx.beginPath();
    ctx.arc(w / 2, h / 2, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "white";
    ctx.font = "bold 6px sans-serif";
    ctx.fillText("Moi (Chantier)", w / 2 - 18, h / 2 - 15);
  }

  // --- JOURNALISATION SUR LE TERMINAL MOBILE ---
  log(category, message) {
    const time = new Date().toLocaleTimeString();

    const line = document.createElement("div");
    line.className = "console-line";

    let colorClass = "text-slate-400";
    if (category === "voice") colorClass = "text-purple-400";
    if (category === "image") colorClass = "text-cyan-400";
    if (category === "network") colorClass = "text-orange-400";
    if (category === "rag") colorClass = "text-emerald-400";
    if (category === "offline-queue") colorClass = "text-rose-400";

    line.innerHTML = `<span class="time">[${time}]</span> <span class="tag ${colorClass}">[${category.toUpperCase()}]</span> <span>${message}</span>`;

    this.dom.consoleLogs.appendChild(line);
    this.dom.consoleLogs.scrollTop = this.dom.consoleLogs.scrollHeight;
  }

  renderConsoleLogs() {
    // Affiche le nombre d'éléments en attente de synchro
    if (this.offlineQueue.length > 0) {
      this.log("offline-queue", `${this.offlineQueue.length} requêtes en attente de synchronisation réseau.`);
    }
  }

  // --- CHATBOT BTP ---
  initChat() {
    if (this.chatInitialized) return;

    // Message de bienvenue initial
    this.chatHistory = [];
    this.renderChatMessage("bot", "Bonjour Boss ! Je suis votre assistant BTP ProsArtisan. Comment puis-je vous aider aujourd'hui ? Vous pouvez me poser des questions sur les dosages de dalles (ciment CPJ 42.5), les enduits extérieurs (ciment CPJ 32.5), le rôle de l'hydrofuge SikaCim, ou les caractéristiques des sables.");

    // Pilules de suggestions
    const suggestions = [
      { text: "Quel ciment pour les dalles ?", query: "Quel ciment pour couler une dalles de structure ?" },
      { text: "Pourquoi l'enduit craquelle ?", query: "Pourquoi mon enduit fissure et comment crepir ?" },
      { text: "Comment doser le SikaCim ?", query: "Quel est le dosage de l'hydrofuge SikaCim ?" },
      { text: "Sable de lagune ou carrière ?", query: "Quelle est la différence entre sable de lagune et sable de carriere ?" }
    ];

    this.dom.chatSuggestions.innerHTML = suggestions.map(s => `
      <button class="suggestion-pill" data-query="${s.query}">${s.text}</button>
    `).join("");

    // Événements des suggestions
    this.dom.chatSuggestions.querySelectorAll(".suggestion-pill").forEach(btn => {
      btn.addEventListener("click", () => {
        const query = btn.getAttribute("data-query");
        this.dom.chatInput.value = query;
        this.sendChat();
      });
    });

    // Événements d'envoi
    this.dom.btnSendChat.addEventListener("click", () => this.sendChat());
    this.dom.chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") this.sendChat();
    });

    // Événement microphone chat
    this.setupChatMic();

    this.chatInitialized = true;
  }

  setupChatMic() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const chatRec = new SpeechRecognition();
      chatRec.continuous = false;
      chatRec.lang = "fr-FR";
      chatRec.interimResults = false;

      chatRec.onstart = () => {
        this.dom.btnChatMic.classList.add("recording");
        this.log("voice", "Dictée vocale du chatbot démarrée...");
      };

      chatRec.onerror = (e) => {
        console.error("Erreur reco chat:", e);
        this.dom.btnChatMic.classList.remove("recording");
        this.log("voice", "Erreur ou annulation de la dictée vocale.");
      };

      chatRec.onend = () => {
        this.dom.btnChatMic.classList.remove("recording");
      };

      chatRec.onresult = (e) => {
        const transcript = e.results[0][0].transcript;
        this.dom.chatInput.value = transcript;
        this.log("voice", `Transcription chatbot : "${transcript}"`);
        this.sendChat();
      };

      this.dom.btnChatMic.addEventListener("click", () => {
        try {
          chatRec.start();
        } catch (err) {
          chatRec.stop();
        }
      });
    } else {
      this.dom.btnChatMic.addEventListener("click", () => {
        this.log("voice", "Reconnaissance vocale non supportée par ce navigateur.");
        alert("La reconnaissance vocale n'est pas supportée par votre navigateur.");
      });
    }
  }

  async sendChat() {
    const text = this.dom.chatInput.value.trim();
    if (!text) return;

    // Vider l'input
    this.dom.chatInput.value = "";

    // Rendre le message utilisateur
    this.renderChatMessage("user", text);
    this.chatHistory.push({ sender: "user", text: text });

    // Indicateur d'écriture bot
    const typingBubbleId = this.renderChatTyping();

    // Simuler un délai de traitement conversationnel
    let delay = 600;
    if (this.networkState === "3g") {
      delay = 2000;
      this.log("network", "Chatbot : Envoi de la requête sur le réseau 3G...");
    }

    await new Promise(resolve => setTimeout(resolve, delay));

    let botResponse = "";
    let sources = [];

    if (this.networkState === "offline") {
      // Résilience Hors-ligne : Utilisation d'une base de réponses locale simple
      this.log("network", "Chatbot Hors-ligne : Génération de la réponse depuis le dictionnaire local.");

      const localKB = {
        "dalle": "Pour le béton de structure (dalles, poteaux), le dosage standard LBTP/BNETD est de 350 kg/m³ de ciment de classe CPJ 42.5. Pour 1 m³ de béton, cela équivaut à 7 sacs de ciment de 50 kg, 400 L de sable de carrière propre et 800 L de gravier concassé 15/25, avec environ 175 à 180 L d'eau propre.",
        "poteau": "Pour les poteaux de structure, le ciment CPJ 42.5 est requis avec du ferraillage HA. Le dosage recommandé est de 350 kg/m³. Piquez bien le béton dans le coffrage pour éliminer les bulles d'air.",
        "enduit": "Les enduits extérieurs traditionnels s'appliquent en 3 couches successives : 1. Gobetis d'accrochage à 500 kg/m³ de ciment CPJ 32.5. 2. Corps d'enduit de dressage à 350 kg/m³. 3. Finition talochée à 250 kg/m³.",
        "crépir": "Le crépissage extérieur se fait avec un mortier dosé à 350 kg/m³ de ciment CPJ 32.5 et sable fin de lagune. N'oubliez pas de mouiller le mur en parpaings avant de commencer.",
        "arase": "Pour bloquer les remontées capillaires d'eau et le salpêtre, l'arase étanche est obligatoire au-dessus du soubassement. Réalisez un mortier de ciment CPJ 42.5 dosé à 350 kg/m³ enrichi d'un sachet d'hydrofuge de masse SikaCim de 1 kg par sac de ciment.",
        "sikacim": "L'adjuvant hydrofuge de masse SikaCim (sachet de 1 kg) s'ajoute directement à l'eau de gâchage. Utilisez 1 sachet de SikaCim par sac de ciment de 50 kg pour l'étanchéité des arases et soubassements.",
        "ciment": "En Côte d'Ivoire, nous utilisons principalement le CPJ 32.5 pour les maçonneries courantes, enduits et mortiers de pose, et le CPJ 42.5 pour les bétons armés de structure (dalles, poteaux, poutres) et arases étanches.",
        "32.5": "Le ciment CPJ 32.5 convient pour les travaux courants de maçonnerie, enduits et pose de parpaings. Il ne doit pas être utilisé pour couler des dalles porteuses ou des poteaux.",
        "42.5": "Le ciment CPJ 42.5 est un ciment haute résistance obligatoire pour les ouvrages en béton armé et les arases étanches de soubassement."
      };

      const q = text.toLowerCase();
      let matchedKey = null;
      for (const key in localKB) {
        if (q.includes(key)) {
          matchedKey = key;
          break;
        }
      }

      if (matchedKey) {
        botResponse = localKB[matchedKey] + " *(Réponse du cache local en mode hors-ligne)*";
      } else {
        botResponse = "Boss, vous êtes actuellement hors-ligne. Je peux vous renseigner sur les dosages de base (dalle, enduit, arase, ciment 32.5/42.5 ou SikaCim) à partir de ma base locale. Posez-moi une question sur ces sujets !";
      }
    } else {
      // En ligne : Requête à l'API PostgreSQL
      try {
        const res = await fetch((window.API_BASE_URL || "") + "/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, history: this.chatHistory })
        });
        const data = await res.json();
        botResponse = data.response;
        sources = data.sources || [];
      } catch (err) {
        console.error(err);
        botResponse = "Désolé Boss, une erreur est survenue lors de la communication avec le serveur de chat.";
      }
    }

    // Supprimer l'indicateur d'écriture
    this.removeChatTyping(typingBubbleId);

    // Rendre la réponse du bot
    this.renderChatMessage("bot", botResponse, sources);
    this.chatHistory.push({ sender: "bot", text: botResponse });

    this.log("rag", `Chatbot : Réponse fournie pour "${text.substring(0, 30)}..."`);
  }

  renderChatMessage(sender, text, sources = []) {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${sender}`;

    // Remplacement simple de retours à la ligne par <br> et markdown gras simple
    let formattedText = text
      .replace(/\n/g, "<br>")
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.*?)\*/g, "<em>$1</em>");

    bubble.innerHTML = formattedText;

    this.dom.chatMessages.appendChild(bubble);
    this.dom.chatMessages.scrollTop = this.dom.chatMessages.scrollHeight;
  }

  renderChatTyping() {
    const id = "typing-" + Date.now();
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble bot flex items-center space-x-1 py-3";
    bubble.id = id;
    bubble.innerHTML = `
      <div class="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce"></div>
      <div class="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style="animation-delay: 0.2s"></div>
      <div class="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style="animation-delay: 0.4s"></div>
    `;
    this.dom.chatMessages.appendChild(bubble);
    this.dom.chatMessages.scrollTop = this.dom.chatMessages.scrollHeight;
    return id;
  }

  removeChatTyping(id) {
    const bubble = document.getElementById(id);
    if (bubble) bubble.remove();
  }
}

// Lancement à la disponibilité du DOM
document.addEventListener("DOMContentLoaded", () => {
  const app = new ClientAppManager();
  app.init();
});
