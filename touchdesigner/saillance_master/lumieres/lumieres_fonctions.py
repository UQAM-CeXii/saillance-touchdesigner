# lumieres_fonctions
# Réservations d'univers DMX (page web des réservations, onglet reservations du tableau Google) et dmx du patch.
# Une réservation = une IP et des univers qui se suivent, pour un seul dmx à la fois, tous patches confondus.
# Les univers sont bloqués par IP : les mêmes univers peuvent servir sur une autre IP.
# Chaque dmx a son DMX Out POP ; ici, une fois par seconde et à chaque changement :
# menus, vérification que ses lumières restent dans sa réservation, Active de son DMX Out, réservation auprès du script Google.

import json, os, re, threading, urllib.request

COLONNES = ['nom', 'ip', 'debut', 'fin', 'note']
CACHE = os.path.join(os.path.expanduser('~'), '.saillance_reservations.json')   # dernière liste reçue
RESERVATIONS = {}             # nom -> {nom, ip, debut, fin, note}
INSCRITS = set()              # chemins des dmx du patch
PRISES = {}                   # réservation prise par un autre patch -> nom de la personne
HORS = set()                  # dmx dont les lumières sortent de la réservation (fenêtre déjà montrée)
ETAT = {'tableau': None, 'reponse': None, 'post': False, 'postes': set(), 'menus': None, 'utilisees': {},
	'version': None, 'en_ligne': False, 'recharger': False}


def afficher(comp, texte):
	# état de la liste des réservations, gardé dans la sous-base lumieres (storage etat) ; les problèmes partent aussi sur le topic error
	comp.op('lumieres').store('etat', texte)


def signaler(comp, texte):
	# problème : envoyé sur le topic error
	comp.op('mqtt/mqtt_fonctions').module.Erreur(comp, texte, 2, 'lumieres', comp.path + '/lumieres')


# ---- réservations

def Charger(comp):
	# télécharge l'onglet reservations ; sans réponse, la dernière liste reçue (copie locale) est utilisée
	url = comp.op('presence').par.Url.eval().strip()
	if not url:
		lire_cache(comp, 'URL du tableau vide (sous-base presence)')
		return
	afficher(comp, 'Téléchargement des réservations ...')
	adresse = url + ('&' if '?' in url else '?') + 'format=reservations'

	def tache():
		try:
			with urllib.request.urlopen(adresse, timeout=20) as reponse:
				ETAT['tableau'] = json.loads(reponse.read().decode('utf-8'))
		except Exception as erreur:
			ETAT['tableau'] = {'erreur': str(erreur)}

	threading.Thread(target=tache, daemon=True).start()


def Recevoir(comp):
	# réponse du tableau, lue par la boucle d'une seconde
	reponse = ETAT['tableau']
	ETAT['tableau'] = None
	if reponse is None:
		return
	if reponse.get('erreur'):
		ETAT['en_ligne'] = False
		lire_cache(comp, 'tableau inaccessible : ' + reponse['erreur'])
		return
	ETAT['en_ligne'] = True
	ETAT['version'] = reponse.get('version')
	lignes = reponse.get('lignes', [])
	try:
		with open(CACHE, 'w', encoding='utf-8') as f:
			json.dump(lignes, f)
	except OSError:
		pass
	Appliquer(comp, lignes, '')


def lire_cache(comp, raison):
	try:
		with open(CACHE, encoding='utf-8') as f:
			lignes = json.load(f)
	except (OSError, ValueError):
		Appliquer(comp, [], raison + ', aucune liste locale')
		return
	Appliquer(comp, lignes, raison + ', dernière liste reçue utilisée, rien n\'est vérifié avec les autres patches')


def entier(valeur):
	try:
		return int(float(str(valeur).strip()))
	except ValueError:
		return None


