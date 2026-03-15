# Guide En-Croissant

## Version connue
- Version : [à remplir par l'utilisateur]
- Stockfish : version 18
- Dernière vérification : 2026-03-15

---

## Ouvrir un fichier PGN

### Étapes
1. Lancer En-Croissant [À CONFIRMER]
2. Menu File → Open / Import PGN (ou icône dossier) [À CONFIRMER]
3. Naviguer vers `~/home-evo/chess/` [À CONFIRMER]
4. Sélectionner le fichier `.pgn` [À CONFIRMER]
5. Les `[Event "..."]` apparaissent comme chapitres séparés [CONFIRMÉ - 2026-03-15 : l'utilisateur a ouvert le premier fichier avec succès]

### Alternative
- Glisser-déposer le fichier `.pgn` dans la fenêtre d'En-Croissant [À CONFIRMER]

### Notes
- En-Croissant modifie le fichier ouvert en continu (ajout de headers, evals)
- FERMER le fichier avant de demander à Claude de le modifier

### Historique
- 2026-03-15 : description initiale créée
- 2026-03-15 : confirmé que l'ouverture de PGN fonctionne et que les chapitres apparaissent

---

## Activer et utiliser Stockfish

### Étapes
1. Stockfish 18 doit être déjà configuré (fait) [CONFIRMÉ - 2026-03-15]
2. Panneau moteur visible en bas ou sur le côté de l'écran [À CONFIRMER]
3. L'évaluation s'affiche en temps réel quand on navigue les coups [À CONFIRMER]
4. Les annotations `[%eval +0.32]` sont ajoutées au PGN automatiquement [CONFIRMÉ - 2026-03-15 : vu dans le fichier QGD modifié]

### Ce qu'on cherche
- Évaluation proche de 0.0 = position égale (normal pour les lignes théoriques)
- Chute brutale (ex: +0.3 → -1.5) = blunder dans notre ligne → à corriger
- Léger avantage Blanc (+0.2 à +0.4) = normal dans le Gambit Dame

### Notes
- L'utilisateur veut utiliser SF18 local car plus puissant et temps illimité (vs SF16 de Lichess)

### Historique
- 2026-03-15 : description initiale créée

---

## Naviguer les variantes

### Étapes
1. Flèches gauche/droite pour avancer/reculer dans les coups [À CONFIRMER]
2. Cliquer sur une variante entre parenthèses pour entrer dedans [À CONFIRMER]
3. Les chapitres (Event) sont listés quelque part dans l'interface [À CONFIRMER — où exactement ?]

### Historique
- 2026-03-15 : description initiale créée

---

## Ajouter des lignes

### Étapes
1. Naviguer jusqu'à la position souhaitée [À CONFIRMER]
2. Jouer un coup alternatif sur l'échiquier [À CONFIRMER]
3. Le coup s'ajoute comme variante [À CONFIRMER]
4. Possibilité d'ajouter des commentaires [À CONFIRMER — comment ?]

### Historique
- 2026-03-15 : description initiale créée

---

## Exporter un PGN modifié

### Étapes
1. File → Save / Export PGN [À CONFIRMER]
2. Le fichier est sauvegardé automatiquement (écrasement) [À CONFIRMER — ou faut-il sauvegarder manuellement ?]

### Notes
- En-Croissant semble sauvegarder en continu (constaté : le fichier est modifié pendant qu'il est ouvert)

### Historique
- 2026-03-15 : description initiale créée
