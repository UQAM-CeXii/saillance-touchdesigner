# parametres
# Actif : tous les send et receive suivent. Autres choix : nouveaux menus et nouveau topic.

def onValueChange(par, prev):
	f = op('receive_fonctions').module
	if par.name == 'Actif':
		f.ChangerActif(parent())
	else:
		f.Actualiser(parent())

def onPulse(par):
	if par.name == 'Recharger':
		op('receive_fonctions').module.Recharger(parent())
