# mqtt_fonctions
# Lien avec le serveur MQTT : connexion, abonnements (tout saillance si désactivé, seulement les receive si activé),
# catalogue des données présentes,
# envoi pour les send, distribution aux receive, infos du poste et erreurs de Touch.
# Composante commune : ne rien modifier sans l'annoncer.

import json, os, subprocess, sys, threading, time
from collections import deque

FORMATAGE = 1                 # version du formatage des messages (champ v)
RACINE = 'saillance'
ZONES = ['jam', 'ecrans', 'globale', 'regie']
INTERVALLE_INFO = 5           # secondes entre deux messages info
CATALOGUE = {}                # topic -> dernier message présent sur le serveur (sans sys)
RECU = {}                     # topic -> heure de réception (ms) de ce message
SEQ = {}                      # topic -> compteur d'envois (repart à 0 à l'ouverture du patch)
DERNIER = {}                  # topic -> texte du dernier message envoyé par ce patch (aperçu des send)
ENVOYES = {}                  # topic -> derniers (ts, seq, chemin du send) envoyés par ce patch
SENDS = {}                    # chemin d'un send -> son topic
ENVOYEURS = set()             # chemins des send du patch, appelés à la cadence d'envoi
ETRANGERS = {}                # chemin d'un send -> heure du dernier message d'un autre envoyeur sur son topic
INSCRITS = {}                 # chemin d'un receive -> (topic écouté ou préfixe, toutes les propriétés)
RECONNEXION = 5               # secondes entre deux essais de reconnexion automatique
ETAT = {'changements': 0, 'menus': False, 'abonnements': [], 'gpu': [], 'gpu_en_cours': False,
	'gpu_heure': 0, 'cpu_avant': None, 'erreurs': {}, 'debut': 0, 'image_debut': 0,
	'voulu': False, 'essai': 0, 'perte': None, 'reabonner': False,
	'gpumem': [], 'lat': -1, 'ping_heure': 0, 'ping_attente': False, 'connexions': 0, 'rc': 0, 'prochain': 0}


def maintenant_ms():
	return int(time.time() * 1000)


def afficher(comp, texte):
	if comp.par.Etat.eval() != texte:
		comp.par.Etat = texte


def reglages(comp):
	# adresse du serveur et fréquence d'envoi : dans la sous-base mqtt
	return comp.op('mqtt').par


def trouver(nom):
	# tous les send (ou receive) du patch, à n'importe quelle profondeur :
	# reconnus par leur DAT send_fonctions ou leur étiquette
	trouves = []
	for c in op('/').findChildren(type=COMP, includeUtility=True):
		if c.path.startswith(('/sys', '/ui', '/local')):
			continue
		if c.op(nom + '_fonctions') is not None or 'commun_' + nom in c.tags:
			trouves.append(c)
	return trouves


def Preparer(comp):
	CATALOGUE.clear()
	RECU.clear()
	SEQ.clear()
	ENVOYES.clear()
	ETAT['changements'] += 1
	ETAT['debut'] = time.time()
	ETAT['images'] = 0
	cpu_systeme()             # première mesure : sert de point de départ
	# les receive se réinscrivent (ouverture du patch ou mise à jour de la composante)
	run("args[0].op('mqtt/mqtt_fonctions').module.Rafraichir(args[0])", comp, delayFrames=60)


def VerifierDoubles(comp):
	# une seule saillance_master par patch
	autres = [c.path for c in trouver('saillance_master') if c.path != comp.path]
	if not autres:
		return
	texte = 'Il y a ' + str(len(autres) + 1) + ' saillance_master dans ce patch (' + ', '.join([comp.path] + autres) + '). Garde-en une seule.'
	print('[saillance_master]', texte)
	afficher(comp, texte)
	try:
		op.TDResources.PopDialog.OpenDefault(text=texte, title='Saillance : saillance_master en double', buttons=['OK'])
	except Exception:
		pass


def Rafraichir(comp):
	# receive rechargés, send actualisés (ouverture, connexion, changement de mode)
	for c in trouver('receive'):
		c.op('receive_fonctions').module.Recharger(c)
	for c in trouver('send'):
		c.op('send_fonctions').module.Actualiser(c)


# ---- abonnements et mode Activé / Désactivé

def topic_ping(comp):
	username = comp.par.Username.eval()
	return RACINE + '/sys/' + username + '/ping' if username else ''


