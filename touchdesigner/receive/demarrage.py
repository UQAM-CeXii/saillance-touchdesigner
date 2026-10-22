# demarrage
# Ouverture du patch ou receive ajouté : même mode que saillance_master, puis s'inscrit auprès d'elle.

def actualiser():
	run("args[0].op('receive_fonctions').module.Synchroniser(args[0]); args[0].op('receive_fonctions').module.Actualiser(args[0])", parent(), delayFrames=5)

def onStart():
	actualiser()

def onCreate():
	actualiser()
