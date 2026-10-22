# presence_fonctions
# Identité (nom + station de travail = username MQTT), tableau « qui travaille sur quoi »
# et vérification de la version de la composante.
# Composante commune : ne rien modifier sans l'annoncer.

import json, os, re, threading, time, urllib.request, uuid

PARTIES = ['Écran', 'Jam', 'Globale']
MAX_USERNAME = 24
DOSSIER = os.path.expanduser('~')   # derniers nom et poste entrés sur cet ordinateur, pour préremplir


def mqtt(comp):
	return comp.op('mqtt/mqtt_fonctions').module


def reglages(comp):
	# paramètres de la présence : dans la sous-base presence
	return comp.op('presence').par


def nb_questions(comp):
	return 4 if reglages(comp).Actif.eval() else 2


def lire(fichier):
	try:
		with open(os.path.join(DOSSIER, fichier), encoding='utf-8') as f:
			return f.read().strip()
	except OSError:
		return ''


def ecrire(fichier, texte):
	try:
		with open(os.path.join(DOSSIER, fichier), 'w', encoding='utf-8') as f:
			f.write(texte)
	except OSError:
		pass


def probleme_de(texte, maximum):
	# '' si le texte est valide : lettres sans accents, chiffres et _ seulement
	if not texte:
		return 'Ce champ est vide.'
	if not re.fullmatch(r'[A-Za-z0-9_]+', texte):
		return 'Lettres (sans accents), chiffres et _ seulement, sans espace ni autre caractère spécial.'
	if len(texte) > maximum:
		return str(maximum) + ' caractères maximum.'
	return ''


def plus_tard(fonction, comp, *args):
	# ouvre la fenêtre suivante une image plus tard, une fois la précédente fermée
	run("args[0].op('presence/presence_fonctions').module." + fonction + "(*args)", comp, *args, delayFrames=1)


def infos_patch():
	nom_fichier = os.path.splitext(project.name)[0]
	trouve = re.search(r'v\d+\.\d+\.\d+', nom_fichier)
	return nom_fichier, (trouve.group(0) if trouve else '')


def construire_message(comp, type_message):
	patch, version = infos_patch()
	return {
		'type': type_message,
		'session': comp.fetch('session', ''),
		'nom': comp.par.Nom.eval(),
		'partie': reglages(comp).Partie.menuLabels[reglages(comp).Partie.menuIndex],
		'tache': reglages(comp).Tache.eval().strip(),
		'patch': patch,
		'version': version,
		'version_commune': comp.par.Version.eval(),
		'heure': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
	}


def requete_post(url, message, delai):
	donnees = json.dumps(message).encode('utf-8')
	requete = urllib.request.Request(url, data=donnees, method='POST',
		headers={'Content-Type': 'text/plain;charset=utf-8'})
	with urllib.request.urlopen(requete, timeout=delai) as reponse:
		return reponse.read().decode('utf-8')


def envoyer(comp, type_message, attendre=False):
	url = reglages(comp).Url.eval().strip()
	if not url or not comp.par.Nom.eval() or not reglages(comp).Actif.eval():
		return
	message = construire_message(comp, type_message)
	comp.store('dernier_envoi', absTime.seconds)
	chemin = comp.path

	def tache():
		try:
			requete_post(url, message, 3 if attendre else 10)
		except Exception as erreur:
			print('[presence] envoi impossible :', erreur)

	if attendre:
		tache()   # à la fermeture, on attend l'envoi avant que TouchDesigner quitte
	else:
		threading.Thread(target=tache, daemon=True).start()