def abonnements_voulus(comp):
	# désactivé : toutes les zones de saillance (sauf sys), pour que les menus montrent tout ;
	# activé : seulement les topics des receive (sauf ceux en pause)
	if not comp.par.Actif.eval():
		return [RACINE + '/' + z + '/#' for z in ZONES]
	voulus = set()
	for cible, toutes in INSCRITS.values():
		if cible:
			voulus.add(cible + '+' if toutes else cible)
	return sorted(voulus)


def Abonner(comp):
	# refait les abonnements quand le mode change ou qu'un receive change de topic ou de pause
	client = comp.op('mqtt/client')
	voulus = abonnements_voulus(comp)
	ping = topic_ping(comp)
	if ping:
		voulus = voulus + [ping]   # latence : le patch reçoit son propre ping
	if comp.par.Connecte.eval():
		for t in ETAT['abonnements']:
			if t not in voulus:
				client.unsubscribe(t)
		for t in voulus:
			if t not in ETAT['abonnements']:
				client.subscribe(t, qos=0)
		ETAT['abonnements'] = voulus
	if comp.par.Actif.eval():
		# activé : on oublie les données qui ne sont plus écoutées
		for topic in list(CATALOGUE):
			if not any(correspond(t[:-1], True, topic) if t.endswith('+') else t == topic for t in voulus):
				CATALOGUE.pop(topic, None)
				RECU.pop(topic, None)
	ETAT['changements'] += 1
	ETAT['menus'] = True


def ChangerMode(comp):
	# Actif de saillance_master : tous les send et receive suivent (réglages bloqués si activé)
	actif = comp.par.Actif.eval()
	ETAT['prochain'] = 0   # à l'activation, l'envoi part tout de suite
	for nom in ('send', 'receive'):
		for c in trouver(nom):
			if nom == 'send':
				ENVOYEURS.add(c.path)
			try:
				if c.par.Actif.eval() != actif:
					c.par.Actif = actif
				c.op(nom + '_fonctions').module.Verrouiller(c, actif)
			except Exception as erreur:
				print('[mqtt]', nom, c.path, 'non changé :', erreur)
	Abonner(comp)
	Rafraichir(comp)


def Cadence(comp):
	# à chaque image, en mode activé seulement : une comparaison d'heure, et les send sont appelés
	# à la fréquence d'envoi commune, selon l'heure réelle (une image lente retarde l'envoi sans le sauter)
	maintenant = time.perf_counter()
	if maintenant < ETAT['prochain']:
		return
	periode = 1.0 / max(1, comp.op('mqtt').par.Frequence.eval())
	ETAT['prochain'] = max(ETAT['prochain'] + periode, maintenant)
	for chemin in list(ENVOYEURS):
		c = op(chemin)
		if c is None or c.op('send_fonctions') is None:
			ENVOYEURS.discard(chemin)
			continue
		try:
			c.op('send_fonctions').module.Envoyer(c)
		except Exception as erreur:
			print('[mqtt] send', chemin, 'non envoyé :', erreur)


# ---- connexion

def Connecter(comp, auto=False):
	username = comp.par.Username.eval()
	client = comp.op('mqtt/client')
	comp.par.Connecte = False
	ETAT['abonnements'] = []
	ETAT['essai'] = time.time()
	client.par.active = False
	if not username:
		ETAT['voulu'] = False
		afficher(comp, 'Identité manquante : pulse « Changer d\'identité » (page Commun)')
		return
	ETAT['voulu'] = True
	adresse = reglages(comp).Adresse.eval().strip()
	client.par.netaddress = adresse
	client.par.specifyid = True
	# identifiant unique pour chaque patch ouvert : personne n'est déconnecté
	client.par.usercid = username + '_' + (comp.fetch('session', '') or 'patch')[:6]
	client.par.username = username
	client.par.reconnect = True
	if not auto:
		afficher(comp, 'Connexion à ' + adresse + ' ...')
	run("args[0].par.active = True", client, delayFrames=2)


def Connecte(comp):
	ETAT['connexions'] += 1
	if ETAT['connexions'] > 1:
		ETAT['rc'] += 1          # reconnexion depuis l'ouverture du patch
	comp.par.Connecte = True
	ETAT['abonnements'] = []
	afficher(comp, 'Connecté')
	Abonner(comp)
	# les messages gardés arrivent juste après l'abonnement : tous les receive sont rechargés ensuite
	run("args[0].op('mqtt/mqtt_fonctions').module.Rafraichir(args[0])", comp, delayFrames=30)
	perte = ETAT['perte']
	if perte:
		# reconnecté : on signale la coupure sur saillance/sys/<username>/error
		ETAT['perte'] = None
		duree = int(time.time() - perte['heure'])
		message = 'Déconnecté du serveur MQTT pendant ' + str(duree) + ' s' + (' (' + perte['raison'] + ')' if perte['raison'] else '')
		print('[mqtt] reconnecté.', message)
		publier_sys(comp, 'error', {'src': comp.path, 'msg': message, 'sv': 2, 't': 'deconnexion'})


