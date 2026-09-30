import calendar
import csv
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock

from flask import Flask, redirect, render_template, jsonify, request, url_for
import pandas as pd
from config import Config
from crea_aula import crear_archivo_dat
from reserva import buscar_reservas, cancelar_reservas, guardar_reserva

# Cliente oficial de OpenAI (se usa únicamente si hay API key configurada)
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
    
DELIMITADOR=";"
NOMBRE_ARCHIVO = "aula.dat"
FECHA_INICIO_CRONOGRAMA = date(2026, 9, 1)
FECHA_FIN_CRONOGRAMA = date(2028, 12, 31)

def cargar_dataframe(nombre_archivo:str):
    """Carga el archivo .dat en un DataFrame de pandas."""
    df = pd.read_csv(nombre_archivo, sep=DELIMITADOR, encoding="utf-8")
    return df


def recuperar_contexto_asistente(mensaje, ruta_aulas, ruta_cronograma, ahora=None):
    """Recupera datos semanales de aulas y reservas relevantes para la consulta."""
    ahora = ahora or datetime.now()
    ruta_aulas = Path(ruta_aulas)
    if not ruta_aulas.exists():
        return "Los datos de aulas no están disponibles.", False

    df_aula = pd.read_csv(
        ruta_aulas,
        sep=DELIMITADOR,
        encoding="utf-8",
        dtype=str,
        keep_default_na=False,
    )
    mensaje_normalizado = mensaje.casefold()
    numeros_aula = set(re.findall(r"\baula\s*(\d+)\b", mensaje_normalizado))
    secciones = set(re.findall(r"\bsecci[oó]n\s+([a-z])\b", mensaje_normalizado))
    ubicaciones = set(re.findall(r"\bp\d+\b", mensaje_normalizado))
    fecha_filtro = None
    fecha_texto = re.search(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})\b", mensaje)
    if fecha_texto:
        for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                fecha_filtro = datetime.strptime(fecha_texto.group(1), formato).date()
                break
            except ValueError:
                continue
    elif re.search(r"\bhoy\b", mensaje_normalizado):
        fecha_filtro = ahora.date()
    elif re.search(r"\bma[ñn]ana\b", mensaje_normalizado):
        fecha_filtro = (ahora + timedelta(days=1)).date()

    semana_siguiente = bool(
        re.search(
            r"\b(?:pr[oó]xima|siguiente)\s+semana\b|\bsemana\s+que\s+viene\b",
            mensaje_normalizado,
        )
    )
    consulta_semanal = bool(re.search(r"\bsemana\b", mensaje_normalizado))
    if fecha_filtro:
        fecha_referencia = fecha_filtro
    else:
        fecha_referencia = ahora.date()
    if semana_siguiente:
        fecha_referencia += timedelta(days=7)
    if consulta_semanal or not fecha_filtro:
        inicio_periodo = fecha_referencia - timedelta(days=fecha_referencia.weekday())
        fin_periodo = inicio_periodo + timedelta(days=5)
    else:
        inicio_periodo = fin_periodo = fecha_referencia

    nombre_filtro = ""
    nombre_explicito = re.search(
        r"\b(?:nombre|solicitante)\s*[:=]\s*([^\n,;.!?]+)", mensaje, re.IGNORECASE
    )
    if nombre_explicito:
        nombre_filtro = nombre_explicito.group(1).strip()

    df_aula["AULA"] = df_aula["AULA"].astype(str)
    df_aula["SECCION"] = df_aula["SECCION"].astype(str)
    df_aula["UBICACION"] = df_aula["UBICACION"].astype(str)

    filtro = pd.Series(True, index=df_aula.index)
    if numeros_aula:
        filtro &= df_aula["AULA"].isin(numeros_aula)
    if secciones:
        filtro &= df_aula["SECCION"].str.casefold().isin(secciones)
    if ubicaciones:
        filtro &= df_aula["UBICACION"].str.casefold().isin(ubicaciones)
    aulas_relevantes = df_aula.loc[filtro] if (numeros_aula or secciones or ubicaciones) else df_aula
    claves_aula = set(zip(aulas_relevantes["AULA"], aulas_relevantes["SECCION"]))

    lineas_aulas = [
        f"Aula {fila['AULA']}, sección {fila['SECCION']}: capacidad {fila['CAPACIDAD']}, "
        f"ubicación {fila['UBICACION']}, adyacentes {fila['ADYACENTE'] or 'ninguna'}."
        for _, fila in aulas_relevantes.iterrows()
    ]
    lineas_disponibilidad = []
    lineas_reservas = []
    ruta_cronograma = Path(ruta_cronograma)
    if ruta_cronograma.exists():
        df_cronograma = pd.read_csv(
            ruta_cronograma,
            sep=DELIMITADOR,
            encoding="utf-8",
            dtype=str,
            keep_default_na=False,
            usecols=[
                "AULA", "SECCION", "FECHA", "HORAINI", "SOLICITANTE", "CONTACTO", "DESCRIPCION"
            ],
        )
        claves_relevantes = {f"{aula}|{seccion}" for aula, seccion in claves_aula}
        df_cronograma["_instante"] = pd.to_datetime(
            df_cronograma["FECHA"] + " " + df_cronograma["HORAINI"],
            format="%d/%m/%Y %H:%M",
            errors="coerce",
        )
        df_cronograma = df_cronograma[df_cronograma["_instante"].notna()].copy()
        df_cronograma["_fecha"] = df_cronograma["_instante"].dt.date
        if numeros_aula or secciones or ubicaciones:
            df_cronograma = df_cronograma[
                df_cronograma["AULA"].add("|").add(df_cronograma["SECCION"]).isin(claves_relevantes)
            ]
        df_semana = df_cronograma[
            df_cronograma["_fecha"].between(inicio_periodo, fin_periodo)
        ].copy()

        for (aula, seccion), franjas in df_semana.groupby(["AULA", "SECCION"], sort=True):
            disponibles = franjas["SOLICITANTE"].str.strip().eq("").sum()
            total = len(franjas)
            estado = "sí" if disponibles else "no"
            lineas_disponibilidad.append(
                f"Aula {aula} sección {seccion}: disponibilidad {estado}, "
                f"{disponibles} de {total} franjas de 30 minutos libres."
            )

        ocupadas = df_semana[df_semana["SOLICITANTE"].str.strip().ne("")].copy()
        filtro_profesor = ""
        profesor_explicito = re.search(
            r"\b(?:profesor(?:a)?|docente)\s+(?:es\s+)?([^,;.!?]+)",
            mensaje,
            re.IGNORECASE,
        )
        if profesor_explicito:
            filtro_profesor = re.split(
                r"\b(?:esta|la\s+semana|semana|en|del|de|para|aula|el|las|los)\b",
                profesor_explicito.group(1),
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip()
        if filtro_profesor:
            coincide_profesor = (
                ocupadas["SOLICITANTE"].str.contains(filtro_profesor, case=False, regex=False)
                | ocupadas["CONTACTO"].str.contains(filtro_profesor, case=False, regex=False)
            )
            ocupadas = ocupadas[coincide_profesor]
        if nombre_filtro:
            coincide_nombre = (
                ocupadas["SOLICITANTE"].str.contains(nombre_filtro, case=False, regex=False)
                | ocupadas["CONTACTO"].str.contains(nombre_filtro, case=False, regex=False)
            )
            ocupadas = ocupadas[coincide_nombre]

        descripciones = [
            valor.strip()
            for valor in df_cronograma["DESCRIPCION"].drop_duplicates()
            if valor.strip() and valor.casefold() in mensaje_normalizado
        ]
        filtro_descripcion = max(descripciones, key=len) if descripciones else ""
        if filtro_descripcion:
            ocupadas = ocupadas[
                ocupadas["DESCRIPCION"].str.contains(
                    filtro_descripcion, case=False, regex=False
                )
            ]

        claves_reserva = ["AULA", "SECCION", "_fecha", "SOLICITANTE", "DESCRIPCION"]
        for clave, franjas in ocupadas.groupby(claves_reserva, sort=True, dropna=False):
            aula, seccion, fecha, solicitante, descripcion = clave
            instantes = sorted(franjas["_instante"].tolist())
            inicio_bloque = fin_bloque = instantes[0]
            bloques = []
            for instante in instantes[1:]:
                if instante == fin_bloque + timedelta(minutes=30):
                    fin_bloque = instante
                else:
                    bloques.append((inicio_bloque, fin_bloque + timedelta(minutes=30)))
                    inicio_bloque = fin_bloque = instante
            bloques.append((inicio_bloque, fin_bloque + timedelta(minutes=30)))
            for inicio, fin in bloques:
                detalle = descripcion or "Reserva sin descripción"
                lineas_reservas.append(
                    f"Aula {aula} sección {seccion}, {fecha:%d/%m/%Y} "
                    f"{inicio:%H:%M}-{fin:%H:%M}: {detalle}; "
                    f"solicitante registrado: {solicitante}."
                )

    contexto = f"Periodo consultado: {inicio_periodo:%d/%m/%Y} a {fin_periodo:%d/%m/%Y}.\n"
    contexto += "Aulas:\n" + ("\n".join(lineas_aulas) or "No hay aulas que coincidan con la consulta.")
    contexto += "\nDisponibilidad semanal (cada franja equivale a 30 minutos):\n"
    contexto += "\n".join(lineas_disponibilidad) or "No hay datos de disponibilidad para el periodo."
    contexto += "\nReservas y clases coincidentes:\n"
    contexto += "\n".join(lineas_reservas[:40]) or "No hay reservas que coincidan con los filtros."
    if len(lineas_reservas) > 40:
        contexto += f"\nSe omitieron {len(lineas_reservas) - 40} reservas adicionales."
    return contexto, False
 
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

    @app.route("/cancelar", methods=["GET", "POST"])
    def cancelar_page():
        fecha_predeterminada = min(
            max(date.today(), FECHA_INICIO_CRONOGRAMA), FECHA_FIN_CRONOGRAMA
        )
        valores = {
            "fecha_inicio": request.values.get("fecha_inicio", fecha_predeterminada.isoformat()),
            "fecha_fin": request.values.get("fecha_fin", fecha_predeterminada.isoformat()),
            "solicitante": request.values.get("solicitante", "").strip(),
            "aula": request.values.get("aula", "").strip(),
            "horario_inicio": request.values.get("horario_inicio", "07:00"),
            "horario_fin": request.values.get("horario_fin", "21:30"),
        }
        aulas_disponibles = []
        archivo_aulas = Path(app.root_path) / NOMBRE_ARCHIVO
        if archivo_aulas.exists():
            with archivo_aulas.open(encoding="utf-8", newline="") as archivo:
                aulas_disponibles = [
                    {
                        "clave": f"{fila['AULA']}|{fila['SECCION']}",
                        "nombre": f"Aula {fila['AULA']} - Sección {fila['SECCION']}",
                    }
                    for fila in csv.DictReader(archivo, delimiter=DELIMITADOR)
                ]
        horas_disponibles = [
            f"{minutos // 60:02d}:{minutos % 60:02d}"
            for minutos in range(7 * 60, 21 * 60 + 31, 30)
        ]
        error = None
        buscar = request.values.get("buscar") == "1" or request.method == "POST"
        canceladas = request.args.get("canceladas", "")
        semana_offset = 0
        max_semana_offset = 0
        dias_semana = []
        filas_cronograma = []
        cantidad_reservas = 0
        accion = request.form.get("accion", "") if request.method == "POST" else ""

        if buscar:
            try:
                if not all((valores["fecha_inicio"], valores["fecha_fin"], valores["horario_inicio"], valores["horario_fin"])):
                    raise ValueError("Completa las fechas y los horarios obligatorios.")
                fecha_inicio = date.fromisoformat(valores["fecha_inicio"])
                fecha_fin = date.fromisoformat(valores["fecha_fin"])
                if not FECHA_INICIO_CRONOGRAMA <= fecha_inicio <= FECHA_FIN_CRONOGRAMA:
                    raise ValueError("La fecha inicial está fuera del período del cronograma.")
                if not FECHA_INICIO_CRONOGRAMA <= fecha_fin <= FECHA_FIN_CRONOGRAMA:
                    raise ValueError("La fecha final está fuera del período del cronograma.")
                if fecha_fin < fecha_inicio:
                    raise ValueError("La fecha final debe ser igual o posterior a la inicial.")
                if valores["aula"] and valores["aula"] not in {
                    aula["clave"] for aula in aulas_disponibles
                }:
                    raise ValueError("El aula seleccionada no existe.")
                if valores["horario_inicio"] not in horas_disponibles or valores["horario_fin"] not in horas_disponibles:
                    raise ValueError("Selecciona horarios válidos en intervalos de 30 minutos.")
                minutos_inicio = int(valores["horario_inicio"][:2]) * 60 + int(valores["horario_inicio"][3:])
                minutos_fin = int(valores["horario_fin"][:2]) * 60 + int(valores["horario_fin"][3:])
                if minutos_fin <= minutos_inicio:
                    raise ValueError("El horario final debe ser posterior al horario inicial.")

                origen_semana = fecha_inicio - timedelta(days=fecha_inicio.weekday())
                max_semana_offset = max(0, (fecha_fin - origen_semana).days // 7)
                try:
                    semana_offset = int(request.values.get("semana_offset", "0"))
                except ValueError:
                    semana_offset = 0
                semana_offset = min(max(semana_offset, 0), max_semana_offset)
                nombres_dias = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado")
                dias_semana = [
                    {
                        "fecha": origen_semana + timedelta(days=semana_offset * 7 + indice),
                        "nombre": nombres_dias[indice],
                        "en_rango": fecha_inicio <= origen_semana + timedelta(days=semana_offset * 7 + indice) <= fecha_fin
                        and FECHA_INICIO_CRONOGRAMA <= origen_semana + timedelta(days=semana_offset * 7 + indice) <= FECHA_FIN_CRONOGRAMA,
                    }
                    for indice in range(6)
                ]

                archivo_cronograma = Path(app.root_path) / "cronograma.dat"
                if not archivo_cronograma.exists():
                    raise ValueError("No existe cronograma.dat. Genera primero el cronograma de aulas.")

                fechas_visibles = {dia["fecha"] for dia in dias_semana if dia["en_rango"]}
                entradas_por_celda = {}
                espacios_visibles = set()
                with archivo_cronograma.open(encoding="utf-8", newline="") as archivo:
                    lector = csv.DictReader(archivo, delimiter=DELIMITADOR)
                    for fila in lector:
                        try:
                            fecha_fila = datetime.strptime(fila["FECHA"], "%d/%m/%Y").date()
                            hora_fila = fila["HORAINI"]
                            datetime.strptime(hora_fila, "%H:%M")
                        except (KeyError, ValueError):
                            continue
                        solicitante = (fila.get("SOLICITANTE") or "").strip()
                        if (
                            fecha_fila not in fechas_visibles
                            or not valores["horario_inicio"] <= hora_fila < valores["horario_fin"]
                            or not solicitante
                            or (valores["solicitante"] and valores["solicitante"].casefold() not in solicitante.casefold())
                            or (valores["aula"] and f"{fila.get('AULA', '')}|{fila.get('SECCION', '')}" != valores["aula"])
                        ):
                            continue
                        entrada = {
                            "aula": fila.get("AULA", ""),
                            "seccion": fila.get("SECCION", ""),
                            "solicitante": solicitante,
                            "descripcion": (fila.get("DESCRIPCION") or "").strip(),
                            "contacto": (fila.get("CONTACTO") or "").strip(),
                            "espacio": "|".join((
                                fila.get("AULA", ""),
                                fila.get("SECCION", ""),
                                fecha_fila.isoformat(),
                                hora_fila,
                            )),
                        }
                        entradas_por_celda.setdefault((fecha_fila, hora_fila), []).append(entrada)
                        espacios_visibles.add(entrada["espacio"])
                        cantidad_reservas += 1

                filas_cronograma = [
                    {
                        "hora": f"{minutos // 60:02d}:{minutos % 60:02d}",
                        "dias": [
                            {
                                "en_rango": dia["en_rango"],
                                "entradas": entradas_por_celda.get((dia["fecha"], f"{minutos // 60:02d}:{minutos % 60:02d}"), []),
                            }
                            for dia in dias_semana
                        ],
                    }
                    for minutos in range(minutos_inicio, minutos_fin, 30)
                ]

                if accion == "cancelar":
                    espacios = request.form.getlist("espacios")
                    if not espacios:
                        raise ValueError("Selecciona al menos un espacio reservado para cancelar.")
                    if not set(espacios).issubset(espacios_visibles):
                        raise ValueError("La selección ya no coincide con los filtros. Actualiza el calendario.")
                    with candado_reservas:
                        cantidad_cancelada = cancelar_reservas(
                            espacios, archivo_cronograma
                        )
                    return redirect(url_for(
                        "cancelar_page",
                        buscar=1,
                        fecha_inicio=fecha_inicio.isoformat(),
                        fecha_fin=fecha_fin.isoformat(),
                        solicitante=valores["solicitante"],
                        aula=valores["aula"],
                        horario_inicio=valores["horario_inicio"],
                        horario_fin=valores["horario_fin"],
                        semana_offset=semana_offset,
                        canceladas=cantidad_cancelada,
                    ))
            except (ValueError, OSError) as exc:
                error = str(exc) or "No se pudo consultar o actualizar el cronograma."

        return render_template(
            "cancelar.html",
            app_name=app.config["APP_NAME"],
            tagline=app.config["APP_TAGLINE"],
            valores=valores,
            horas_disponibles=horas_disponibles,
            aulas_disponibles=aulas_disponibles,
            dias_semana=dias_semana,
            filas_cronograma=filas_cronograma,
            cantidad_reservas=cantidad_reservas,
            semana_offset=semana_offset,
            max_semana_offset=max_semana_offset,
            error=error,
            buscar=buscar,
            canceladas=canceladas,
            fecha_minima=FECHA_INICIO_CRONOGRAMA,
            fecha_maxima=FECHA_FIN_CRONOGRAMA,
        )

    @app.route("/cronograma")
    def cronograma():
        hoy = date.today()
        mes = request.args.get("mes", hoy.strftime("%Y-%m"))
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
            fecha_seleccionada = date.fromisoformat(
                request.args.get("fecha", hoy.isoformat())
            )
        except ValueError:
            fecha_seleccionada = hoy

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
    # API: asistente de IA (OpenAI)
    # ------------------------------------------------------------------
    @app.route("/api/asistente", methods=["POST"])
    def asistente():
        """
        Recibe un mensaje del usuario y responde usando la API de OpenAI.
        Requiere OPENAI_API_KEY configurada en el archivo .env
        """
        data = request.get_json(silent=True) or {}
        mensaje = data.get("mensaje", "").strip()

        if not mensaje:
            return jsonify({"error": "El campo 'mensaje' es requerido."}), 400

        if not app.config["OPENAI_API_KEY"] or OpenAI is None:
            return jsonify({
                "respuesta": "El asistente de IA aún no está configurado. "
                             "Agrega tu OPENAI_API_KEY en el archivo .env para activarlo."
            })

        try:
            ruta_datos = Path(app.root_path)
            contexto, necesita_filtros = recuperar_contexto_asistente(
                mensaje,
                ruta_datos / NOMBRE_ARCHIVO,
                ruta_datos / "cronograma.dat",
            )
            if necesita_filtros:
                return jsonify({
                    "respuesta": "Para consultar el cronograma, indica al menos un filtro: "
                                 "nombre o solicitante, fecha (DD/MM/AAAA) o número de aula."
                })
            client = OpenAI(api_key=app.config["OPENAI_API_KEY"])
            respuesta = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=500,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Responde en español y usa el contexto recuperado como única fuente para "
                            "preguntas sobre aulas, clases, reservas y disponibilidad. Sé conciso, con un "
                            "máximo de 120 palabras; no inventes datos. El periodo del contexto indica "
                            "la semana consultada y cada franja libre equivale a 30 minutos. Para preguntas "
                            "sobre disponibilidad, indica las aulas con franjas libres según el resumen. "
                            "Para clases o reservas, usa las fechas, horas, descripciones y aulas listadas. "
                            "El cronograma no tiene una columna PROFESOR: SOLICITANTE y CONTACTO son los "
                            "datos registrados, no afirmes que identifican al profesor salvo que el contexto "
                            "lo confirme. Si no hay coincidencias, dilo claramente.\n\n"
                            f"{contexto}"
                        ),
                    },
                    {"role": "user", "content": mensaje},
                ],
            )
            texto = respuesta.choices[0].message.content or ""
            return jsonify({"respuesta": texto})
        except Exception as exc:  # pragma: no cover - manejo simple de errores
            return jsonify({"error": f"Error al conectar con OpenAI: {exc}"}), 500

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
