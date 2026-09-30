document.addEventListener("DOMContentLoaded", () => {
    const scheduleLoading = document.getElementById("scheduleLoading");
    if (scheduleLoading) {
        const showScheduleLoading = () => {
            scheduleLoading.hidden = false;
            document.body.setAttribute("aria-busy", "true");
        };

        document.querySelector(".schedule-filters form")?.addEventListener("submit", showScheduleLoading);
        document.querySelectorAll(".calendar-day[href]").forEach((day) => {
            day.addEventListener("click", showScheduleLoading);
        });
        window.addEventListener("pageshow", () => {
            scheduleLoading.hidden = true;
            document.body.removeAttribute("aria-busy");
        });
    }

    const cancelForm = document.getElementById("cancelReservationsForm");
    if (cancelForm) {
        cancelForm.addEventListener("submit", (event) => {
            const seleccionadas = cancelForm.querySelectorAll('input[name="espacios"]:checked');
            if (!seleccionadas.length) {
                event.preventDefault();
                window.alert("Selecciona al menos un espacio reservado para cancelar.");
                return;
            }
            if (!window.confirm(`¿Cancelar ${seleccionadas.length} espacio(s) seleccionado(s)?`)) {
                event.preventDefault();
            }
        });
    }

    const form = document.getElementById("formAsistente");
    if (!form) return;

    const historial = document.getElementById("chatHistorial");
    const input = document.getElementById("mensajeInput");

    function agregarBurbuja(texto, tipo) {
        const burbuja = document.createElement("div");
        burbuja.className = `chat-bubble ${tipo}`;
        burbuja.textContent = texto;
        historial.appendChild(burbuja);
        historial.scrollTop = historial.scrollHeight;
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const mensaje = input.value.trim();
        if (!mensaje) return;

        agregarBurbuja(mensaje, "user");
        input.value = "";

        agregarBurbuja("Escribiendo...", "asistente");
        const placeholder = historial.lastElementChild;

        try {
            const respuesta = await fetch("/api/asistente", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ mensaje }),
            });
            const datos = await respuesta.json();
            placeholder.textContent = datos.respuesta || datos.error || "No hubo respuesta.";
        } catch (error) {
            placeholder.textContent = "Error de conexión con el servidor.";
        }
    });
});
