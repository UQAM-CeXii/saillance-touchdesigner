# fichiers_fonctions
# Liste les médias, .tox et autres fichiers du patch qui sont introuvables sur cet ordinateur.
# Composante commune : ne rien modifier sans l'annoncer.

import os


def Verifier(comp):
	table = comp.op('manquants')
	table.clear()
	table.appendRow(['operateur', 'parametre', 'fichier'])
	for o in op('/').findChildren(includeUtility=True):
		if o.path.startswith(('/sys', '/ui', '/local', comp.path + '/')):
			continue
		for p in o.pars():
			if p.style not in ('File', 'Folder') or p.name == 'externaltox':
				continue
			try:
				valeur = str(p.eval()).strip()
			except Exception:
				continue
			if not valeur or valeur.startswith(('http://', 'https://', 'rtsp://')):
				continue
			chemin = os.path.normpath(valeur if os.path.isabs(valeur) else os.path.join(project.folder, valeur))
			existe = os.path.isdir(chemin) if p.style == 'Folder' else os.path.isfile(chemin)
			if not existe:
				table.appendRow([o.path, p.name, valeur])
	n = table.numRows - 1
	comp.par.Fichiers = 'Aucun fichier manquant' if n == 0 else (
		str(n) + ' fichier(s) manquant(s) : voir la table manquants (viewer)')
	for r in range(1, table.numRows):
		print('[fichiers] introuvable :', table[r, 0].val, table[r, 1].val, table[r, 2].val)
