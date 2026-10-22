# parametres
# Réservation : vérifiée tout de suite. Recharger : relit les réservations.

def f():
	o = op('dmx_fonctions')
	return o.module if o is not None else None

def onValueChange(par, prev):
	m = f()
	if m is not None and par.name == 'Reservation':
		m.Changer(parent())

def onPulse(par):
	m = f()
	if m is not None and par.name == 'Recharger':
		m.Recharger(parent())
