# parametres
# Réglages de la sous-base presence : allumer ou éteindre la présence, partie et tâche.

def onValueChange(par, prev):
	f = op('presence_fonctions').module
	if par.name == 'Actif':
		f.ActiverPresence(parent(2))
	else:
		f.MiseAJour(parent(2))
