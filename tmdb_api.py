import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.tmdb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
BACKDROP_BASE_URL = "https://image.tmdb.org/t/p/w1280"

def get_api_key():
    return TMDB_API_KEY

def set_api_key(new_key):
    global TMDB_API_KEY
    import dotenv
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        open(env_path, 'w').close()
    dotenv.set_key(env_path, "TMDB_API_KEY", new_key)
    TMDB_API_KEY = new_key
    
    # Clear caches so any previously failed requests (due to bad key) can be retried immediately
    _search_cache.clear()
    _details_cache.clear()

# ---------------------------------------------------------------------------
# Per-session caches
# ---------------------------------------------------------------------------
_search_cache = {}
_details_cache = {}          # movie_id -> full details dict
_db_status_cache = None      # None means "dirty / needs refresh"


def _get_db_status_map():
    """Return the cached DB status map, refreshing only when dirty."""
    global _db_status_cache
    if _db_status_cache is None:
        import database
        _db_status_cache = {m["id"]: m["status"] for m in database.get_movies()}
    return _db_status_cache


def invalidate_db_cache():
    """Call this whenever the database is written to."""
    global _db_status_cache
    _db_status_cache = None
    # Also clear the details cache so stale statuses are not served
    _details_cache.clear()


def _make_request(endpoint, params=None, retries=3):
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
            response = requests.get(
                f"{BASE_URL}{endpoint}", params=params, headers=headers, timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError:
            print(f"Connection error on {endpoint}, retrying ({attempt+1}/{retries})...")
            time.sleep(0.5)
        except Exception as e:
            print(f"API Error ({endpoint}): {e}")
            break

    return {}


import database


def inject_db_status(movies_list):
    if not movies_list:
        return movies_list
    db_cache = _get_db_status_map()
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
        "vote_average": item.get("vote_average"),
        "media_type": "movie"
    }

