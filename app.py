from pathlib import Path

from flask import Flask, redirect, render_template, jsonify, request, url_for
import pandas as pd
from config import Config
from crea_aula import crear_archivo_dat

# Cliente oficial de Anthropic (se usa únicamente si hay API key configurada)
try:
    import anthropic
except ImportError:
    anthropic = None
    
DELIMITADOR=";"
NOMBRE_ARCHIVO = "aula.dat"

def cargar_dataframe(nombre_archivo:str):
    """Carga el archivo .dat en un DataFrame de pandas."""
    df = pd.read_csv(nombre_archivo, sep=DELIMITADOR, encoding="utf-8")
    return df
 
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # ------------------------------------------------------------------
    # Rutas de páginas
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        return render_template(
            "index.html",
            app_name=app.config["APP_NAME"],
            tagline=app.config["APP_TAGLINE"],
            aula_creada=request.args.get("aula_creada") == "1",
        )

    @app.route("/crear-aula", methods=["POST"])
    def crear_aula():
        crear_archivo_dat(str(Path(app.root_path) / NOMBRE_ARCHIVO))
        return redirect(url_for("index", aula_creada=1))

    @app.route("/aulas")
    def aulas():
        # Placeholder: aquí se listarán las aulas inteligentes registradas
        df_aula = cargar_dataframe("aulas.dat")
        
        aulas_demo = [
            {"nombre": "Aula 101 - Matemáticas", "estado": "Activa", "estudiantes": 28},
            {"nombre": "Aula 205 - Ciencias",     "estado": "Activa", "estudiantes": 24},
            {"nombre": "Aula 310 - Idiomas",       "estado": "En pausa", "estudiantes": 19},
        ]
        return render_template("index.html",
                                app_name=app.config["APP_NAME"],
                                tagline=app.config["APP_TAGLINE"],
                                aulas=aulas_demo)

    # ------------------------------------------------------------------
    # API: asistente de IA (Claude)
    # ------------------------------------------------------------------
    @app.route("/api/asistente", methods=["POST"])
    def asistente():
        """
        Recibe un mensaje del usuario y responde usando la API de Claude.
        Requiere ANTHROPIC_API_KEY configurada en el archivo .env
        """
        data = request.get_json(silent=True) or {}
        mensaje = data.get("mensaje", "").strip()

        if not mensaje:
            return jsonify({"error": "El campo 'mensaje' es requerido."}), 400

        if not app.config["ANTHROPIC_API_KEY"] or anthropic is None:
            return jsonify({
                "respuesta": "El asistente de IA aún no está configurado. "
                             "Agrega tu ANTHROPIC_API_KEY en el archivo .env para activarlo."
            })

        try:
            client = anthropic.Anthropic(api_key=app.config["ANTHROPIC_API_KEY"])
            respuesta = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                messages=[{"role": "user", "content": mensaje}],
            )
            texto = "".join(
                bloque.text for bloque in respuesta.content if bloque.type == "text"
            )
            return jsonify({"respuesta": texto})
        except Exception as exc:  # pragma: no cover - manejo simple de errores
            return jsonify({"error": f"Error al conectar con Claude: {exc}"}), 500

    # ------------------------------------------------------------------
    # Salud del servicio
    # ------------------------------------------------------------------
    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "app": app.config["APP_NAME"]})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config["PORT"], debug=app.config["DEBUG"])
