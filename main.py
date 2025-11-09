import os
import json
from flask import Flask, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore, auth
from flask_cors import CORS
import cloudinary
import cloudinary.uploader  

app = Flask(__name__)
app.url_map.strict_slashes = False

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# ✅ CORS configurado para tu frontend local y desplegado
CORS(app,
     resources={r"/*": {"origins": ["http://localhost:5173", "https://portfolio-d0ea2.web.app"]}},
     supports_credentials=True,
     expose_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization", "Access-Control-Allow-Origin"],
     automatic_options=True 
)

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

def clean_firestore_data(data):
    """Convierte campos especiales de Firestore en JSON serializable."""
    if isinstance(data, list):
        return [clean_firestore_data(d) for d in data]
    elif isinstance(data, dict):
        clean = {}
        for k, v in data.items():
            if isinstance(v, firestore.SERVER_TIMESTAMP.__class__):
                clean[k] = None
            elif hasattr(v, "isoformat"):  # datetime
                clean[k] = v.isoformat()
            else:
                clean[k] = clean_firestore_data(v)
        return clean
    else:
        return data
# ✅ Obtener remitentes (remitters) del usuario autenticado
@app.route("/remitters", methods=["GET"])
def get_remitters():
    try:
        # 🧠 1️⃣ Obtener parámetros de búsqueda y paginación
        searched_value = request.args.get("searched_value", "").lower()
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 10))

        # 🧠 2️⃣ Obtener ID del usuario autenticado (puedes pasarlo por header Authorization o query)
        id_token = request.headers.get("Authorization")

        if not id_token:
            return jsonify({"error": "Falta token de autenticación"}), 401

        # 🔍 Verificar token y obtener UID
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token["uid"]

        # 🧠 3️⃣ Buscar al usuario en Firestore
        user_doc = db.collection("users").document(uid).get()

        if not user_doc.exists:
            return jsonify({"error": "Usuario no encontrado"}), 404

        user_data = user_doc.to_dict()
        remitters = user_data.get("remitters", [])

        # 🧠 4️⃣ Filtrar por búsqueda
        if searched_value:
            remitters = [
                r for r in remitters
                if searched_value in r.get("name", "").lower() or searched_value in r.get("email", "").lower()
            ]

        # 🧠 5️⃣ Paginación
        total = len(remitters)
        total_pages = (total + page_size - 1) // page_size
        start = (page - 1) * page_size
        end = start + page_size
        paginated_remitters = remitters[start:end]

        # 🧠 6️⃣ Responder
        return jsonify({
            "response": {
                "results": paginated_remitters,
                "total_pages": total_pages,
                "total_results": total
            }
        }), 200

    except Exception as e:
        print("🔥 Error en /remitters:", e)
        return jsonify({"error": str(e)}), 400

@app.route("/remitters", methods=["POST"])
def add_remitter():
    try:
        # 🔐 Verificar token del usuario
        id_token = request.headers.get("Authorization")
        if not id_token:
            return jsonify({"error": "Falta token"}), 401

        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token["uid"]

        # 📥 Datos del remitente nuevo
        data = request.get_json()
        name = data.get("name")
        email = data.get("email")

        if not name or not email:
            return jsonify({"error": "Faltan campos obligatorios (name, email)"}), 400

        # 📄 Buscar usuario en Firestore
        user_ref = db.collection("users").document(uid)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"error": "Usuario no encontrado"}), 404

        user_data = user_doc.to_dict()
        remitters = user_data.get("remitters", [])

        # 🚫 Validar si ya existe el remitente (por email)
        if any(r.get("email") == email for r in remitters):
            return jsonify({"error": "El remitente ya existe"}), 400

        # ✅ Agregar nuevo remitente
        new_remitter = {"name": name, "email": email}
        remitters.append(new_remitter)

        # 💾 Guardar de nuevo
        user_ref.update({"remitters": remitters})

        return jsonify({
            "message": "Remitente agregado correctamente",
            "remitter": new_remitter
        }), 201

    except Exception as e:
        print("🔥 Error en /remitters (POST):", e)
        return jsonify({"error": str(e)}), 400



    # ✅ Crear nueva solicitud (request)