def _format_tv(item):
    poster = item.get("poster_path")
    backdrop = item.get("backdrop_path")
    return {
        "id": item.get("id"),
        "title": item.get("name") or item.get("title"),
        "poster_path": f"{IMAGE_BASE_URL}{poster}" if poster else None,
        "backdrop_path": f"{BACKDROP_BASE_URL}{backdrop}" if backdrop else None,
        "release_date": item.get("first_air_date"),
        "vote_average": item.get("vote_average"),
        "media_type": "tv"
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

def get_popular(page=1):
    data = _make_request("/movie/popular", {"language": "en-US", "page": page})
    return inject_db_status([_format_movie(m) for m in data.get("results", [])])


def search_tv(query, page=1):
    data = _make_request("/search/tv", {"query": query, "language": "en-US", "page": page, "include_adult": False})
    return inject_db_status([_format_tv(m) for m in data.get("results", [])])

def get_trending_tv(page=1, time_window="day"):
    data = _make_request(f"/trending/tv/{time_window}", {"page": page})
    return inject_db_status([_format_tv(m) for m in data.get("results", [])])

def get_upcoming_tv(page=1):
    data = _make_request("/tv/on_the_air", {"language": "en-US", "page": page})
    return inject_db_status([_format_tv(m) for m in data.get("results", [])])

def get_top_rated_tv(page=1):
    data = _make_request("/tv/top_rated", {"language": "en-US", "page": page})
    return inject_db_status([_format_tv(m) for m in data.get("results", [])])

def get_popular_tv(page=1):
    data = _make_request("/tv/popular", {"language": "en-US", "page": page})
    return inject_db_status([_format_tv(m) for m in data.get("results", [])])

def get_movie_details(movie_id):
    """Fetch full movie details. Results are cached for the session lifetime."""
    if movie_id in _details_cache:
        return _details_cache[movie_id]

    data = _make_request(f"/movie/{movie_id}", {"append_to_response": "credits,videos,similar"})
    if not data:
        return None

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
    movie["production_countries"] = [c["iso_3166_1"] for c in data.get("production_countries", [])]

    credits = data.get("credits", {})
    crew = credits.get("crew", [])
    cast = credits.get("cast", [])

    movie["director"] = next((member["name"] for member in crew if member.get("job") == "Director"), "Unknown")
    movie["cast"] = [member["name"] for member in cast[:10]]
    movie["cast_details"] = [{"id": c["id"], "name": c["name"], "profile_path": c.get("profile_path"), "character": c.get("character")} for c in cast[:15]]

    # Videos
    videos = data.get("videos", {}).get("results", [])
    movie["trailers"] = [v for v in videos if v.get("site") == "YouTube" and v.get("type") in ["Trailer", "Teaser"]]

    # Similar
    similar_data = data.get("similar", {}).get("results", [])
    movie["similar"] = [_format_movie(m) for m in similar_data]

    result = inject_db_status([movie])[0]
    _details_cache[movie_id] = result
    return result

def get_tv_details(tv_id):
    if f"tv_{tv_id}" in _details_cache:
        return _details_cache[f"tv_{tv_id}"]

    data = _make_request(f"/tv/{tv_id}", {"append_to_response": "credits,videos,similar"})
    if not data:
        return None

    tv = _format_tv(data)
    tv["series_name"] = data.get("name")
    tv["genres"] = [g["name"] for g in data.get("genres", [])]
    tv["overview"] = data.get("overview")
    ep_run = data.get("episode_run_time", [])
    tv["runtime"] = ep_run[0] if ep_run else None
    tv["tagline"] = data.get("tagline", "")

    tv["tmdb_status"] = data.get("status", "Unknown")
    tv["budget"] = 0
    tv["revenue"] = 0
    tv["original_language"] = data.get("original_language", "").upper()
    tv["homepage"] = data.get("homepage", "")
    tv["production_companies"] = [c["name"] for c in data.get("production_companies", [])]
    tv["production_countries"] = [c["iso_3166_1"] for c in data.get("production_countries", [])]

    credits = data.get("credits", {})
    crew = credits.get("crew", [])
    cast = credits.get("cast", [])

    tv["director"] = next((member["name"] for member in crew if member.get("job") in ["Executive Producer", "Creator"]), "Unknown")
    tv["cast"] = [member["name"] for member in cast[:10]]
    tv["cast_details"] = [{"id": c["id"], "name": c["name"], "profile_path": c.get("profile_path"), "character": c.get("character")} for c in cast[:15]]

    videos = data.get("videos", {}).get("results", [])
    tv["trailers"] = [v for v in videos if v.get("site") == "YouTube" and v.get("type") in ["Trailer", "Teaser"]]

    similar_data = data.get("similar", {}).get("results", [])
    tv["similar"] = [_format_tv(m) for m in similar_data]

    result = inject_db_status([tv])[0]
    _details_cache[f"tv_{tv_id}"] = result
    return result

def get_age_rating(media_id, media_type="movie"):
    if media_type == "movie":
        data = _make_request(f"/movie/{media_id}/release_dates")
        results = data.get("results", [])
        us_release = next((r for r in results if r["iso_3166_1"] == "US"), None)
        if us_release:
            dates = us_release.get("release_dates", [])
            for d in dates:
                if d.get("certification"):
                    return d["certification"]
    else:
        data = _make_request(f"/tv/{media_id}/content_ratings")
        results = data.get("results", [])
        us_release = next((r for r in results if r["iso_3166_1"] == "US"), None)
        if us_release:
            return us_release.get("rating")
    return None


def get_person_details(person_id):
    data = _make_request(f"/person/{person_id}", {"append_to_response": "combined_credits"})
    if not data:
        return None
    credits = data.get("combined_credits", {})
    cast_credits = credits.get("cast", [])
    
    # Sort by popularity
    cast_credits = sorted(cast_credits, key=lambda x: x.get("popularity", 0), reverse=True)
    
    formatted_credits = []
    seen_ids = set()
    for c in cast_credits:
        cid = c.get("id")
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        
        if c.get("media_type") == "tv":
            formatted_credits.append(_format_tv(c))
        else:
            formatted_credits.append(_format_movie(c))
            
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "biography": data.get("biography"),
        "profile_path": f"{IMAGE_BASE_URL}{data.get('profile_path')}" if data.get("profile_path") else None,
        "birthday": data.get("birthday"),
        "place_of_birth": data.get("place_of_birth"),
        "known_for_department": data.get("known_for_department"),
        "credits": inject_db_status(formatted_credits[:20]) # Top 20 credits
    }

