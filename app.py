from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import requests
import random

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

API_KEY = "26d79b573974be9e3561d7ed1dc8e085"
MAX_GUESSES = 6

US_MAIN_NETWORKS = [
    "ABC", "NBC", "CBS", "FOX", "The CW", "PBS",
    "HBO", "Showtime", "AMC", "USA Network", "FX", "TNT",
    "Netflix", "Hulu", "Disney+", "Amazon Prime Video", "Apple TV+",
    "Peacock", "Paramount+", "HBO Max"
]

def get_random_show():
    while True:
        page = random.randint(1, 50)
        url = f"https://api.themoviedb.org/3/tv/popular?api_key={API_KEY}&language=en-US&page={page}"
        data = requests.get(url).json()
        eligible_shows = [s for s in data["results"] if s.get("vote_count",0) > 1000]
        if not eligible_shows:
            continue
        show = random.choice(eligible_shows)
        detail_url = f"https://api.themoviedb.org/3/tv/{show['id']}?api_key={API_KEY}&language=en-US"
        show_detail = requests.get(detail_url).json()
        us_networks = [n for n in show_detail.get("networks", []) if n.get("name") in US_MAIN_NETWORKS]
        if not us_networks:
            continue
        return {
            "id": show_detail['id'],
            "name": show_detail.get("name", "Unknown"),
            "poster": show_detail.get("poster_path"),
            "backdrop": show_detail.get("backdrop_path"),
            "network": us_networks[0]["name"],
            "first_air_year": show_detail.get("first_air_date", "????")[:4],
            "genre": show_detail.get("genres")[0]["name"] if show_detail.get("genres") else "Unknown",
            "number_of_seasons": show_detail.get("number_of_seasons", "Unknown"),
            "status": show_detail.get("status", "Unknown"),
        }

def search_show(title):
    url = f"https://api.themoviedb.org/3/search/tv?api_key={API_KEY}&query={title}"
    data = requests.get(url).json()
    if not data["results"]:
        return None
    for s in data["results"]:
        if s["name"].lower() == title.lower():
            detail_url = f"https://api.themoviedb.org/3/tv/{s['id']}?api_key={API_KEY}&language=en-US"
            show_detail = requests.get(detail_url).json()
            us_networks = [n for n in show_detail.get("networks", []) if n.get("name") in US_MAIN_NETWORKS]
            network_name = us_networks[0]["name"] if us_networks else (show_detail["networks"][0]["name"] if show_detail.get("networks") else "Unknown")
            return {
                "id": show_detail['id'],
                "name": show_detail.get("name", "Unknown"),
                "poster": show_detail.get("poster_path"),
                "backdrop": show_detail.get("backdrop_path"),
                "network": network_name,
                "first_air_year": show_detail.get("first_air_date", "????")[:4],
                "genre": show_detail.get("genres")[0]["name"] if show_detail.get("genres") else "Unknown",
                "number_of_seasons": show_detail.get("number_of_seasons", "Unknown"),
                "status": show_detail.get("status", "Unknown"),
            }
    return None

def compare_shows(target, guess):
    result = {}
    for field in ["network","first_air_year","genre","number_of_seasons","status"]:
        if field=="genre":
            result[field] = {"color": "green" if guess["genre"] == target["genre"] else "gray", "arrow": ""}
        elif field=="first_air_year":
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
        elif field=="number_of_seasons":
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
            trailer_url = f"https://www.youtube.com/embed/{video['key']}"
            print("Trailer URL:", trailer_url)  # debug
            return trailer_url
    print("No trailer found for show_id", show_id)
    return None

@app.route("/", methods=["GET","POST"])
def index():
    if "target" not in session:
        session["target"] = get_random_show()
    if "guesses" not in session:
        session["guesses"] = []

    target = session["target"]
    winner = False
    message = None

    if request.method == "POST":
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

    trailer_url = get_trailer(target["id"])

    return render_template(
        "index.html",
        target=target,
        guesses=session["guesses"],
        winner=winner,
        message=message,
        max_guesses=MAX_GUESSES,
        trailer_url=trailer_url
    )

@app.route("/autocomplete")
def autocomplete():
    query = request.args.get("q","")
    if not query:
        return jsonify({"results":[]})
    url = f"https://api.themoviedb.org/3/search/tv?api_key={API_KEY}&query={query}"
    data = requests.get(url).json()
    suggestions = []
    for show in data.get("results", [])[:10]:
        year = show.get("first_air_date","")[:4] or "????"
        suggestions.append({"name": show['name'], "year": year})
    return jsonify({"results": suggestions})

@app.route("/reset")
def reset():
    session.pop("target", None)
    session.pop("guesses", None)
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True, port=5005)
