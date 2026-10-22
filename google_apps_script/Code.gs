// Saillance, tableau de présence TouchDesigner
// Reçoit les signaux de la composante presence (doPost) et affiche qui travaille sur quoi (doGet).

const FEUILLE = 'presence';
const DELAI_ACTIF_MS = 2 * 60 * 1000;   // un patch sans signal depuis 2 minutes disparaît de la page
const DELAI_NETTOYAGE_MS = 60 * 60 * 1000; // les lignes sans signal depuis 1 heure sont supprimées
const ENTETES = ['session', 'nom', 'partie', 'tache', 'patch', 'version', 'version_commune', 'debut', 'dernier_signal', 'heure_envoi'];
const DEPOT_GITHUB = 'UQAM-CeXii/saillance-touchdesigner';   // la dernière release donne la version officielle
// Réservations d'univers DMX : une rangée par réservation (une IP, des univers qui se suivent, un seul dmx à la fois) ;
// les univers sont bloqués par IP : les mêmes univers peuvent servir sur une autre IP
const FEUILLE_RESERVATIONS = 'reservations';
const COLONNES_RESERVATIONS = ['nom', 'ip', 'debut', 'fin', 'note'];
const DELAI_ENVOI_S = 8;   // une réservation sans nouvelles de son patch depuis 8 s est libérée

function feuille_() {
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  let feuille = classeur.getSheetByName(FEUILLE);
  if (!feuille) {
    feuille = classeur.insertSheet(FEUILLE);
  }
  // Feuille d'une ancienne version (colonnes différentes) : on la remet à neuf, les sessions se réinscrivent au prochain signal
  const entetes = feuille.getRange(1, 1, 1, ENTETES.length).getValues()[0];
  if (entetes.join() !== ENTETES.join()) {
    feuille.clear();
    feuille.appendRow(ENTETES);
    feuille.setFrozenRows(1);
  }
  return feuille;
}

// Version officielle : tag de la dernière release GitHub, gardé 10 minutes en cache
function versionOfficielle_() {
  const cache = CacheService.getScriptCache();
  const gardee = cache.get('version_officielle');
  if (gardee !== null) return gardee;
  let version = '';
  try {
    const r = UrlFetchApp.fetch('https://api.github.com/repos/' + DEPOT_GITHUB + '/releases/latest',
      { muteHttpExceptions: true, headers: { 'User-Agent': 'saillance', 'Accept': 'application/vnd.github+json' } });
    if (r.getResponseCode() === 200) version = String(JSON.parse(r.getContentText()).tag_name || '');
  } catch (err) {
    return '';
  }
  cache.put('version_officielle', version, 600);
  return version;
}

// Signal envoyé par TouchDesigner : type = ouverture, signal ou fermeture
function doPost(e) {
  const d = JSON.parse(e.postData.contents);
  if (d.type === 'dmx') return recevoirDmx_(d);
  if (!d.session || !d.type) return ContentService.createTextOutput('message incomplet');
  ['nom', 'partie', 'tache', 'patch', 'version', 'version_commune', 'heure'].forEach(k => { if (d[k] === undefined) d[k] = ''; });

  const verrou = LockService.getScriptLock();
  verrou.waitLock(10000);
  try {
    const feuille = feuille_();
    const valeurs = feuille.getDataRange().getValues();
    const maintenant = new Date();
    let ligne = -1;
    for (let i = 1; i < valeurs.length; i++) {
      if (valeurs[i][0] === d.session) { ligne = i + 1; break; }
    }

    if (d.type === 'fermeture') {
      if (ligne > 0) feuille.deleteRow(ligne);
    } else if (ligne > 0) {
      const debut = valeurs[ligne - 1][7];
      feuille.getRange(ligne, 2, 1, 9).setValues([[d.nom, d.partie, d.tache, d.patch, d.version, d.version_commune, debut, maintenant, d.heure]]);
    } else {
      feuille.appendRow([d.session, d.nom, d.partie, d.tache, d.patch, d.version, d.version_commune, maintenant, maintenant, d.heure]);
    }

    nettoyer_(feuille, maintenant);
  } finally {
    verrou.releaseLock();
  }
  return ContentService.createTextOutput(JSON.stringify({ version_officielle: versionOfficielle_() }))
    .setMimeType(ContentService.MimeType.JSON);
}

