# demarrage
# Ouverture du patch ou send ajouté : même mode que saillance_master, et le topic réglé est créé.

def synchroniser():
	run("args[0].op('send_fonctions').module.Synchroniser(args[0])", parent(), delayFrames=5)

def onStart():
	synchroniser()

def onCreate():
	synchroniser()