@app.route("/request", methods=["POST"])
def create_request():
    try:
        # 🔒 Verificar token de autenticación (enviado en headers)
        id_token = request.headers.get("Authorization")
        if not id_token:
            return jsonify({"error": "Falta token de autenticación"}), 401

        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token["uid"]
        email_logged = decoded_token.get("email")

        # 🧾 Leer los campos del formulario
        subject = request.form.get("subject")
        user_asigned = request.form.get("user_asigned")

        if not subject or not user_asigned:
            return jsonify({
                "error": "Faltan campos obligatorios (subject, user_asigned)"
            }), 400

        # 🗂️ Subir documentos (pueden ser múltiples)
        uploaded_files = request.files.getlist("document")
        documents = []

        for file in uploaded_files:
            upload_result = cloudinary.uploader.upload(
                file,
                resource_type="auto"
            )
            documents.append({
                "name": file.filename,
                "url": upload_result.get("secure_url"),
                "observation": "",
                "status": "uploaded",
                "subject": subject
            })

        # 🧠 Verificar si el remitente ya existe (por correo)
        remitter_query = db.collection("users").where("email", "==", user_asigned).get()

        if not remitter_query:
            # Crear remitente básico (usuario no registrado aún)
            new_remitter = {
                "email": user_asigned,
                "role": "external",
                "status": "pending",
                "date_created": firestore.SERVER_TIMESTAMP,
                "remitters": []
            }
            db.collection("users").add(new_remitter)

        # 🕒 Crear el request
        doc_data = {
            "creator_user": email_logged,
            "creator_uid": uid,
            "date_created": firestore.SERVER_TIMESTAMP,
            "user_asigned": user_asigned,
            "subject": subject,
            "documents": documents
        }

        db.collection("request").add(doc_data)

        # 🧼 Limpiar los datos antes de responder
        doc_data_response = clean_firestore_data(doc_data)

        return jsonify({
            "message": "Solicitud creada correctamente",
            "data": doc_data_response
        }), 201

    except Exception as e:
        print("🔥 Error en /request:", e)
        return jsonify({"error": str(e)}), 400


# ✅ Permitir preflight para /request (CORS)


# ✅ Endpoint para listar requests visibles al usuario logueado
@app.route("/requests", methods=["GET", "OPTIONS"])
def get_requests():
    try:
        # 🔐 Verificar token
        id_token = request.headers.get("Authorization")
        if not id_token:
            return jsonify({"error": "Falta token"}), 401

        decoded_token = auth.verify_id_token(id_token)
        email_logged = decoded_token.get("email")

        # 🔍 Parámetros de búsqueda
        searched_value = request.args.get("searched_value", "").lower()
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 10))

        # 🔎 Traer todas las solicitudes donde el usuario sea creador o asignado
        requests_ref = db.collection("request")
        docs_creator = requests_ref.where("creator_user", "==", email_logged).stream()
        docs_assigned = requests_ref.where("user_asigned", "==", email_logged).stream()

        all_docs = list(docs_creator) + list(docs_assigned)

        # 🧩 Convertir a lista con ID incluido
        results = []
        for doc in all_docs:
            data = doc.to_dict()
            if searched_value in data.get("subject", "").lower():
                results.append({
                    "id": doc.id,  # 👈 incluimos el ID del documento
                    **clean_firestore_data(data)
                })

        # 🔢 Paginación
        start = (page - 1) * page_size
        end = start + page_size
        paginated_clean = [clean_firestore_data(r) for r in paginated]

        return jsonify({
            "response": {
                "results": paginated_clean,
                "total_results": total,
                "total_pages": total_pages
            }
        }), 200

    except Exception as e:
        print("🔥 Error en /requests:", e)
        return jsonify({"error": str(e)}), 400


    except Exception as e:
        print("🔥 Error en /requests:", e)
        return jsonify({"error": str(e)}), 400

@app.route("/requests-sent", methods=["GET", "OPTIONS"])
def get_requests_sent():
    if request.method == "OPTIONS":
        response = jsonify({"message": "CORS preflight OK"})
        response.headers.add("Access-Control-Allow-Origin", "http://localhost:5173")
        response.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        response.headers.add("Access-Control-Allow-Headers", "Authorization, Content-Type")
        return response, 200

    try:
        # 🔐 Token
        id_token = request.headers.get("Authorization")
        if not id_token:
            return jsonify({"error": "Falta token"}), 401

        decoded_token = auth.verify_id_token(id_token)
        email_logged = decoded_token.get("email")

        # 🔍 Filtros
        searched_value = request.args.get("searched_value", "").lower()
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 10))

        # 🔎 Consultar solo las solicitudes creadas por el usuario
        query = db.collection("request").where("creator_user", "==", email_logged).get()
        requests_sent = [doc.to_dict() for doc in query]

        # 🔎 Búsqueda
        if searched_value:
            requests_sent = [
                r for r in requests_sent
                if searched_value in r.get("subject", "").lower()
                or searched_value in r.get("user_asigned", "").lower()
            ]

        # 📄 Paginación
        total = len(requests_sent)
        total_pages = (total + page_size - 1) // page_size
        start = (page - 1) * page_size
        end = start + page_size
        paginated = requests_sent[start:end]

        return jsonify({
            "response": {
                "results": paginated,
                "total_results": total,
                "total_pages": total_pages
            }
        }), 200

    except Exception as e:
        print("🔥 Error en /requests-sent:", e)
        return jsonify({"error": str(e)}), 400


