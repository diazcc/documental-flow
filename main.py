import os
import json
from flask import Flask, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore, auth
from flask_cors import CORS

app = Flask(__name__)

cloudinary.config(
    cloud_name="tu_cloud_name",
    api_key="tu_api_key",
    api_secret="tu_api_secret"
)

# ✅ CORS configurado para tu frontend local y desplegado
CORS(app, resources={r"/*": {"origins": ["http://localhost:5173", "https://portfolio-d0ea2.web.app"]}})

# ✅ Inicializar Firebase
firebase_config = os.getenv("FIREBASE_SERVICE_ACCOUNT")

if not firebase_config:
    raise ValueError("FIREBASE_SERVICE_ACCOUNT no está configurada en las variables de entorno.")

cred = credentials.Certificate(json.loads(firebase_config))
firebase_admin.initialize_app(cred)

db = firestore.client()

# ✅ Endpoint principal
@app.route("/")
def home():
    return jsonify({"message": "Servidor funcionando correctamente 🚀"})
    
@app.route("/upload-pdf", methods=["POST"])
def upload_pdf():
    try:
        # El archivo llega desde el Front (form-data)
        file = request.files["file"]

        # Subir a Cloudinary (como archivo RAW, no imagen)
        upload_result = cloudinary.uploader.upload(
            file,
            resource_type="raw"  # 👈 necesario para PDF
        )

        return jsonify({
            "message": "Archivo subido correctamente",
            "url": upload_result["secure_url"]
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400
# ✅ Obtener todos los usuarios (solo lectura)
@app.route("/users", methods=["GET"])
def get_users():
    users_ref = db.collection("users")
    docs = users_ref.stream()
    users = [doc.to_dict() for doc in docs]
    return jsonify(users)

# ✅ Crear usuario (registro)
@app.route("/signup", methods=["POST"])
def signup():
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")
        name = data.get("name")

        if not email or not password:
            return jsonify({"error": "Email y password son requeridos"}), 400

        # 🔥 Crear usuario en Firebase Authentication
        user = auth.create_user(
            email=email,
            password=password,
            display_name=name
        )

        # 🔥 Guardar datos adicionales en Firestore
        db.collection("users").document(user.uid).set({
            "uid": user.uid,
            "name": name,
            "email": email,
            "created_at": firestore.SERVER_TIMESTAMP
        })

        return jsonify({"message": "Usuario creado correctamente", "uid": user.uid}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ✅ Iniciar sesión (login)
@app.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            return jsonify({"error": "Email y password son requeridos"}), 400

        # ⚠️ Firebase Admin SDK no permite autenticar con contraseña directamente
        # Esto se debe hacer desde el frontend usando Firebase JS SDK
        return jsonify({
            "message": "El login debe realizarse desde el frontend con Firebase Auth. Luego envía el ID token al backend."
        }), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ✅ Verificar token enviado por el frontend
@app.route("/verify_token", methods=["POST"]) 
def verify_token():
    try:
        data = request.get_json()
        id_token = data.get("id_token")

        if not id_token:
            return jsonify({"error": "Falta id_token"}), 400

        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token["uid"]
        return jsonify({"message": "Token válido", "uid": uid}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 401


# ✅ Cerrar sesión (logout)
@app.route("/logout", methods=["POST"])
def logout():
    # En Firebase, el cierre de sesión se hace en el frontend eliminando el token local.
    # Aquí puedes invalidar tokens si quieres forzar cierre desde el backend.
    return jsonify({"message": "Sesión cerrada correctamente (client-side)"}), 200


# ✅ Ejecutar servidor
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
