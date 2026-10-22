# send_fonctions
# Envoie les canaux du CHOP branché (ou le texte du DAT branché) sur un topic MQTT.
# Composante commune : ne rien modifier sans l'annoncer.

import json, re, time

MAX_TEXTE = 12
MAX_LABEL = 6
MAX_CANAUX = 16
MAX_LIGNES = 64        # format table : lignes de données, sans l'en-tête
MAX_COLONNES = 16
MAX_OCTETS = 8192      # format table : taille maximale du message
ETAPES = ('Module', 'Composante', 'Propriete')
REGLAGES = ('Format', 'Mode', 'Zone', 'Module', 'Composante', 'Propriete')


def afficher(comp, nom, texte):
	p = getattr(comp.par, nom)
	if p.eval() != texte:
		p.val = texte


def probleme_de(nom, texte, maximum, tiret=False):
	if not texte:
		return nom + ' : à remplir'
	if tiret and not re.fullmatch(r'[A-Za-z0-9_-]+', texte):
		return nom + ' : lettres, chiffres, _ et - seulement, sans espace, accent ni autre caractère spécial'
	if not tiret and not re.fullmatch(r'[A-Za-z0-9_]+', texte):
		return nom + ' : lettres, chiffres et _ seulement, sans espace, accent ni autre caractère spécial'
	if len(texte) > maximum:
		return nom + ' : ' + str(maximum) + ' caractères maximum'
	return ''


def construire_topic(comp):
	# saillance/zone/module/composante/propriete, en minuscules ; retourne (topic, erreur)
	morceaux = ['saillance', comp.par.Zone.eval()]
	for par in (comp.par.Module, comp.par.Composante, comp.par.Propriete):
		texte = par.eval().strip()
		erreur = probleme_de(par.label, texte, MAX_TEXTE, True)
		if erreur:
			return '', erreur
		morceaux.append(texte.lower())
	return '/'.join(morceaux), ''


def menus(comp, m):
	# Module, Composante et Propriété proposent les noms déjà présents sur le serveur (on peut en écrire un nouveau)
	choix = [comp.par.Zone.eval()] + [getattr(comp.par, e).eval().strip().lower() for e in ETAPES]
	signature = (m.ETAT['changements'], tuple(choix))
	if comp.fetch('menus', None) == signature:
		return
	comp.store('menus', signature)
	morceaux = [t.split('/')[1:] for t in m.CATALOGUE]
	for i, etape in enumerate(ETAPES, start=1):
		options = sorted({x[i] for x in morceaux if x[:i] == choix[:i]})
		par = getattr(comp.par, etape)
		if list(par.menuNames) != options:
			par.menuNames = options
			par.menuLabels = options


def lire_texte(comp):
	# DAT branché : un texte seul, ou une table nom | texte (une ligne par valeur)
	d = comp.op('in_texte')
	if d.isTable and d.numCols >= 2:
		valeurs, labels = [], []
		for r in range(d.numRows):
			nom = d[r, 0].val.strip()
			erreur = probleme_de('Ligne « ' + nom + ' »', nom, MAX_LABEL)
			if erreur:
				return None, None, erreur + ' (1re colonne du DAT branché)'
			valeurs.append(d[r, 1].val)
			labels.append(nom)
		if not valeurs:
			return None, None, 'Le DAT branché est vide'
		if len(valeurs) > MAX_CANAUX:
			return None, None, 'Le DAT branché a ' + str(len(valeurs)) + ' lignes, ' + str(MAX_CANAUX) + ' maximum'
		return valeurs, labels, ''
	texte = d.text.strip()
	if not texte:
		return None, None, 'Texte vide : rien n\'est envoyé (la donnée sur le serveur est gardée)'
	return texte, None, ''


def lire_table(comp):
	# DAT branché : val = liste des rangées (cases en texte), toutes les rangées sont des données, pas de noms de colonnes
	d = comp.op('in_table')
	if not d.isTable or d.numRows == 0:
		return None, None, 'Branche une table (Table DAT)'
	if d.numCols > MAX_COLONNES:
		return None, None, 'La table a ' + str(d.numCols) + ' colonnes, ' + str(MAX_COLONNES) + ' maximum'
	if d.numRows > MAX_LIGNES:
		return None, None, 'La table a ' + str(d.numRows) + ' rangées, ' + str(MAX_LIGNES) + ' maximum'
	lignes = [[d[r, c].val for c in range(d.numCols)] for r in range(d.numRows)]
	taille = len(json.dumps({'val': lignes}))
	if taille > MAX_OCTETS:
		return None, None, 'La table est trop grosse (' + str(taille) + ' octets, ' + str(MAX_OCTETS) + ' maximum)'
	return lignes, [], ''


