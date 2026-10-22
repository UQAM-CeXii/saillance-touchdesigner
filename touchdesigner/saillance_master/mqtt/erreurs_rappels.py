# erreurs_rappels
# Chaque erreur ou avertissement de Touch est envoyé sur saillance/sys/<username>/error.

def onError(dat, rowIndex, message, absFrame, frame, severity, type, source, *args):
	op('mqtt_fonctions').module.Erreur(parent(2), message, severity, type, source)
