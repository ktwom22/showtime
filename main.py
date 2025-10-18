import os
import random
import requests
import json
from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "secret123")
TMDB_KEY = os.getenv("TMDB_API_KEY", "26d79b573974be9e3561d7ed1dc8e085")

# If your app is behind a proxy or hosted platform that rewrites host headers,
# set SITE_URL to your public URL (e.g. "https://your-app.example.com") in your environment.
SITE_URL = os.getenv("SITE_URL", "").rstrip("/")

MAX_GUESSES = 6
DAILY_FILE = "daily_games.json"

# Allowed networks/services
ALLOWED_NETWORKS = [
    # Broadcast
    "ABC", "NBC", "CBS", "FOX", "The CW",
    # Streaming
    "Netflix", "Hulu", "Disney+", "HBO Max", "Prime Video", "Apple TV+",
    # Cable
    "AMC", "FX", "USA Network", "Syfy", "Showtime", "Starz", "TNT", "BBC America"
]

# ---------------- Helper: English check ---------------- #
def is_english_from_details(details):
    """
    Decide whether a show is English-speaking based on TMDB details.
    Checks original_language and spoken_languages.
    """
    if not details:
        return False
    orig = details.get("original_language") or ""
    if orig.lower() == "en":
        return True
    for lang in details.get("spoken_languages", []):
        iso = lang.get("iso_639_1", "")
        if iso.lower() == "en":
            return True
        name = lang.get("english_name", "") or lang.get("name", "")
        if name and "english" in name.lower():
            return True
    return False

def looks_like_logo(path):
    """Simple heuristic to avoid showing logo-like images as the poster."""
    if not path:
        return False
    p = path.lower()
    if "logo" in p:
        return True
    if p.endswith(".svg"):
        return True
    return False

# ---------------- Daily Show Logic ---------------- #
def pick_random_show():
    """Pick a random TV show on allowed US networks/streaming services that has a trailer and is English-speaking."""
    try:
        for attempt in range(50):  # More attempts to ensure we find one with a trailer in English
            page = random.randint(1, 10)
            res = requests.get(
                "https://api.themoviedb.org/3/tv/popular",
                params={"api_key": TMDB_KEY, "language": "en-US", "page": page},
                timeout=10
            ).json()
            shows = res.get("results", [])
            random.shuffle(shows)

            for show in shows:
                details = requests.get(
                    f"https://api.themoviedb.org/3/tv/{show['id']}?api_key={TMDB_KEY}&language=en-US",
                    timeout=10
                ).json()

                # Ensure the show is English-speaking
                if not is_english_from_details(details):
                    continue

                # Check for allowed networks
                networks = [n.get("name") for n in details.get("networks", []) if n.get("name")]
                if not any(net in ALLOWED_NETWORKS for net in networks):
                    continue

                # Require a YouTube Trailer (strict)
                videos = requests.get(
                    f"https://api.themoviedb.org/3/tv/{show['id']}/videos?api_key={TMDB_KEY}&language=en-US",
                    timeout=10
                ).json()
                trailer_key = next(
                    (v["key"] for v in videos.get("results", [])
                     if v.get("type", "").lower() == "trailer" and v.get("site", "").lower() == "youtube"),
                    None
                )

                if trailer_key:
                    return {
                        "id": show["id"],
                        "name": show.get("name"),
                        "poster": show.get("poster_path"),
                        "overview": show.get("overview", ""),
                        "trailer_key": trailer_key
                    }

        return None
    except Exception as e:
        print("Error picking random show:", e)
        return None

def update_daily_games():
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    try:
        with open(DAILY_FILE, "r") as f:
            daily_data = json.load(f)
    except FileNotFoundError:
        daily_data = {}

    if current_date not in daily_data:
        daily_data[current_date] = {}

    slot = "morning" if now.hour < 17 else "evening"
    if slot not in daily_data[current_date]:
        show = pick_random_show()
        if show:
            daily_data[current_date][slot] = {
                "id": show["id"],
                "name": show["name"],
                "poster": show.get("poster"),
                "overview": show.get("overview", ""),
                "trailer_key": show.get("trailer_key")
            }
            with open(DAILY_FILE, "w") as f:
                json.dump(daily_data, f, indent=2)
            print(f"✅ Picked {slot} show:", show["name"])

