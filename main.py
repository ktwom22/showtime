from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import requests
import random
import json
import os
import os


app = Flask(__name__)
app.secret_key = "your_secret_key_here"

API_KEY = os.getenv("API_KEY")
MAX_GUESSES = 6
LEADERBOARD_FILE = "leaderboard.json"

US_MAIN_NETWORKS = [
    "ABC", "NBC", "CBS", "FOX", "The CW", "PBS",
    "HBO", "Showtime", "AMC", "USA Network", "FX", "TNT",
    "Netflix", "Hulu", "Disney+", "Amazon Prime Video", "Apple TV+",
    "Peacock", "Paramount+", "HBO Max"
]

# ----- Leaderboard -----
def load_leaderboard():
    if not os.path.exists(LEADERBOARD_FILE):
        return []
    with open(LEADERBOARD_FILE, "r") as f:
        return json.load(f)

def save_leaderboard(data):
    with open(LEADERBOARD_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ----- API Helpers -----
def get_random_show():
    while True:
        page = random.randint(1, 40)
        url = f"https://api.themoviedb.org/3/tv/popular?api_key={API_KEY}&language=en-US&page={page}"
        data = requests.get(url).json()
        shows = [s for s in data["results"] if s.get("vote_count", 0) > 1000]
        if not shows:
            continue
        show = random.choice(shows)
        detail_url = f"https://api.themoviedb.org/3/tv/{show['id']}?api_key={API_KEY}&language=en-US"
        details = requests.get(detail_url).json()

        us_networks = [n for n in details.get("networks", []) if n.get("name") in US_MAIN_NETWORKS]
        if not us_networks:
            continue

        return {
            "id": details["id"],
            "name": details.get("name", "Unknown"),
            "poster": details.get("poster_path"),
            "network": us_networks[0]["name"],
            "first_air_year": details.get("first_air_date", "????")[:4],
            "genre": details.get("genres")[0]["name"] if details.get("genres") else "Unknown",
            "number_of_seasons": details.get("number_of_seasons", "Unknown"),
            "status": details.get("status", "Unknown"),
        }

def search_show(title):
    url = f"https://api.themoviedb.org/3/search/tv?api_key={API_KEY}&query={title}"
    data = requests.get(url).json()
    if not data["results"]:
        return None
    for s in data["results"]:
        if s["name"].lower() == title.lower():
            detail_url = f"https://api.themoviedb.org/3/tv/{s['id']}?api_key={API_KEY}&language=en-US"
            details = requests.get(detail_url).json()
            us_networks = [n for n in details.get("networks", []) if n.get("name") in US_MAIN_NETWORKS]
            network_name = us_networks[0]["name"] if us_networks else (
                details["networks"][0]["name"] if details.get("networks") else "Unknown"
            )
            return {
                "id": details["id"],
                "name": details.get("name", "Unknown"),
                "poster": details.get("poster_path"),
                "network": network_name,
                "first_air_year": details.get("first_air_date", "????")[:4],
                "genre": details.get("genres")[0]["name"] if details.get("genres") else "Unknown",
                "number_of_seasons": details.get("number_of_seasons", "Unknown"),
                "status": details.get("status", "Unknown"),
            }
    return None

def compare_shows(target, guess):
    result = {}
    for field in ["network","first_air_year","genre","number_of_seasons","status"]:
        if field in ["first_air_year","number_of_seasons"]:
            color = "green" if guess[field] == target[field] else "gray"
            arrow = ""
            try:
                guess_val = int(guess[field])
                target_val = int(target[field])
                if guess_val < target_val:
                    arrow = "↑"
                elif guess_val > target_val:
                    arrow = "↓"
            except:
                arrow = ""
            result[field] = {"color": color, "arrow": arrow}
        else:
            result[field] = {"color": "green" if guess[field] == target[field] else "gray", "arrow": ""}
    return result

def get_trailer(show_id):
    url = f"https://api.themoviedb.org/3/tv/{show_id}/videos?api_key={API_KEY}&language=en-US"
    data = requests.get(url).json()
    for video in data.get("results", []):
        if video["site"].lower() == "youtube" and video["type"].lower() == "trailer":
            return f"https://www.youtube.com/embed/{video['key']}"
    return None

# ----- Routes -----
@app.route("/", methods=["GET","POST"])
def index():
    if "target" not in session:
        session["target"] = get_random_show()
    if "guesses" not in session:
        session["guesses"] = []

    target = session["target"]
    winner = False
    message = None

    if request.method == "POST" and "guess" in request.form:
        guess_title = request.form["guess"].strip()
        guess = search_show(guess_title)
        if not guess:
            message = "❌ No show found."
        else:
            comparison = compare_shows(target, guess)
            guesses = session.get("guesses", [])
            guesses.append({"guess": guess, "compare": comparison})
            session["guesses"] = guesses

            if guess["name"].lower() == target["name"].lower():
                winner = True
                message = f"🎉 Correct! It was {target['name']}!"

    game_over = winner or len(session.get("guesses", [])) >= MAX_GUESSES
    trailer_url = get_trailer(target["id"]) if game_over else None
    leaderboard = load_leaderboard()

    return render_template(
        "index.html",
        target=target,
        guesses=session["guesses"],
        winner=winner,
        message=message,
        max_guesses=MAX_GUESSES,
        trailer_url=trailer_url,
        game_over=game_over,
        leaderboard=leaderboard
    )

@app.route("/autocomplete")
def autocomplete():
    query = request.args.get("q", "")
    if not query:
        return jsonify({"results": []})
    url = f"https://api.themoviedb.org/3/search/tv?api_key={API_KEY}&query={query}"
    data = requests.get(url).json()
    results = []
    for s in data.get("results", [])[:10]:
        year = s.get("first_air_date", "")[:4] or "????"
        results.append({"name": s["name"], "year": year})
    return jsonify({"results": results})

@app.route("/add_leader", methods=["POST"])
def add_leader():
    data = request.get_json()
    name = data.get("player_name", "Unknown")
    guesses = data.get("guesses", 0)

    leaderboard = load_leaderboard()
    leaderboard.append({"name": name, "guesses": guesses})
    leaderboard = sorted(leaderboard, key=lambda x: x["guesses"])[:10]
    save_leaderboard(leaderboard)
    return jsonify({"status": "ok"})

@app.route("/reset")
def reset():
    session.pop("target", None)
    session.pop("guesses", None)
    return redirect(url_for("index"))

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

