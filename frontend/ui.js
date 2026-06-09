/**
 * ui.js
 * Gestion de l'interface utilisateur, rendu dynamique et liaison d'événements.
 */

import { dbInstance, appInstance, MOCK_INSTITUTIONAL_DOCS } from "./app.js";

// Éléments du DOM
let dom = {};

export function initUI() {
  // Récupération globale des éléments du DOM
  dom = {
    // Ingestion Panel
    docSelect: document.getElementById("doc-select"),
    fileImport: document.getElementById("file-import"),
    btnImportFile: document.getElementById("btn-import-file"),
    importProgressContainer: document.getElementById("import-progress-container"),
    importProgressBar: document.getElementById("import-progress-bar"),
    toastNotification: document.getElementById("toast-notification"),
    toastMessage: document.getElementById("toast-message"),
    rawTextPreview: document.getElementById("raw-text-preview"),
    vlmMarkdownPreview: document.getElementById("vlm-markdown-preview"),
    btnVlmExtract: document.getElementById("btn-vlm-extract"),
    btnLlmDownscale: document.getElementById("btn-llm-downscale"),
    pislStepVlm: document.getElementById("pisl-step-vlm"),
    pislStepLlm: document.getElementById("pisl-step-llm"),
    importHistoryList: document.getElementById("import-history-list"),
    btnRefreshImports: document.getElementById("btn-refresh-imports"),

    // Staging / Admin Panel
    stagingList: document.getElementById("staging-list"),
    stagingDetails: document.getElementById("staging-details"),
    productionList: document.getElementById("production-list"),

    // Mobile Simulator
    btnNetworkWifi: document.getElementById("btn-net-wifi"),
    btnNetwork3g: document.getElementById("btn-net-3g"),
    btnNetworkOffline: document.getElementById("btn-net-offline"),
    pathologySelector: document.getElementById("pathology-selector"),
    btnRunDiagnostic: document.getElementById("btn-run-diagnostic"),
    mobileScreenSelect: document.getElementById("mobile-screen-select"),
    mobileScreenResult: document.getElementById("mobile-screen-result"),
    mobileLoader: document.getElementById("mobile-loader"),
    mobileResultContainer: document.getElementById("mobile-result-container"),
    btnBackToSelect: document.getElementById("btn-back-to-select"),
    
    // Filters Mobile
    filterMaxBudget: document.getElementById("filter-budget"),
    filterHardwareOnly: document.getElementById("filter-hardware-only"),

    // Logs Console
    logsConsole: document.getElementById("logs-console"),
    btnClearLogs: document.getElementById("btn-clear-logs")
  };

  // Enregistrer les écouteurs d'événements
  setupEventListeners();

  // Initialisation des données
  populateDocSelect();
  renderStagingList();
  renderProductionList();
  renderMobilePresets();
  renderImportHistory();
  appInstance.addLogListener(addTerminalLog);

  // Premier log système
  appInstance.log("system", "Prototype ProsArtisan IA démarré avec succès. Prêt pour les tests.");
}