def get_current_daily_show():
    try:
        with open(DAILY_FILE, "r") as f:
            daily_data = json.load(f)
    except FileNotFoundError:
        return None
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    slot = "morning" if now.hour < 17 else "evening"
    if current_date in daily_data and slot in daily_data[current_date]:
        return daily_data[current_date][slot]
    return None

# ---------------- Helper Functions ---------------- #
def compare_values(target, guess):
    def color(val1, val2):
        return "green" if val1 == val2 else "gray"
    def arrow(num1, num2):
        if not (isinstance(num1, int) and isinstance(num2, int)):
            return ""
        return "⬆️" if num1 < num2 else ("⬇️" if num1 > num2 else "")
    return {
        "network": {"color": color(target["network"], guess["network"])},
        "first_air_year": {"color": color(target["first_air_year"], guess["first_air_year"]),
                           "arrow": arrow(int(guess["first_air_year"]), int(target["first_air_year"]))},
        "genre": {"color": color(target["genre"], guess["genre"])},
        "number_of_seasons": {"color": color(target["number_of_seasons"], guess["number_of_seasons"]),
                              "arrow": arrow(int(guess["number_of_seasons"]), int(target["number_of_seasons"]))},
        "status": {"color": color(target["status"], guess["status"])}
    }

# ---------------- Routes ---------------- #
@app.route("/", methods=["GET", "POST"])
def index():
    daily_game = get_current_daily_show()
    if not daily_game:
        update_daily_games()
        daily_game = get_current_daily_show()
    if not daily_game:
        return "No daily show available. Try again later."

    if "guesses" not in session:
        session["guesses"] = []
        session["winner"] = False

    guesses = session["guesses"]
    winner = session.get("winner", False)

    # Fetch target details
    details = requests.get(
        f"https://api.themoviedb.org/3/tv/{daily_game['id']}?api_key={TMDB_KEY}&language=en-US"
    ).json()
    genres = details.get("genres", [])
    main_genre = genres[0]["name"] if genres else "Unknown"
    poster_path = details.get("poster_path", "") or daily_game.get("poster")
    poster_to_show = poster_path if poster_path and not looks_like_logo(poster_path) else ""

    # Prefer stored trailer_key (update_daily_games ensured it exists). Fallback to fetching videos.
    trailer_key = daily_game.get("trailer_key")
    if not trailer_key:
        videos = requests.get(
            f"https://api.themoviedb.org/3/tv/{daily_game['id']}/videos?api_key={TMDB_KEY}&language=en-US"
        ).json()
        trailer_key = next((v["key"] for v in videos.get("results", []) if v["type"] == "Trailer"), None)

    target = {
        "title": details.get("name"),
        "network": details["networks"][0]["name"] if details.get("networks") else "Unknown",
        "first_air_year": details.get("first_air_date", "????")[:4],
        "genre": main_genre,
        "number_of_seasons": details.get("number_of_seasons", "?"),
        "status": details.get("status", "Unknown"),
        "poster": poster_to_show,
        "trailer": f"https://www.youtube.com/embed/{trailer_key}" if trailer_key else None
    }

    game_over = len(guesses) >= MAX_GUESSES or winner

    if request.method == "POST":
        guess_title = request.form["guess"].strip()
        params = {"api_key": TMDB_KEY, "query": guess_title, "language": "en-US"}
        res = requests.get("https://api.themoviedb.org/3/search/tv", params=params).json()
        if not res.get("results"):
            return render_template("index.html", message="❌ No show found.",
                                   guesses=guesses, target=target, winner=winner,
                                   game_over=game_over, trailer_url=None, max_guesses=MAX_GUESSES,
                                   logo_url=logo_url, blank_image_url=blank_image_url)
        results = res.get("results", [])

        # Find the first English result from the search results
        chosen = None
        for s in results:
            # Prefer checking original_language if present (fast)
            if s.get("original_language", "").lower() == "en":
                chosen = s
                break
            # Otherwise fetch details and check spoken_languages (rare)
            details_guess_tmp = requests.get(
                f"https://api.themoviedb.org/3/tv/{s['id']}?api_key={TMDB_KEY}&language=en-US"
            ).json()
            if is_english_from_details(details_guess_tmp):
                chosen = s
                break

        if not chosen:
            return render_template("index.html", message="❌ No English show found.",
                                   guesses=guesses, target=target, winner=winner,
                                   game_over=game_over, trailer_url=None, max_guesses=MAX_GUESSES,
                                   logo_url=logo_url, blank_image_url=blank_image_url)

        show = chosen
        details_guess = requests.get(
            f"https://api.themoviedb.org/3/tv/{show['id']}?api_key={TMDB_KEY}&language=en-US"
        ).json()
        # Double-check it's English (safety)
        if not is_english_from_details(details_guess):
            return render_template("index.html", message="❌ No English show found.",
                                   guesses=guesses, target=target, winner=winner,
                                   game_over=game_over, trailer_url=None, max_guesses=MAX_GUESSES,
                                   logo_url=logo_url, blank_image_url=blank_image_url)

        genres_guess = details_guess.get("genres", [])
        main_genre_guess = genres_guess[0]["name"] if genres_guess else "Unknown"
        guess_data = {
            "title": details_guess.get("name"),
            "network": details_guess["networks"][0]["name"] if details_guess.get("networks") else "Unknown",
            "first_air_year": details_guess.get("first_air_date", "????")[:4],
            "genre": main_genre_guess,
            "number_of_seasons": details_guess.get("number_of_seasons", "?"),
            "status": details_guess.get("status", "Unknown"),
        }
        compare = compare_values(target, guess_data)
        guesses.append({"guess": guess_data, "compare": compare})
        session["guesses"] = guesses

        if guess_data["title"].lower() == target["title"].lower():
            session["winner"] = True
            winner = True

        game_over = len(guesses) >= MAX_GUESSES or winner

        if game_over:
            videos = requests.get(
                f"https://api.themoviedb.org/3/tv/{daily_game['id']}/videos?api_key={TMDB_KEY}&language=en-US"
            ).json()
            trailer_key = next((v["key"] for v in videos.get("results", []) if v["type"] == "Trailer"), None)
            target["trailer"] = f"https://www.youtube.com/embed/{trailer_key}" if trailer_key else None

    # Final render — always pass logo_url and blank_image_url so template can set social meta to a tiny blank image
    return render_template("index.html",
                           guesses=guesses, target=target, winner=winner,
                           game_over=game_over, trailer_url=target.get("trailer"),
                           max_guesses=MAX_GUESSES, logo_url=logo_url, blank_image_url=blank_image_url)


@app.route("/reset")
def reset():
    session.clear()
    return redirect(url_for("index"))


@app.route("/autocomplete")
def autocomplete():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"results": []})
    params = {
        "api_key": TMDB_KEY,
        "query": query,
        "language": "en-US",
        "include_adult": "false"
    }
    res = requests.get("https://api.themoviedb.org/3/search/tv", params=params).json()
    results = []
    # Filter autocomplete results to English-language shows (using original_language where available)
    for s in res.get("results", [])[:50]:
        if s.get("original_language", "").lower() != "en":
            continue
        year = s.get("first_air_date", "")[:4] if s.get("first_air_date") else "N/A"
        results.append({"name": s["name"], "year": year})
        if len(results) >= 20:
            break
    return jsonify({"results": results})


@app.route("/add_leader", methods=["POST"])
def add_leader():
    return jsonify({"success": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5005))
    app.run(host="0.0.0.0", port=port)