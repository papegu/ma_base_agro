CREATE SCHEMA IF NOT EXISTS agroeco;

SET search_path TO agroeco, public;

CREATE TABLE IF NOT EXISTS agroeco.region (
    region_id SERIAL PRIMARY KEY,
    region_name VARCHAR(100) NOT NULL,
    country VARCHAR(100),
    geom GEOMETRY(MultiPolygon, 4326),
    bbox TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS agroeco.station (
    station_id SERIAL PRIMARY KEY,
    region_id INTEGER REFERENCES agroeco.region(region_id),
    station_name VARCHAR(150) NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    elevation_m DOUBLE PRECISION,
    station_type VARCHAR(50),
    geom GEOMETRY(Point, 4326)
);

CREATE TABLE IF NOT EXISTS agroeco.climate_daily (
    climate_id BIGSERIAL PRIMARY KEY,
    station_id INTEGER REFERENCES agroeco.station(station_id),
    date DATE NOT NULL,
    precipitation_mm DOUBLE PRECISION,
    temperature_min_c DOUBLE PRECISION,
    temperature_max_c DOUBLE PRECISION,
    temperature_mean_c DOUBLE PRECISION,
    relative_humidity_pct DOUBLE PRECISION,
    source VARCHAR(100),
    UNIQUE (station_id, date)
);

CREATE TABLE IF NOT EXISTS agroeco.soil_profile (
    soil_profile_id SERIAL PRIMARY KEY,
    region_id INTEGER REFERENCES agroeco.region(region_id),
    profile_code VARCHAR(100),
    soil_type VARCHAR(100),
    texture_class VARCHAR(100),
    organic_matter_pct DOUBLE PRECISION,
    ph DOUBLE PRECISION,
    geom GEOMETRY(Point, 4326),
    source VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS agroeco.crop (
    crop_id SERIAL PRIMARY KEY,
    crop_name VARCHAR(100) NOT NULL UNIQUE,
    crop_group VARCHAR(80)
);

CREATE TABLE IF NOT EXISTS agroeco.agricultural_production (
    production_id BIGSERIAL PRIMARY KEY,
    region_id INTEGER REFERENCES agroeco.region(region_id),
    station_id INTEGER REFERENCES agroeco.station(station_id),
    crop_id INTEGER REFERENCES agroeco.crop(crop_id),
    year INTEGER NOT NULL,
    production_tonnes DOUBLE PRECISION,
    area_ha DOUBLE PRECISION,
    yield_kg_ha DOUBLE PRECISION,
    source VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS agroeco.water_point (
    water_point_id SERIAL PRIMARY KEY,
    region_id INTEGER REFERENCES agroeco.region(region_id),
    feature_name VARCHAR(150),
    point_type VARCHAR(80),
    geom GEOMETRY(Point, 4326),
    source VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS agroeco.land_unit (
    land_unit_id SERIAL PRIMARY KEY,
    region_id INTEGER REFERENCES agroeco.region(region_id),
    unit_name VARCHAR(150),
    unit_type VARCHAR(80),
    geom GEOMETRY(MultiPolygon, 4326),
    source VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS agroeco.remote_sensing_product (
    product_id SERIAL PRIMARY KEY,
    product_name VARCHAR(200),
    sensor VARCHAR(100),
    acquisition_date DATE,
    cloud_cover_pct DOUBLE PRECISION,
    spatial_resolution_m DOUBLE PRECISION,
    source VARCHAR(100),
    file_path TEXT,
    region_id INTEGER REFERENCES agroeco.region(region_id)
);

CREATE TABLE IF NOT EXISTS agroeco.spectral_index (
    index_id BIGSERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES agroeco.remote_sensing_product(product_id),
    index_name VARCHAR(50),
    date DATE,
    min_value DOUBLE PRECISION,
    max_value DOUBLE PRECISION,
    mean_value DOUBLE PRECISION,
    file_path TEXT
);

CREATE TABLE IF NOT EXISTS agroeco.geospatial_layer (
    layer_id SERIAL PRIMARY KEY,
    layer_name VARCHAR(150),
    geometry_type VARCHAR(50),
    file_path TEXT,
    crs VARCHAR(50),
    region_id INTEGER REFERENCES agroeco.region(region_id),
    source VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS agroeco.article_artifact (
    artifact_id BIGSERIAL PRIMARY KEY,
    article_name VARCHAR(200),
    source_root TEXT,
    source_path TEXT,
    stored_path TEXT,
    relative_path TEXT,
    file_name VARCHAR(200),
    extension VARCHAR(20),
    file_size_bytes INTEGER,
    category VARCHAR(60),
    is_code BOOLEAN,
    is_tabular BOOLEAN,
    is_geospatial BOOLEAN,
    sha256 VARCHAR(128),
    copied BOOLEAN,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agroeco.article_run (
    run_id BIGSERIAL PRIMARY KEY,
    code_file_id BIGINT REFERENCES agroeco.article_artifact(artifact_id),
    run_name VARCHAR(200),
    script_path TEXT,
    execution_status VARCHAR(50),
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    output_summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_climate_station_date ON agroeco.climate_daily(station_id, date);
CREATE INDEX IF NOT EXISTS idx_agri_region_year ON agroeco.agricultural_production(region_id, year);
CREATE INDEX IF NOT EXISTS idx_spectral_product ON agroeco.spectral_index(product_id, index_name);
CREATE INDEX IF NOT EXISTS idx_article_category ON agroeco.article_artifact(category);

COMMENT ON TABLE agroeco.region IS 'Régions géographiques de référence pour l’Afrique de l’Ouest et le Sénégal';
COMMENT ON TABLE agroeco.climate_daily IS 'Données climatiques journalières des stations';
COMMENT ON TABLE agroeco.soil_profile IS 'Propriétés pédologiques et profils de sol';
COMMENT ON TABLE agroeco.agricultural_production IS 'Production agricole par région, culture et année';
COMMENT ON TABLE agroeco.remote_sensing_product IS 'Produits de télédétection et images multi-sources';
COMMENT ON TABLE agroeco.article_artifact IS 'Métadonnées des scripts, données et outputs des articles';