def valider(ligne):
	# une rangée du tableau -> (réservation, problème)
	nom = str(ligne.get('nom', '')).strip()
	if not re.fullmatch(r'[A-Za-z0-9_]{1,24}', nom):
		return None, 'réservation « ' + nom + ' » : lettres, chiffres et _ seulement, 24 caractères maximum'
	ip = str(ligne.get('ip', '')).strip()
	if not re.fullmatch(r'(\d{1,3}\.){3}\d{1,3}', ip) or any(int(x) > 255 for x in ip.split('.')):
		return None, nom + ' : IP invalide (ex. 10.0.21.60)'
	debut, fin = entier(ligne.get('debut', '')), entier(ligne.get('fin', ''))
	if debut is None or fin is None or not 0 <= debut <= fin <= 32767:
		return None, nom + ' : univers invalides (de 0 à 32767, le premier avant le dernier)'
	return {'nom': nom, 'ip': ip, 'debut': debut, 'fin': fin, 'note': str(ligne.get('note', '')).strip()}, ''


def Appliquer(comp, lignes, note):
	RESERVATIONS.clear()
	problemes = []
	for ligne in lignes:
		r, probleme = valider(ligne)
		if r is None:
			problemes.append(probleme)
			continue
		# univers bloqués par IP : les mêmes univers sur une autre IP ne se chevauchent pas
		autre = next((x for x in RESERVATIONS.values() if x['ip'] == r['ip'] and r['debut'] <= x['fin'] and r['fin'] >= x['debut']), None)
		if r['nom'] in RESERVATIONS:
			problemes.append(r['nom'] + ' : nom en double, seule la première rangée est gardée')
		elif autre:
			problemes.append(r['nom'] + ' et ' + autre['nom'] + ' se chevauchent sur ' + r['ip'] + ', ' + r['nom'] + ' ignorée')
		else:
			RESERVATIONS[r['nom']] = r
	table = comp.op('lumieres/reservations')
	table.clear()
	table.appendRow(COLONNES)
	for r in sorted(RESERVATIONS.values(), key=lambda x: x['debut']):
		table.appendRow([r[c] for c in COLONNES])
	ETAT['menus'] = None
	Tic(comp)
	texte = str(len(RESERVATIONS)) + ' réservation(s)'
	if note:
		texte += ' (' + note + ')'
	if problemes:
		texte += ', ' + str(len(problemes)) + ' problème(s) : ' + ' ; '.join(problemes)
		for p in problemes:
			signaler(comp, p)
	afficher(comp, texte)


def univers_texte(r):
	return str(r['debut']) if r['debut'] == r['fin'] else str(r['debut']) + ' à ' + str(r['fin'])


# ---- dmx

def module(c):
	o = c.op('dmx_fonctions') if c is not None else None
	return o.module if o is not None else None


def lire(c, nom, defaut=None):
	p = getattr(c.par, nom, None)
	return p.eval() if p is not None else defaut


def menu(c, exclus=()):
	# réservations libres, plus celle déjà choisie par ce dmx
	p = getattr(c.par, 'Reservation', None) if c is not None else None
	if p is None:
		return
	actuelle = p.eval()
	noms = sorted((n for n in RESERVATIONS if n not in exclus or n == actuelle), key=lambda n: RESERVATIONS[n]['debut'])
	p.menuNames = noms
	p.menuLabels = [n + ' (univers ' + univers_texte(RESERVATIONS[n]) + ')' for n in noms]


def Inscrire(comp, c):
	INSCRITS.add(c.path)
	ETAT['menus'] = None
	run("args[0].op('lumieres/lumieres_fonctions').module.Tic(args[0])", comp, delayFrames=1, fromOP=comp)


def Demarrer(comp):
	# ouverture du patch : tous les dmx, à n'importe quelle profondeur, puis le tableau
	for c in op('/').findChildren(tags=['commun_dmx'], type=COMP):
		if not c.path.startswith(('/sys', '/ui', '/local')):
			INSCRITS.add(c.path)
	Charger(comp)


