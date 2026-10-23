# maj_fonctions
# Bouton « Mettre à jour » : télécharge la version officielle de saillance_master, send_mqtt, receive, dmx et fichiers_manquants
# depuis la dernière release GitHub du repository (réglage Depot de la sous-base mise_a_jour) et remplace celles du patch.
# Les réglages sont gardés, sauf ceux dont la valeur par défaut a changé dans la nouvelle version (un dmx est mis à jour sur place)
# et que personne n'avait modifiés.
# Composante commune : ne rien modifier sans l'annoncer.

import json, os, re, threading, time, urllib.request

DOSSIER = os.path.join(os.path.expanduser('~'), '.saillance_maj')   # .tox téléchargés
RESULTATS = {}                # chemin de saillance_master -> réponse de GitHub, en attente d'être traitée
VERIFS = {}                   # chemin de saillance_master -> tag de la dernière release, en attente d'être comparé
CLE = 'saillance_maj'         # rangé dans le parent de saillance_master pendant le remplacement


def afficher(comp, texte):
	comp.par.Etatmaj = texte
	print('[mise à jour]', texte)


def lire_url(adresse, delai):
	requete = urllib.request.Request(adresse, headers={'User-Agent': 'saillance-touchdesigner', 'Accept': 'application/vnd.github+json'})
	with urllib.request.urlopen(requete, timeout=delai) as reponse:
		return reponse.read()


def Verifier(comp):
	# à l'ouverture : lit le tag de la dernière release ; Suivre propose la mise à jour si le patch est en retard
	depot = comp.op('mise_a_jour').par.Depot.eval().strip().strip('/')
	if not depot:
		return
	chemin = comp.path

	def tache():
		try:
			release = json.loads(lire_url('https://api.github.com/repos/' + depot + '/releases/latest', 15).decode('utf-8'))
			VERIFS[chemin] = release.get('tag_name', '')
		except Exception as erreur:
			print('[mise à jour] version officielle illisible :', erreur)

	threading.Thread(target=tache, daemon=True).start()


def Proposer(comp, officielle):
	actuelle = comp.par.Version.eval()
	if not officielle or officielle == actuelle:
		return
	afficher(comp, 'Nouvelle version disponible : ' + officielle)
	op.TDResources.PopDialog.OpenDefault(
		text='Ce patch a saillance_master ' + actuelle + ', la version officielle est ' + officielle + '.\n'
			'« Mettre à jour » remplace les pièces communes du patch et garde vos réglages.',
		title='Saillance : nouvelle version',
		buttons=['Mettre à jour', 'Plus tard'],
		callback=lambda info: MettreAJour(comp) if info.get('button') == 'Mettre à jour' else None,
		escButton=2)


def MettreAJour(comp):
	depot = comp.op('mise_a_jour').par.Depot.eval().strip().strip('/')
	if not depot:
		afficher(comp, 'Mise à jour impossible : repository GitHub vide (sous-base mise_a_jour)')
		return
	if comp.fetch('maj_en_cours', False):
		return
	comp.store('maj_en_cours', True)
	afficher(comp, 'Téléchargement de la dernière release de ' + depot + ' ...')
	chemin = comp.path
	actuelle = comp.par.Version.eval()

	def tache():
		# fil séparé : seulement du réseau et des fichiers, rien de Touch
		try:
			release = json.loads(lire_url('https://api.github.com/repos/' + depot + '/releases/latest', 30).decode('utf-8'))
			version = release.get('tag_name', '')
			if not version:
				RESULTATS[chemin] = {'erreur': 'aucune release publiée sur ' + depot}
				return
			if version == actuelle:
				RESULTATS[chemin] = {'version': version, 'fichiers': {}}
				return
			os.makedirs(DOSSIER, exist_ok=True)
			fichiers = {}
			for fichier in release.get('assets', []):
				# commun_<nom>.tox ou commun_<nom>_vX.Y.Z.tox
				trouve = re.fullmatch(r'commun_(.+?)(_v\d+\.\d+\.\d+)?\.tox', fichier.get('name', ''))
				if not trouve:
					continue
				destination = os.path.join(DOSSIER, 'commun_' + trouve.group(1) + '_' + version + '.tox')
				with open(destination, 'wb') as f:
					f.write(lire_url(fichier['browser_download_url'], 60))
				fichiers[trouve.group(1)] = destination
			RESULTATS[chemin] = {'version': version, 'fichiers': fichiers}
		except Exception as erreur:
			RESULTATS[chemin] = {'erreur': str(erreur)}

	threading.Thread(target=tache, daemon=True).start()