def lire_valeurs(comp):
	# retourne (valeur, labels, erreur)
	if comp.par.Format.eval() == 'string':
		return lire_texte(comp)
	if comp.par.Format.eval() == 'table':
		return lire_table(comp)
	chop = comp.op('in_valeurs')
	if chop.numChans == 0:
		return None, None, 'Aucun canal : branche un CHOP'
	if chop.numChans > MAX_CANAUX:
		return None, None, 'Le CHOP branché a ' + str(chop.numChans) + ' canaux, ' + str(MAX_CANAUX) + ' maximum'
	valeurs, labels, hors = [], [], []
	for c in chop.chans():
		erreur = probleme_de('Canal « ' + c.name + ' »', c.name, MAX_LABEL)
		if erreur:
			return None, None, erreur + ' (renommer avec un Rename CHOP)'
		v = float(c.eval())
		if not 0 <= v <= 1:
			# hors de 0 à 1 : envoyée quand même, mais ramenée à la borne la plus proche
			hors.append('« ' + c.name + ' » = ' + str(round(v, 4)) + ' envoyé ' + ('0' if v < 0 else '1'))
			v = min(max(v, 0.0), 1.0)
		valeurs.append(round(v, 6))
		labels.append(c.name)
	comp.store('avertissement', 'hors de 0 à 1 : ' + ', '.join(hors) if hors else '')
	alerter_hors(comp, hors)
	return valeurs, labels, ''


def alerter_hors(comp, hors):
	# fenêtre une fois quand une valeur sort de 0 à 1 (pas de nouvelle fenêtre tant qu'elle reste dehors, au plus une aux 30 s)
	if not hors:
		comp.store('alerte_hors', False)
		return
	if comp.fetch('alerte_hors', False) or time.time() - comp.fetch('alerte_heure', 0) < 30:
		return
	comp.store('alerte_hors', True)
	comp.store('alerte_heure', time.time())
	texte = (comp.path + ' : une valeur est hors de 0 à 1.\n' + ', '.join(hors) +
		'.\nElle est envoyée ramenée à 0 ou 1. Mets tes valeurs entre 0 et 1 (ex. Math CHOP, Range).')
	print('[send]', texte.replace('\n', ' '))
	try:
		op.TDResources.PopDialog.OpenDefault(text=texte, title='Saillance : valeur hors de 0 à 1', buttons=['OK'])
	except Exception:
		pass


def entrees(comp, fmt):
	# seule l'entrée du format choisi existe : in_valeurs (CHOP) pour float, in_texte (DAT) pour string, in_table (DAT) pour table
	for nom, type_op, y, voulu in (('in_valeurs', inCHOP, 0, fmt == 'float'), ('in_texte', inDAT, -150, fmt == 'string'),
			('in_table', inDAT, -300, fmt == 'table')):
		o = comp.op(nom)
		if voulu and o is None:
			o = comp.create(type_op, nom)
			o.nodeX, o.nodeY = 0, y
			o.color = (0.2, 0.4, 0.75)
		elif not voulu and o is not None:
			o.destroy()


def Verrouiller(comp, actif):
	# activé : réglages bloqués (on ne change pas un topic pendant qu'il envoie) ; Actif et Créer le topic restent libres
	for nom in REGLAGES:
		getattr(comp.par, nom).readOnly = actif


def Synchroniser(comp):
	# ouverture du patch ou send ajouté : même mode que saillance_master, et le topic réglé est créé
	commun = getattr(op, 'commun', None)
	if commun is not None:
		commun.op('mqtt/mqtt_fonctions').module.ENVOYEURS.add(comp.path)
	actif = commun.par.Actif.eval() if commun is not None else comp.par.Actif.eval()
	if comp.par.Actif.eval() != actif:
		comp.par.Actif = actif
	Verrouiller(comp, actif)
	Creer(comp, vide=False)   # à l'ouverture : seulement une vraie valeur, jamais un message vide
	Actualiser(comp)


def nouveau(comp, m, topic):
	# topic absent du serveur et jamais créé par ce send : rien n'est envoyé avant « Créer le topic »
	return topic not in m.CATALOGUE and topic not in comp.fetch('crees', [])


def connu(comp, topic):
	# topic vu sur le serveur (mode désactivé) ou créé : ce send peut y envoyer
	crees = [t for t in comp.fetch('crees', []) if t != topic] + [topic]
	comp.store('crees', crees[-50:])


def Creer(comp, vide=True):
	# bouton Créer le topic (et ouverture du patch) : ce send peut maintenant envoyer sur ce topic ;
	# la valeur actuelle est poussée une fois pour que le topic existe sur le serveur ;
	# bouton seulement (vide=True) : sans entrée valide, un message vide du bon format est poussé
	topic, erreur = construire_topic(comp)
	if erreur:
		return
	connu(comp, topic)
	comp.store('dernier', None)
	comp.store('a_pousser', 'vide' if vide else 'valeur')
	if vide:
		Actualiser(comp)   # désactivé : poussé tout de suite ; activé : à la prochaine cadence


