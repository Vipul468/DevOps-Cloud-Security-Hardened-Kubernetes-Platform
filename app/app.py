from flask import Flask, jsonify

app = Flask(__name__)

@app.get("/")
def home():
    return jsonify(
        application="Security-Hardened Kubernetes Platform",
        status="running",
        message="Hello from Flask on Kubernetes"
    )

@app.get("/health")
def health():
    return jsonify(status="healthy"), 200

@app.get("/ready")
def ready():
    return jsonify(status="ready"), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
