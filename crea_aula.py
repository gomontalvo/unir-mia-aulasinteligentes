"""
crear_aula_dat.py
-----------------
Genera el archivo 'aula.dat' con los datos de las aulas y luego lo
carga en un DataFrame de pandas para verificar su contenido.
 
Estructura de cada registro (separados por ';'):
    AULA ; SECCION ; CAPACIDAD ; UBICACION ; ADYACENTE
"""
 
import csv
from datetime import date, datetime, time, timedelta
from pathlib import Path
 
# ---------------------------------------------------------------------
# 1) Datos de las aulas (tomados de aulas_0.csv)
#    Cada tupla: (aula, seccion, capacidad, ubicacion, adyacente)
# ---------------------------------------------------------------------
datos_aulas = [
    (1, "A", 10, "P1", "2,3"),
    (1, "B", 20, "P1", "2,3"),
    (2, "A", 20, "P1", "1,3"),
    (3, "A", 20, "P1", "1,2"),
    (4, "A", 15, "P2", "5,6"),
    (4, "B", 20, "P2", "5,6"),
    (5, "A", 20, "P2", "4,6"),
    (6, "A", 15, "P2", "4,5"),
]
 
ENCABEZADO = ["AULA", "SECCION", "CAPACIDAD", "UBICACION", "ADYACENTE"]
NOMBRE_ARCHIVO = "aula.dat"
NOMBRE_ARCHIVO_CRONOGRAMA = "cronograma.dat"
DELIMITADOR = ";"
ENCABEZADO_CRONOGRAMA = [
    "AULA", "SECCION", "FECHA", "HORAINI", "SOLICITANTE", "CONTACTO", "DESCRIPCION"
]
FECHA_INICIO = date(2026, 9, 1)
FECHA_FIN = date(2028, 12, 31)
 
 
def crear_cronograma_dat(
    nombre_archivo_aulas: str = NOMBRE_ARCHIVO,
    nombre_archivo: str = NOMBRE_ARCHIVO_CRONOGRAMA,
) -> None:
    """Crea un espacio de 30 minutos por aula, sección y fecha."""
    with open(nombre_archivo_aulas, encoding="utf-8", newline="") as archivo_aulas:
        aulas = [
            (fila["AULA"], fila["SECCION"])
            for fila in csv.DictReader(archivo_aulas, delimiter=DELIMITADOR)
        ]

    cantidad_registros = 0
    fecha = FECHA_INICIO
    with open(nombre_archivo, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo, delimiter=DELIMITADOR, lineterminator="\n")
        escritor.writerow(ENCABEZADO_CRONOGRAMA)
        while fecha <= FECHA_FIN:
            hora = datetime.combine(fecha, time(7, 0))
            hora_fin = datetime.combine(fecha, time(21, 30))
            while hora <= hora_fin:
                for aula, seccion in aulas:
                    escritor.writerow([
                        aula,
                        seccion,
                        fecha.strftime("%d/%m/%Y"),
                        hora.strftime("%H:%M"),
                        "",
                        "",
                        ""
                    ])
                    cantidad_registros += 1
                hora += timedelta(minutes=30)
            fecha += timedelta(days=1)

    print(
        f"Archivo '{nombre_archivo}' creado con "
        f"{cantidad_registros} registros."
    )

def crear_archivo_dat(nombre_archivo: str = NOMBRE_ARCHIVO) -> None:
    """Crea el archivo .dat con los datos de las aulas."""
    with open(nombre_archivo, "w", encoding="utf-8", newline="") as f:
        # Línea de encabezado
        f.write(DELIMITADOR.join(ENCABEZADO) + "\n")
        # Líneas de datos
        for aula, seccion, capacidad, ubicacion, adyacente in datos_aulas:
            linea = DELIMITADOR.join(
                [str(aula), seccion, str(capacidad), ubicacion, adyacente]
            )
            f.write(linea + "\n")
    print(f"Archivo '{nombre_archivo}' creado con {len(datos_aulas)} registros.")
    nombre_cronograma = str(Path(nombre_archivo).with_name(NOMBRE_ARCHIVO_CRONOGRAMA))
    crear_cronograma_dat(nombre_archivo, nombre_cronograma)


#if __name__ == "__main__":
#    crear_archivo_dat()
 
 