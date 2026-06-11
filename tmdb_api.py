import os
import requests
from dotenv import load_dotenv

load_dotenv()
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.tmdb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
BACKDROP_BASE_URL = "https://image.tmdb.org/t/p/w1280"

import time

_search_cache = {}

def _make_request(endpoint, params=None, retries=5):
    if not TMDB_API_KEY:
        print("Error: TMDB_API_KEY is not set.")
        return {}
    if params is None:
        params = {}
    params["api_key"] = TMDB_API_KEY
    headers = {
        "User-Agent": "WorldsIveWatched/1.0",
        "Accept": "application/json"
    }
    for attempt in range(retries):
        try:
            response = requests.get(f"{BASE_URL}{endpoint}", params=params, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error on {endpoint}, retrying ({attempt+1}/{retries})...")
            time.sleep(1.5)
        except Exception as e:
            print(f"API Error ({endpoint}): {e}")
            break
            
    return {}

import database

def inject_db_status(movies_list):
    if not movies_list:
        return movies_list
    db_cache = {m["id"]: m["status"] for m in database.get_movies()}
    for m in movies_list:
        m["status"] = db_cache.get(m["id"])
    return movies_list

def _format_movie(item):
    poster = item.get("poster_path")
    backdrop = item.get("backdrop_path")
    return {
        "id": item.get("id"),
        "title": item.get("title") or item.get("name"),
        "poster_path": f"{IMAGE_BASE_URL}{poster}" if poster else None,
        "backdrop_path": f"{BACKDROP_BASE_URL}{backdrop}" if backdrop else None,
        "release_date": item.get("release_date"),
        "vote_average": item.get("vote_average")
    }

def search_movies(query, page=1):
    data = _make_request("/search/movie", {"query": query, "language": "en-US", "page": page, "include_adult": False})
    return inject_db_status([_format_movie(m) for m in data.get("results", [])])

def get_trending(page=1, time_window="day"):
    data = _make_request(f"/trending/movie/{time_window}", {"page": page})
    return inject_db_status([_format_movie(m) for m in data.get("results", [])])

def get_upcoming(page=1):
    data = _make_request("/movie/upcoming", {"language": "en-US", "page": page})
    return inject_db_status([_format_movie(m) for m in data.get("results", [])])

def get_top_rated(page=1):
    data = _make_request("/movie/top_rated", {"language": "en-US", "page": page})
    return inject_db_status([_format_movie(m) for m in data.get("results", [])])

def get_movie_details(movie_id):
    data = _make_request(f"/movie/{movie_id}", {"append_to_response": "credits,videos,similar"})
    if not data: return None
    movie = _format_movie(data)
    collection = data.get("belongs_to_collection")
    movie["series_name"] = collection.get("name") if isinstance(collection, dict) else None
    movie["genres"] = [g["name"] for g in data.get("genres", [])]
    movie["overview"] = data.get("overview")
    movie["runtime"] = data.get("runtime")
    movie["tagline"] = data.get("tagline", "")
    
    # Extended Facts
    movie["tmdb_status"] = data.get("status", "Unknown")
    movie["budget"] = data.get("budget", 0)
    movie["revenue"] = data.get("revenue", 0)
    movie["original_language"] = data.get("original_language", "").upper()
    movie["homepage"] = data.get("homepage", "")
    movie["production_companies"] = [c["name"] for c in data.get("production_companies", [])]
    
    credits = data.get("credits", {})
    crew = credits.get("crew", [])
    cast = credits.get("cast", [])
    
    movie["director"] = next((member["name"] for member in crew if member.get("job") == "Director"), "Unknown")
    movie["cast"] = [member["name"] for member in cast[:10]]
    
    # Videos
    videos = data.get("videos", {}).get("results", [])
    movie["trailers"] = [v for v in videos if v.get("site") == "YouTube" and v.get("type") in ["Trailer", "Teaser"]]
    
    # Similar
    similar_data = data.get("similar", {}).get("results", [])
    movie["similar"] = [_format_movie(m) for m in similar_data]
    
    return inject_db_status([movie])[0]

def get_genres():
    data = _make_request("/genre/movie/list", {"language": "en-US"})
    return data.get("genres", [])

def get_movies_by_genre(genre_id, page=1):
    data = _make_request("/discover/movie", {"with_genres": genre_id, "language": "en-US", "page": page})
    return inject_db_status([_format_movie(m) for m in data.get("results", [])])

def get_collection_poster(series_name):
    data = _make_request("/search/collection", {"query": series_name, "language": "en-US", "page": 1})
    results = data.get("results", [])
    if results:
        poster = results[0].get("poster_path")
        return f"{IMAGE_BASE_URL}{poster}" if poster else None
    return None


import database

def advanced_discover(params, page=1):
    params = params.copy()
    show_me = params.pop("show_me", None)
    query = params.pop("query", None)
    
    if query:
        cache_key = f"{query}_{params}_{show_me}"
        if page == 1 or cache_key not in _search_cache:
            search_params = {"query": query, "language": "en-US"}
            filtered = []
            for p in range(1, 4):
                search_params["page"] = p
                data = _make_request("/search/movie", search_params)
                raw_movies = data.get("results", [])
                
                for m in raw_movies:
                    genres_str = params.get("with_genres")
                    if genres_str:
                        req_genres = set(int(x) for x in genres_str.split(","))
                        m_genres = set(m.get("genre_ids", []))
                        if not m_genres.intersection(req_genres):
                            continue
                            
                    min_rating = params.get("vote_average.gte")
                    if min_rating and m.get("vote_average", 0) < float(min_rating):
                        continue
                            
                    req_lang = params.get("with_original_language")
                    if req_lang and m.get("original_language") != req_lang:
                        continue
                        
                    date_gte = params.get("primary_release_date.gte")
                    date_lte = params.get("primary_release_date.lte")
                    if date_gte or date_lte:
                        rel_date = m.get("release_date")
                        if not rel_date:
                            continue
                        if date_gte and rel_date < date_gte:
                            continue
                        if date_lte and rel_date > date_lte:
                            continue
                            
                    filtered.append(m)
                    
                if p >= data.get("total_pages", 1):
                    break
                    
            _search_cache[cache_key] = filtered
            
        filtered = _search_cache[cache_key]
        start_idx = (page - 1) * 20
        end_idx = start_idx + 20
        results = [_format_movie(m) for m in filtered[start_idx:end_idx]]
        
    else:
        default_params = {"language": "en-US", "page": page}
        default_params.update(params)
        data = _make_request("/discover/movie", default_params)
        results = [_format_movie(m) for m in data.get("results", [])]
        
    results = inject_db_status(results)
    
    if show_me == "unseen":
        results = [m for m in results if m["status"] != "watched"]
        
    return results