function setupEventListeners() {
  dom.btnRefreshImports.addEventListener("click", renderImportHistory);

  // Ingestion PDF
  dom.docSelect.addEventListener("change", async (e) => {
    const doc = MOCK_INSTITUTIONAL_DOCS.find(d => d.id === e.target.value);
    if (doc) {
      dom.rawTextPreview.textContent = doc.raw_text;
      dom.vlmMarkdownPreview.textContent = "";
      dom.btnVlmExtract.disabled = false;
      dom.btnLlmDownscale.disabled = true;
      dom.pislStepVlm.classList.remove("step-done");
      dom.pislStepLlm.classList.remove("step-done");

      // Si c'est un document importé, restaurer l'état visuel depuis l'historique PostgreSQL
      if (doc.id.startsWith("custom-")) {
        try {
          const history = await dbInstance.getImportHistory();
          const record = history.find(item => item.id === doc.id);
          if (record) {
            if (record.vlm_extracted) {
              dom.pislStepVlm.classList.add("step-done");
              dom.btnLlmDownscale.disabled = false;
              dom.vlmMarkdownPreview.textContent = doc.markdown_tables || "";
            }
            if (record.llm_downscaled) {
              dom.pislStepLlm.classList.add("step-done");
              dom.btnLlmDownscale.disabled = true;
            }
          }
        } catch (err) {
          console.error("Erreur lors de la restauration du statut de l'import:", err);
        }
      }
    }
  });

  // Import de fichier personnalisé (.txt, .md)
  dom.btnImportFile.addEventListener("click", () => {
    dom.fileImport.click();
  });

  dom.fileImport.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Désactiver le bouton d'importation et afficher la jauge de progression
    dom.btnImportFile.disabled = true;
    dom.importProgressContainer.classList.remove("hidden");
    dom.importProgressBar.style.width = "0%";

    appInstance.log("system", `Initialisation de l'importation de : "${file.name}"...`);

    let progress = 0;
    const interval = setInterval(() => {
      progress += 10;
      dom.importProgressBar.style.width = `${progress}%`;
      appInstance.log("system", `Chargement du document... ${progress}%`);

      if (progress >= 100) {
        clearInterval(interval);

        // Masquer la jauge après une courte animation
        setTimeout(() => {
          dom.importProgressContainer.classList.add("hidden");
          dom.btnImportFile.disabled = false;
        }, 300);

        // Lire le fichier
        const reader = new FileReader();
        
        reader.onerror = () => {
          dom.btnImportFile.disabled = false;
          dom.importProgressContainer.classList.add("hidden");
          dom.fileImport.value = ""; // Réinitialiser en cas d'erreur
          appInstance.log("system", `Erreur lors de la lecture du fichier : ${file.name}`);
          alert("Impossible de lire ce fichier.");
        };

        reader.onload = (event) => {
          let textContent = event.target.result;

          // Si c'est un PDF, simuler l'extraction textuelle pour éviter d'afficher du code binaire illisible
          if (file.name.toLowerCase().endsWith(".pdf")) {
            textContent = `[PROSARTISAN PDF EXTRACTOR]\nFichier PDF analysé : ${file.name}\nTaille : ${(file.size / 1024).toFixed(1)} Ko\n\n` +
                          `--- CONTENU TECHNIQUE EXTRAIT ---\n` +
                          `SECTION 5.4 : SPÉCIFICATIONS DES ARASES ÉTANCHES ET SOUBASSEMENTS\n` +
                          `Le mortier de ciment pour coupure de capillarité doit être dosé à 350 kg/m³ de ciment CPJ 42.5.\n` +
                          `L'utilisation d'un hydrofuge de masse SikaCim (ou équivalent certifié) est requise à raison de 1 sachet (pot de 1kg) par sac de ciment.\n` +
                          `L'enduit de soubassement étanche doit être appliqué en deux couches croisées d'épaisseur totale minimale de 20 mm.\n` +
                          `Le gâchage mécanique ou gâchage manuel rigoureux sur aire propre doit être assuré pour éviter toute pollution du béton.`;
          }
          
          // Déterminer une structure de table simulée basée sur le contenu du fichier
          let extractedMarkdownTable = `| Composant | Dosage Estimé | Spécification Chantier |
| :--- | :--- | :--- |
| Ciment local | 350 kg/m³ (Standard) | CPJ 32.5 ou CPJ 42.5 |
| Agrégats | Ratio 1:2 | Brouette rase |`;

          // Essayer d'extraire des lignes de dosage existantes pour rendre la démo vivante
          if (
            textContent.toLowerCase().includes("arase") ||
            textContent.toLowerCase().includes("soubassement") ||
            textContent.toLowerCase().includes("sikacim")
          ) {
            extractedMarkdownTable = `| Élément d'Arase | Dosage Spécifié BNETD / LBTP | Rôle Technique |
| :--- | :--- | :--- |
| Mortier d'arase | 350 kg/m³ (CPJ 42.5) | Coupure capillarité soubassement |
| Hydrofuge de masse | SikaCim (1 sachet de 1kg / sac) | Étanchéité à l'eau de remontée |
| Épaisseur arase | 20 mm d'épaisseur minimale | Barrière anti-humidité |`;
          } else if (
            textContent.toLowerCase().includes("ciment") ||
            textContent.toLowerCase().includes("dose") ||
            textContent.toLowerCase().includes("lbtp")
          ) {
            extractedMarkdownTable = `| Élément Extrait | Dosage Spécifié | Contexte Fichier |
| :--- | :--- | :--- |
| Ciment Recommandé | 350 kg/m³ ou plus | Détecté dans le texte importé |
| Granulats fins | Sable propre | Ratio d'enduit ou de mortier |`;
          }

          // Créer un document personnalisé et l'injecter dans la liste globale
          const docId = "custom-" + Date.now();
          const customDoc = {
            id: docId,
            title: `📁 ${file.name}`,
            raw_text: textContent,
            markdown_tables: extractedMarkdownTable
          };

          MOCK_INSTITUTIONAL_DOCS.push(customDoc);

          // Réinitialiser la valeur de l'input après la lecture réussie
          dom.fileImport.value = "";

          // Ajouter l'option dans le sélecteur et l'activer
          const option = document.createElement("option");
          option.value = docId;
          option.text = customDoc.title;
          option.selected = true;
          dom.docSelect.add(option);

          // Mettre à jour l'aperçu
          dom.rawTextPreview.textContent = customDoc.raw_text;
          dom.vlmMarkdownPreview.textContent = "";
          dom.btnVlmExtract.disabled = false;
          dom.btnLlmDownscale.disabled = true;
          dom.pislStepVlm.classList.remove("step-done");
          dom.pislStepLlm.classList.remove("step-done");

          appInstance.log("system", `Importation complétée pour : "${file.name}"`);
          
          // Enregistrer initialement l'importation dans PostgreSQL
          dbInstance.logImport({
            id: docId,
            filename: file.name,
            file_size: file.size,
            imported_at: new Date().toISOString(),
            status: "PENDING_VLM"
          }).then(() => {
            renderImportHistory();
          }).catch(err => {
            console.error("Erreur lors de l'enregistrement de l'import :", err);
          });

          // Afficher la notification toast
          showToast(`Importation réussie : ${file.name}`);
        };
        
        reader.readAsText(file);
      }
    }, 150); // Progression réaliste de 1.5 seconde au total
  });

  dom.btnVlmExtract.addEventListener("click", async () => {
    const docId = dom.docSelect.value;
    dom.btnVlmExtract.disabled = true;
    try {
      const vlmResult = await appInstance.simulateVlmExtraction(docId);
      if (vlmResult) {
        dom.vlmMarkdownPreview.textContent = vlmResult.markdown;
        dom.btnLlmDownscale.disabled = false;
        dom.pislStepVlm.classList.add("step-done");

        if (docId.startsWith("custom-")) {
          appInstance.log("system", `Mise à jour statut VLM (PostgreSQL) pour : ${docId}`);
          await dbInstance.updateImportStatus(docId, {
            vlm_extracted: true,
            status: "PENDING_LLM"
          });
          await renderImportHistory();
        }
      }
    } catch (err) {
      console.error(err);
      appInstance.log("system", `Erreur d'extraction VLM : ${err.message}`);
      dom.btnVlmExtract.disabled = false;
      alert("Une erreur s'est produite lors de l'extraction VLM.");
    }
  });

  dom.btnLlmDownscale.addEventListener("click", async () => {
    const docId = dom.docSelect.value;
    const doc = MOCK_INSTITUTIONAL_DOCS.find(d => d.id === docId);
    dom.btnLlmDownscale.disabled = true;
    try {
      const stagingItem = await appInstance.simulateLLMDownscaling(
        doc.title,
        doc.raw_text,
        doc.markdown_tables
      );

      if (stagingItem) {
        dom.pislStepLlm.classList.add("step-done");

        if (docId.startsWith("custom-")) {
          appInstance.log("system", `Mise à jour statut LLM (PostgreSQL) pour : ${docId}`);
          await dbInstance.updateImportStatus(docId, {
            llm_downscaled: true,
            status: "INGESTED"
          });
          await renderImportHistory();
        }

        await renderStagingList();
        await selectStagingItem(stagingItem.id);
      }
    } catch (err) {
      console.error(err);
      appInstance.log("system", `Erreur de déclassement LLM : ${err.message}`);
      dom.btnLlmDownscale.disabled = false;
      alert("Une erreur s'est produite lors du déclassement LLM.");
    }
  });

  // Sélections de réseau mobile
  dom.btnNetworkWifi.addEventListener("click", () => setNetworkUI("wifi"));
  dom.btnNetwork3g.addEventListener("click", () => setNetworkUI("3g"));
  dom.btnNetworkOffline.addEventListener("click", () => setNetworkUI("offline"));

  // Lancement du diagnostic mobile
  dom.btnRunDiagnostic.addEventListener("click", runDiagnosticWorkflow);
  dom.btnBackToSelect.addEventListener("click", () => {
    dom.mobileScreenResult.classList.add("hidden");
    dom.mobileScreenSelect.classList.remove("hidden");
  });

  // Nettoyage des logs
  dom.btnClearLogs.addEventListener("click", () => {
    dom.logsConsole.innerHTML = '<div class="text-gray-500 italic">Terminal nettoyé. En attente de nouvelles actions...</div>';
  });

  // Déconnexion
  const btnLogout = document.getElementById("btn-logout");
  if (btnLogout) {
    btnLogout.addEventListener("click", () => {
      localStorage.removeItem("auth_token");
      localStorage.removeItem("user_email");
      window.location.href = "/login.html";
    });
  }
}

