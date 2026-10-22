# demarrage
# Ouverture du patch ou dmx ajouté : réservation vérifiée.

def demarrer():
	run("args[0].op('dmx_fonctions').module.Changer(args[0]) if args[0].op('dmx_fonctions') is not None else None", parent(), delayFrames=5)

def onStart():
	demarrer()

def onCreate():
	demarrer()
