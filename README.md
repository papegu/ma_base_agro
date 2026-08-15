# Base multimodale agroécologique pour l’Afrique de l’Ouest et le Sénégal

Ce dépôt construit une base SQLite multimodale, temporelle et géospatiale à partir des fichiers réellement présents dans le dépôt : CSV, Excel, archives ZIP, shapefiles éventuels contenus dans les ZIP, GeoPackage et GeoTIFF/TIFF si disponibles.

## État réel du dépôt

Les données actuellement présentes à la racine incluent notamment :

- `pluvio_statio-2023-2014.csv`
- `temp_statio-2023-2014.csv`
- `temporal_fold_year_ranges.csv`
- `production-agricole-2003-2012.zip`
- `point_eau_pastoraux.zip`
- `unites_pastorales-2.zip`
- `infra_socio_economique.zip`

Le pipeline de ce dépôt scanne automatiquement un dossier configurable, détecte les formats pris en charge, extrait les archives ZIP, nettoie les colonnes et alimente une base SQLite unique.

## Scripts disponibles

- `scripts/create_multimodal_database.py` : script principal de scan, nettoyage et ingestion SQLite
- `scripts/ingestion_pipeline.py` : logique du pipeline
- `scripts/inspect_multimodal_database.py` : inspection des tables et des nombres de lignes
- `check_db_counts.py` : alias simple vers le script d’inspection
- `multimodal_db_gui.py` : interface d’exploration de la base si une base SQLite existe déjà

## Dépendances

Installation recommandée :

```bash
pip install -r requirements.txt
```

Remarques :

- `pandas` et `openpyxl` sont utilisés pour les fichiers tabulaires.
- `geopandas`, `fiona`, `shapely`, `pyproj` et `rasterio` améliorent l’ingestion géospatiale.
- Si les dépendances géospatiales lourdes ne sont pas installées, le pipeline continue de fonctionner en mode dégradé : les couches vectorielles et rasters sont inventoriés et catalogués avec warnings, sans ingestion complète des géométries.

## Construire la base SQLite

Depuis la racine du dépôt :

```bash
python scripts/create_multimodal_database.py
```

Par défaut :

- si un dossier `upload/` existe, il sera scanné ;
- sinon, c’est la racine actuelle du dépôt qui sera utilisée.

Exemple avec chemins explicites :

```bash
python scripts/create_multimodal_database.py \
  --source-dir /chemin/vers/les/donnees \
  --db-path /chemin/vers/data/multimodal_base.sqlite \
  --report-path /chemin/vers/reports/latest_ingestion_report.json
```

## Sorties générées

Le pipeline crée par défaut :

- `data/multimodal_base.sqlite` : base SQLite consolidée
- `reports/latest_ingestion_report.json` : rapport de scan/nettoyage/ingestion
- `data/workspace/` : espace de travail pour les extractions ZIP

## Schéma SQLite créé

Le pipeline crée au minimum les tables de catalogue suivantes :

- `data_sources`
- `ingestion_runs`
- `table_catalog`
- `column_catalog`
- `geospatial_layers`
- `raster_catalog`

Il crée aussi automatiquement une table nettoyée pour chaque source tabulaire pertinente, et une version `*_long` quand une table large contient principalement des colonnes annuelles (`2003`, `2004`, etc.).

## Nettoyage et normalisation effectués

Le pipeline :

- détecte automatiquement les délimiteurs CSV (`;`, `,`, tabulation, etc.) ;
- gère les encodages usuels (`utf-8-sig`, `utf-8`, `cp1252`, `latin-1`) ;
- normalise les noms de colonnes en `snake_case` ASCII ;
- tente de convertir les colonnes numériques et temporelles ;
- identifie des rôles de colonnes (temporelles, spatiales, administratives, mesures) ;
- extrait les ZIP dans un espace de travail dédié ;
- catalogue les rasters et couches géospatiales ;
- stocke les géométries vectorielles en `WKT` quand les dépendances géospatiales sont disponibles.

## Vérifier la base générée

```bash
python scripts/inspect_multimodal_database.py
```

ou :

```bash
python check_db_counts.py
```

## Limites actuelles

- Les shapefiles et GeoPackage sont pleinement ingérés seulement si les dépendances géospatiales optionnelles sont installées.
- Les rasters sont catalogués avec leurs métadonnées ; le pipeline ne charge pas les pixels en table SQLite.
- Les CSV très irréguliers peuvent nécessiter un contrôle manuel du rapport JSON.
- Le dépôt ne contient actuellement ni dossier `upload/` ni anciens scripts `config/` / `download_*` / `gee_*` mentionnés dans les versions précédentes du README.
