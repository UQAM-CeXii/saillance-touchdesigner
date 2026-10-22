# parametres
# Réagit aux paramètres personnalisés de saillance_master.

def presence():
	return op('presence/presence_fonctions').module

def mqtt():
	return op('mqtt/mqtt_fonctions').module

def lumieres():
	return op('lumieres/lumieres_fonctions').module

def onValueChange(par, prev):
	if par.name == 'Actif':
		mqtt().ChangerMode(parent())

def onPulse(par):
	if par.name == 'Reconnecter':
		mqtt().Connecter(parent())
	elif par.name == 'Changeridentite':
		presence().ChangerIdentite(parent())
	elif par.name == 'Miseajour':
		op('mise_a_jour/maj_fonctions').module.MettreAJour(parent())