// --- RENDU INGESTION ---
async function renderImportHistory() {
  if (!dom.importHistoryList) return;
  try {
    const history = await dbInstance.getImportHistory();
    if (!history || history.length === 0) {
      dom.importHistoryList.innerHTML = `
        <tr>
          <td colspan="6" class="p-2 text-center text-gray-500 italic">Aucun document importé pour le moment.</td>
        </tr>
      `;
      return;
    }

    dom.importHistoryList.innerHTML = history.map(item => {
      let sizeStr = "";
      const size = item.file_size;
      if (size < 1024) {
        sizeStr = `${size} B`;
      } else if (size < 1024 * 1024) {
        sizeStr = `${(size / 1024).toFixed(1)} Ko`;
      } else {
        sizeStr = `${(size / (1024 * 1024)).toFixed(1)} Mo`;
      }

      let dateStr = item.imported_at;
      try {
        const date = new Date(item.imported_at);
        if (!isNaN(date.getTime())) {
          dateStr = date.toLocaleString("fr-FR", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit"
          });
        }
      } catch (e) {
        console.error("Date formatting error:", e);
      }

      let statusBadge = "";
      if (item.status === "PENDING_VLM") {
        statusBadge = `<span class="px-2 py-0.5 rounded-full text-[9px] font-medium bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">En attente VLM</span>`;
      } else if (item.status === "PENDING_LLM") {
        statusBadge = `<span class="px-2 py-0.5 rounded-full text-[9px] font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20">En attente LLM</span>`;
      } else if (item.status === "INGESTED") {
        statusBadge = `<span class="px-2 py-0.5 rounded-full text-[9px] font-medium bg-green-500/10 text-green-400 border border-green-500/20">Ingéré</span>`;
      } else {
        statusBadge = `<span class="px-2 py-0.5 rounded-full text-[9px] font-medium bg-gray-500/10 text-gray-400 border border-gray-500/20">${item.status}</span>`;
      }

      const vlmStatus = item.vlm_extracted ? "✅" : "⏳";
      const llmStatus = item.llm_downscaled ? "✅" : "⏳";

      return `
        <tr class="hover:bg-white/5 transition-colors border-b border-white/5">
          <td class="p-2 truncate max-w-[150px]" title="${item.filename}">${item.filename}</td>
          <td class="p-2">${sizeStr}</td>
          <td class="p-2">${dateStr}</td>
          <td class="p-2 text-center">${vlmStatus}</td>
          <td class="p-2 text-center">${llmStatus}</td>
          <td class="p-2">${statusBadge}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Erreur lors du rendu de l'historique des imports:", err);
    dom.importHistoryList.innerHTML = `
      <tr>
        <td colspan="6" class="p-2 text-center text-red-400 italic">Erreur lors de la récupération de l'historique.</td>
      </tr>
    `;
  }
}

function populateDocSelect() {
  dom.docSelect.innerHTML = MOCK_INSTITUTIONAL_DOCS.map(
    doc => `<option value="${doc.id}">${doc.title}</option>`
  ).join("");
  
  // Activer le premier document
  dom.docSelect.dispatchEvent(new Event("change"));
}

// --- RENDU STAGING ---
async function renderStagingList() {
  try {
    const items = await dbInstance.getStagingItems();
    
    if (items.length === 0) {
      dom.stagingList.innerHTML = `<div class="text-gray-400 italic text-center py-4 text-xs">Aucun élément en staging</div>`;
      dom.stagingDetails.innerHTML = `<div class="text-gray-400 italic text-center py-8 text-xs">Sélectionnez une fiche pour l'examiner et la modifier</div>`;
      return;
    }

    dom.stagingList.innerHTML = items.map(item => {
      let badgeColor = "bg-yellow-500/20 text-yellow-400";
      if (item.status === "APPROVED") badgeColor = "bg-green-500/20 text-green-400";
      if (item.status === "REJECTED") badgeColor = "bg-red-500/20 text-red-400";

      return `
        <div class="p-3 bg-white/5 border border-white/10 rounded-lg cursor-pointer hover:bg-white/10 transition flex justify-between items-center mb-2" 
             id="stage-card-${item.id}">
          <div>
            <div class="font-medium text-white text-sm truncate max-w-[200px]">
              ${item.generated_json.alternative_prosartisan.titre_vulgarise}
            </div>
            <div class="text-xs text-gray-400 mt-1">${item.raw_pdf_source}</div>
          </div>
          <span class="text-xs px-2 py-0.5 rounded-full font-semibold ${badgeColor}">
            ${item.status}
          </span>
        </div>
      `;
    }).join("");

    // Ajouter l'écouteur de clic pour chaque carte de staging
    items.forEach(item => {
      const card = document.getElementById(`stage-card-${item.id}`);
      if (card) {
        card.addEventListener("click", async () => await selectStagingItem(item.id));
      }
    });
  } catch (err) {
    console.error(err);
    dom.stagingList.innerHTML = `<div class="text-red-400 italic text-center py-4 text-xs">Erreur de connexion serveur</div>`;
    dom.stagingDetails.innerHTML = `<div class="text-red-400 italic text-center py-8 text-xs font-sans">Impossible de contacter le serveur PostgreSQL. Vérifiez que server.py et PostgreSQL sont démarrés.</div>`;
  }
}