# ✅ Traer solicitudes RECIBIDAS (asignadas) al usuario (user_asigned == email)
@app.route("/requests-received", methods=["GET", "OPTIONS"])
def get_requests_received():
    if request.method == "OPTIONS":
        response = jsonify({"message": "CORS preflight OK"})
        response.headers.add("Access-Control-Allow-Origin", "http://localhost:5173")
        response.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        response.headers.add("Access-Control-Allow-Headers", "Authorization, Content-Type")
        return response, 200

    try:
        # 🔐 Token
        id_token = request.headers.get("Authorization")
        if not id_token:
            return jsonify({"error": "Falta token"}), 401

        decoded_token = auth.verify_id_token(id_token)
        email_logged = decoded_token.get("email")

        # 🔍 Filtros
        searched_value = request.args.get("searched_value", "").lower()
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 10))

        # 🔎 Consultar solo las solicitudes asignadas al usuario
        query = db.collection("request").where("user_asigned", "==", email_logged).get()
        requests_received = [doc.to_dict() for doc in query]

        # 🔎 Búsqueda
        if searched_value:
            requests_received = [
                r for r in requests_received
                if searched_value in r.get("subject", "").lower()
                or searched_value in r.get("creator_user", "").lower()
            ]

        # 📄 Paginación
        total = len(requests_received)
        total_pages = (total + page_size - 1) // page_size
        start = (page - 1) * page_size
        end = start + page_size
        paginated = requests_received[start:end]

        return jsonify({
            "response": {
                "results": paginated,
                "total_results": total,
                "total_pages": total_pages
            }
        }), 200

    except Exception as e:
        print("🔥 Error en /requests-received:", e)
        return jsonify({"error": str(e)}), 400

# ✅ Permitir preflight para /request (CORS)
@app.route("/request", methods=["OPTIONS"])
def request_options():
    return '', 204
@app.route("/check-connection", methods=["GET"])
def check_connection():
    try:
        # Prueba simple: leer una colección o simplemente verificar que Firestore responde
        db.collection("test_connection").document("ping").set({"ok": True})
        return jsonify({
            "status": "ok",
            "message": "Conexión con backend y Firestore exitosa 🚀"
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Error al conectar con Firestore",
            "error": str(e)
        }), 500

@app.route("/files", methods=["GET"])
def get_files():
    try:
        searched_value = request.args.get("searched_value", "").lower()
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 10))

        files_ref = db.collection("documents").order_by("created_at", direction=firestore.Query.DESCENDING)
        docs = files_ref.stream()

        # Convertir a lista
        all_files = [doc.to_dict() for doc in docs]

        # Filtrar por búsqueda
        if searched_value:
            all_files = [
                f for f in all_files
                if searched_value in f.get("document_name", "").lower()
            ]

        # Paginación
        total_files = len(all_files)
        total_pages = (total_files + page_size - 1) // page_size
        start = (page - 1) * page_size
        end = start + page_size

        paginated_files = all_files[start:end]

        return jsonify({
            "response": {
                "results": paginated_files,
                "total_pages": total_pages
            }
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/upload-pdf", methods=["POST"])
def upload_pdf():
    try:
        file = request.files["file"]

        upload_result = cloudinary.uploader.upload(
            file,
            resource_type="raw"
        )

        file_data = {
            "document_name": file.filename,
            "url": upload_result["secure_url"],
            "created_at": firestore.SERVER_TIMESTAMP
        }

        # 🧪 Debug
        print("Guardando en Firestore:", file_data)

        db.collection("documents").add(file_data)

        return jsonify({
            "message": "Archivo subido correctamente",
            "url": upload_result["secure_url"]
        }), 200

    except Exception as e:
        print("🔥 Error en upload_pdf:", e)
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

@app.route("/remitters", methods=["OPTIONS"])
def remitters_options():
    return '', 204

@app.route("/request", methods=["OPTIONS"])
def request_options():
    return '', 204

@app.route("/requests", methods=["OPTIONS"])
def requests_options():
    return '', 204
# ✅ Ejecutar servidor
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