// Réservations prises par les dmx : chaque patch envoie chaque seconde les réservations de ses dmx activés ;
// une réservation déjà prise par un autre patch est refusée. Gardé 8 s en mémoire : un patch planté libère ses réservations
// après 8 s, un patch fermé tout de suite (liste liberer). La réponse donne aussi la version de la liste : Touch la relit quand elle change.
function recevoirDmx_(d) {
  const cache = CacheService.getScriptCache();
  const verrou = LockService.getScriptLock();
  verrou.waitLock(10000);
  try {
    const demandees = Object.keys(d.prises || {});
    const liberer = d.liberer || [];
    const actuels = cache.getAll(demandees.concat(liberer).map(nom => 'dmxr_' + nom));
    const ecrire = {};
    demandees.forEach(nom => {
      const a = actuels['dmxr_' + nom] && JSON.parse(actuels['dmxr_' + nom]);
      if (a && a.username !== d.username) return;   // déjà prise par un autre patch
      ecrire['dmxr_' + nom] = JSON.stringify({ username: d.username, nom: d.nom, poste: d.poste, src: d.prises[nom].src, t: Date.now() });
    });
    if (Object.keys(ecrire).length) cache.putAll(ecrire, DELAI_ENVOI_S);
    // retire seulement ce que ce patch avait pris
    const retirer = liberer.map(nom => 'dmxr_' + nom).filter(k => actuels[k] && JSON.parse(actuels[k]).username === d.username);
    if (retirer.length) cache.removeAll(retirer);
  } finally {
    verrou.releaseLock();
  }
  return ContentService.createTextOutput(JSON.stringify({ prises: envoisReservations(d.toutes || []), version: versionReservations_() }))
    .setMimeType(ContentService.MimeType.JSON);
}

// Qui a pris chaque réservation (patch ouvert dans les 8 dernières secondes), pour Touch et la page des réservations
function envoisReservations(noms) {
  const brut = CacheService.getScriptCache().getAll((noms || []).map(nom => 'dmxr_' + nom));
  const envois = {};
  Object.keys(brut).forEach(k => { envois[k.slice(5)] = JSON.parse(brut[k]); });
  return envois;
}

// Supprime les sessions abandonnées (plantage, perte de réseau)
function nettoyer_(feuille, maintenant) {
  const valeurs = feuille.getDataRange().getValues();
  for (let i = valeurs.length - 1; i >= 1; i--) {
    const t = new Date(valeurs[i][8]).getTime();
    if (isNaN(t) || maintenant - t > DELAI_NETTOYAGE_MS) feuille.deleteRow(i + 1);
  }
}

// Page web (onglet Site Web dans Teams), JSON avec ?format=json,
// les réservations DMX avec ?format=reservations, ou la page des réservations DMX avec ?page=lumieres
function doGet(e) {
  if (e && e.parameter && e.parameter.page === 'lumieres') {
    return HtmlService.createHtmlOutputFromFile('lumieres')
      .setTitle('Saillance, réservations DMX')
      .addMetaTag('viewport', 'width=device-width, initial-scale=1')
      .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  }
  if (e && e.parameter && e.parameter.format === 'reservations') {
    return ContentService.createTextOutput(JSON.stringify(listeReservations()))
      .setMimeType(ContentService.MimeType.JSON);
  }
  if (e && e.parameter && e.parameter.format === 'json') {
    return ContentService.createTextOutput(JSON.stringify(listeActive()))
      .setMimeType(ContentService.MimeType.JSON);
  }
  return HtmlService.createHtmlOutputFromFile('page')
    .setTitle('Saillance, qui travaille sur quoi')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL); // permet l'affichage dans Teams
}

function feuilleReservations_() {
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  let feuille = classeur.getSheetByName(FEUILLE_RESERVATIONS);
  if (!feuille) {
    feuille = classeur.insertSheet(FEUILLE_RESERVATIONS);
    feuille.appendRow(COLONNES_RESERVATIONS);
    feuille.setFrozenRows(1);
  }
  return feuille;
}

// Change à chaque ajout, modification ou retrait : Touch relit la liste quand elle change
function versionReservations_() {
  return PropertiesService.getScriptProperties().getProperty('version_reservations') || '0';
}

function changerVersion_() {
  PropertiesService.getScriptProperties().setProperty('version_reservations', String(Date.now()));
}

// Rangées de l'onglet reservations, par nom de colonne
function reservations_() {
  const valeurs = feuilleReservations_().getDataRange().getValues();
  const entetes = valeurs[0].map(v => String(v).trim().toLowerCase());
  const lignes = [];
  for (let i = 1; i < valeurs.length; i++) {
    const ligne = {};
    let vide = true;
    entetes.forEach((nom, j) => {
      if (!nom) return;
      ligne[nom] = String(valeurs[i][j]).trim();
      if (ligne[nom]) vide = false;
    });
    if (!vide) lignes.push(ligne);
  }
  return lignes;
}

// ---- page des réservations DMX (?page=lumieres), appelée avec google.script.run, et Touch (?format=reservations)

function listeReservations() {
  return { lignes: reservations_(), version: versionReservations_() };
}