def Seconde(comp):
	# une fois par seconde (chaque_seconde de saillance_master)
	if ETAT['recharger']:
		ETAT['recharger'] = False
		Charger(comp)
	Recevoir(comp)
	Tic(comp)
	Poster(comp)


def infos(c, r, texte):
	# infos de la réservation choisie et état, affichés sur le dmx
	valeurs = {'Ip': r['ip'] if r else '', 'Premierunivers': r['debut'] if r else 0, 'Dernierunivers': r['fin'] if r else 0,
		'Note': r['note'] if r else '', 'Etat': texte}
	for nom, valeur in valeurs.items():
		p = getattr(c.par, nom, None)
		if p is not None and p.eval() != valeur:
			p.val = valeur


def colonne(entetes, *noms):
	for nom in noms:
		if nom in entetes:
			return entetes.index(nom)
	return -1


def univers_utilises(c):
	# univers Art-Net (et IP imposées par les lumières) écrits par ce dmx, lus dans sa table dmxmap ; None si illisible
	m = module(c)
	carte = m.Carte(c) if m is not None else c.op('dmxmap')
	if carte is None or carte.numRows < 1:
		return set(), set()
	entetes = [x.val.strip().lower() for x in carte.row(0)]
	i_u = colonne(entetes, 'universe', 'univers')
	if i_u < 0:
		return None, None
	i_net, i_sub = colonne(entetes, 'net'), colonne(entetes, 'subnet')
	i_ip = colonne(entetes, 'netaddress', 'net address', 'ip')
	univers, ips = set(), set()
	for rangee in carte.rows()[1:]:
		u = entier(rangee[i_u].val)
		if u is None:
			continue
		if u <= 15 and i_net >= 0 and i_sub >= 0:
			# Art-Net : net, subnet et univers forment le numéro d'univers (port-address)
			u = (entier(rangee[i_net].val) or 0) * 256 + (entier(rangee[i_sub].val) or 0) * 16 + u
		univers.add(u)
		if i_ip >= 0 and rangee[i_ip].val.strip() not in ('', '0.0.0.0', '255.255.255.255'):
			ips.add(rangee[i_ip].val.strip())
	return univers, ips


def fenetre(c, texte):
	run("ui.messageBox('dmx : rien ne sort', args[0], buttons=['OK'])", c.path + '\n\n' + texte, delayFrames=1)


def verifier(c, r):
	# '' si les lumières de ce dmx restent dans sa réservation, sinon ce qui bloque
	m = module(c)
	if m is None:
		return 'dmx_fonctions supprimé : reprendre un dmx neuf'
	if m.Sortie(c) is None:
		return 'Aucun DMX Out POP dans le dmx'
	if m.Carte(c) is None:
		return 'Aucun DMX Map DAT dans le dmx : les univers ne peuvent pas être vérifiés'
	univers, ips = univers_utilises(c)
	if univers is None:
		return 'Table dmxmap illisible : prévenir gabc ou gabp'
	if not univers:
		return 'Aucun canal DMX dans dmxout : branchez vos lumières au DMX Out POP'
	hors = sorted(u for u in univers if not r['debut'] <= u <= r['fin'])
	if hors:
		return ('Les lumières sortent de la réservation ' + r['nom'] + ' (univers ' + univers_texte(r) + ') : univers '
			+ ', '.join(str(u) for u in hors[:8]) + (' ...' if len(hors) > 8 else '') + '. Réduisez le nombre de lumières, ou agrandissez la réservation.')
	return ''


