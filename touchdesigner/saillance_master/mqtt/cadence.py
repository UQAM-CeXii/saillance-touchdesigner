# cadence
# À chaque image, en mode activé seulement : la composante commune appelle les send à la fréquence d'envoi commune.

def onFrameStart(frame):
	op('mqtt_fonctions').module.Cadence(parent(2))
