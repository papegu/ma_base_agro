import re
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / 'data' / 'multimodal_base.sqlite'


def infer(file_name: str):
    name = file_name.lower()
    metadata = {
        'region': 'Sénégal',
        'agro_zone': 'Zone agro-écologique du Sénégal',
        'spectral_index': 'NDVI' if 'ndvi' in name else 'Indice de végétation',
        'satellite_source': 'MODIS/061/MOD13A2' if 'ndvi' in name else 'Source raster inconnue',
        'period_start': None,
        'period_end': None,
        'time_period': None,
        'use_case': 'Suivi de la végétation et de l’état agroécologique',
    }
    match = re.search(r'(20\d{2})[_-](\d{2})', file_name)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        metadata['period_start'] = f'{year}-{month:02d}-01'
        metadata['period_end'] = f'{year}-{month:02d}-31'
        metadata['time_period'] = f'{year}-{month:02d}'
    return metadata


conn = sqlite3.connect(DB_PATH)
cols = [r[1] for r in conn.execute('PRAGMA table_info("geotiff_catalog")').fetchall()]
needed = ['region','agro_zone','spectral_index','satellite_source','period_start','period_end','time_period','use_case']
for c in needed:
    if c not in cols:
        conn.execute(f'ALTER TABLE geotiff_catalog ADD COLUMN {c} TEXT')
        cols.append(c)

rows = conn.execute('SELECT id, file_name FROM geotiff_catalog ORDER BY id').fetchall()
for row_id, file_name in rows:
    if not file_name:
        continue
    meta = infer(file_name)
    conn.execute(
        'UPDATE geotiff_catalog SET region=?, agro_zone=?, spectral_index=?, satellite_source=?, period_start=?, period_end=?, time_period=?, use_case=? WHERE id=?',
        (
            meta['region'],
            meta['agro_zone'],
            meta['spectral_index'],
            meta['satellite_source'],
            meta['period_start'],
            meta['period_end'],
            meta['time_period'],
            meta['use_case'],
            row_id,
        ),
    )

conn.commit()
print('Columns:', [r[1] for r in conn.execute('PRAGMA table_info("geotiff_catalog")').fetchall()])
print('Sample rows:', conn.execute('SELECT id, file_name, region, agro_zone, spectral_index, satellite_source, time_period, use_case FROM geotiff_catalog ORDER BY id LIMIT 5').fetchall())
conn.close()