def Demarrer(comp):
	AfficherPresence(comp)
	if comp.fetch('session', None):
		return
	maj = comp.parent().fetch('saillance_maj', None, search=False)
	if maj and time.time() - maj.get('heure', 0) < 120:
		return   # rechargée par « Mettre à jour » : maj_fonctions remet l'identité et reconnecte
	if maj:
		comp.parent().unstore('saillance_maj')   # reste d'une mise à jour interrompue
	comp.store('session', uuid.uuid4().hex[:12])
	mqtt(comp).Preparer(comp)
	# petit délai pour laisser TouchDesigner finir de charger avant d'ouvrir la fenêtre
	run("args[0].op('presence/presence_fonctions').module.DemanderNom(args[0])", comp, delayFrames=30)


def DemanderNom(comp, probleme=''):
	# étape 1 : le nom
	comp.store('en_dialogue', True)
	dernier = comp.par.Nom.eval() or lire('.saillance_nom.txt')

	def reponse(info):
		if info.get('button') != 'OK':
			Abandonner(comp)
			return
		nom = (info.get('enteredText') or '').strip()
		erreur = probleme_de(nom, MAX_USERNAME - 2)
		if erreur:
			plus_tard('DemanderNom', comp, erreur)
			return
		comp.par.Nom = nom
		ecrire('.saillance_nom.txt', nom)
		plus_tard('DemanderPoste', comp)

	op.TDResources.PopDialog.OpenDefault(
		text=(probleme + '\n\n' if probleme else '') +
			'Qui travaille sur ce patch ?\nPrénom + initiale du nom (ex. : gabc). Lettres, chiffres et _ seulement.',
		title='Saillance (1/' + str(nb_questions(comp)) + ')',
		buttons=['OK', 'Annuler'],
		callback=reponse,
		textEntry=dernier or ' ',
		escButton=2,
		enterButton=1)


def DemanderPoste(comp, probleme=''):
	# étape 2 : la station de travail ; username = nom_poste, 24 caractères maximum
	nom = comp.par.Nom.eval()
	maximum = MAX_USERNAME - len(nom) - 1
	dernier = comp.par.Poste.eval() or lire('.saillance_poste.txt')

	def reponse(info):
		if info.get('button') != 'OK':
			Abandonner(comp)
			return
		poste = (info.get('enteredText') or '').strip()
		erreur = probleme_de(poste, maximum)
		if erreur:
			plus_tard('DemanderPoste', comp, erreur)
			return
		comp.par.Poste = poste
		comp.par.Username = nom + '_' + poste
		ecrire('.saillance_poste.txt', poste)
		if reglages(comp).Actif.eval():
			plus_tard('DemanderPartie', comp)
		else:
			Finir(comp, True)   # présence fermée : seulement le nom et la station

	op.TDResources.PopDialog.OpenDefault(
		text=(probleme + '\n\n' if probleme else '') +
			'Nom de ta station de travail (ex. : pc01, portable).\nLettres, chiffres et _ seulement, '
			+ str(maximum) + ' caractères maximum.',
		title='Saillance (2/' + str(nb_questions(comp)) + ')',
		buttons=['OK', 'Annuler'],
		callback=reponse,
		textEntry=dernier or ' ',
		escButton=2,
		enterButton=1)


def DemanderPartie(comp, connecter=True):
	# étape 3 (présence seulement) : la partie de l'installation
	comp.store('en_dialogue', True)
	partie = reglages(comp).Partie

	def reponse(info):
		if info.get('button') in PARTIES:
			partie.menuIndex = PARTIES.index(info.get('button'))
		plus_tard('DemanderTache', comp, connecter)

	op.TDResources.PopDialog.OpenDefault(
		text='Sur quelle partie travailles-tu ?',
		title='Saillance (3/4)',
		buttons=PARTIES,
		callback=reponse,
		enterButton=partie.menuIndex + 1)


def DemanderTache(comp, connecter=True):
	# étape 4 (présence seulement) : une courte description de la tâche
	def reponse(info):
		if info.get('button') == 'OK':
			reglages(comp).Tache = (info.get('enteredText') or '').strip()[:80]
		Finir(comp, connecter)

	op.TDResources.PopDialog.OpenDefault(
		text='Que fais-tu ? (courte description, ex. : réglage du son station 3)',
		title='Saillance (4/4)',
		buttons=['OK', 'Passer'],
		callback=reponse,
		textEntry=reglages(comp).Tache.eval() or ' ',
		escButton=2,
		enterButton=1)


