import os
import json
from flask import Flask, jsonify
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)

# Leer variable de entorno FIREBASE_SERVICE_ACCOUNT
firebase_config = os.getenv("FIREBASE_SERVICE_ACCOUNT")

if not firebase_config:
    raise ValueError("FIREBASE_SERVICE_ACCOUNT no está configurada en las variables de entorno.")

# Cargar las credenciales desde el JSON en formato string
cred = credentials.Certificate(json.loads(firebase_config))
firebase_admin.initialize_app(cred)

# Inicializar Firestore
db = firestore.client()

@app.route("/")
def home():
    return jsonify({"message": "Servidor funcionando correctamente 🚀"})

@app.route("/users")
def get_users():
    users_ref = db.collection("users")
    docs = users_ref.stream()
    users = [doc.to_dict() for doc in docs]
    return jsonify(users)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
