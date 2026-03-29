# RomPatcher Desktop

Application locale de patch de ROMs et de binaires, écrite en Python, pensée pour être utilisée directement sur Windows sans serveur ni hébergement.

## Ce que fait déjà le logiciel

- Interface graphique locale avec sélection de ROM, patch et sortie.
- Interface en onglets pour appliquer un patch, créer un patch, et convertir les ROMs N64.
- Glisser-déposer des fichiers directement sur les champs Windows.
- Icône Windows dédiée pour l'application et le binaire packagé.
- Ligne de commande pour inspection, création, application et conversion N64.
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
