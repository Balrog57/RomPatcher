# RomPatcher Desktop

Patcher Windows autonome pour appliquer, creer, analyser et convertir des patchs de ROMs et de binaires.

## Fonctionnalites

- Interface graphique locale avec onglets `Appliquer`, `Creer` et `Outils`
- Layout adaptatif avec partie haute fixe
- Seuls `Analyse et details` et `Journal` restent scrollables
- Glisser-deposer de fichiers sur les champs Windows
- Analyse rapide du patch charge avec format, validations et metadonnees
- Creation et application de patchs sans hebergement
- Verification de mises a jour depuis les releases GitHub
- Mise a jour automatique alignee avec l'installateur Windows
- Proposition d'installation automatique de `xdelta3.exe` pour les patchs `.xdelta` / `VCDiff`
- Outil N64 pour convertir le byte order (`z64`, `v64`, `n64`)
- CLI pour inspecter, appliquer, creer et convertir

## Formats supportes

Application :

- `IPS`
- `EBP`
- `UPS`
- `BPS`
- `PPF`
- `APS (GBA)`
- `APS (N64)`
- `RUP`
- `BSDiff` via `bsdiff4` optionnel
- `VCDiff / xdelta` via `xdelta3` optionnel

Creation :

- `IPS`
- `EBP`
- `UPS`
- `BPS`
- `PPF`
- `APS (GBA)`
- `APS (N64)`
- `RUP`

## Lancement local

### Interface graphique

```powershell
python app.py
```

### CLI

```powershell
python -m pip install -e .
rompatcher --version
rompatcher inspect "mon_patch.bps"
rompatcher apply "jeu.smc" "traduction.bps"
rompatcher create "jeu_original.gba" "jeu_modifie.gba" --format bps --description "Version traduite"
rompatcher n64-byteswap "jeu.v64" --target z64
```

## Distribution Windows

Les releases officielles publient maintenant un installateur Windows Inno Setup :

- fichier de release : `RomPatcher-Setup-vX.Y.Z-win64.exe`
- installation dans `%LOCALAPPDATA%\Programs\RomPatcher Desktop`
- icone integree a l'application et a l'installateur
- dossier du menu Demarrer configurable pendant l'installation
- option de raccourci bureau via case a cocher
- lancement de l'application propose en fin d'installation

L'installateur est concu pour un usage simple sans hebergement externe : tout passe par les releases GitHub publiques.

## Workflow GitHub Actions

Le workflow `.github/workflows/build-release.yml` :

- valide la compilation des sources
- verifie la coherence entre le tag Git et la version Python
- construit `RomPatcher.exe` avec PyInstaller
- compile l'installateur Inno Setup
- publie l'artefact et la release GitHub

Le build se lance :

- sur un tag `vX.Y.Z`
- ou manuellement via `workflow_dispatch`

## Release officielle

```powershell
python .\scripts\bump_version.py 1.1.1
git add .
git commit -m "Release 1.1.1"
git tag v1.1.1
git push origin main
git push origin v1.1.1
```

## Mise a jour automatique

Depuis l'application installee :

- RomPatcher verifie la derniere release GitHub
- telecharge l'installateur correspondant
- ferme l'application
- lance l'installateur en mode silencieux
- relance RomPatcher une fois la mise a jour terminee

Ce mecanisme reste compatible avec les anciennes releases portables, mais les nouvelles releases officielles sont basees sur l'installateur Inno Setup.

## Dependances optionnelles

### BSDiff

```powershell
python -m pip install bsdiff4
```

### xdelta / VCDiff

RomPatcher peut proposer le telechargement automatique de `xdelta3.exe` quand un patch `VCDiff / xdelta` en a besoin.

En manuel, vous pouvez aussi placer `xdelta3.exe` :

- dans le `PATH` de Windows
- a cote de `RomPatcher.exe`
- dans un dossier `tools/` voisin de l'application
