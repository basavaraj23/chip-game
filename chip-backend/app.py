from flask import Flask, jsonify, request
app = Flask(__name__)

@app.get("/healthz")
def healthz(): return "ok", 200

@app.get("/livez")
def livez(): return "alive", 200

@app.post("/api/collect")
def collect():
    data = request.json or {}
    player = data.get("player", "You")
    chips = int(data.get("chips", 1))
    return jsonify({"message": f"{player} collected {chips} chips!"})

@app.get("/api/leaderboard")
def leaderboard():
    return jsonify([{"player":"Alice","chips":10},{"player":"Bob","chips":7},{"player":"Charlie","chips":5}])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
