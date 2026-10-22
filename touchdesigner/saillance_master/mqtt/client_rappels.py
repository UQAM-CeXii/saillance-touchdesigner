# client_rappels
# Rappels du MQTT Client DAT.

def m():
	return op('mqtt_fonctions').module

def commun():
	return parent(2)

def onConnect(dat, *args):
	m().Connecte(commun())

def onConnectFailure(dat, msg='', *args):
	m().Echec(commun(), msg)

def onConnectionLost(dat, msg='', *args):
	m().Perdu(commun(), msg)

def onDisconnect(dat, *args):
	m().Perdu(commun(), '')

def onMessage(dat, topic, payload, qos=0, retained=False, *args):
	m().Recevoir(commun(), topic, payload, bool(retained))

def onPublish(dat, *args):
	return

def onSubscribe(dat, *args):
	return

def onSubscribeFailure(dat, msg='', *args):
	print('[mqtt] abonnement refusé :', msg)

def onUnsubscribe(dat, *args):
	return

def onUnsubscribeFailure(dat, *args):
	return
