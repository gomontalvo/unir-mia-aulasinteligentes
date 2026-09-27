"""
crear_aula_dat.py
-----------------
Genera el archivo 'aula.dat' con los datos de las aulas y luego lo
carga en un DataFrame de pandas para verificar su contenido.
 
Estructura de cada registro (separados por ';'):
    AULA ; SECCION ; CAPACIDAD ; UBICACION ; ADYACENTE
"""
 
import pandas as pd
 
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
DELIMITADOR = ";"
 
 
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
 
 