import csv
import random
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from itertools import combinations
from pathlib import Path


DELIMITADOR = ";"
HORA_INICIO = "07:00"
HORA_FIN = "21:30"
INTERVALO_MINUTOS = 30
FECHA_MINIMA = date(2026, 9, 1)
FECHA_MAXIMA = date(2028, 12, 31)
CAMPOS_CRONOGRAMA = [
    "AULA", "SECCION", "FECHA", "HORAINI", "SOLICITANTE", "CONTACTO", "DESCRIPCION"
]


def _leer_aulas(ruta_aulas):
    aulas = defaultdict(list)
    with open(ruta_aulas, encoding="utf-8", newline="") as archivo:
        for fila in csv.DictReader(archivo, delimiter=DELIMITADOR):
            aulas[fila["AULA"]].append(
                {
                    "seccion": fila["SECCION"],
                    "capacidad": int(fila["CAPACIDAD"]),
                    "adyacentes": {
                        vecino.strip()
                        for vecino in fila.get("ADYACENTE", "").split(",")
                        if vecino.strip()
                    },
                }
            )
    return aulas


def _leer_ocupacion(ruta_cronograma):
    ocupadas = set()
    registradas = set()
    aulas_ocupadas_por_horario = defaultdict(set)
    with open(ruta_cronograma, encoding="utf-8", newline="") as archivo:
        for fila in csv.DictReader(archivo, delimiter=DELIMITADOR):
            fecha = datetime.strptime(fila["FECHA"], "%d/%m/%Y").date()
            horario = fila["HORAINI"]
            aula = fila["AULA"]
            seccion = fila["SECCION"]
            clave = (aula, seccion, fecha, horario)
            registradas.add(clave)
            solicitante = (fila.get("SOLICITANTE") or "").strip()
            if solicitante:
                ocupadas.add(clave)
                aulas_ocupadas_por_horario[(fecha, horario)].add(aula)
    return ocupadas, aulas_ocupadas_por_horario, registradas


def _fechas_reserva(fecha_inicio, fecha_fin, dias_semana):
    if isinstance(fecha_inicio, str):
        fecha_inicio = date.fromisoformat(fecha_inicio)
    if isinstance(fecha_fin, str):
        fecha_fin = date.fromisoformat(fecha_fin)
    if fecha_inicio < FECHA_MINIMA or fecha_fin > FECHA_MAXIMA:
        raise ValueError("Las fechas deben estar entre 01/09/2026 y 31/12/2028.")
    if fecha_fin < fecha_inicio:
        raise ValueError("La fecha final debe ser igual o posterior a la inicial.")
    dias_semana = {int(dia) for dia in dias_semana}
    if not dias_semana or any(dia < 0 or dia > 5 for dia in dias_semana):
        raise ValueError("Selecciona al menos un día de lunes a sábado.")

    fechas = []
    fecha = fecha_inicio
    while fecha <= fecha_fin:
        if fecha.weekday() in dias_semana:
            fechas.append(fecha)
        fecha += timedelta(days=1)
    if not fechas:
        raise ValueError("El rango no contiene fechas para los días seleccionados.")
    return fechas


def _horarios():
    inicio = int(HORA_INICIO[:2]) * 60 + int(HORA_INICIO[3:])
    fin = int(HORA_FIN[:2]) * 60 + int(HORA_FIN[3:])
    return [
        f"{minuto // 60:02d}:{minuto % 60:02d}"
        for minuto in range(inicio, fin + 1, INTERVALO_MINUTOS)
    ]