async function selectStagingItem(id) {
  try {
    // Retirer les bordures actives de toutes les cartes
    const items = await dbInstance.getStagingItems();
    items.forEach(item => {
      const card = document.getElementById(`stage-card-${item.id}`);
      if (card) card.classList.remove("border-blue-500");
    });

    const card = document.getElementById(`stage-card-${id}`);
    if (card) card.classList.add("border-blue-500");

    const item = items.find(x => x.id === id);
    if (item) {
      renderStagingDetails(item);
    }
  } catch (err) {
    console.error(err);
  }
}

function renderStagingDetails(item) {
  const json = item.generated_json;
  const isReadOnly = item.status !== "PENDING";

  dom.stagingDetails.innerHTML = `
    <div class="space-y-4">
      <div class="flex justify-between items-start border-b border-white/10 pb-3">
        <div>
          <h4 class="text-white font-semibold">${json.alternative_prosartisan.titre_vulgarise}</h4>
          <p class="text-xs text-gray-400">Origine : ${item.raw_pdf_source} - Réf : ${json.norme_origine.reference_article}</p>
        </div>
        ${
          !isReadOnly 
          ? `<span class="bg-yellow-500/20 text-yellow-400 text-xs px-2 py-1 rounded">Validation Requise</span>`
          : `<span class="${item.status === 'APPROVED' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'} text-xs px-2 py-1 rounded">${item.status}</span>`
        }
      </div>

      <!-- Comparatif Norme vs Alternative -->
      <div class="grid grid-cols-2 gap-4">
        <div class="p-3 bg-red-950/20 border border-red-900/30 rounded-lg">
          <div class="text-xs font-semibold text-red-400 mb-1">Norme Institutionnelle Brute (BNETD/LBTP)</div>
          <div class="text-xs text-gray-300 max-h-[150px] overflow-y-auto leading-relaxed">
            ${json.norme_origine.texte_brut}
          </div>
        </div>
        <div class="p-3 bg-green-950/20 border border-green-900/30 rounded-lg">
          <div class="text-xs font-semibold text-green-400 mb-1">Downscaling (Alternative ProsArtisan)</div>
          <div class="text-xs text-gray-300 leading-relaxed">
            <textarea id="edit-methode" class="w-full bg-transparent border-0 focus:ring-0 p-0 text-xs resize-none" rows="6" ${isReadOnly ? 'readonly' : ''}>${json.alternative_prosartisan.methode_execution}</textarea>
          </div>
        </div>
      </div>

      <!-- Liste des dosages (Modifiables) -->
      <div>
        <div class="text-xs font-semibold text-white mb-2">Dosages Chantier Recommandés (Unités Locales)</div>
        <div class="space-y-2" id="staging-dosages-list">
          ${json.alternative_prosartisan.dosages_recommandes.map((d, idx) => `
            <div class="flex items-center space-x-2 text-xs bg-white/5 p-2 rounded border border-white/5">
              <span class="text-gray-400 w-1/3 truncate">${d.element}</span>
              <input type="text" value="${d.ratio}" class="bg-white/10 text-white border-0 text-xs rounded px-2 py-0.5 w-1/3 focus:ring-1 focus:ring-blue-500" id="edit-ratio-${idx}" ${isReadOnly ? 'readonly' : ''}>
              <select class="bg-white/10 text-white border-0 text-xs rounded px-2 py-0.5 w-1/3 focus:ring-1 focus:ring-blue-500" id="edit-unit-${idx}" ${isReadOnly ? 'disabled' : ''}>
                <option value="Sac" ${d.unite_mesure_locale === "Sac" ? "selected" : ""}>Sac</option>
                <option value="Brouette (60L)" ${d.unite_mesure_locale === "Brouette (60L)" ? "selected" : ""}>Brouette (60L)</option>
                <option value="Seau de maçon (10L)" ${d.unite_mesure_locale === "Seau de maçon (10L)" ? "selected" : ""}>Seau (10L)</option>
                <option value="Pelle" ${d.unite_mesure_locale === "Pelle" ? "selected" : ""}>Pelle</option>
              </select>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- Coût local & justification -->
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="text-xs font-semibold text-white block mb-1">Estimation Prix local (FCFA)</label>
          <input type="text" id="edit-price" value="${json.cout_estime_local.estimation_m2_fcfa}" class="w-full bg-white/5 border border-white/10 text-xs text-white rounded p-2 focus:ring-1 focus:ring-blue-500" ${isReadOnly ? 'readonly' : ''}>
        </div>
        <div>
          <label class="text-xs font-semibold text-white block mb-1">Gamme Budget</label>
          <select id="edit-budget-level" class="w-full bg-white/5 border border-white/10 text-xs text-white rounded p-2 focus:ring-1 focus:ring-blue-500" ${isReadOnly ? 'disabled' : ''}>
            <option value="Faible" ${json.cout_estime_local.gamme_prix === "Faible" ? "selected" : ""}>Faible (Quincaillerie simple)</option>
            <option value="Moyen" ${json.cout_estime_local.gamme_prix === "Moyen" ? "selected" : ""}>Moyen (Structure standard)</option>
            <option value="Eleve" ${json.cout_estime_local.gamme_prix === "Eleve" ? "selected" : ""}>Élevé (Étanchéité technique)</option>
          </select>
        </div>
      </div>

      <!-- Boutons d'action -->
      ${
        !isReadOnly 
        ? `
          <div class="flex justify-end space-x-3 pt-3 border-t border-white/10">
            <button class="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded text-xs font-semibold transition" id="btn-staging-reject">
              Rejeter la fiche
            </button>
            <button class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs font-semibold transition" id="btn-staging-save">
              Enregistrer les modifs
            </button>
            <button class="px-4 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded text-xs font-semibold transition" id="btn-staging-approve">
              Approuver & Indexer (Prod)
            </button>
          </div>
        `
        : ""
      }
    </div>
  `;

  if (!isReadOnly) {
    document.getElementById("btn-staging-reject").addEventListener("click", async () => {
      const reason = prompt("Raison du rejet :");
      if (reason !== null) {
        await appInstance.rejectItem(item.id, reason);
        await renderStagingList();
        await renderProductionList();
        const items = await dbInstance.getStagingItems();
        renderStagingDetails(items.find(x => x.id === item.id));
      }
    });

    document.getElementById("btn-staging-save").addEventListener("click", async () => {
      const updatedJson = getStagingFormValues(item);
      await appInstance.updateItemContent(item.id, updatedJson);
      await renderStagingList();
      alert("Modifications enregistrées en staging avec succès !");
    });

    document.getElementById("btn-staging-approve").addEventListener("click", async () => {
      // D'abord sauvegarder les modifs actuelles
      const updatedJson = getStagingFormValues(item);
      await appInstance.updateItemContent(item.id, updatedJson);
      
      // Ensuite approuver
      await appInstance.approveItem(item.id);
      await renderStagingList();
      await renderProductionList();
      
      // Rafraîchir la vue détails
      const items = await dbInstance.getStagingItems();
      const updatedItem = items.find(x => x.id === item.id);
      renderStagingDetails(updatedItem);
    });
  }
}

function getStagingFormValues(item) {
  const json = JSON.parse(JSON.stringify(item.generated_json)); // Deep copy
  
  json.alternative_prosartisan.methode_execution = document.getElementById("edit-methode").value;
  json.cout_estime_local.estimation_m2_fcfa = document.getElementById("edit-price").value;
  json.cout_estime_local.gamme_prix = document.getElementById("edit-budget-level").value;

  // Récupérer les dosages modifiés
  json.alternative_prosartisan.dosages_recommandes.forEach((d, idx) => {
    d.ratio = document.getElementById(`edit-ratio-${idx}`).value;
    d.unite_mesure_locale = document.getElementById(`edit-unit-${idx}`).value;
  });

  return json;
}

// --- RENDU PRODUCTION (Vector DB Qdrant) ---
async function renderProductionList() {
  try {
    const items = await dbInstance.getProductionItems();
    
    if (items.length === 0) {
      dom.productionList.innerHTML = `<div class="text-gray-400 italic text-center py-4">Aucune fiche en production dans Qdrant</div>`;
      return;
    }

    dom.productionList.innerHTML = items.map(item => {
      const priceColor = item.cout_estime_local.gamme_prix === "Faible" ? "text-green-400" : (item.cout_estime_local.gamme_prix === "Moyen" ? "text-yellow-400" : "text-red-400");
      return `
        <div class="p-3 bg-blue-950/20 border border-blue-900/30 rounded-lg mb-2">
          <div class="flex justify-between items-center">
            <span class="font-medium text-white text-sm">${item.alternative_prosartisan.titre_vulgarise}</span>
            <span class="text-[10px] bg-blue-500/20 text-blue-300 px-1.5 py-0.5 rounded font-mono">Qdrant Index</span>
          </div>
          <div class="text-xs text-gray-400 mt-1 line-clamp-2">${item.alternative_prosartisan.methode_execution}</div>
          <div class="mt-2 flex justify-between items-center text-[10px]">
            <span class="text-gray-400">Budget : <strong class="${priceColor}">${item.cout_estime_local.gamme_prix}</strong></span>
            <span class="text-gray-500">Ouvrage : ${item.metadata.type_ouvrage}</span>
          </div>
        </div>
      `;
    }).join("");
  } catch (err) {
    console.error(err);
    dom.productionList.innerHTML = `<div class="text-red-400 italic text-center py-4 text-xs">Erreur de connexion index Qdrant</div>`;
  }
}

// --- SMARPHONE SIMULATOR ---
let selectedPresetId = null;

function renderMobilePresets() {
  const presets = INITIAL_PATHOLOGY_PRESETS;
  
  dom.pathologySelector.innerHTML = presets.map(p => `
    <div class="p-3 bg-white/5 border border-white/10 rounded-xl cursor-pointer hover:bg-white/10 hover:border-blue-500/50 transition flex space-x-3 items-center" 
         id="preset-card-${p.id}">
      <img src="${p.image}" class="w-12 h-12 rounded-lg object-cover bg-gray-800" alt="${p.title}" />
      <div class="flex-1 min-w-0">
        <div class="font-semibold text-white text-xs truncate">${p.title}</div>
        <div class="text-[10px] text-gray-400 line-clamp-1 mt-0.5">${p.description}</div>
      </div>
    </div>
  `).join("") + `
    <!-- Option d'importation personnalisée dans le simulateur -->
    <div class="p-3 bg-white/5 border border-dashed border-white/20 rounded-xl cursor-pointer hover:bg-white/10 hover:border-blue-500/50 transition flex space-x-3 items-center" 
         id="preset-card-custom-mobile">
      <div class="w-12 h-12 rounded-lg bg-blue-950/40 border border-blue-500/30 flex items-center justify-center text-lg" id="custom-mobile-icon">📷</div>
      <div class="flex-1 min-w-0">
        <div class="font-semibold text-white text-xs truncate" id="custom-mobile-title">Prendre/Importer Photo</div>
        <div class="text-[10px] text-gray-400 line-clamp-1 mt-0.5" id="custom-mobile-desc">Fichier image local</div>
      </div>
      <input type="file" id="mobile-image-upload" class="hidden" accept="image/*">
    </div>
  `;

  const customCard = document.getElementById("preset-card-custom-mobile");
  const mobileUploadInput = document.getElementById("mobile-image-upload");
  const customIcon = document.getElementById("custom-mobile-icon");
  const customTitle = document.getElementById("custom-mobile-title");
  const customDesc = document.getElementById("custom-mobile-desc");

  presets.forEach(p => {
    const card = document.getElementById(`preset-card-${p.id}`);
    card.addEventListener("click", () => {
      presets.forEach(pr => {
        document.getElementById(`preset-card-${pr.id}`).classList.remove("border-blue-500", "bg-blue-500/10");
      });
      customCard.classList.remove("border-blue-500", "bg-blue-500/10");
      card.classList.add("border-blue-500", "bg-blue-500/10");
      selectedPresetId = p.id;
      dom.btnRunDiagnostic.disabled = false;

      // Restaurer l'affichage de la carte custom
      customIcon.innerHTML = "📷";
      customTitle.textContent = "Prendre/Importer Photo";
      customDesc.textContent = "Fichier image local";
    });
  });

  customCard.addEventListener("click", (e) => {
    if (e.target !== mobileUploadInput) {
      mobileUploadInput.click();
    }
  });

  mobileUploadInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;

    mobileUploadInput.value = "";

    const reader = new FileReader();
    reader.onload = (event) => {
      customIcon.innerHTML = `<img src="${event.target.result}" class="w-full h-full object-cover rounded-lg" />`;
      customTitle.textContent = file.name;
      customDesc.textContent = `${(file.size / 1024).toFixed(0)} Ko (3G compressé)`;
      
      presets.forEach(pr => {
        document.getElementById(`preset-card-${pr.id}`).classList.remove("border-blue-500", "bg-blue-500/10");
      });
      customCard.classList.add("border-blue-500", "bg-blue-500/10");
      
      selectedPresetId = "custom-upload";
      dom.btnRunDiagnostic.disabled = false;
      
      appInstance.log("mobile-app", `Photo importée dans le simulateur : ${file.name}`);
    };
    reader.readAsDataURL(file);
  });
}

function setNetworkUI(state) {
  appInstance.setNetworkState(state);
  
  // Style des boutons
  [dom.btnNetworkWifi, dom.btnNetwork3g, dom.btnNetworkOffline].forEach(btn => {
    btn.classList.remove("bg-blue-600", "text-white", "bg-white/10", "text-gray-300");
    btn.classList.add("bg-white/10", "text-gray-300");
  });

  const activeBtn = state === "wifi" ? dom.btnNetworkWifi : (state === "3g" ? dom.btnNetwork3g : dom.btnNetworkOffline);
  activeBtn.classList.remove("bg-white/10", "text-gray-300");
  activeBtn.classList.add("bg-blue-600", "text-white");
}

async function runDiagnosticWorkflow() {
  if (!selectedPresetId) return;

  const preset = selectedPresetId === "custom-upload"
    ? {
        id: "custom-upload",
        title: "Photo importée",
        tags: ["remontee_capillaire", "humidite_bas", "salpetre"]
      }
    : INITIAL_PATHOLOGY_PRESETS.find(p => p.id === selectedPresetId);
  
  // Masquer formulaire, afficher loader
  dom.mobileScreenSelect.classList.add("hidden");
  dom.mobileScreenResult.classList.remove("hidden");
  dom.mobileLoader.classList.remove("hidden");
  dom.mobileResultContainer.classList.add("hidden");

  // Récupérer les filtres
  const filters = {
    maxBudget: dom.filterMaxBudget.value,
    onlyHardwareStore: dom.filterHardwareOnly.checked
  };

  try {
    // Lancer le workflow
    const result = await appInstance.processUserPhotoAndRAG(preset, filters);
    
    // Cache loader
    dom.mobileLoader.classList.add("hidden");
    dom.mobileResultContainer.classList.remove("hidden");

    if (result.status === "success") {
      const d = result.data;
      const isOffline = result.source === "local_cache";
      
      dom.mobileResultContainer.innerHTML = `
        <div class="space-y-4">
          <!-- Diagnostic Header -->
          <div class="flex justify-between items-center bg-white/5 p-2 rounded-lg border border-white/5">
            <div>
              <div class="text-[10px] text-gray-400">Diagnostic :</div>
              <div class="font-bold text-white text-xs">${d.pathologie_detectee}</div>
            </div>
            <span class="text-[9px] px-2 py-0.5 rounded font-bold ${isOffline ? 'bg-orange-500/20 text-orange-400' : 'bg-green-500/20 text-green-400'}">
              ${isOffline ? 'CACHE LOCAL' : 'MODÈLE CLOUD'}
            </span>
          </div>

          <!-- Le Bouclier d'Autorité -->
          <div class="p-3 bg-gradient-to-r from-blue-900/40 to-indigo-900/40 border border-blue-500/30 rounded-xl relative overflow-hidden">
            <div class="absolute top-1 right-2 text-[9px] text-blue-400 font-bold tracking-wider">🛡️ BOUCLIER CLIENT</div>
            <div class="text-[10px] font-semibold text-blue-300 mb-1">Argumentaire de confiance :</div>
            <div class="text-[11px] text-white leading-relaxed italic">
              ${d.argumentaire_client}
            </div>
            <div class="mt-2 text-[9px] text-blue-400 flex items-center">
              <span class="mr-1">👉</span> Lisez ce texte au propriétaire pour expliquer les travaux
            </div>
          </div>

          <!-- Recette Technique -->
          <div class="p-3 bg-white/5 border border-white/10 rounded-xl">
            <div class="text-[10px] font-semibold text-white mb-2">🛠️ La Recette Technique du Boss</div>
            <div class="text-[11px] text-gray-300 leading-relaxed whitespace-pre-line">
              ${d.instructions_techniques}
            </div>
          </div>

          <!-- Matériaux & Dosages -->
          <div class="p-3 bg-white/5 border border-white/10 rounded-xl">
            <div class="text-[10px] font-semibold text-white mb-2">📦 Matériaux & Dosages Recommandés</div>
            <div class="space-y-2 mb-3">
              ${d.dosages.map(dos => `
                <div class="flex justify-between items-center text-[10px] border-b border-white/5 pb-1">
                  <span class="text-gray-400">${dos.element}</span>
                  <span class="font-bold text-white">${dos.ratio}</span>
                </div>
              `).join("")}
            </div>
            
            <div class="text-[10px] font-semibold text-white mb-1.5">Disponibilité à l'achat :</div>
            <div class="flex flex-wrap gap-1.5">
              ${d.materiaux.map(mat => {
                const badge = mat.disponibilite === "Quincaillerie" 
                  ? "bg-green-500/20 text-green-300 border-green-500/20" 
                  : "bg-purple-500/20 text-purple-300 border-purple-500/20";
                return `
                  <span class="text-[9px] px-1.5 py-0.5 rounded border ${badge}">
                    ${mat.nom} (${mat.disponibilite})
                  </span>
                `;
              }).join("")}
            </div>
          </div>

          <!-- Détail Coût & Justification -->
          <div class="p-3 bg-white/5 border border-white/10 rounded-xl flex justify-between items-center text-[10px]">
            <div>
              <div class="text-gray-400">Estimation locale :</div>
              <div class="font-bold text-white text-xs">${d.estimation_fcfa}</div>
            </div>
            <div class="text-right">
              <div class="text-gray-400">Niveau de prix :</div>
              <span class="font-bold text-yellow-400">${d.budget_categorie}</span>
            </div>
          </div>
        </div>
      `;
    } else {
      // Cas sans résultats ou échec
      dom.mobileResultContainer.innerHTML = `
        <div class="p-4 bg-red-950/20 border border-red-900/30 rounded-xl text-center">
          <div class="text-xl mb-1">🔍</div>
          <div class="text-xs font-semibold text-white">Pas de solution en cache</div>
          <div class="text-[10px] text-gray-400 mt-2 leading-relaxed">
            ${result.message}
          </div>
        </div>
      `;
    }
  } catch (err) {
    console.error(err);
    appInstance.log("system", `Erreur réseau ou technique lors du diagnostic : ${err.message}`);
    
    // Cacher le loader et afficher l'erreur
    dom.mobileLoader.classList.add("hidden");
    dom.mobileResultContainer.classList.remove("hidden");
    dom.mobileResultContainer.innerHTML = `
      <div class="p-4 bg-red-950/20 border border-red-900/30 rounded-xl text-center">
        <div class="text-md mb-1">⚠️</div>
        <div class="text-xs font-semibold text-white">Erreur de connexion</div>
        <div class="text-[10px] text-gray-400 mt-2 leading-relaxed">
          Le serveur API ProsArtisan est actuellement injoignable. Veuillez vérifier que server.py et votre base PostgreSQL sont actifs.
        </div>
      </div>
    `;
  }
}

/**
 * Affiche une notification toast temporaire
 */
function showToast(message) {
  dom.toastMessage.textContent = message;
  dom.toastNotification.classList.remove("translate-x-full");
  dom.toastNotification.classList.add("translate-x-0");

  // Masquer après 3.5 secondes
  setTimeout(() => {
    dom.toastNotification.classList.remove("translate-x-0");
    dom.toastNotification.classList.add("translate-x-full");
  }, 3500);
}

// --- TERMINAL LOGS ---
function addTerminalLog(logItem) {
  const categoryColors = {
    system: "text-blue-400 font-semibold",
    vlm: "text-purple-400",
    "llm-downscale": "text-yellow-400",
    "staging-db": "text-pink-400",
    "vector-db": "text-cyan-400 font-mono",
    "mobile-app": "text-emerald-400",
    network: "text-orange-400",
    "api-gateway": "text-indigo-400",
    "vision-model": "text-teal-400",
    "llm-rag": "text-blue-300"
  };

  const color = categoryColors[logItem.category] || "text-gray-300";
  const detailsHtml = logItem.details 
    ? `<button class="text-[10px] text-gray-500 underline ml-2 cursor-pointer focus:outline-none" onclick="this.nextElementSibling.classList.toggle('hidden')">voir détails</button>
       <pre class="hidden bg-black/40 p-2 rounded text-[10px] mt-1 border border-white/5 text-gray-400 overflow-x-auto font-mono max-h-[200px] whitespace-pre-wrap">${logItem.details}</pre>`
    : "";

  const logLine = document.createElement("div");
  logLine.className = "py-1 border-b border-white/5 last:border-0";
  logLine.innerHTML = `
    <span class="text-gray-600 font-mono text-[10px]">${logItem.timestamp}</span>
    <span class="${color} text-[11px] font-semibold uppercase tracking-wider mx-1">[${logItem.category}]</span>
    <span class="text-gray-300 text-[11px]">${logItem.message}</span>
    ${detailsHtml}
  `;

  dom.logsConsole.appendChild(logLine);
  
  // Scroll automatique vers le bas
  dom.logsConsole.scrollTop = dom.logsConsole.scrollHeight;
}
