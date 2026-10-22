# receive_fonctions
# Choix du topic étape par étape, parmi les données présentes sur le serveur, et sorties CHOP et DAT.
# saillance_master prévient ce receive quand un message arrive : rien ne tourne sans message.
# L'âge de la donnée est une expression du CHOP info.
# Composante commune : ne rien modifier sans l'annoncer.

import time

ETAPES = ('Zone', 'Module', 'Composante', 'Propriete')
REGLAGES = ETAPES
TOUTES = '*'


def afficher(comp, nom, texte):
	p = getattr(comp.par, nom)
	if p.eval() != texte:
		p.val = texte


def mqtt():
	commun = getattr(op, 'commun', None)
	return commun.op('mqtt/mqtt_fonctions').module if commun is not None else None


def menus(comp, catalogue, choix):
	# chaque menu ne propose que ce qui existe sous les choix précédents
	morceaux = [t.split('/')[1:] for t in catalogue]
	for i, etape in enumerate(ETAPES):
		options = sorted({m[i] for m in morceaux if m[:i] == choix[:i]})
		labels = list(options)
		if etape == 'Propriete' and options:
			options = [TOUTES] + options
			labels = ['* (toutes)'] + labels
		par = getattr(comp.par, etape)
		if list(par.menuNames) != options:
			par.menuNames = options
			par.menuLabels = labels


def valeurs(comp, canaux):
	# Constant CHOP valeurs : un canal par valeur reçue
	chop = comp.op('valeurs')
	chop.seq.const.numBlocks = max(1, len(canaux))
	for i, (nom, valeur) in enumerate(canaux):
		getattr(chop.par, 'const' + str(i) + 'name').val = nom
		getattr(chop.par, 'const' + str(i) + 'value').val = valeur
	if not canaux:
		chop.par.const0name = ''


def vider(comp):
	comp.store('vus', {})
	comp.store('props', {})
	comp.store('canaux', [])
	comp.store('derniere', -1)
	comp.store('latence', -1)
	valeurs(comp, [])
	comp.op('texte').text = ''
	comp.op('textes').clear()
	comp.op('table').clear()


def Actualiser(comp):
	# choix changés, catalogue changé, ouverture du patch : menus, topic, inscription auprès de saillance_master
	m = mqtt()
	if m is None:
		afficher(comp, 'Etat', 'saillance_master introuvable dans ce patch')
		return
	choix = [getattr(comp.par, e).eval().strip() for e in ETAPES]
	toutes = choix[3] == TOUTES
	cible = None
	if comp.par.Actif.eval():
		# activé : réglages bloqués, topic pris tel quel (on s'y abonne même s'il n'a pas encore de donnée)
		manque = [getattr(comp.par, e) for e, c in zip(ETAPES, choix) if not c]
		if manque:
			afficher(comp, 'Topic', '')
			afficher(comp, 'Etat', 'Choisis : ' + manque[0].label + ' (désactive pour modifier les réglages)')
		else:
			cible = 'saillance/' + '/'.join(choix[:3]) + '/' if toutes else 'saillance/' + '/'.join(choix)
	else:
		# désactivé : menus de tout ce qui est sur le serveur
		menus(comp, m.CATALOGUE, choix)
		for etape, c in zip(ETAPES, choix):
			par = getattr(comp.par, etape)
			if not c or c not in par.menuNames:
				afficher(comp, 'Topic', '')
				afficher(comp, 'Etat', 'Choisis : ' + par.label + ('' if not c else ' (« ' + c + ' » n\'est pas sur le serveur présentement)'))
				break
		else:
			cible = 'saillance/' + '/'.join(choix[:3]) + '/' if toutes else 'saillance/' + '/'.join(choix)
	if comp.fetch('cible', None) != cible:
		comp.store('cible', cible)
		vider(comp)
	if cible is None:
		m.Inscrire(comp.path, None, False)
		return
	afficher(comp, 'Topic', cible + TOUTES if toutes else cible)
	m.Inscrire(comp.path, cible, toutes)
	presents = [t for t in m.CATALOGUE if m.correspond(cible, toutes, t)]
	if not presents:
		commun = getattr(op, 'commun', None)
		afficher(comp, 'Etat', 'Aucune donnée sur ce topic présentement' if commun is not None and commun.par.Connecte.eval()
			else 'Pas connecté au serveur MQTT (voir saillance_master)')
		return
	for t in presents:
		Message(comp, t, m.CATALOGUE[t], m.RECU.get(t, int(time.time() * 1000)))


def Verrouiller(comp, actif):
	# activé : réglages bloqués ; Actif et Recharger restent libres
	for nom in REGLAGES:
		getattr(comp.par, nom).readOnly = actif


def Synchroniser(comp):
	# ouverture du patch ou receive ajouté : même mode que saillance_master
	commun = getattr(op, 'commun', None)
	actif = commun.par.Actif.eval() if commun is not None else comp.par.Actif.eval()
	if comp.par.Actif.eval() != actif:
		comp.par.Actif = actif
	Verrouiller(comp, actif)