def Suivre(comp):
	# chaque seconde : propose la mise à jour (après les fenêtres d'identité), puis traite la réponse quand elle est arrivée
	if comp.path in VERIFS and not comp.fetch('en_dialogue', False) and not comp.fetch('maj_en_cours', False):
		Proposer(comp, VERIFS.pop(comp.path))
	reponse = RESULTATS.pop(comp.path, None)
	if reponse is None:
		return
	comp.store('maj_en_cours', False)
	if reponse.get('erreur'):
		afficher(comp, 'Mise à jour impossible : ' + reponse['erreur'])
		return
	version = reponse.get('version', '')
	if version == comp.par.Version.eval():
		afficher(comp, 'Déjà à jour (' + version + ')')
		return
	fichiers = reponse.get('fichiers', {})
	if 'saillance_master' not in fichiers:
		afficher(comp, 'Mise à jour impossible : commun_saillance_master.tox absent de la release ' + version)
		return
	Remplacer(comp, version, fichiers)


IDENTITE = ('Nom', 'Poste', 'Username')


def photo(c):
	# valeur de chaque paramètre personnalisé, avec sa valeur par défaut de l'ancienne version
	pars = {}
	for p in c.customPars:
		if p.isPulse or p.name == 'Version' or p.style == 'Header':
			continue
		if p.mode == ParMode.EXPRESSION:
			valeur = ('expr', p.expr)
		elif p.mode == ParMode.BIND:
			valeur = ('bind', p.bindExpr)
		elif p.mode == ParMode.EXPORT:
			continue
		else:
			valeur = ('val', p.val)
		pars[p.name] = (valeur, p.default)
	return pars


def remettre(c, pars):
	for nom, (valeur, ancien_defaut) in pars.items():
		p = getattr(c.par, nom, None)
		if p is None:
			continue          # paramètre retiré dans la nouvelle version
		genre, contenu = valeur
		if genre == 'val' and contenu == ancien_defaut and p.default != ancien_defaut:
			continue          # jamais modifié, et la nouvelle version a un autre défaut : on garde le nouveau
		try:
			if genre == 'expr':
				p.expr = contenu
				p.mode = ParMode.EXPRESSION
			elif genre == 'bind':
				p.bindExpr = contenu
				p.mode = ParMode.BIND
			elif p.isMenu and not p.isString and contenu not in p.menuNames:
				continue      # choix qui n'existe plus dans le menu
			elif p.readOnly and nom not in IDENTITE:
				continue      # valeurs officielles ou affichées : celles de la nouvelle version
			else:
				p.val = contenu
		except Exception as erreur:
			print('[mise à jour] paramètre', nom, 'de', c.path, 'non remis :', erreur)


def Remplacer(comp, version, fichiers):
	trouver = comp.op('mqtt/mqtt_fonctions').module.trouver
	cibles = []
	compte = []
	dmx = []
	# nom cherché (DAT <nom>_fonctions ou étiquette commun_<nom>) -> .tox
	for nom, fichier in (('send', 'send_mqtt'), ('receive', 'receive'), ('dmx', 'dmx'), ('fichiers', 'fichiers_manquants')):
		trouves = trouver(nom, True)
		chemin = fichiers.get(fichier)
		if chemin is None:
			if trouves:
				compte.append(str(len(trouves)) + ' ' + fichier + ' non mis à jour (commun_' + fichier + '.tox absent de la release ' + version + ')')
			continue
		if nom == 'dmx':
			dmx = [c.path for c in trouves]
		else:
			cibles += [(c, chemin) for c in trouves]
		compte.append(str(len(trouves)) + ' ' + fichier)
	# saillance_master en dernier : c'est elle qui fait la mise à jour
	cibles.append((comp, fichiers['saillance_master']))
	for c, fichier in cibles:
		print('[mise à jour]', c.path, '<-', os.path.basename(fichier))

	parent = comp.parent()
	parent.store(CLE, {
		'version': version,
		'heure': time.time(),
		'commun': comp.path,
		'session': comp.fetch('session', None),
		'cibles': dict([(c.path, photo(c)) for c, _ in cibles] +
			[(s.path, photo(s)) for s in (comp.op('mqtt'), comp.op('presence')) if s is not None]),
		'compte': 'saillance_master, ' + ', '.join(compte),
		'dmx': dmx,
		'fichier_dmx': fichiers.get('dmx'),
	})
	afficher(comp, 'Remplacement par ' + version + ' : saillance_master, ' + ', '.join(compte) + ' ...')
	# la suite est faite par la nouvelle version, quelques images plus tard
	run("op(args[0]).op('mise_a_jour/maj_fonctions').module.Restaurer(args[0], args[1], 0)",
		comp.path, parent.path, delayFrames=10, fromOP=parent)
	for c, fichier in cibles:
		c.par.enableexternaltox = True
		c.par.externaltox = fichier
		c.par.reinitnet.pulse()


SCRIPTS_DMX = ('dmx_fonctions', 'demarrage', 'parametres')