def Echec(comp, raison):
	comp.par.Connecte = False
	perte = ETAT['perte']
	debut = 'Déconnecté depuis ' + str(int(time.time() - perte['heure'])) + ' s' if perte else 'Connexion impossible'
	afficher(comp, debut + ', nouvel essai automatique aux ' + str(RECONNEXION) + ' s : ' + str(raison))


def Perdu(comp, raison):
	if not comp.par.Connecte.eval():
		return    # déjà déconnecté (ex. Connecter qui coupe avant de reconnecter)
	comp.par.Connecte = False
	ETAT['perte'] = {'heure': time.time(), 'raison': str(raison or '')}
	ETAT['essai'] = time.time()
	print('[mqtt] déconnecté du serveur MQTT', ('(' + str(raison) + ')') if raison else '', ': reconnexion automatique')
	afficher(comp, 'Déconnecté du serveur, reconnexion automatique ...')


def Surveiller(comp):
	# chaque seconde : si la connexion est voulue mais absente, nouvel essai aux RECONNEXION secondes
	if not ETAT['voulu'] or comp.par.Connecte.eval():
		return
	if time.time() - ETAT['essai'] < RECONNEXION:
		return
	perte = ETAT['perte']
	if perte:
		afficher(comp, 'Déconnecté depuis ' + str(int(time.time() - perte['heure'])) + ' s, reconnexion automatique ...')
	Connecter(comp, auto=True)


# ---- réception

def correspond(cible, toutes, topic):
	if not cible:
		return False
	return topic.startswith(cible) if toutes else topic == cible


def Recevoir(comp, topic, payload, retained=False):
	if topic == topic_ping(comp):
		# retour du ping (aux 60 s) : latence aller-retour
		try:
			texte = payload.decode('utf-8', 'replace') if isinstance(payload, (bytes, bytearray)) else str(payload)
			ETAT['lat'] = max(0, maintenant_ms() - int(json.loads(texte)['ts']))
			ETAT['ping_attente'] = False
		except Exception:
			pass
		return
	morceaux = topic.split('/')
	if len(morceaux) != 5 or morceaux[0] != RACINE or morceaux[1] not in ZONES:
		return
	if not payload:
		# message gardé effacé : la donnée n'est plus sur le serveur
		if CATALOGUE.pop(topic, None) is not None:
			RECU.pop(topic, None)
			ETAT['changements'] += 1
			ETAT['menus'] = True
		return
	texte = payload.decode('utf-8', 'replace') if isinstance(payload, (bytes, bytearray)) else str(payload)
	try:
		message = json.loads(texte)
		if not isinstance(message, dict) or 'val' not in message:
			raise ValueError
	except ValueError:
		print('[mqtt] message ignoré, format inconnu :', topic)
		return
	if topic not in CATALOGUE:
		ETAT['changements'] += 1
		ETAT['menus'] = True
	CATALOGUE[topic] = message
	recu = maintenant_ms()
	RECU[topic] = recu
	if not retained:
		reperer_etrangers(topic, message)
	# les receive qui écoutent ce topic sont prévenus tout de suite (aucun travail sans message)
	for chemin, (cible, toutes) in list(INSCRITS.items()):
		if correspond(cible, toutes, topic):
			c = op(chemin)
			if c is None or c.op('receive_fonctions') is None:
				INSCRITS.pop(chemin, None)
				continue
			c.op('receive_fonctions').module.Message(c, topic, message, recu)


def reperer_etrangers(topic, message):
	# un message qui ne vient pas d'un send donné : un autre envoyeur publie sur son topic
	cle = (message.get('ts'), message.get('seq'))
	auteur = None
	for ts, seq, chemin in ENVOYES.get(topic, ()):
		if (ts, seq) == cle:
			auteur = chemin
			break
	for chemin, t in list(SENDS.items()):
		if t == topic and chemin != auteur:
			ETRANGERS[chemin] = time.time()


def Inscrire(chemin, cible, toutes):
	# appelée par les receive : cible = topic écouté (ou préfixe si toutes), None si aucun choix valide ou en pause
	if INSCRITS.get(chemin) != (cible, toutes):
		INSCRITS[chemin] = (cible, toutes)
		ETAT['reabonner'] = True


# ---- envoi