// Vérifie une réservation ; ancien = son nom avant modification (vide pour un ajout). Renvoie { erreur } ou { r }
function verifierReservation_(d, ancien, lignes) {
  const entier = v => (String(v).trim() === '' ? NaN : Number(v));
  const r = { nom: String(d.nom || '').trim(), ip: String(d.ip || '').trim(), debut: entier(d.debut), fin: entier(d.fin), note: String(d.note || '').trim() };
  if (!/^[A-Za-z0-9_]{1,24}$/.test(r.nom)) return { erreur: 'Nom : lettres, chiffres et _ seulement, 24 caractères maximum.' };
  if (!/^(\d{1,3}\.){3}\d{1,3}$/.test(r.ip) || r.ip.split('.').some(x => Number(x) > 255)) return { erreur: 'IP : quatre nombres de 0 à 255 séparés par des points, ex. 10.0.21.60.' };
  if (!Number.isInteger(r.debut) || !Number.isInteger(r.fin) || r.debut < 0 || r.fin > 32767 || r.debut > r.fin) {
    return { erreur: 'Univers : des nombres entiers de 0 à 32767, le premier plus petit ou égal au dernier.' };
  }
  for (const l of lignes) {
    if (l.nom === ancien) continue;
    if (l.nom === r.nom) return { erreur: 'Le nom ' + r.nom + ' existe déjà.' };
    if (String(l.ip).trim() === r.ip && r.debut <= Number(l.fin) && r.fin >= Number(l.debut)) {
      return { erreur: 'Chevauche ' + l.nom + ' sur ' + r.ip + ' (univers ' + l.debut + (l.debut === l.fin ? '' : ' à ' + l.fin) + ').' };
    }
  }
  return { r: r };
}

function ecrireReservation_(ancien, d) {
  const verrou = LockService.getScriptLock();
  verrou.waitLock(10000);
  try {
    const feuille = feuilleReservations_();
    const v = verifierReservation_(d, ancien, reservations_());
    if (v.erreur) return v;
    const valeurs = feuille.getDataRange().getValues();
    const entetes = valeurs[0].map(x => String(x).trim().toLowerCase());
    const rangee = entetes.map(e => (v.r[e] === undefined ? '' : v.r[e]));
    const colonne = entetes.indexOf('nom');
    let i = -1;
    if (ancien) {
      for (let j = 1; j < valeurs.length; j++) if (String(valeurs[j][colonne]).trim() === ancien) i = j + 1;
      if (i < 0) return { erreur: 'La réservation ' + ancien + ' n\'existe plus.' };
      feuille.getRange(i, 1, 1, rangee.length).setValues([rangee]);
    } else {
      feuille.appendRow(rangee);
    }
    changerVersion_();
  } finally {
    verrou.releaseLock();
  }
  return listeReservations();
}

// Ajoute une réservation ; renvoie { erreur } ou { lignes, version }
function ajouterReservation(d) {
  return ecrireReservation_('', d);
}

// Modifie la réservation nommée ancien (nom compris) ; renvoie { erreur } ou { lignes, version }
function modifierReservation(ancien, d) {
  return ecrireReservation_(String(ancien || '').trim(), d);
}

// Retire une réservation par son nom ; renvoie { lignes, version }
function retirerReservation(nom) {
  const verrou = LockService.getScriptLock();
  verrou.waitLock(10000);
  try {
    const feuille = feuilleReservations_();
    const valeurs = feuille.getDataRange().getValues();
    const colonne = valeurs[0].map(v => String(v).trim().toLowerCase()).indexOf('nom');
    for (let i = valeurs.length - 1; i >= 1; i--) {
      if (String(valeurs[i][colonne]).trim() === nom) feuille.deleteRow(i + 1);
    }
    changerVersion_();
  } finally {
    verrou.releaseLock();
  }
  return listeReservations();
}

// Sessions actives et version officielle, appelée par la page toutes les 20 secondes
function listeActive() {
  const officielle = versionOfficielle_();
  const valeurs = feuille_().getDataRange().getValues();
  const maintenant = Date.now();
  const actives = [];
  for (let i = 1; i < valeurs.length; i++) {
    const [session, nom, partie, tache, patch, version, versionCommune, debut, dernier] = valeurs[i];
    const tDebut = new Date(debut).getTime(), tDernier = new Date(dernier).getTime();
    if (isNaN(tDebut) || isNaN(tDernier)) continue;   // ligne illisible : ignorée plutôt que de bloquer la page
    if (maintenant - tDernier > DELAI_ACTIF_MS) continue;
    actives.push({
      nom: String(nom), partie: String(partie), tache: String(tache), patch: String(patch), version: String(version),
      versionCommune: String(versionCommune), aJour: String(versionCommune) === officielle,
      debut: new Date(tDebut).toISOString(), dernier: new Date(tDernier).toISOString()
    });
  }
  actives.sort((a, b) => a.debut.localeCompare(b.debut));
  return { officielle: officielle, sessions: actives };
}
