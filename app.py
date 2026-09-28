import calendar
import csv
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock

from flask import Flask, redirect, render_template, jsonify, request, url_for
import pandas as pd
from config import Config
from crea_aula import crear_archivo_dat
from reserva import buscar_reservas, guardar_reserva

# Cliente oficial de Anthropic (se usa únicamente si hay API key configurada)
try:
    import anthropic
except ImportError:
    anthropic = None
    
DELIMITADOR=";"
NOMBRE_ARCHIVO = "aula.dat"
FECHA_INICIO_CRONOGRAMA = date(2026, 9, 1)
FECHA_FIN_CRONOGRAMA = date(2028, 12, 31)

def cargar_dataframe(nombre_archivo:str):
    """Carga el archivo .dat en un DataFrame de pandas."""
    df = pd.read_csv(nombre_archivo, sep=DELIMITADOR, encoding="utf-8")
    return df
 
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    candado_reservas = Lock()

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
        df_aula = cargar_dataframe("aula.dat")
        
        df_aula["nombre"] = "Aula " + df_aula["AULA"].astype(str) + df_aula["SECCION"]
        
        lista_aulas = df_aula[["nombre", "UBICACION", "CAPACIDAD"]].to_dict(orient="records")
        
        #lista_aulas = [
        #    {"nombre": "Aula 101 - Matemáticas", "estado": "Activa", "estudiantes": 28},
        #    {"nombre": "Aula 205 - Ciencias",     "estado": "Activa", "estudiantes": 24},
        #    {"nombre": "Aula 310 - Idiomas",       "estado": "En pausa", "estudiantes": 19},
        #]
        return render_template("index.html",
                                app_name=app.config["APP_NAME"],
                                tagline=app.config["APP_TAGLINE"],
                                aulas=lista_aulas)

    @app.route("/reserva", methods=["GET", "POST"])
    def reserva_page():
        manana = max(date.today(), FECHA_INICIO_CRONOGRAMA)
        while manana.weekday() == 6:
            manana += timedelta(days=1)
        if manana > FECHA_FIN_CRONOGRAMA:
            manana = FECHA_FIN_CRONOGRAMA
        valores = {
            "fecha_inicio": request.form.get("fecha_inicio", manana.isoformat()),
            "fecha_fin": request.form.get("fecha_fin", manana.isoformat()),
            "horario": request.form.get("horario", "07:00"),
            "horario_fin": request.form.get("horario_fin", "07:30"),
            "alumnos": request.form.get("alumnos", ""),
            "solicitante": request.form.get("solicitante", "").strip(),
            "descripcion": request.form.get("descripcion", "").strip(),
            "contacto": request.form.get("contacto", "").strip(),
        }
        nombres_dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
        dias_seleccionados = request.form.getlist("dias_semana")
        if request.method == "GET":
            dias_seleccionados = [str(manana.weekday())]
        dias_seleccionados = [dia for dia in dias_seleccionados if dia in {str(i) for i in range(6)}]
        horas_reserva = [
            f"{minutos // 60:02d}:{minutos % 60:02d}"
            for minutos in range(7 * 60, 21 * 60 + 31, 30)
        ]
        resultado = None
        error = None
        aviso = None
        reservada = request.args.get("reservada") == "1"

        def clave_opcion(opcion):
            return (
                f"{opcion['aula']}|{','.join(opcion['secciones'])}|"
                f"{opcion['horario']}|{opcion['horario_fin']}"
            )

        def buscar_opciones():
            return buscar_reservas(
                valores["fecha_inicio"],
                valores["fecha_fin"],
                valores["horario"],
                valores["horario_fin"],
                dias_seleccionados,
                valores["alumnos"],
                Path(app.root_path) / NOMBRE_ARCHIVO,
                Path(app.root_path) / "cronograma.dat",
            )

        if request.method == "POST":
            accion = request.form.get("accion")
            if not valores["solicitante"] or not valores["descripcion"]:
                error = "Solicitante y descripción son obligatorios."
            elif not valores["alumnos"]:
                error = "Ingresa el número de alumnos para comprobar la capacidad."
            elif not dias_seleccionados:
                error = "Selecciona al menos un día de lunes a sábado."
            else:
                try:
                    resultado = buscar_opciones()
                    if accion == "realizar":
                        seleccion = request.form.get("opcion", "")
                        with candado_reservas:
                            resultado = buscar_opciones()
                            opcion = next(
                                (item for item in resultado["opciones"] if clave_opcion(item) == seleccion),
                                None,
                            )
                            if opcion is None:
                                error = "La opción seleccionada ya no está disponible. Revisa las opciones actualizadas."
                            else:
                                guardar_reserva(
                                    opcion,
                                    resultado["fechas"],
                                    valores["solicitante"],
                                    valores["descripcion"],
                                    valores["contacto"],
                                    Path(app.root_path) / "cronograma.dat",
                                )
                                return redirect(url_for("reserva_page", reservada=1))
                    elif accion != "buscar":
                        error = "Acción de reserva no válida."
                except (ValueError, OSError) as exc:
                    error = str(exc) or "No se pudo consultar el cronograma."

                if resultado and not resultado["opciones"] and error is None:
                    if resultado["motivo"] == "capacidad":
                        error = (
                            f"No hay un aula con capacidad para {valores['alumnos']} alumnos. "
                            f"La capacidad máxima por aula, sumando sus secciones, es "
                            f"{resultado['capacidad_maxima']} alumnos."
                        )
                    else:
                        error = "No hay aulas disponibles para esas fechas, días y horario."
                elif resultado and resultado["motivo"] == "horario_alternativo":
                    aviso = "No hay espacio en el horario solicitado; estas opciones usan otros horarios libres."

        return render_template(
            "reserva.html",
            app_name=app.config["APP_NAME"],
            tagline=app.config["APP_TAGLINE"],
            valores=valores,
            nombres_dias=nombres_dias,
            dias_seleccionados=dias_seleccionados,
            horas_reserva=horas_reserva,
            resultado=resultado,
            error=error,
            aviso=aviso,
            reservada=reservada,
            fecha_minima=FECHA_INICIO_CRONOGRAMA,
            fecha_maxima=FECHA_FIN_CRONOGRAMA,
        )

    @app.route("/cronograma")
    def cronograma():
        mes = request.args.get("mes", "2026-09")
        try:
            anio, numero_mes = (int(parte) for parte in mes.split("-", 1))
            mes_fecha = date(anio, numero_mes, 1)
        except (ValueError, TypeError):
            mes_fecha = FECHA_INICIO_CRONOGRAMA.replace(day=1)
            anio, numero_mes = mes_fecha.year, mes_fecha.month

        if mes_fecha < FECHA_INICIO_CRONOGRAMA.replace(day=1):
            mes_fecha = FECHA_INICIO_CRONOGRAMA.replace(day=1)
        elif mes_fecha > FECHA_FIN_CRONOGRAMA.replace(day=1):
            mes_fecha = FECHA_FIN_CRONOGRAMA.replace(day=1)
        anio, numero_mes = mes_fecha.year, mes_fecha.month
        mes = mes_fecha.strftime("%Y-%m")

        try:
            fecha_seleccionada = date.fromisoformat(request.args.get("fecha", ""))
        except ValueError:
            fecha_seleccionada = FECHA_INICIO_CRONOGRAMA

        if (
            fecha_seleccionada.strftime("%Y-%m") != mes
            or fecha_seleccionada < FECHA_INICIO_CRONOGRAMA
            or fecha_seleccionada > FECHA_FIN_CRONOGRAMA
            or fecha_seleccionada.weekday() == 6
        ):
            ultimo_dia = calendar.monthrange(anio, numero_mes)[1]
            fecha_seleccionada = next(
                date(anio, numero_mes, dia)
                for dia in range(1, ultimo_dia + 1)
                if FECHA_INICIO_CRONOGRAMA <= date(anio, numero_mes, dia)
                <= FECHA_FIN_CRONOGRAMA
                and date(anio, numero_mes, dia).weekday() < 6
            )

        archivo_aulas = Path(app.root_path) / NOMBRE_ARCHIVO
        archivo_cronograma = Path(app.root_path) / "cronograma.dat"
        aulas_disponibles = []
        if archivo_aulas.exists():
            with archivo_aulas.open(encoding="utf-8", newline="") as archivo:
                aulas_disponibles = [
                    {
                        "clave": f"{fila['AULA']}|{fila['SECCION']}",
                        "nombre": f"Aula {fila['AULA']} - {fila['SECCION']}",
                        "ubicacion": fila["UBICACION"],
                    }
                    for fila in csv.DictReader(archivo, delimiter=DELIMITADOR)
                ]

        filtro_solicitante = request.args.get("solicitante", "").strip()
        filtro_aula = request.args.get("aula", "")
        filtro_ubicacion = request.args.get("ubicacion", "")
        horas_disponibles = [
            f"{minutos // 60:02d}:{minutos % 60:02d}"
            for minutos in range(7 * 60, 21 * 60 + 31, 30)
        ]
        hora_inicio = request.args.get("hora_inicio", "07:00")
        hora_fin = request.args.get("hora_fin", "21:30")
        if hora_inicio not in horas_disponibles:
            hora_inicio = "07:00"
        if hora_fin not in horas_disponibles:
            hora_fin = "21:30"
        horario_invalido = hora_fin < hora_inicio
        if horario_invalido:
            hora_fin = hora_inicio

        inicio_semana = fecha_seleccionada - timedelta(days=fecha_seleccionada.weekday())
        dias_semana = [
            {
                "fecha": inicio_semana + timedelta(days=desplazamiento),
                "nombre": ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado")[desplazamiento],
                "en_periodo": FECHA_INICIO_CRONOGRAMA
                <= inicio_semana + timedelta(days=desplazamiento)
                <= FECHA_FIN_CRONOGRAMA,
            }
            for desplazamiento in range(6)
        ]

        entradas_por_celda = {}
        if archivo_cronograma.exists():
            fechas_semana = {dia["fecha"] for dia in dias_semana}
            ubicacion_por_aula = {
                aula["clave"]: aula["ubicacion"] for aula in aulas_disponibles
            }
            with archivo_cronograma.open(encoding="utf-8", newline="") as archivo:
                for fila in csv.DictReader(archivo, delimiter=DELIMITADOR):
                    try:
                        fecha_fila = datetime.strptime(fila["FECHA"], "%d/%m/%Y").date()
                    except ValueError:
                        continue
                    clave_aula = f"{fila['AULA']}|{fila['SECCION']}"
                    solicitante = fila.get("SOLICITANTE", "").strip()
                    if fecha_fila not in fechas_semana:
                        continue
                    if filtro_aula and clave_aula != filtro_aula:
                        continue
                    if filtro_ubicacion and ubicacion_por_aula.get(clave_aula) != filtro_ubicacion:
                        continue
                    if filtro_solicitante and filtro_solicitante.casefold() not in solicitante.casefold():
                        continue
                    clave_celda = (fecha_fila, fila["HORAINI"])
                    entradas_por_celda.setdefault(clave_celda, []).append(
                        {
                            "aula": fila["AULA"],
                            "seccion": fila["SECCION"],
                            "solicitante": solicitante,
                            "descripcion": fila.get("DESCRIPCION", "").strip(),
                            "contacto": fila.get("CONTACTO", "").strip(),
                        }
                    )

        filas_cronograma = []
        minutos_inicio = int(hora_inicio[:2]) * 60 + int(hora_inicio[3:])
        minutos_fin = int(hora_fin[:2]) * 60 + int(hora_fin[3:])
        for minutos in range(minutos_inicio, minutos_fin + 1, 30):
            hora = f"{minutos // 60:02d}:{minutos % 60:02d}"
            filas_cronograma.append(
                {
                    "hora": hora,
                    "dias": [
                        {
                            "en_periodo": dia["en_periodo"],
                            "entradas": entradas_por_celda.get((dia["fecha"], hora), []),
                        }
                        for dia in dias_semana
                    ],
                }
            )

        semanas_calendario = [
            semana[:6]
            for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(anio, numero_mes)
        ]
        return render_template(
            "cronograma.html",
            app_name=app.config["APP_NAME"],
            tagline=app.config["APP_TAGLINE"],
            mes=mes,
            mes_nombre=("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")[numero_mes - 1],
            numero_mes=numero_mes,
            anio=anio,
            semanas_calendario=semanas_calendario,
            fecha_seleccionada=fecha_seleccionada,
            dias_semana=dias_semana,
            filas_cronograma=filas_cronograma,
            aulas_disponibles=aulas_disponibles,
            ubicaciones=sorted({aula["ubicacion"] for aula in aulas_disponibles}),
            filtro_solicitante=filtro_solicitante,
            filtro_aula=filtro_aula,
            filtro_ubicacion=filtro_ubicacion,
            horas_disponibles=horas_disponibles,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            horario_invalido=horario_invalido,
            cronograma_disponible=archivo_cronograma.exists(),
            fecha_inicio=FECHA_INICIO_CRONOGRAMA,
            fecha_fin=FECHA_FIN_CRONOGRAMA,
        )

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