def publier(comp, topic, contenu, retain, source=None):
	SEQ[topic] = SEQ.get(topic, 0) + 1
	message = {'v': FORMATAGE, 'ts': maintenant_ms(), 'seq': SEQ[topic]}
	message.update(contenu)
	texte = json.dumps(message)
	if source:
		# noté avant l'envoi : le serveur peut renvoyer le message tout de suite
		ENVOYES.setdefault(topic, deque(maxlen=100)).append((message['ts'], message['seq'], source))
		DERNIER[topic] = texte
	comp.op('mqtt/client').publish(topic, texte.encode('utf-8'), qos=0, retain=retain)


def Publier(comp, topic, val, fmt, labels=None, source=None):
	# appelée par les tox send ; retourne l'état à afficher dans le tox
	if not comp.par.Connecte.eval():
		return 'Pas connecté au serveur MQTT (voir saillance_master)'
	contenu = {'val': val, 'f': fmt}
	if fmt == 'float' or labels:
		contenu['label'] = labels or []
	# message gardé par le serveur : un patch ouvert plus tard voit la donnée tout de suite
	publier(comp, topic, contenu, True, source)
	return 'OK'


def publier_sys(comp, genre, contenu):
	username = comp.par.Username.eval()
	if comp.par.Connecte.eval() and username:
		publier(comp, RACINE + '/sys/' + username + '/' + genre, contenu, False)


# ---- erreurs (Error DAT)

def Erreur(comp, message, severite, famille, source):
	try:
		severite = int(severite)
	except (TypeError, ValueError):
		pass
	if (isinstance(severite, int) and severite < 2) or str(severite).lower() in ('message', 'info', 'information'):
		return   # simple information de Touch (ex. « 1 node copied. ») : pas une erreur
	source = getattr(source, 'path', source)
	cle = (str(source), str(message))
	if time.time() - ETAT['erreurs'].get(cle, 0) < 1:
		return   # même erreur répétée : envoyée au plus une fois par seconde
	if len(ETAT['erreurs']) > 500:
		ETAT['erreurs'].clear()
	ETAT['erreurs'][cle] = time.time()
	publier_sys(comp, 'error', {'src': str(source), 'msg': str(message), 'sv': severite, 't': str(famille)})


# ---- infos du poste, aux 5 secondes

def cpu_systeme():
	# pourcentage d'utilisation de tout l'ordinateur depuis la mesure précédente (-1 si impossible)
	try:
		if sys.platform.startswith('win'):
			import ctypes

			class Temps(ctypes.Structure):
				_fields_ = [('bas', ctypes.c_uint32), ('haut', ctypes.c_uint32)]

			inactif, noyau, usager = Temps(), Temps(), Temps()
			if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(inactif), ctypes.byref(noyau), ctypes.byref(usager)):
				return -1
			valeur = lambda t: (t.haut << 32) | t.bas
			actuel = (valeur(inactif), valeur(noyau) + valeur(usager))   # le temps noyau inclut l'inactif
			avant = ETAT['cpu_avant']
			ETAT['cpu_avant'] = actuel
			if not avant or actuel[1] == avant[1]:
				return -1
			return max(0, min(100, round(100 * (1 - (actuel[0] - avant[0]) / (actuel[1] - avant[1])))))
		return max(0, min(100, round(100 * os.getloadavg()[0] / (os.cpu_count() or 1))))
	except Exception:
		return -1


def ram_systeme():
	# pourcentage de mémoire vive de l'ordinateur utilisée (-1 si impossible)
	try:
		if sys.platform.startswith('win'):
			import ctypes

			class Memoire(ctypes.Structure):
				_fields_ = [('dwLength', ctypes.c_uint32), ('dwMemoryLoad', ctypes.c_uint32),
					('ullTotalPhys', ctypes.c_uint64), ('ullAvailPhys', ctypes.c_uint64),
					('ullTotalPageFile', ctypes.c_uint64), ('ullAvailPageFile', ctypes.c_uint64),
					('ullTotalVirtual', ctypes.c_uint64), ('ullAvailVirtual', ctypes.c_uint64),
					('ullAvailExtendedVirtual', ctypes.c_uint64)]

			m = Memoire()
			m.dwLength = ctypes.sizeof(Memoire)
			if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
				return -1
			return int(m.dwMemoryLoad)
		infos = {}
		with open('/proc/meminfo') as f:
			for ligne in f:
				nom, valeur = ligne.split(':')
				infos[nom] = int(valeur.split()[0])
		return round(100 * (1 - infos['MemAvailable'] / infos['MemTotal']))
	except Exception:
		return -1


