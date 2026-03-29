# RomPatcher Desktop

Patcher Windows autonome pour appliquer, creer, analyser et convertir des patchs de ROMs et de binaires.

## Fonctionnalites

- Interface graphique locale avec onglets `Appliquer`, `Creer` et `Outils`.
- Layout adaptatif : la zone haute reste fixe, seuls `Analyse et details` et `Journal` sont scrollables.
- Glisser-deposer de fichiers sur les champs Windows.
- Analyse rapide du patch charge avec affichage du format, des validations et des metadonnees.
- Creation et application de patchs sans hebergement.
- Verification de mises a jour et auto-update depuis les releases GitHub.
- Outil N64 pour convertir le byte order (`z64`, `v64`, `n64`).
- CLI pour inspecter, appliquer, creer et convertir.

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

## Releases officielles

Les binaires Windows officiels sont produits a distance depuis GitHub et publies dans les releases.

- Aucun `.exe` n'est conserve dans le depot.
- Les repertoires `build/`, `dist/` et le fichier `RomPatcher.spec` sont des artefacts locaux ignores.
- Les releases publient un seul fichier Windows : `RomPatcher-vX.Y.Z-win64.exe`.
- Le bouton `Mise a jour` de l'application packagée telecharge les nouvelles versions depuis les releases publiques.
- Le depot a ete allege pour la distribution : pas de suite de tests embarquee, pas de script de build local conserve.

## Workflow de release

La release officielle se fait a partir d'un tag Git :

```powershell
python .\scripts\bump_version.py 1.0.0
git add .
git commit -m "Release 1.0.0"
git tag v1.0.0
git push origin main
git push origin v1.0.0
```

Le workflow GitHub dans `.github/workflows/build-release.yml` :

- valide la compilation des sources,
- verifie la coherence entre le tag et la version Python,
- construit l'executable Windows,
- publie l'artefact et la release GitHub.

## Mise a jour automatique

- verification de la derniere release GitHub depuis l'application packagée,
- telechargement du nouvel `.exe`,
- remplacement automatique du binaire,
- redemarrage de l'application.

Ce mecanisme repose uniquement sur les releases GitHub publiques.

## Dependances optionnelles

### BSDiff

```powershell
python -m pip install bsdiff4
```

### xdelta / VCDiff

Placez `xdelta3.exe` dans le `PATH` de Windows, ou dans un dossier `tools/` a la racine du projet.
