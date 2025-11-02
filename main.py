import os
import json
import jwt
import datetime
from flask import Flask, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["http://localhost:5173", "https://portfolio-d0ea2.web.app"]}})

# 🔐 Clave secreta para JWT (puedes ponerla como variable de entorno también)
app.config["SECRET_KEY"] = os.getenv("JWT_SECRET", "super_secret_key")

# 🔥 Configurar Firebase
firebase_config = os.getenv("FIREBASE_SERVICE_ACCOUNT")
if not firebase_config:
    raise ValueError("FIREBASE_SERVICE_ACCOUNT no está configurada en las variables de entorno.")

cred = credentials.Certificate(json.loads(firebase_config))
firebase_admin.initialize_app(cred)
db = firestore.client()

# ✅ Ruta de prueba
@app.route("/")
def home():
    return jsonify({"message": "Servidor funcionando correctamente 🚀"})

# 👤 Crear usuario
@app.route("/register", methods=["POST"])
def register_user():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    name = data.get("name")

    if not email or not password or not name:
        return jsonify({"error": "Todos los campos son obligatorios"}), 400

    # Verificar si ya existe
    users_ref = db.collection("users").where("email", "==", email).stream()
    if any(users_ref):
        return jsonify({"error": "El usuario ya existe"}), 409

    hashed_password = generate_password_hash(password)

    # Crear usuario en Firestore
    user_data = {
        "email": email,
        "name": name,
        "password": hashed_password,
        "created_at": datetime.datetime.utcnow(),
    }
    db.collection("users").add(user_data)

    return jsonify({"message": "Usuario creado exitosamente"}), 201

# 🔑 Iniciar sesión
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    users_ref = db.collection("users").where("email", "==", email).stream()
    user_doc = next(users_ref, None)

    if not user_doc:
        return jsonify({"error": "Usuario no encontrado"}), 404

    user_data = user_doc.to_dict()
    if not check_password_hash(user_data["password"], password):
        return jsonify({"error": "Contraseña incorrecta"}), 401

    # Generar token JWT (expira en 1 hora)
    token = jwt.encode(
        {
            "email": email,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        },
        app.config["SECRET_KEY"],
        algorithm="HS256"
    )

    return jsonify({"token": token, "user": {"name": user_data["name"], "email": email}}), 200

# 🚪 Cerrar sesión (simple)
@app.route("/logout", methods=["POST"])
def logout():
    # En este ejemplo no hay sesión persistente, pero podrías invalidar tokens si los guardas en Firestore
    return jsonify({"message": "Sesión cerrada correctamente"}), 200

# 🧩 Proteger rutas (ejemplo)
@app.route("/profile", methods=["GET"])
def profile():
    token = request.headers.get("Authorization")
    if not token:
        return jsonify({"error": "Token requerido"}), 401

    try:
        decoded = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        email = decoded["email"]
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expirado"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Token inválido"}), 401

    # Buscar el usuario
    users_ref = db.collection("users").where("email", "==", email).stream()
    user_doc = next(users_ref, None)
    if not user_doc:
        return jsonify({"error": "Usuario no encontrado"}), 404

    return jsonify({"profile": user_doc.to_dict()}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