def message_vide(fmt):
	# message vide du bon format : val sans valeur (float et table : liste vide, string : texte vide)
	return ('', None) if fmt == 'string' else ([], [])


def pousser(comp, m, commun, topic, actif):
	# un seul envoi demandé par Créer le topic, dès que la connexion le permet ;
	# activé avec une entrée valide : l'envoi normal s'en charge
	demande = comp.fetch('a_pousser', False)
	if not demande or not commun.par.Connecte.eval():
		return ''
	fmt = comp.par.Format.eval()
	valeur, labels, erreur = lire_valeurs(comp)
	if not erreur and actif:
		return ''
	if erreur:
		if demande != 'vide':
			return ''
		if topic in m.CATALOGUE:
			comp.store('a_pousser', False)
			return 'topic déjà sur le serveur, rien n\'est remplacé'
		valeur, labels = message_vide(fmt)
	comp.store('a_pousser', False)
	etat = m.Publier(commun, topic, valeur, fmt, labels, comp.path)
	if etat != 'OK':
		return etat
	return 'topic créé vide, rien de branché' if erreur else 'topic créé avec la valeur actuelle'


def ChangerActif(comp):
	# Actif d'un send : tous les send et receive suivent, par saillance_master
	commun = getattr(op, 'commun', None)
	actif = comp.par.Actif.eval()
	if commun is not None and commun.par.Actif.eval() != actif:
		commun.par.Actif = actif
	else:
		Verrouiller(comp, actif)
		Actualiser(comp)


def Actualiser(comp):
	# réglages changés, catalogue changé, connexion, ouverture : entrée, menus, topic, et état en mode désactivé
	entrees(comp, comp.par.Format.eval())
	commun = getattr(op, 'commun', None)
	if commun is None:
		afficher(comp, 'Etat', 'saillance_master introuvable dans ce patch')
		return
	m = commun.op('mqtt/mqtt_fonctions').module
	topic, erreur = construire_topic(comp)
	afficher(comp, 'Topic', topic)
	if comp.par.Actif.eval():
		return    # activé : l'envoi et l'état sont faits à la cadence d'envoi commune (Envoyer)
	menus(comp, m)
	comp.store('dernier', None)   # à l'activation, l'envoi repart tout de suite
	texte = 'Désactivé : rien n\'est envoyé, réglages modifiables'
	if not erreur:
		if topic in m.CATALOGUE and topic not in comp.fetch('crees', []):
			connu(comp, topic)        # déjà sur le serveur : pas besoin de Créer le topic
		pousse = pousser(comp, m, commun, topic, False)
		if pousse:
			texte = 'Désactivé : ' + pousse
	afficher(comp, 'Etat', texte)


def Envoyer(comp):
	# appelée par saillance_master à la fréquence d'envoi commune, seulement en mode activé
	commun = getattr(op, 'commun', None)
	if commun is None:
		afficher(comp, 'Etat', 'saillance_master introuvable dans ce patch')
		return
	m = commun.op('mqtt/mqtt_fonctions').module
	fmt = comp.par.Format.eval()
	topic, erreur = construire_topic(comp)
	if erreur:
		afficher(comp, 'Etat', erreur)
		return
	m.SENDS[comp.path] = topic
	if nouveau(comp, m, topic):
		afficher(comp, 'Etat', 'Nouveau topic : rien n\'est envoyé. Clique « Créer le topic » pour le créer et commencer l\'envoi')
		return
	pousse = pousser(comp, m, commun, topic, True)   # Créer le topic sans rien de branché : message vide
	afficher(comp, 'Apercu', m.DERNIER.get(topic, ''))
	valeur, labels, erreur = lire_valeurs(comp)
	afficher(comp, 'Labels', ', '.join(labels) if labels else '')
	if erreur:
		afficher(comp, 'Etat', erreur + (' (' + pousse + ')' if pousse else ''))
		return
	# en continu, ou seulement quand ça change
	if comp.par.Mode.eval() != 'evenement' or comp.fetch('dernier', None) != (topic, valeur):
		etat = m.Publier(commun, topic, valeur, fmt, labels, comp.path)
		if etat == 'OK':
			comp.store('dernier', (topic, valeur))
			comp.store('a_pousser', False)
		comp.store('etat', etat)
	etat = comp.fetch('etat', 'OK')
	if etat == 'OK':
		autres = [c for c, t in m.SENDS.items() if t == topic and c != comp.path and op(c) is not None]
		if autres:
			etat = 'OK, mais ' + autres[0] + ' (dans ce patch) envoie aussi sur ce topic'
		elif time.time() - m.ETRANGERS.get(comp.path, 0) < 10:
			etat = 'OK, mais un autre envoyeur publie aussi sur ce topic'
		elif fmt == 'float' and comp.fetch('avertissement', ''):
			etat = 'OK, mais ' + comp.fetch('avertissement', '')
	afficher(comp, 'Etat', etat)
