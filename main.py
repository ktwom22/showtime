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
TMDB_KEY = "26d79b573974be9e3561d7ed1dc8e085"

MAX_GUESSES = 6
DAILY_FILE = "daily_games.json"

ALLOWED_NETWORKS = [
    "ABC", "NBC", "CBS", "FOX", "The CW",
    "Netflix", "Hulu", "Disney+", "HBO Max", "Prime Video", "Apple TV+",
    "AMC", "FX", "USA Network", "Syfy", "Showtime", "Starz", "TNT", "BBC America"
]

# ----------------- Helpers ----------------- #
def is_english(details):
    if not details:
        return False
    if details.get("original_language", "").lower() == "en":
        return True
    for lang in details.get("spoken_languages", []):
        iso = lang.get("iso_639_1", "")
        if iso.lower() == "en":
            return True
    return False

def pick_random_show():
    """
    Try multiple TMDB pages; if nothing acceptable, return fallback show.
    """
    try:
        for attempt in range(50):
            page = random.randint(1, 10)
            res = requests.get(
                "https://api.themoviedb.org/3/tv/popular",
                params={"api_key": TMDB_KEY, "language": "en-US", "page": page},
                timeout=8
            )
            if res.status_code != 200:
                # log and continue
                print("TMDB /tv/popular error", res.status_code, res.text)
                continue
            shows = res.json().get("results", [])
            random.shuffle(shows)
            for show in shows:
                show_id = show.get("id")
                if not show_id:
                    continue
                details_res = requests.get(
                    f"https://api.themoviedb.org/3/tv/{show_id}",
                    params={"api_key": TMDB_KEY, "language": "en-US"},
                    timeout=8
                )
                if details_res.status_code != 200:
                    continue
                details = details_res.json()
                if not is_english(details):
                    continue
                networks = [n.get("name") for n in details.get("networks", []) if n.get("name")]
                # require some network info (loose)
                if not networks:
                    continue
                videos_res = requests.get(
                    f"https://api.themoviedb.org/3/tv/{show_id}/videos",
                    params={"api_key": TMDB_KEY, "language": "en-US"},
                    timeout=8
                )
                if videos_res.status_code != 200:
                    continue
                videos = videos_res.json().get("results", [])
                trailer_key = next(
                    (v["key"] for v in videos if v.get("type","").lower() == "trailer" and v.get("site","").lower() == "youtube"),
                    None
                )
                if trailer_key:
                    return {
                        "id": show_id,
                        "name": show.get("name"),
                        "poster": show.get("poster_path"),
                        "trailer_key": trailer_key
                    }
        # fallback
        return {
            "id": 1399,
            "name": "Game of Thrones",
            "poster": "/u3bZgnGQ9T01sWNhyveQz0wH0Hl.jpg",
            "trailer_key": "giYeaKsXnsI"
        }
    except Exception as e:
        print("pick_random_show error:", e)
        return {
            "id": 1399,
            "name": "Game of Thrones",
            "poster": "/u3bZgnGQ9T01sWNhyveQz0wH0Hl.jpg",
            "trailer_key": "giYeaKsXnsI"
        }

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
            daily_data[current_date][slot] = show
            with open(DAILY_FILE, "w") as f:
                json.dump(daily_data, f, indent=2)
            print("Saved daily show:", show["name"])

def get_current_daily_show():
    try:
        with open(DAILY_FILE, "r") as f:
            daily_data = json.load(f)
    except FileNotFoundError:
        return None
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    slot = "morning" if now.hour < 17 else "evening"
    return daily_data.get(current_date, {}).get(slot)

def compare_values(target, guess):
    def color(val1, val2):
        return "green" if val1 == val2 else "gray"
    def arrow(num1, num2):
        try:
            n1 = int(num1)
            n2 = int(num2)
        except:
            return ""
        return "⬆️" if n1 < n2 else ("⬇️" if n1 > n2 else "")
    return {
        "network": {"color": color(target["network"], guess["network"])},
        "first_air_year": {"color": color(target["first_air_year"], guess["first_air_year"]),
                           "arrow": arrow(guess["first_air_year"], target["first_air_year"])},
        "genre": {"color": color(target["genre"], guess["genre"])},
        "number_of_seasons": {"color": color(target["number_of_seasons"], guess["number_of_seasons"]),
                              "arrow": arrow(guess["number_of_seasons"], target["number_of_seasons"])},
        "status": {"color": color(target["status"], guess["status"])}
    }

def build_target_from_details(details, daily_game):
    return {
        "title": details.get("name"),
        "network": details["networks"][0]["name"] if details.get("networks") else "Unknown",
        "first_air_year": (details.get("first_air_date") or "????")[:4],
        "genre": (details.get("genres") or [{}])[0].get("name", "Unknown"),
        "number_of_seasons": details.get("number_of_seasons", "?"),
        "status": details.get("status", "Unknown"),
        "poster": daily_game.get("poster"),
        "trailer": f"https://www.youtube.com/embed/{daily_game['trailer_key']}" if daily_game.get("trailer_key") else None
    }