def get_person_full_credits(person_id, page=1):
    data = _make_request(f"/person/{person_id}", {"append_to_response": "combined_credits"})
    if not data:
        return []
        
    credits = data.get("combined_credits", {})
    cast_credits = credits.get("cast", [])
    
    # Sort by popularity
    cast_credits = sorted(cast_credits, key=lambda x: x.get("popularity", 0), reverse=True)
    
    formatted_credits = []
    seen_ids = set()
    for c in cast_credits:
        cid = c.get("id")
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        
        if c.get("media_type") == "tv":
            formatted_credits.append(_format_tv(c))
        else:
            formatted_credits.append(_format_movie(c))
            
    # Manually paginate (20 items per page)
    start_idx = (page - 1) * 20
    end_idx = start_idx + 20
    page_items = formatted_credits[start_idx:end_idx]
    
    return inject_db_status(page_items)


from functools import lru_cache

@lru_cache(maxsize=1)
def get_genres():
    data = _make_request("/genre/movie/list", {"language": "en-US"})
    return data.get("genres", [])

@lru_cache(maxsize=1)
def get_languages():
    data = _make_request("/configuration/languages")
    if data and isinstance(data, list):
        return sorted(data, key=lambda x: x.get("english_name", ""))
    return []

@lru_cache(maxsize=1)
def get_countries():
    data = _make_request("/configuration/countries")
    if data and isinstance(data, list):
        return sorted(data, key=lambda x: x.get("english_name", ""))
    return []


def get_movies_by_genre(genre_id, page=1):
    data = _make_request("/discover/movie", {"with_genres": genre_id, "language": "en-US", "page": page})
    return inject_db_status([_format_movie(m) for m in data.get("results", [])])


def get_collection_poster(series_name, media_type="movie"):
    if media_type == "tv":
        data_tv = _make_request("/search/tv", {"query": series_name, "language": "en-US", "page": 1})
        results_tv = data_tv.get("results", [])
        if results_tv and results_tv[0].get("poster_path"):
            return f"{IMAGE_BASE_URL}{results_tv[0]['poster_path']}"
        return None
        
    data = _make_request("/search/collection", {"query": series_name, "language": "en-US", "page": 1})
    results = data.get("results", [])
    if results and results[0].get("poster_path"):
        return f"{IMAGE_BASE_URL}{results[0]['poster_path']}"
        
    return None