def Tic(comp):
	# états, Active des DMX Out et menus des dmx
	prises = ETAT['reponse']
	if prises is not None:
		ETAT['reponse'] = None
		PRISES.clear()
		PRISES.update(prises)
	utilisees = {}
	for chemin in sorted(INSCRITS):
		c = op(chemin)
		if c is None:
			INSCRITS.discard(chemin)
			HORS.discard(chemin)
			continue
		m = module(c)
		if m is not None:
			try:
				m.Automatique(c)
			except Exception as erreur:
				print('[lumieres]', chemin, ':', erreur)
		nom = lire(c, 'Reservation', '')
		r = RESERVATIONS.get(nom)
		if r is None:
			texte = 'Choisir une réservation' if not nom else 'Réservation absente du tableau : ' + nom
		elif nom in utilisees:
			texte = nom + ' est déjà prise par ' + utilisees[nom]
		else:
			# demandée au script Google même si un autre patch l'a : elle revient à ce patch quand l'autre la libère
			utilisees[nom] = chemin
			probleme = verifier(c, r)
			if PRISES.get(nom):
				texte = nom + ' est déjà prise par ' + PRISES[nom]
			elif probleme:
				texte = probleme
				if probleme.startswith('Les lumières sortent') and chemin not in HORS:
					HORS.add(chemin)
					fenetre(c, probleme)
			else:
				texte = 'OK' if ETAT['en_ligne'] else 'OK (tableau inaccessible : réservation pas vérifiée avec les autres patches)'
		if not texte.startswith('Les lumières sortent'):
			HORS.discard(chemin)
		infos(c, r, texte)
	# menus : une réservation prise (ici ou par un autre patch) n'apparaît plus dans les autres dmx
	cle = (tuple(sorted(PRISES.items())), tuple(sorted(utilisees.items())), tuple(sorted(RESERVATIONS)))
	if cle != ETAT['menus']:
		ETAT['menus'] = cle
		for chemin in INSCRITS:
			menu(op(chemin), set(PRISES) | {n for n, ch in utilisees.items() if ch != chemin})
	ETAT['utilisees'] = utilisees


# ---- réservation auprès du script Google

def Poster(comp, attendre=False):
	# réserve les réservations choisies par les dmx de ce patch ; le script renvoie celles prises par les autres
	# et la version de la liste (changée sur la page web : la liste est relue)
	url = comp.op('presence').par.Url.eval().strip()
	utilisees = {} if attendre else ETAT.get('utilisees', {})
	if not url or (ETAT['post'] and not attendre) or not (INSCRITS or ETAT['postes']):
		return
	prises = {nom: {'src': chemin} for nom, chemin in utilisees.items()}
	message = {'type': 'dmx', 'username': comp.par.Username.eval(), 'nom': comp.par.Nom.eval(), 'poste': comp.par.Poste.eval(),
		'prises': prises, 'liberer': [n for n in ETAT['postes'] if n not in prises], 'toutes': sorted(RESERVATIONS)}
	ETAT['postes'] = set(prises)
	donnees = json.dumps(message).encode('utf-8')
	moi = message['username']

	def tache():
		try:
			requete = urllib.request.Request(url, data=donnees, method='POST', headers={'Content-Type': 'text/plain;charset=utf-8'})
			with urllib.request.urlopen(requete, timeout=2 if attendre else 10) as reponse:
				r = json.loads(reponse.read().decode('utf-8'))
			ETAT['reponse'] = {n: x.get('nom') or x.get('username', '') for n, x in r.get('prises', {}).items() if x.get('username') != moi}
			ETAT['en_ligne'] = True
			if not attendre and r.get('version') and r.get('version') != ETAT['version']:
				ETAT['version'] = r.get('version')
				ETAT['recharger'] = True   # relue par la boucle d'une seconde (pas de Touch dans un fil séparé)
		except Exception:
			ETAT['en_ligne'] = False
		finally:
			ETAT['post'] = False

	ETAT['post'] = True
	if attendre:
		tache()
	else:
		threading.Thread(target=tache, daemon=True).start()


def Fermer(comp):
	# fermeture du patch : ses réservations sont libérées tout de suite
	if ETAT['postes']:
		Poster(comp, attendre=True)
