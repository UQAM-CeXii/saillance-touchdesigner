# saillance-touchdesigner

Le gabarit TouchDesigner de Saillance et ses composantes communes : `saillance_master`, `send_mqtt`, `receive`, `dmx` et `fichiers_manquants`.

Page de réservation d'univers DMX : https://script.google.com/macros/s/AKfycbyZFmDfJqlqXfAgfx2R_CQ3TkY4DwTO1oeTaT_bfuuLD6i-opOG5i3yLJ7P_8v5zivNeg/exec?page=lumieres

## Télécharger

Les fichiers à utiliser (.tox et gabarit .toe) sont dans la **dernière release** : https://github.com/gab-carpentier/saillance-touchdesigner/releases/latest

Dans un patch, le bouton **Mettre à jour** de `saillance_master` (page Commun) installe la dernière release tout seul.

## Contenu du repository

| Dossier | Contenu |
|---|---|
| `touchdesigner/` | Le texte de chaque script (DAT) des composantes, un fichier par opérateur, rangé comme dans le patch. Ex. : `touchdesigner/saillance_master/mqtt/mqtt_fonctions.py` est le DAT `saillance_master/mqtt/mqtt_fonctions`. |
| `google_apps_script/` | Le script Google des réservations DMX (`Code.gs`) et ses pages web |

Les .tox et .toe ne sont jamais dans le repository, seulement dans les releases.

## Documentation

Le wiki Confluence SAILLANCE 2026 : TD Gabarit, TD saillance_master, TD MQTT, TD DMX. https://wikienseignement-uqam.atlassian.net/wiki/spaces/MI/pages/247627860