def reglage(p):
	if p.mode == ParMode.EXPRESSION:
		return ('expr', p.expr)
	if p.mode == ParMode.BIND:
		return ('bind', p.bindExpr)
	return ('val', p.val)


def appliquer(p, valeur):
	genre, contenu = valeur
	if genre == 'expr':
		p.expr = contenu
		p.mode = ParMode.EXPRESSION
	elif genre == 'bind':
		p.bindExpr = contenu
		p.mode = ParMode.BIND
	else:
		p.mode = ParMode.CONSTANT
		p.val = contenu


def MettreAJourDmx(comp, chemins, fichier):
	# Un dmx n'est pas rechargé : seuls la base (ses paramètres), ses scripts, dmxout et dmxmap sont mis à jour.
	# Les lumières, les templates et tout ce que chacun a ajouté restent tels quels.
	# Dans dmxout et dmxmap, un réglage change seulement si la nouvelle version l'a changé.
	atelier = comp.op('mise_a_jour')
	try:
		neuf = atelier.loadTox(fichier)
	except Exception as erreur:
		print('[mise à jour] dmx non mis à jour :', erreur)
		return
	officiel = neuf.fetch('officiel', {}, search=False)
	for chemin in chemins:
		c = op(chemin)
		if c is None:
			continue
		try:
			# la base : paramètres de la nouvelle version, réglages de chacun remis
			pars = photo(c)
			c.destroyCustomPars()
			c.copyParameters(neuf, custom=True, builtin=False)
			remettre(c, pars)
			for t in neuf.tags:
				c.tags.add(t)
			# les scripts : remplacés
			for nom in SCRIPTS_DMX:
				nouveau = neuf.op(nom)
				if nouveau is None:
					continue
				ancien = c.op(nom)
				x, y = (ancien.nodeX, ancien.nodeY) if ancien is not None else (nouveau.nodeX, nouveau.nodeY)
				if ancien is not None:
					ancien.destroy()
				copie = c.copy(nouveau, name=nom)
				copie.nodeX, copie.nodeY = x, y
			# dmxout et dmxmap : gardés (fils et réglages), sauf les réglages changés par la nouvelle version
			ancien_officiel = c.fetch('officiel', {}, search=False)
			for nom, reglages in officiel.items():
				o = c.op(nom)
				if o is None:
					nouveau = neuf.op(nom)
					if nouveau is not None:
						c.copy(nouveau, name=nom)
					continue
				avant = ancien_officiel.get(nom, {})
				if not avant:
					continue          # ancienne version sans photo : tout est gardé
				for nom_par, valeur in reglages.items():
					if nom_par in avant and tuple(avant[nom_par]) == tuple(valeur):
						continue      # pas changé par la nouvelle version : réglage de chacun gardé
					p = getattr(o.par, nom_par, None)
					if p is not None:
						try:
							appliquer(p, tuple(valeur))
						except Exception as erreur:
							print('[mise à jour]', o.path, nom_par, 'non changé :', erreur)
			c.store('officiel', officiel)
		except Exception as erreur:
			print('[mise à jour] dmx', chemin, 'non mis à jour :', erreur)
	neuf.destroy()


def Restaurer(chemin_commun, chemin_parent, essai):
	parent = op(chemin_parent)
	donnees = parent.fetch(CLE, None, search=False) if parent else None
	comp = op(chemin_commun)
	if not donnees or comp is None:
		return
	if comp.par.Version.eval() != donnees['version'] and essai < 30:
		# pas encore rechargée : on réessaie un peu plus tard
		run("op(args[0]).op('mise_a_jour/maj_fonctions').module.Restaurer(args[0], args[1], args[2])",
			chemin_commun, chemin_parent, essai + 1, delayFrames=10, fromOP=parent)
		return
	n = 0
	for chemin, pars in donnees['cibles'].items():
		c = op(chemin)
		if c is None:
			continue
		remettre(c, pars)
		c.par.externaltox = ''    # le contenu reste dans le patch, sans dépendre du fichier téléchargé
		n += 1
	if donnees.get('dmx') and donnees.get('fichier_dmx'):
		MettreAJourDmx(comp, donnees['dmx'], donnees['fichier_dmx'])
	if donnees.get('session'):
		comp.store('session', donnees['session'])
	parent.unstore(CLE)
	comp.store('maj_en_cours', False)
	comp.op('presence/presence_fonctions').module.Reprendre(comp)
	if comp.par.Version.eval() == donnees['version']:
		afficher(comp, 'Mis à jour en ' + donnees['version'] + ' : ' + donnees.get('compte', str(n) + ' composantes') + '. Sauvegarde le patch.')
	else:
		afficher(comp, 'Mise à jour incomplète : saillance_master est encore en ' + comp.par.Version.eval())
