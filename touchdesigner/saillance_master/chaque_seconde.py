# chaque_seconde
# Une fois par seconde, quand le LFO seconde passe à 1 : tout ce qui doit être vérifié régulièrement.

def onOffToOn(channel, sampleIndex, val, prev):
	commun = parent()
	if project.cookRate != 60:
		project.cookRate = 60
	op('presence/presence_fonctions').module.Battement(commun)
	op('mqtt/mqtt_fonctions').module.Seconde(commun)
	op('mise_a_jour/maj_fonctions').module.Suivre(commun)
	op('lumieres/lumieres_fonctions').module.Seconde(commun)
