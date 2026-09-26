# Aulas Inteligentes con IA

Aplicación web para la gestión de **aulas inteligentes potenciadas por IA**, construida con
**Python (Flask)**, **HTML5** y **Bootstrap 5**. Integra la API de **Claude (Anthropic)** para
funciones de inteligencia artificial dentro del aula (asistente docente, resúmenes,
generación de material, etc.).

![Powered by Claude](https://img.shields.io/badge/Powered%20by-Claude-D97757?style=flat-square)

---

## 🧱 Estructura del proyecto

```
aulas-inteligentes-ia/
├── app.py                  # Aplicación Flask (rutas y arranque)
├── config.py                # Configuración (variables de entorno)
├── requirements.txt          # Dependencias de Python
├── .env.example               # Ejemplo de variables de entorno
├── .gitignore
├── templates/
│   ├── base.html             # Plantilla base (navbar, footer, estilos)
│   └── index.html            # Página de inicio "Aulas Inteligentes con IA"
└── static/
    ├── css/styles.css         # Estilos con paleta de color estilo Claude
    ├── js/main.js              # Lógica de interacción / llamadas a la API
    └── img/                    # Recursos gráficos (logo, íconos, etc.)
```

## 🚀 Requisitos previos

- Python 3.10 o superior
- Cuenta de [GitHub](https://github.com)
- (Opcional) API Key de Anthropic si vas a usar el asistente de IA: https://console.anthropic.com/

## ⚙️ Instalación local

```bash
# 1. Clonar el repositorio
git clone https://github.com/<tu-usuario>/aulas-inteligentes-ia.git
cd aulas-inteligentes-ia

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate      # En Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env y agregar tu ANTHROPIC_API_KEY (opcional)

# 5. Ejecutar la aplicación
python app.py
```

La aplicación quedará disponible en `http://127.0.0.1:5000`.

## 📤 Subir el proyecto a GitHub

```bash
git init
git add .
git commit -m "Proyecto inicial: Aulas Inteligentes con IA"
git branch -M main
git remote add origin https://github.com/<tu-usuario>/aulas-inteligentes-ia.git
git push -u origin main
```

> ⚠️ El archivo `.env` está excluido en `.gitignore` para no subir tu API Key por error.

## 🎨 Paleta de color

El diseño usa una paleta inspirada en la identidad visual de Claude (Anthropic):

| Uso                | Color     |
|--------------------|-----------|
| Fondo principal     | `#F5F1EA` |
| Texto principal      | `#1F1E1D` |
| Acento primario (coral) | `#D97757` |
| Acento secundario    | `#BD5D3A` |
| Superficie / tarjetas | `#FFFFFF` |
| Bordes suaves        | `#E8E2D6` |

## 🧩 Próximos pasos sugeridos

- Añadir autenticación de usuarios (Flask-Login) para docentes y estudiantes.
- Conectar la ruta `/api/asistente` con la API de Claude para respuestas reales (ya incluida como stub).
- Agregar una base de datos (SQLite/PostgreSQL) para aulas, cursos y usuarios.
- Desplegar en Render, Railway o un servidor propio.

## 📄 Licencia

Proyecto de código abierto, libre de usar y modificar.