def _seleccionar_geneticamente(candidatos, semilla):
    if len(candidatos) <= 3:
        return sorted(candidatos, key=lambda opcion: (-opcion["puntuacion"], opcion["horario"]))

    generador = random.Random(semilla)
    poblacion_maxima = min(64, len(candidatos))
    por_clave = {
        (opcion["aula"], tuple(opcion["secciones"]), opcion["horario"], opcion["horario_fin"]): opcion
        for opcion in candidatos
    }
    mejor_inicial = max(candidatos, key=lambda opcion: opcion["puntuacion"])
    poblacion = [mejor_inicial]
    poblacion.extend(generador.sample(candidatos, poblacion_maxima - 1))

    def competir():
        participantes = generador.sample(poblacion, min(4, len(poblacion)))
        return max(participantes, key=lambda opcion: opcion["puntuacion"])

    for _ in range(40):
        poblacion.sort(key=lambda opcion: opcion["puntuacion"], reverse=True)
        siguiente = poblacion[: max(2, poblacion_maxima // 8)]
        while len(siguiente) < poblacion_maxima:
            padre_a = competir()
            padre_b = competir()
            clave_hijo = (
                padre_a["aula"],
                tuple(padre_a["secciones"]),
                padre_b["horario"],
                padre_b["horario_fin"],
            )
            hijo = por_clave.get(clave_hijo)
            if hijo is None or generador.random() < 0.15:
                hijo = generador.choice(candidatos)
            siguiente.append(hijo)
        poblacion = siguiente

    encontrados = {
        (opcion["aula"], tuple(opcion["secciones"]), opcion["horario"], opcion["horario_fin"]): opcion
        for opcion in poblacion
    }
    mejores = sorted(encontrados.values(), key=lambda opcion: opcion["puntuacion"], reverse=True)
    if len(mejores) < 3:
        vistos = set(encontrados)
        mejores.extend(
            opcion
            for opcion in sorted(candidatos, key=lambda item: item["puntuacion"], reverse=True)
            if (
                opcion["aula"],
                tuple(opcion["secciones"]),
                opcion["horario"],
                opcion["horario_fin"],
            ) not in vistos
        )
    return mejores[:3]


def buscar_reservas(
    fecha_inicio,
    fecha_fin,
    horario,
    horario_fin,
    dias_semana,
    alumnos,
    ruta_aulas="aula.dat",
    ruta_cronograma="cronograma.dat",
):
    """Devuelve hasta tres opciones libres para todas las fechas recurrentes."""
    fechas = _fechas_reserva(fecha_inicio, fecha_fin, dias_semana)
    try:
        alumnos = int(alumnos)
    except (TypeError, ValueError) as exc:
        raise ValueError("Ingresa un número de alumnos válido.") from exc
    if alumnos < 1:
        raise ValueError("El número de alumnos debe ser mayor que cero.")

    horarios = _horarios()
    if horario not in horarios or horario_fin not in horarios:
        raise ValueError("Los horarios deben estar entre 07:00 y 21:30, cada 30 minutos.")
    minutos_solicitados = int(horario[:2]) * 60 + int(horario[3:])
    minutos_finales = int(horario_fin[:2]) * 60 + int(horario_fin[3:])
    if minutos_finales <= minutos_solicitados:
        raise ValueError("La hora final debe ser posterior a la hora inicial.")
    duracion = minutos_finales - minutos_solicitados

    aulas = _leer_aulas(ruta_aulas)
    ocupadas, aulas_ocupadas_por_horario, registradas = _leer_ocupacion(ruta_cronograma)
    capacidad_maxima = max(
        (sum(seccion["capacidad"] for seccion in secciones) for secciones in aulas.values()),
        default=0,
    )
    if alumnos > capacidad_maxima:
        return {
            "opciones": [],
            "capacidad_maxima": capacidad_maxima,
            "motivo": "capacidad",
            "fechas": fechas,
        }

    candidatos = []
    for aula, secciones_aula in aulas.items():
        for cantidad in range(1, len(secciones_aula) + 1):
            for grupo in combinations(secciones_aula, cantidad):
                capacidad = sum(seccion["capacidad"] for seccion in grupo)
                if capacidad < alumnos:
                    continue
                nombres_secciones = tuple(seccion["seccion"] for seccion in grupo)
                vecinos = set().union(*(seccion["adyacentes"] for seccion in grupo))
                for minutos_candidatos in range(
                    int(HORA_INICIO[:2]) * 60 + int(HORA_INICIO[3:]),
                    int(HORA_FIN[:2]) * 60 + int(HORA_FIN[3:]) - duracion + 1,
                    INTERVALO_MINUTOS,
                ):
                    hora = f"{minutos_candidatos // 60:02d}:{minutos_candidatos % 60:02d}"
                    minutos_fin_candidato = minutos_candidatos + duracion
                    hora_fin_candidata = (
                        f"{minutos_fin_candidato // 60:02d}:{minutos_fin_candidato % 60:02d}"
                    )
                    horarios_bloque = [
                        f"{minuto // 60:02d}:{minuto % 60:02d}"
                        for minuto in range(minutos_candidatos, minutos_fin_candidato, INTERVALO_MINUTOS)
                    ]
                    if any(
                        (aula, seccion, fecha, hora) not in registradas
                        or (aula, seccion, fecha, hora) in ocupadas
                        for fecha in fechas
                        for hora in horarios_bloque
                        for seccion in nombres_secciones
                    ):
                        continue
                    puntos_por_fecha = []
                    for fecha in fechas:
                        aulas_vecinas_ocupadas = set().union(
                            *(
                                aulas_ocupadas_por_horario[(fecha, hora_bloque)]
                                for hora_bloque in horarios_bloque
                            )
                        )
                        bonus_adyacencia = 8 if vecinos.intersection(aulas_vecinas_ocupadas) else 0
                        puntos_por_fecha.append(bonus_adyacencia)
                    diferencia_horaria = abs(
                        minutos_candidatos - minutos_solicitados
                    )
                    puntuacion_hora = max(0, 100 - diferencia_horaria)
                    maximin = min(puntuacion_hora + puntos for puntos in puntos_por_fecha)
                    desperdicio = capacidad - alumnos
                    puntuacion = maximin - desperdicio * 0.25 - (cantidad - 1) * 2
                    candidatos.append(
                        {
                            "aula": aula,
                            "secciones": list(nombres_secciones),
                            "horario": hora,
                            "horario_fin": hora_fin_candidata,
                            "capacidad": capacidad,
                            "alumnos": alumnos,
                            "fechas": len(fechas),
                            "puntuacion": round(puntuacion, 2),
                            "adyacente": any(puntos > 0 for puntos in puntos_por_fecha),
                            "horario_solicitado": hora == horario,
                        }
                    )

    opciones_solicitadas = [
        opcion for opcion in candidatos if opcion["horario"] == horario
    ]
    opciones_evaluadas = opciones_solicitadas or candidatos
    if not opciones_evaluadas:
        return {
            "opciones": [],
            "capacidad_maxima": capacidad_maxima,
            "motivo": "disponibilidad",
            "fechas": fechas,
        }

    opciones_una_seccion = [
        opcion for opcion in opciones_evaluadas if len(opcion["secciones"]) == 1
    ]
    if opciones_una_seccion:
        opciones_evaluadas = opciones_una_seccion

    semilla = sum(
        ord(caracter)
        for caracter in f"{fecha_inicio}{fecha_fin}{horario}{horario_fin}{alumnos}"
    )
    opciones = _seleccionar_geneticamente(opciones_evaluadas, semilla)
    for opcion in opciones:
        opcion["nombre"] = f"Aula {opcion['aula']} · Sección {', '.join(opcion['secciones'])}"
    return {
        "opciones": opciones,
        "capacidad_maxima": capacidad_maxima,
        "motivo": None if opciones_solicitadas else "horario_alternativo",
        "fechas": fechas,
    }


def guardar_reserva(opcion, fechas, solicitante, descripcion, contacto, ruta_cronograma):
    """Actualiza las filas de cronograma y conserva atómica la versión anterior."""
    ruta = Path(ruta_cronograma)
    with ruta.open(encoding="utf-8", newline="") as archivo:
        lector = csv.DictReader(archivo, delimiter=DELIMITADOR)
        campos = list(lector.fieldnames or [])
        filas = list(lector)
    if not campos:
        raise ValueError("El cronograma no tiene una cabecera válida.")

    for campo in CAMPOS_CRONOGRAMA:
        if campo not in campos:
            campos.append(campo)

    fechas_texto = {fecha.strftime("%d/%m/%Y") for fecha in fechas}
    secciones = set(opcion["secciones"])
    inicio = int(opcion["horario"][:2]) * 60 + int(opcion["horario"][3:])
    fin = int(opcion["horario_fin"][:2]) * 60 + int(opcion["horario_fin"][3:])
    horarios_bloque = {
        f"{minuto // 60:02d}:{minuto % 60:02d}"
        for minuto in range(inicio, fin, INTERVALO_MINUTOS)
    }
    objetivo = {
        (seccion, fecha, horario)
        for seccion in secciones
        for fecha in fechas_texto
        for horario in horarios_bloque
    }
    actualizados = set()
    for fila in filas:
        clave = (
            fila.get("SECCION", ""),
            fila.get("FECHA", ""),
            fila.get("HORAINI", ""),
        )
        coincide = (
            fila.get("AULA") == opcion["aula"]
            and clave in objetivo
        )
        if not coincide:
            continue
        if (fila.get("SOLICITANTE") or "").strip():
            raise ValueError("Una de las secciones seleccionadas acaba de ser reservada.")
        fila["SOLICITANTE"] = solicitante
        fila["CONTACTO"] = contacto
        fila["DESCRIPCION"] = descripcion
        actualizados.add(clave)

    if actualizados != objetivo:
        raise ValueError("El cronograma no contiene todos los horarios seleccionados.")

    temporal = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=ruta.parent,
            delete=False,
        ) as archivo_temporal:
            temporal = Path(archivo_temporal.name)
            escritor = csv.DictWriter(
                archivo_temporal,
                fieldnames=campos,
                delimiter=DELIMITADOR,
                lineterminator="\n",
                extrasaction="ignore",
            )
            escritor.writeheader()
            escritor.writerows(filas)
        temporal.replace(ruta)
    except Exception:
        if temporal is not None:
            temporal.unlink(missing_ok=True)
        raise

    return len(actualizados)