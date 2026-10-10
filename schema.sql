-- Dark-vessel detection schema
-- PostgreSQL + PostGIS. Run against a database with PostGIS enabled:
--   CREATE EXTENSION IF NOT EXISTS postgis;
--   psql -d <your_db> -f schema.sql

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------
-- scenes: one row per (scene, representation) pair. The same acquisition
-- shows up multiple times here -- once as "raw", once as "baq_4bit",
-- once as "jp2_r20", etc. -- so you can compare sizes/detector results
-- across representations of the identical scene.
-- ---------------------------------------------------------------------
CREATE TABLE scenes (
    scene_id        BIGSERIAL PRIMARY KEY,
    product_id      TEXT        NOT NULL,          -- e.g. Sentinel-1 product identifier, shared across representations of the same acquisition
    acquisition_time TIMESTAMPTZ NOT NULL,
    representation  TEXT        NOT NULL,          -- 'raw' | 'baq' | 'jp2'
    repr_param      JSONB,                         -- {"bits_per_sample": 4} or {"compression_ratio": 20} etc.
    file_path       TEXT        NOT NULL,           -- where the actual data lives (local path or object-store URI)
    file_size_bytes BIGINT,
    footprint       geometry(Polygon, 4326) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT scenes_representation_check
        CHECK (representation IN ('raw', 'baq', 'jp2')),
    CONSTRAINT scenes_product_repr_unique
        UNIQUE (product_id, representation, repr_param)
);

CREATE INDEX scenes_footprint_gist ON scenes USING GIST (footprint);
CREATE INDEX scenes_product_id_idx ON scenes (product_id);
CREATE INDEX scenes_acquisition_time_idx ON scenes (acquisition_time);

-- ---------------------------------------------------------------------
-- detections: one row per detector output. Tied to a specific scene
-- representation, so the same physical ship detected in the raw vs. the
-- BAQ vs. the JPEG2000 version of a scene gets separate rows you can
-- compare.
-- ---------------------------------------------------------------------
CREATE TABLE detections (
    detection_id    BIGSERIAL PRIMARY KEY,
    scene_id        BIGINT      NOT NULL REFERENCES scenes(scene_id) ON DELETE CASCADE,
    geom            geometry(Point, 4326) NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL,           -- usually == scenes.acquisition_time, kept separate in case of per-detection timing
    confidence      REAL,
    detector_name   TEXT        NOT NULL,           -- 'cfar_baseline', etc.
    is_dark         BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX detections_geom_gist ON detections USING GIST (geom);
CREATE INDEX detections_scene_id_idx ON detections (scene_id);
CREATE INDEX detections_detected_at_idx ON detections (detected_at);
CREATE INDEX detections_is_dark_idx ON detections (is_dark) WHERE is_dark;

-- ---------------------------------------------------------------------
-- ais_broadcasts: AIS positions from Global Fishing Watch / NOAA
-- MarineCadastre, used as the "ground truth" vessels against which
-- detections are matched.
-- ---------------------------------------------------------------------
CREATE TABLE ais_broadcasts (
    ais_id          BIGSERIAL PRIMARY KEY,
    mmsi            BIGINT      NOT NULL,
    broadcast_time  TIMESTAMPTZ NOT NULL,
    geom            geometry(Point, 4326) NOT NULL,
    speed_knots     REAL,
    heading_deg     REAL,
    source          TEXT        NOT NULL DEFAULT 'gfw'  -- 'gfw' | 'marinecadastre'
);

CREATE INDEX ais_geom_gist ON ais_broadcasts USING GIST (geom);
CREATE INDEX ais_mmsi_idx ON ais_broadcasts (mmsi);
CREATE INDEX ais_broadcast_time_idx ON ais_broadcasts (broadcast_time);

-- ---------------------------------------------------------------------
-- dark_vessel_matches: the output of the spatial-temporal join. One row
-- per detection: either it matched an AIS broadcast within tolerance, or
-- it didn't and is_dark = TRUE. Materialized here (rather than computed
-- fresh every query) so you have an auditable record of what matched
-- what, with what distance/time gap, for a given tolerance setting.
-- ---------------------------------------------------------------------
CREATE TABLE dark_vessel_matches (
    match_id            BIGSERIAL PRIMARY KEY,
    detection_id         BIGINT   NOT NULL REFERENCES detections(detection_id) ON DELETE CASCADE,
    matched_ais_id       BIGINT   REFERENCES ais_broadcasts(ais_id) ON DELETE SET NULL,  -- NULL => dark
    match_distance_m     REAL,
    match_time_delta_s   REAL,
    distance_tolerance_m REAL     NOT NULL,
    time_tolerance_s     REAL     NOT NULL,
    is_dark              BOOLEAN  NOT NULL,
    computed_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX dvm_detection_id_idx ON dark_vessel_matches (detection_id);
CREATE INDEX dvm_is_dark_idx ON dark_vessel_matches (is_dark) WHERE is_dark;

-- ---------------------------------------------------------------------
-- Example spatial-temporal join: for a given distance tolerance (meters,
-- cast via geography) and time window, find the nearest AIS broadcast to
-- each detection and flag anything with no match within tolerance as dark.
-- Use geography casts (::geography) so ST_DWithin's distance argument is
-- in meters rather than degrees.
-- ---------------------------------------------------------------------
-- INSERT INTO dark_vessel_matches
--     (detection_id, matched_ais_id, match_distance_m, match_time_delta_s,
--      distance_tolerance_m, time_tolerance_s, is_dark)
-- SELECT
--     d.detection_id,
--     best.ais_id,
--     best.distance_m,
--     best.time_delta_s,
--     1000.0,   -- distance_tolerance_m
--     600.0,    -- time_tolerance_s
--     (best.ais_id IS NULL) AS is_dark
-- FROM detections d
-- LEFT JOIN LATERAL (
--     SELECT
--         a.ais_id,
--         ST_Distance(d.geom::geography, a.geom::geography) AS distance_m,
--         EXTRACT(EPOCH FROM (d.detected_at - a.broadcast_time)) AS time_delta_s
--     FROM ais_broadcasts a
--     WHERE ST_DWithin(d.geom::geography, a.geom::geography, 1000.0)
--       AND a.broadcast_time BETWEEN d.detected_at - INTERVAL '600 seconds'
--                                AND d.detected_at + INTERVAL '600 seconds'
--     ORDER BY d.geom::geography <-> a.geom::geography
--     LIMIT 1
-- ) best ON TRUE
-- WHERE d.scene_id = <target_scene_id>;