# parametres
# Actif : tous les send et receive suivent. Créer le topic : ce send peut envoyer sur son nouveau topic.
# Autres réglages : entrée, menus et topic refaits.

def onValueChange(par, prev):
	if par.name == 'Actif':
		op('send_fonctions').module.ChangerActif(parent())
	else:
		op('send_fonctions').module.Actualiser(parent())

def onPulse(par):
	if par.name == 'Creer':
		op('send_fonctions').module.Creer(parent())