# ----------------- Routes ----------------- #
@app.route("/", methods=["GET"])
def index():
    daily_game = get_current_daily_show()
    if not daily_game:
        update_daily_games()
        daily_game = get_current_daily_show()
    if not daily_game:
        return "No daily show available. Check TMDB key or logs.", 500

    if "guesses" not in session:
        session["guesses"] = []
        session["winner"] = False

    guesses = session.get("guesses", [])
    winner = session.get("winner", False)

    # Fetch live details for target
    details_res = requests.get(
        f"https://api.themoviedb.org/3/tv/{daily_game['id']}",
        params={"api_key": TMDB_KEY, "language": "en-US"},
        timeout=8
    )
    details = details_res.json() if details_res.status_code == 200 else {}
    target = build_target_from_details(details, daily_game)

    game_over = len(guesses) >= MAX_GUESSES or winner

    return render_template("index.html",
                           guesses=guesses,
                           target=target,
                           winner=winner,
                           game_over=game_over,
                           max_guesses=MAX_GUESSES)

@app.route("/guess", methods=["POST"])
def guess():
    try:
        daily_game = get_current_daily_show()
        if not daily_game:
            update_daily_games()
            daily_game = get_current_daily_show()
        if not daily_game:
            return jsonify({"error": "No daily show available"}), 500

        data = request.form or request.get_json() or {}
        guess_title = (data.get("guess") or "").strip()
        if not guess_title:
            return jsonify({"error": "Empty guess"}), 400

        # Search TMDB for guess
        search_res = requests.get(
            "https://api.themoviedb.org/3/search/tv",
            params={"api_key": TMDB_KEY, "query": guess_title, "language": "en-US", "include_adult": "false"},
            timeout=8
        )
        if search_res.status_code != 200:
            print("TMDB search failed", search_res.status_code, search_res.text)
            return jsonify({"error": "TMDB search failed"}), 500

        results = search_res.json().get("results", [])
        if not results:
            return jsonify({"error": "No shows found for that guess"}), 404

        show = results[0]
        details_guess_res = requests.get(
            f"https://api.themoviedb.org/3/tv/{show['id']}",
            params={"api_key": TMDB_KEY, "language": "en-US"},
            timeout=8
        )
        details_guess = details_guess_res.json() if details_guess_res.status_code == 200 else {}

        guess_data = {
            "title": details_guess.get("name") or show.get("name"),
            "network": details_guess.get("networks", [{}])[0].get("name", "Unknown"),
            "first_air_year": (details_guess.get("first_air_date") or "????")[:4],
            "genre": (details_guess.get("genres") or [{}])[0].get("name", "Unknown"),
            "number_of_seasons": details_guess.get("number_of_seasons", "?"),
            "status": details_guess.get("status", "Unknown"),
        }

        # Build target for comparison
        details_target_res = requests.get(
            f"https://api.themoviedb.org/3/tv/{daily_game['id']}",
            params={"api_key": TMDB_KEY, "language": "en-US"},
            timeout=8
        )
        details_target = details_target_res.json() if details_target_res.status_code == 200 else {}
        target = build_target_from_details(details_target, daily_game)

        compare = compare_values(target, guess_data)

        guesses = session.get("guesses", [])
        guesses.append({"guess": guess_data, "compare": compare})
        session["guesses"] = guesses
        session.modified = True

        if guess_data["title"].lower() == target["title"].lower():
            session["winner"] = True
            session.modified = True

        winner = session.get("winner", False)
        game_over = len(guesses) >= MAX_GUESSES or winner

        remaining = max(0, MAX_GUESSES - len(guesses))
        blur_level = (20 * remaining * remaining) // (MAX_GUESSES * MAX_GUESSES)

        return jsonify({
            "guesses": guesses,
            "winner": winner,
            "game_over": game_over,
            "target": target,
            "blur_level": 0 if winner else blur_level
        })
    except Exception as e:
        import traceback
        print("❌ ERROR IN /guess ROUTE:", e)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/autocomplete")
def autocomplete():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"results": []})
    res = requests.get(
        "https://api.themoviedb.org/3/search/tv",
        params={"api_key": TMDB_KEY, "query": query, "language": "en-US", "include_adult": "false"},
        timeout=8
    )
    if res.status_code != 200:
        return jsonify({"results": []})
    results = []
    for s in res.json().get("results", [])[:50]:
        if s.get("original_language", "").lower() != "en":
            continue
        year = (s.get("first_air_date") or "")[:4] if s.get("first_air_date") else "N/A"
        results.append({"name": s.get("name"), "year": year})
        if len(results) >= 20:
            break
    return jsonify({"results": results})

@app.route("/reset")
def reset():
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, debug=True)
