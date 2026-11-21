# Évaluation de la transcription vocale

## Préparer 20 à 30 commandes

1. Obtenir l’accord des personnes enregistrées et utiliser des commandes de démonstration sans données personnelles ni information industrielle confidentielle.
2. Enregistrer 20 à 30 courtes commandes en français dans `webm`, `ogg`, `wav`, `mp3`, `mp4` ou `m4a`. Inclure plusieurs exemples avec identifiants comme `POMPE-002`, `AL-000004` et `OT`, ainsi que quelques nombres et termes métier. Garder un seul locuteur par fichier et un niveau sonore comparable.
3. Nommer les fichiers de façon stable (`cmd-001.wav`, etc.) et créer `references.csv` en UTF-8 avec l’en-tête `filename,reference`. La colonne `reference` contient exactement ce qui a été prononcé, relu manuellement.
4. Démarrer le backend, obtenir un JWT utilisateur existant, puis fournir le token via `VOICE_ACCESS_TOKEN` (ne pas le mettre dans la commande ou le CSV).

```powershell
$env:VOICE_ACCESS_TOKEN = '<JWT>'
python scripts/eval_transcription.py .\audio-eval .\references.csv
```

Le script envoie chaque fichier à `/api/voice/transcribe/`, puis affiche le WER global (distance d’édition des mots divisée par le nombre de mots de référence), la médiane et le P95 des latences, ainsi que la proportion des identifiants attendus correctement reconnus. Les identifiants sont extraits des références selon `POMPE-n`, `AL-n` et `OT`. Les erreurs sont comptées sans afficher le token ni le texte transcrit.

Cette évaluation utilise l’endpoint Groq configuré par l’application et entraîne des coûts fournisseur. Le texte n’est pas enregistré par l’endpoint de transcription. Conserver les enregistrements localement dans un dossier privé, les supprimer après l’évaluation et ne pas les ajouter au dépôt Git.
