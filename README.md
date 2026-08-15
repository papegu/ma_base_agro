# Base multimodale agroécologique pour l’Afrique de l’Ouest et le Sénégal

Ce projet met en place une base de données multimodale pour l’agroécologie en Afrique de l’Ouest et plus particulièrement au Sénégal, en intégrant :

- Données temporelles
- Données spatiales
- Données climatiques
- Données pédologiques
- Données agricoles
- Données de télédétection (Sentinel, Landsat, MODIS)
- Fichiers tabulaires et géospatiaux
- Préparation d’indices spectraux

## Structure du dossier

- [config/project_config.py](config/project_config.py): paramètres globaux, limites géographiques, indices spectraux, ID projet Earth Engine
- [scripts/create_multimodal_database.py](scripts/create_multimodal_database.py): création de la base SQLite
- [scripts/download_gee_data.py](scripts/download_gee_data.py): téléchargement ciblé depuis Google Earth Engine
- [scripts/download_cloud_data.py](scripts/download_cloud_data.py): téléchargement des données publiques depuis des plateformes cloud
- [scripts/spectral_indices.py](scripts/spectral_indices.py): calcul des indices spectrales
- [scripts/gee_scan_and_assets.py](scripts/gee_scan_and_assets.py): scan du dossier local et reconnaissance des collections GEE
- [requirements.txt](requirements.txt): dépendances Python

## Données actuelles déjà disponibles dans le dossier

- [pluvio_statio-2023-2014.csv](pluvio_statio-2023-2014.csv): pluviométrie
- [temp_statio-2023-2014.csv](temp_statio-2023-2014.csv): température
- Archive [production-agricole-2003-2012.zip](production-agricole-2003-2012.zip): production agricole
- Archive [point_eau_pastoraux.zip](point_eau_pastoraux.zip): points d’eau pastoraux
- Archive [unites_pastorales-2.zip](unites_pastorales-2.zip): unités pastorales
- Archive [infra_socio_economique.zip](infra_socio_economique.zip): infrastructures socio-économiques

## Limites géographiques

- Sénégal: lon -17.6 to -11.3, lat 12.0 to 17.3
- Afrique de l’Ouest: lon -20 to 20, lat -5 to 30

## ID projet Google Earth Engine

- project37246

## Collections GEE utilisées

- COPERNICUS/S2_SR_HARMONIZED
- LANDSAT/LC08/C02/T1_L2
- MODIS/061/MOD13A2
- UCSB-CHG/CHIRPS/PENTAD
- ECMWF/ERA5_LAND/HOURLY
- OpenLandMap/soil
- USGS/SRTMGL1_003

## Indices spectraux inclus

- NDVI
- NDWI
- EVI
- SAVI
- NDBI
- MNDWI

## Dépendances

```bash
pip install -r requirements.txt
```

## Authentification GEE

```bash
earthengine authenticate --project project37246
```

## Exécution

### 1. Créer la base SQLite

```bash
python scripts\create_multimodal_database.py
```

### 2. Télécharger les données Sentinel / GEE

```bash
python scripts\download_gee_data.py
```

### 3. Télécharger les données cloud publiques

```bash
python scripts\download_cloud_data.py
```

### 4. Calculer les indices spectraux

```bash
python scripts\spectral_indices.py
```

### 5. Scanner le dossier et explorer les collections GEE

```bash
python scripts\gee_scan_and_assets.py
```

## Remarque

Les exportations Earth Engine sont lancées vers Google Drive avec le dossier `senegal_gee` pour validation avant envoi vers une asset ou un stockage local.
