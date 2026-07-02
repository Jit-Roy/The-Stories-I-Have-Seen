import sqlite3
import os
import json
import sys

if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

DB_NAME = os.path.join(base_dir, "movies.db")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Create movies table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY,
            tmdb_id INTEGER UNIQUE,
            title TEXT,
            poster_path TEXT,
            status TEXT, -- "watched" or "watch_later"
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            series_name TEXT
        )
    ''')
    
    # Simple migration: try adding the series_name column in case the db is older
    try:
        cursor.execute('ALTER TABLE movies ADD COLUMN series_name TEXT')
    except sqlite3.OperationalError:
        pass # Column already exists
        
    try:
        cursor.execute('ALTER TABLE movies ADD COLUMN vote_average REAL')
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute('ALTER TABLE movies ADD COLUMN release_date TEXT')
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute('ALTER TABLE movies ADD COLUMN runtime INTEGER')
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute('ALTER TABLE movies ADD COLUMN genres TEXT')
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute('ALTER TABLE movies ADD COLUMN director TEXT')
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute('ALTER TABLE movies ADD COLUMN "cast" TEXT')
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute('ALTER TABLE movies ADD COLUMN production_companies TEXT')
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute('ALTER TABLE movies ADD COLUMN original_language TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE movies ADD COLUMN production_countries TEXT')
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

def add_movie(tmdb_id, title, poster_path, status, series_name=None, vote_average=None, release_date=None, runtime=None, genres=None, director=None, cast=None, production_companies=None, original_language=None, production_countries=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        # Serialize list fields to JSON
        genres_json = json.dumps(genres) if genres else None
        cast_json = json.dumps(cast) if cast else None
        companies_json = json.dumps(production_companies) if production_companies else None
        countries_json = json.dumps(production_countries) if production_countries else None
        
        cursor.execute('''
            INSERT INTO movies (tmdb_id, title, poster_path, status, series_name, vote_average, release_date, runtime, genres, director, "cast", production_companies, original_language, production_countries)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (tmdb_id, title, poster_path, status, series_name, vote_average, release_date, runtime, genres_json, director, cast_json, companies_json, original_language, countries_json))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        # If movie already exists, just update the status
        cursor.execute('''
            UPDATE movies SET status = ? WHERE tmdb_id = ?
        ''', (status, tmdb_id))
        conn.commit()
        success = True
    except Exception as e:
        print(f"Error adding movie: {e}")
        success = False
    finally:
        conn.close()
        
    return success

def remove_movie(tmdb_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM movies WHERE tmdb_id = ?', (tmdb_id,))
    conn.commit()
    conn.close()

def get_movies(status=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if status:
        cursor.execute('SELECT tmdb_id, title, poster_path, status, series_name, vote_average, release_date, runtime, genres, director, "cast", production_companies, original_language, production_countries FROM movies WHERE status = ? ORDER BY added_at DESC', (status,))
    else:
        cursor.execute('SELECT tmdb_id, title, poster_path, status, series_name, vote_average, release_date, runtime, genres, director, "cast", production_companies, original_language, production_countries FROM movies ORDER BY added_at DESC')
        
    movies = cursor.fetchall()
    conn.close()
    
    # Return as list of dicts for easier handling
    return [
        {
            "id": m[0],
            "title": m[1],
            "poster_path": m[2],
            "status": m[3],
            "series_name": m[4],
            "vote_average": m[5],
            "release_date": m[6],
            "runtime": m[7],
            "genres": json.loads(m[8]) if m[8] else [],
            "director": m[9],
            "cast": json.loads(m[10]) if m[10] else [],
            "production_companies": json.loads(m[11]) if m[11] else [],
            "original_language": m[12],
            "production_countries": json.loads(m[13]) if m[13] else []
        }
        for m in movies
    ]

def set_series(tmdb_id, series_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # convert empty strings to None
    series_name = series_name.strip() if series_name and series_name.strip() else None
    cursor.execute('''
        UPDATE movies SET series_name = ? WHERE tmdb_id = ?
    ''', (series_name, tmdb_id))
    conn.commit()
    conn.close()
