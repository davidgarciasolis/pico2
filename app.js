let chart;

const API_URL = "https://api.mueblesavenida.com/items/temperaturas";

document.addEventListener("DOMContentLoaded", () => {
  const fechaDesdeInput = document.getElementById("fecha-desde");
  const fechaHastaInput = document.getElementById("fecha-hasta");
  const btnActualizar = document.getElementById("btn-actualizar");

  const { desde, hasta } = getRangoUltimaSemana();
  fechaDesdeInput.value = desde;
  fechaHastaInput.value = hasta;

  btnActualizar.addEventListener("click", cargarDatos);
  fechaDesdeInput.addEventListener("change", cargarDatos);
  fechaHastaInput.addEventListener("change", cargarDatos);

  cargarDatos();
});

function getRangoUltimaSemana() {
  const hoy = new Date();
  const hasta = toLocalDateString(hoy);
  const desdeDate = new Date(hoy);
  desdeDate.setDate(desdeDate.getDate() - 6);
  const desde = toLocalDateString(desdeDate);

  return { desde, hasta };
}

function toLocalDateString(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function buildDateRangeParams(desde, hasta) {
  const params = new URLSearchParams();
  params.set("sort", "fecha");
  params.set("limit", "1000");

  if (desde) {
    const start = new Date(`${desde}T00:00:00`);
    params.set("filter[fecha][_gte]", start.toISOString());
  }

  if (hasta) {
    const end = new Date(`${hasta}T23:59:59.999`);
    params.set("filter[fecha][_lte]", end.toISOString());
  }

  return params.toString();
}

async function cargarDatos() {
  const estado = document.getElementById("estado-carga");
  const fechaDesde = document.getElementById("fecha-desde").value;
  const fechaHasta = document.getElementById("fecha-hasta").value;

  if (fechaDesde && fechaHasta && fechaDesde > fechaHasta) {
    alert("La fecha 'desde' no puede ser mayor que la fecha 'hasta'.");
    return;
  }

  try {
    estado.textContent = "Cargando datos...";

    const query = buildDateRangeParams(fechaDesde, fechaHasta);
    const res = await fetch(`${API_URL}?${query}`);
    const json = await res.json();

    const datos = Array.isArray(json?.data) ? json.data : Array.isArray(json) ? json : [];
    const datosOrdenados = datos
      .filter((d) => d && (d.fecha || d.timestamp))
      .sort((a, b) => new Date(a.fecha || a.timestamp) - new Date(b.fecha || b.timestamp));

    if (!datosOrdenados.length) {
      estado.textContent = "No hay registros en el rango seleccionado.";
      dibujarGrafica([], []);
      return;
    }

    estado.textContent = `Mostrando ${datosOrdenados.length} registros entre ${fechaDesde || "inicio"} y ${fechaHasta || "fin"}.`;

    const labels = datosOrdenados.map((d) =>
      new Date(d.fecha || d.timestamp).toLocaleString()
    );
    const temperaturas = datosOrdenados.map((d) => d.temperatura);

    dibujarGrafica(labels, temperaturas);
  } catch (err) {
    console.error("Error cargando datos:", err);
    estado.textContent = "Error al obtener datos de la API.";
    alert("Error al obtener datos de la API");
  }
}

function dibujarGrafica(labels, data) {
  const ctx = document.getElementById("grafica");

  if (chart) chart.destroy();

  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Temperatura (°C)",
          data,
          borderColor: "#dc2626",
          backgroundColor: "rgba(220, 38, 38, 0.1)",
          tension: 0.3,
          fill: true,
          pointRadius: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      scales: {
        x: {
          ticks: {
            maxRotation: 45,
            minRotation: 45,
          },
        },
      },
    },
  });
}
