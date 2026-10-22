# saillance-touchdesigner

Le gabarit TouchDesigner de Saillance et ses composantes communes : `saillance_master`, `send_mqtt`, `receive`, `dmx` et `fichiers_manquants`.

## Télécharger

Les fichiers à utiliser (.tox et gabarit .toe) sont dans la **dernière release** : https://github.com/UQAM-CeXii/saillance-touchdesigner/releases/latest

Dans un patch, le bouton **Mettre à jour** de `saillance_master` (page Commun) installe la dernière release tout seul.

## Contenu du repository

| Dossier | Contenu |
|---|---|
| `touchdesigner/` | Le texte de chaque script (DAT) des composantes, un fichier par opérateur, rangé comme dans le patch. Ex. : `touchdesigner/saillance_master/mqtt/mqtt_fonctions.py` est le DAT `saillance_master/mqtt/mqtt_fonctions`. |
| `google_apps_script/` | Le script Google des réservations DMX (`Code.gs`) et ses pages web |

Les .tox et .toe ne sont jamais dans le repository, seulement dans les releases.

## Publier une release

1. Copiez le texte des DAT modifiés dans leurs fichiers de `touchdesigner/`, puis faites un commit et un push.
1. Mettez la nouvelle version dans **Version commune** de `saillance_master`.
1. Exportez les 5 .tox (`commun_<nom>_vX.Y.Z.tox`) et sauvegardez le gabarit (.toe).
1. **Releases** > **Draft a new release** : tag = la même version (ex. `v0.4.0`), titre = la version, description = ce qui a changé.
1. Joignez les 5 .tox et le .toe, puis **Publish release**.

Le tag doit être exactement la **Version commune** de `saillance_master`, sinon la mise à jour ne se termine pas.

## Documentation

Le wiki Confluence SAILLANCE 2026 : TD Gabarit, TD saillance_master, TD MQTT, TD DMX.