def ChangerActif(comp):
	# Actif d'un receive : tous les send et receive suivent, par saillance_master
	commun = getattr(op, 'commun', None)
	actif = comp.par.Actif.eval()
	if commun is not None and commun.par.Actif.eval() != actif:
		commun.par.Actif = actif
	else:
		Verrouiller(comp, actif)
		Actualiser(comp)


def Recharger(comp):
	# même effet qu'Actif éteint puis rallumé : menus, topic et dernière donnée repris du catalogue
	comp.store('cible', None)
	comp.store('vus', {})
	Actualiser(comp)


def canaux_de(message, prefixe=''):
	val = message.get('val')
	labels = message.get('label') or []
	canaux = []
	for i, v in enumerate(val if isinstance(val, list) else [val]):
		nom = labels[i] if i < len(labels) and labels[i] else 'v' + str(i + 1)
		try:
			canaux.append((prefixe + str(nom), float(v)))
		except (TypeError, ValueError):
			pass
	return canaux


def sorties(comp, formats):
	# seules les sorties des données reçues existent : out_valeurs (float), out_texte (string), out_table (table)
	if not formats:
		return    # rien de reçu : on ne touche pas aux sorties (les fils branchés restent)
	for nom, source, type_op, y, voulu in (('out_valeurs', 'null_valeurs', outCHOP, 150, 'float' in formats),
			('out_texte', 'null_texte', outDAT, -200, 'string' in formats),
			('out_table', 'null_table', outDAT, -450, 'table' in formats)):
		o = comp.op(nom)
		if voulu and o is None:
			o = comp.create(type_op, nom)
			o.nodeX, o.nodeY = 600, y
			o.color = (0.25, 0.6, 0.3)
			o.inputConnectors[0].connect(comp.op(source))
		elif not voulu and o is not None:
			o.destroy()


def appliquer(comp, toutes):
	# reconstruit les sorties à partir du ou des derniers messages
	props = comp.fetch('props', {})
	canaux, formats, lignes, tables = [], set(), [], []
	for prop in sorted(props):
		message = props[prop]
		fmt = message.get('f', 'float')
		formats.add(fmt)
		if fmt == 'table':
			tables.append((prop, message.get('val') or []))
		elif fmt == 'string':
			val = message.get('val')
			if isinstance(val, list):
				noms = message.get('label') or []
				for i, v in enumerate(val):
					nom = noms[i] if i < len(noms) and noms[i] else 'v' + str(i + 1)
					lignes.append([prop + '_' + str(nom) if toutes else str(nom), str(v)])
			else:
				lignes.append([prop, str(val)])
		else:
			canaux += canaux_de(message, prop + '_' if toutes else '')
	comp.store('canaux', canaux)
	valeurs(comp, canaux)
	en_table = toutes or len(lignes) > 1
	comp.op('choix_texte').par.index = 1 if en_table else 0
	if en_table:
		table = comp.op('textes')
		table.clear()
		table.appendRow(['nom', 'texte'])
		for ligne in lignes:
			table.appendRow(ligne)
	else:
		texte = lignes[0][1] if lignes else ''
		if comp.op('texte').text != texte:
			comp.op('texte').text = texte
	if tables:
		remplir_table(comp, tables, toutes)
	afficher(comp, 'Format', ', '.join(sorted(formats)))
	afficher(comp, 'Labels', ', '.join(n for n, v in canaux))
	sorties(comp, formats)


def remplir_table(comp, tables, toutes):
	# format table : les rangées de val telles quelles, sans rangée de noms
	# avec « toutes » : une colonne propriete en premier, puis les rangées de chaque propriété l'une sous l'autre
	table = comp.op('table')
	table.clear()
	for prop, lignes in tables:
		for ligne in lignes:
			ligne = ligne if isinstance(ligne, list) else [ligne]
			table.appendRow(([prop] if toutes else []) + [str(x) for x in ligne])


def Message(comp, topic, message, recu):
	# appelée par saillance_master à l'arrivée d'un message sur le topic écouté
	cle = (message.get('seq'), message.get('ts'))
	vus = comp.fetch('vus', {})
	if vus.get(topic) == cle:
		return
	vus[topic] = cle
	comp.store('vus', vus)
	toutes = comp.par.Propriete.eval() == TOUTES
	props = comp.fetch('props', {}) if toutes else {}
	props[topic.split('/')[-1]] = message
	comp.store('props', props)
	appliquer(comp, toutes)
	ts = message.get('ts')
	comp.store('latence', recu - ts if isinstance(ts, (int, float)) else -1)
	# heure de Touch (absTime) à l'arrivée : l'âge du CHOP info est calculé par expression
	comp.store('derniere', absTime.seconds - max(0.0, time.time() - recu / 1000.0))
	afficher(comp, 'Etat', 'OK')