def Finir(comp, connecter):
	comp.store('en_dialogue', False)
	envoyer(comp, 'ouverture')
	if connecter:
		mqtt(comp).Connecter(comp)


def Abandonner(comp):
	comp.store('en_dialogue', False)
	if not comp.par.Username.eval():
		comp.par.Etat = 'Identité manquante : pulse « Changer d\'identité » (page Commun)'
		print('[saillance_master] aucune identité : pas de connexion au serveur MQTT.')
	else:
		mqtt(comp).Connecter(comp)


def ChangerIdentite(comp):
	if not comp.fetch('session', None):
		comp.store('session', uuid.uuid4().hex[:12])
	DemanderNom(comp)


def AfficherPresence(comp):
	# présence allumée : Partie et Tâche apparaissent sur la page Commun de saillance_master, liées à la sous-base presence
	for nom in ('Spresence', 'Partie', 'Tache'):
		p = getattr(comp.par, nom, None)
		if p is not None:
			p.destroy()
	page = next((p for p in comp.customPages if p.name == 'Commun'), None)
	if page is None or not reglages(comp).Actif.eval():
		return
	page.appendHeader('Spresence', label='Présence')
	source = reglages(comp).Partie
	p = page.appendMenu('Partie', label='Partie')[0]
	p.menuNames = source.menuNames
	p.menuLabels = source.menuLabels
	p.help = source.help
	p.bindExpr = "op('presence').par.Partie"
	p.mode = ParMode.BIND
	p = page.appendStr('Tache', label='Tâche')[0]
	p.help = reglages(comp).Tache.help
	p.bindExpr = "op('presence').par.Tache"
	p.mode = ParMode.BIND


def ActiverPresence(comp):
	# présence rallumée : on demande la partie et la tâche, sans se reconnecter au serveur MQTT
	AfficherPresence(comp)
	if reglages(comp).Actif.eval():
		if not comp.fetch('session', None):
			comp.store('session', uuid.uuid4().hex[:12])
		if comp.par.Username.eval():
			DemanderPartie(comp, False)
	else:
		Fermer(comp, forcer=True)


def MiseAJour(comp):
	# Partie ou Tâche modifiée à la main dans les paramètres
	if not comp.fetch('en_dialogue', False) and comp.fetch('session', None):
		envoyer(comp, 'signal')


def Reprendre(comp):
	# après une mise à jour : on garde l'identité et on se reconnecte sans reposer les questions
	if not comp.fetch('session', None):
		comp.store('session', uuid.uuid4().hex[:12])
	comp.store('en_dialogue', False)
	mqtt(comp).Preparer(comp)
	if comp.par.Username.eval():
		envoyer(comp, 'ouverture')
		mqtt(comp).Connecter(comp)
	else:
		DemanderNom(comp)


def Battement(comp):
	# chaque seconde : signal au tableau aux Intervalle secondes
	if not comp.fetch('session', None) or comp.fetch('en_dialogue', False):
		return
	if absTime.seconds - comp.fetch('dernier_envoi', 0) >= reglages(comp).Intervalle.eval():
		envoyer(comp, 'signal')


def Fermer(comp, forcer=False):
	# signal de fermeture au tableau (Actif désactivé, ou fermeture de Touch)
	url = reglages(comp).Url.eval().strip()
	if url and comp.par.Nom.eval() and comp.fetch('session', None) and (forcer or reglages(comp).Actif.eval()):
		try:
			requete_post(url, construire_message(comp, 'fermeture'), 3)
		except Exception as erreur:
			print('[presence] envoi impossible :', erreur)
