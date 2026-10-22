# dmx_fonctions
# Envoie en DMX (Art-Net) dans une réservation d'univers. Chacun branche et règle ses lumières comme il veut,
# même dans le DMX Out POP : le dmx met seulement l'IP de la réservation dans dmxout et vérifie par dmxmap
# que ses univers restent dans la réservation (État). Actif allume seulement le Active de dmxout.
# Rien n'est obligatoire : un paramètre ou un opérateur supprimé ou renommé est simplement sauté.


# ---- outils

def lire(comp, nom, defaut=None):
	# valeur d'un paramètre du dmx, ou defaut s'il a été supprimé
	p = getattr(comp.par, nom, None)
	if p is None:
		return defaut
	try:
		return p.eval()
	except Exception:
		return defaut


def fixer(o, nom, valeur):
	# règle un paramètre d'un opérateur s'il existe (menu : par nom) ; False sinon
	p = getattr(o.par, nom, None) if o is not None else None
	if p is None:
		return False
	try:
		if p.isMenu and valeur not in p.menuNames:
			return False
		if p.eval() != valeur:
			p.val = valeur
		return True
	except Exception:
		return False


def enfants(comp, nom_type):
	# opérateurs d'un type (ex. 'dmxoutPOP') directement dans le dmx, triés par nom
	import td
	t = getattr(td, nom_type, None)
	if t is None:
		return []
	return sorted(comp.findChildren(type=t, maxDepth=1), key=lambda o: o.name)


def Sortie(comp):
	o = enfants(comp, 'dmxoutPOP')
	return o[0] if o else None


def Carte(comp):
	o = enfants(comp, 'dmxmapDAT')
	return o[0] if o else None


# ---- réservation

def lumieres():
	commun = getattr(op, 'commun', None)
	if commun is None or commun.op('lumieres/lumieres_fonctions') is None:
		return None, None
	return commun, commun.op('lumieres/lumieres_fonctions').module


def Inscrire(comp):
	# les lumières de saillance_master vérifient ce dmx, remplissent son menu et réservent sa réservation
	commun, m = lumieres()
	if m is None:
		if getattr(comp.par, 'Etat', None) is not None:
			comp.par.Etat = 'saillance_master (lumieres) introuvable dans le patch : réservation pas vérifiée'
		return
	m.Inscrire(commun, comp)


def Changer(comp):
	Inscrire(comp)


def Recharger(comp):
	commun, m = lumieres()
	if m is not None:
		m.Charger(commun)


# ---- mise à jour : réglages officiels de dmxout et dmxmap

SYSTEME = ('dmxout', 'dmxmap')


def reglage(p):
	if p.mode == ParMode.EXPRESSION:
		return ('expr', p.expr)
	if p.mode == ParMode.BIND:
		return ('bind', p.bindExpr)
	return ('val', p.val)


def Officiel(comp):
	# réglages de dmxout et dmxmap tels que livrés : la mise à jour compare ceux de deux versions
	photo = {}
	for nom in SYSTEME:
		o = comp.op(nom)
		if o is not None:
			photo[nom] = {p.name: reglage(p) for p in o.pars() if not p.isCustom and not p.isPulse and not p.readOnly}
	comp.store('officiel', photo)
	return photo


# ---- IP, automatique (une fois par seconde, par les lumières de saillance_master)

def Automatique(comp):
	# IP de la réservation dans le DMX Out ; le reste est réglé par chacun
	ip = lire(comp, 'Ip', '')
	if ip:
		fixer(Sortie(comp), 'netaddress', ip)