def advanced_discover(params, page=1, media_type="movie"):
    params = params.copy()
    show_me = params.pop("show_me", None)
    query = params.pop("query", None)
    endpoint_search = f"/search/{media_type}"
    endpoint_discover = f"/discover/{media_type}"
    formatter = _format_tv if media_type == "tv" else _format_movie

    if query:
        cache_key = f"{query}_{params}_{show_me}_{media_type}"
        if page == 1 or cache_key not in _search_cache:
            search_params = {"query": query, "language": "en-US"}
            filtered = []
            for p in range(1, 4):
                search_params["page"] = p
                data = _make_request(endpoint_search, search_params)
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

                    # Filter dates
                    date_field = "first_air_date" if media_type == "tv" else "release_date"
                    date_gte = params.get(f"{date_field}.gte") or params.get("primary_release_date.gte")
                    date_lte = params.get(f"{date_field}.lte") or params.get("primary_release_date.lte")
                    
                    if date_gte or date_lte:
                        rel_date = m.get(date_field)
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
        results = inject_db_status([formatter(m) for m in filtered[start_idx:end_idx]])

        if show_me == "unseen":
            results = [m for m in results if m["status"] != "watched"]

        return results

    # ── Discover (no query) ──────────────────────────────────────────────────
    PAGE_SIZE = 20
    MAX_PAGES_PER_CALL = 10

    if show_me != "unseen":
        api_params = {"language": "en-US", "page": page}
        
        # fix param translation for tv
        if media_type == "tv":
            if "primary_release_date.gte" in params:
                params["first_air_date.gte"] = params.pop("primary_release_date.gte")
            if "primary_release_date.lte" in params:
                params["first_air_date.lte"] = params.pop("primary_release_date.lte")
                
        api_params.update(params)
        data = _make_request(endpoint_discover, api_params)
        results = inject_db_status([formatter(m) for m in data.get("results", [])])
        return results

    params_key = str(sorted(params.items()))
    cursor_key = f"__unseen_cursor_{params_key}_{media_type}"
    if page == 1:
        _search_cache[cursor_key] = 1

    tmdb_page = _search_cache.get(cursor_key, 1)
    collected = []
    pages_fetched = 0

    while len(collected) < PAGE_SIZE and pages_fetched < MAX_PAGES_PER_CALL:
        api_params = {"language": "en-US", "page": tmdb_page}
        if media_type == "tv":
            if "primary_release_date.gte" in params:
                params["first_air_date.gte"] = params.pop("primary_release_date.gte")
            if "primary_release_date.lte" in params:
                params["first_air_date.lte"] = params.pop("primary_release_date.lte")
        api_params.update(params)
        data = _make_request(endpoint_discover, api_params)
        raw = data.get("results", [])
        total_tmdb_pages = data.get("total_pages", 1)

        if not raw:
            break

        batch = inject_db_status([formatter(m) for m in raw])
        unseen = [m for m in batch if m["status"] != "watched"]
        collected.extend(unseen)

        tmdb_page += 1
        pages_fetched += 1

        if tmdb_page > total_tmdb_pages:
            break

    _search_cache[cursor_key] = tmdb_page
    return collected[:PAGE_SIZE]
# ---------------------------------------------------------------------------
# Discovery for Analytics
# ---------------------------------------------------------------------------
def discover_by_person(name, is_director=False, page=1):
    search = _make_request("/search/person", {"query": name})
    if not search or not search.get("results"):
        return []
    person_id = search["results"][0]["id"]
    
    params = {"sort_by": "popularity.desc", "page": page}
    if is_director:
        params["with_crew"] = person_id
    else:
        params["with_cast"] = person_id
        
    res = _make_request("/discover/movie", params)
    movies = res.get("results", []) if res else []
    return inject_db_status([_format_movie(m) for m in movies])

def discover_by_studio(name, page=1):
    search = _make_request("/search/company", {"query": name})
    if not search or not search.get("results"):
        return []
    company_id = search["results"][0]["id"]
    
    res = _make_request("/discover/movie", {"with_companies": company_id, "sort_by": "popularity.desc", "page": page})
    movies = res.get("results", []) if res else []
    return inject_db_status([_format_movie(m) for m in movies])

def discover_by_language(lang_code, page=1):
    res = _make_request("/discover/movie", {"with_original_language": lang_code.lower(), "sort_by": "popularity.desc", "page": page})
    movies = res.get("results", []) if res else []
    return inject_db_status([_format_movie(m) for m in movies])

def discover_by_era(decade_str, page=1):
    # decade_str is something like "2010s"
    try:
        start_year = int(decade_str[:4])
        end_year = start_year + 9
        res = _make_request("/discover/movie", {
            "primary_release_date.gte": f"{start_year}-01-01",
            "primary_release_date.lte": f"{end_year}-12-31",
            "sort_by": "popularity.desc",
            "page": page
        })
        movies = res.get("results", []) if res else []
        return inject_db_status([_format_movie(m) for m in movies])
    except:
        return []
        
def discover_by_genre(genre_name, page=1):
    # Fetch genres list to map name to ID
    genres_data = get_genres()
    genre_id = None
    for g in genres_data:
        if g["name"].lower() == genre_name.lower():
            genre_id = g["id"]
            break
            
    if not genre_id:
        return []
        
    res = _make_request("/discover/movie", {"with_genres": genre_id, "sort_by": "popularity.desc", "page": page})
    movies = res.get("results", []) if res else []
    return inject_db_status([_format_movie(m) for m in movies])
