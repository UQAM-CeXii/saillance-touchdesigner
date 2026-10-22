# boucle
# Ouverture et fermeture du patch.

def presence():
	return op('presence/presence_fonctions').module

def lumieres():
	return op('lumieres/lumieres_fonctions').module

def demarrer():
	project.cookRate = 60
	presence().Demarrer(parent())
	run("args[0].op('mqtt/mqtt_fonctions').module.VerifierDoubles(args[0])", parent(), delayFrames=120)
	# réservations DMX et dmx du patch
	run("args[0].op('lumieres/lumieres_fonctions').module.Demarrer(args[0])", parent(), delayFrames=10)
	# version officielle (dernière release GitHub)
	run("args[0].op('mise_a_jour/maj_fonctions').module.Verifier(args[0])", parent(), delayFrames=60)

def onStart():
	demarrer()

def onCreate():
	demarrer()

def onExit():
	lumieres().Fermer(parent())
	presence().Fermer(parent())