def lire_gpu():
	# une mesure aux 5 s, carte NVIDIA seulement (rien si nvidia-smi n'est pas là) : utilisation et mémoire en %
	try:
		sortie = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'],
			capture_output=True, text=True, timeout=4, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
		utilisation, utilisee, totale = [float(x) for x in sortie.stdout.strip().splitlines()[0].split(',')]
		ETAT['gpu'].append(int(utilisation))
		if totale > 0:
			ETAT['gpumem'].append(round(100 * utilisee / totale))
	except Exception:
		pass
	ETAT['gpu_en_cours'] = False


def canal(chop, nom, defaut):
	c = chop[nom] if chop is not None else None
	return c.eval() if c is not None else defaut


def nom_toe():
	# nom du fichier .toe ouvert, version comprise (lu à chaque info : un Save As est pris en compte)
	nom = str(getattr(project, 'name', '') or '')
	return nom if not nom or nom.endswith('.toe') else nom + '.toe'


def Info(comp, maintenant):
	duree = maintenant - ETAT['debut']
	images = absTime.frame - ETAT['image_debut']
	ETAT['debut'] = maintenant
	ETAT['image_debut'] = absTime.frame
	perf = comp.op('mqtt/perf')
	pic = comp.op('mqtt/msmax')                              # image la plus longue des 5 dernières secondes (Trail et Analyze)
	# moyennes sur les 5 dernières secondes
	fps = images / duree if duree > 0 else 0
	df = max(0, round(project.cookRate * duree - images))   # images perdues pendant ces 5 s
	mesures, ETAT['gpu'] = ETAT['gpu'], []
	gpu = round(sum(mesures) / len(mesures)) if mesures else -1
	mesures, ETAT['gpumem'] = ETAT['gpumem'], []
	gpumem = mesures[-1] if mesures else -1
	msmax = pic[0].eval() if pic is not None and pic.numChans else -1
	if maintenant - ETAT['ping_heure'] >= 60:                # ping aux 60 s seulement
		if ETAT['ping_attente']:
			ETAT['lat'] = -1                                 # le ping précédent n'est pas revenu
		ETAT['ping_heure'] = maintenant
		ETAT['ping_attente'] = True
		publier_sys(comp, 'ping', {})
	lat = ETAT['lat']                                        # dernière latence mesurée, change seulement aux 60 s
	perform = canal(perf, 'performmode', 1 if getattr(ui, 'performMode', False) else 0)
	secteur = canal(perf, 'aclinestatus', 1)                 # 0 = sur batterie
	publier_sys(comp, 'infos', {
		'app': nom_toe(),
		'fps': round(fps, 1),
		'fpsmin': round(1000 / msmax, 1) if msmax > 0 else -1,
		'msmax': round(msmax, 1) if msmax > 0 else -1,
		'df': df,
		'cpu': cpu_systeme(),                                # moyenne depuis le dernier envoi
		'ram': ram_systeme(),
		'gpu': gpu,
		'gpumem': gpumem,
		'ac': 0 if secteur == 0 else 1,
		'performModeL': 1 if perform >= 0.5 else 0,
		'lat': lat,
		'rc': ETAT['rc'],
	})


def Seconde(comp):
	# une fois par seconde (chaque_seconde de saillance_master) : reconnexion, menus, nettoyage, infos du poste
	Surveiller(comp)
	if ETAT['menus']:
		# catalogue changé : menus des receive et des send
		ETAT['menus'] = False
		for c in trouver('receive') + trouver('send'):
			nom = 'receive' if c.op('receive_fonctions') is not None else 'send'
			c.op(nom + '_fonctions').module.Actualiser(c)
	for chemin in list(INSCRITS):
		if op(chemin) is None:
			INSCRITS.pop(chemin, None)
			ETAT['reabonner'] = True
	for chemin in list(SENDS):
		if op(chemin) is None:
			SENDS.pop(chemin, None)
			ETRANGERS.pop(chemin, None)
	if ETAT['reabonner']:
		ETAT['reabonner'] = False
		if comp.par.Actif.eval():
			Abonner(comp)
	maintenant = time.time()
	if not ETAT['debut']:
		ETAT['debut'] = maintenant
		ETAT['image_debut'] = absTime.frame
	elif maintenant - ETAT['debut'] >= INTERVALLE_INFO:
		Info(comp, maintenant)
	if maintenant - ETAT['gpu_heure'] >= INTERVALLE_INFO and not ETAT['gpu_en_cours']:
		ETAT['gpu_heure'] = maintenant
		ETAT['gpu_en_cours'] = True
		threading.Thread(target=lire_gpu, daemon=True).start()
