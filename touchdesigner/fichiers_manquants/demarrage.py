# demarrage
# Vérification à l'ouverture, une fois le patch chargé.

def onStart():
	run("args[0].op('fichiers_fonctions').module.Verifier(args[0])", parent(), delayFrames=120)

def onCreate():
	onStart()
