# RomPatcher Desktop

Application locale de patch de ROMs et de binaires, écrite en Python, pensée pour être utilisée directement sur Windows sans serveur ni hébergement.

## Ce que fait déjà le logiciel

- Interface graphique locale avec sélection de ROM, patch et sortie.
- Interface en onglets pour appliquer un patch, créer un patch, et convertir les ROMs N64.
- Glisser-déposer des fichiers directement sur les champs Windows.
- Icône Windows dédiée pour l'application et le binaire packagé.
- Version applicative centralisée et affichée dans l'interface et la CLI.
- Ligne de commande pour inspection, création, application et conversion N64.
- Vérification des mises à jour GitHub depuis l'application packagée.
- Téléchargement et remplacement automatique de l'exécutable Windows depuis les releases GitHub.
- Détection automatique du format par signature binaire.
- Support natif des formats :
  - `IPS`
  - `EBP`
  - `UPS`
  - `BPS`
  - `PPF`
  - `APS (GBA)`
  - `APS (N64)`
  - `RUP`
- Support optionnel :
  - `BSDiff` via `bsdiff4`
  - `VCDiff / xdelta` via `xdelta3.exe` ou `xdelta3` dans le `PATH`
- Retrait automatique de l'en-tête SNES copier de 512 octets avec sortie en `.sfc`.
- Outil utilitaire pour convertir le byte order des ROMs Nintendo 64 (`z64`, `v64`, `n64`).
- Création native de patchs :
  - `IPS`
  - `EBP`
  - `UPS`
  - `BPS`
  - `PPF`
  - `APS (GBA)`
  - `APS (N64)`
  - `RUP`

## Lancement rapide sous Windows

### Sans installation

```powershell
python app.py
```

### En ligne de commande

```powershell
python -m pip install -e .
rompatcher --version
rompatcher inspect "mon_patch.bps"
rompatcher apply "jeu.smc" "traduction.bps"
rompatcher create "jeu_original.gba" "jeu_modifie.gba" --format bps --description "Version traduite"
rompatcher create "jeu_original.z64" "jeu_modifie.z64" --format aps-n64
rompatcher create "jeu_original.bin" "jeu_modifie.bin" --format rup --title "Mon patch"
rompatcher n64-byteswap "jeu.v64" --target z64
```

### Exemple EBP avec métadonnées

```powershell
rompatcher create "earthbound.sfc" "earthbound_mod.sfc" --format ebp --title "Mon Hack" --author "Marc" --description "Traduction FR"
```

## Construire un `.exe` Windows

1. Installer PyInstaller :

```powershell
python -m pip install pyinstaller
```

2. Construire l'application :

```powershell
.\build_windows.ps1
```

Le binaire sera généré dans `dist/RomPatcher.exe`.

## Workflow GitHub et releases

Le dépôt contient maintenant un workflow GitHub Actions dans `.github/workflows/build-release.yml`.

- Chaque `push` sur `main` compile l'exécutable Windows et publie un artefact téléchargeable dans GitHub Actions.
- Chaque tag `vX.Y.Z` compile l'exécutable, crée une release GitHub et y attache :
  - `RomPatcher-vX.Y.Z-win64.exe`
  - `RomPatcher-vX.Y.Z-win64.exe.sha256`

### Préparer une nouvelle version

1. Mettre à jour la version :

```powershell
python .\scripts\bump_version.py 0.2.0
```

2. Committer les changements puis créer le tag :

```powershell
git add .
git commit -m "Release 0.2.0"
git tag v0.2.0
git push origin main --tags
```

Le workflow GitHub construira automatiquement le nouvel `.exe` et publiera la release.

## Mise à jour automatique

- Dans l'exécutable Windows packagé, le bouton `Mise à jour` vérifie la dernière release GitHub.
- Au démarrage du `.exe`, l'application peut aussi vérifier automatiquement s'il existe une version plus récente.
- Si une nouvelle version est disponible, l'application télécharge le dernier `.exe`, ferme l'ancienne version, remplace le binaire et relance automatiquement RomPatcher.

Ce mécanisme repose uniquement sur les releases GitHub publiques, sans serveur dédié.

## Dépendances optionnelles

### BSDiff

```powershell
python -m pip install bsdiff4
```

### xdelta / VCDiff

Placez `xdelta3.exe` dans le `PATH` de Windows, ou dans un dossier `tools/` à la racine du projet.

## Limitations actuelles

- Le coeur natif couvre déjà la majorité des formats historiques de patch ROM.
- `BSDiff` et `xdelta` nécessitent encore une dépendance externe optionnelle.
- La création est actuellement disponible pour `IPS`, `EBP`, `UPS`, `BPS` et `PPF`.
- La création est maintenant aussi disponible pour `APS (GBA)`, `APS (N64)` et `RUP`.
- `BSDiff` et `xdelta` restent orientés application de patch, pas création.
