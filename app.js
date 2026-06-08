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
      actualizarResumen([], fechaDesde, fechaHasta);
      dibujarGrafica([], []);
      return;
    }

    estado.textContent = `Mostrando ${datosOrdenados.length} registros entre ${fechaDesde || "inicio"} y ${fechaHasta || "fin"}.`;

    const datosValidos = datosOrdenados.filter((d) => Number.isFinite(Number(d.temperatura)));
    const labels = datosValidos.map((d) => new Date(d.fecha || d.timestamp).toLocaleString());
    const temperaturas = datosValidos.map((d) => Number(d.temperatura));

    actualizarResumen(temperaturas, fechaDesde, fechaHasta);

    dibujarGrafica(labels, temperaturas);
  } catch (err) {
    console.error("Error cargando datos:", err);
    estado.textContent = "Error al obtener datos de la API.";
    actualizarResumen([], fechaDesde, fechaHasta);
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
          borderColor: "#ea580c",
          backgroundColor: "rgba(234, 88, 12, 0.10)",
          tension: 0.3,
          fill: true,
          pointRadius: 2,
          pointHoverRadius: 4,
          pointBackgroundColor: "#fdba74",
          pointBorderColor: "#ea580c",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          display: false,
        },
        tooltip: {
          displayColors: false,
          backgroundColor: "rgba(15, 23, 42, 0.96)",
          borderColor: "rgba(148, 163, 184, 0.22)",
          borderWidth: 1,
          titleColor: "#ffffff",
          bodyColor: "#e5eefb",
        },
      },
      scales: {
        y: {
          grid: {
            color: "rgba(148, 163, 184, 0.14)",
          },
          ticks: {
            color: "#c7d5e6",
          },
        },
        x: {
          grid: {
            display: false,
          },
          ticks: {
            color: "#c7d5e6",
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 6,
          },
        },
      },
    },
  });
}

function actualizarResumen(temperaturas, fechaDesde, fechaHasta) {
  const registrosEl = document.getElementById("metric-registros");
  const mediaEl = document.getElementById("metric-media");
  const rangoEl = document.getElementById("metric-rango");

  if (!temperaturas.length) {
    registrosEl.textContent = "0";
    mediaEl.textContent = "--";
    rangoEl.textContent = formatRango(fechaDesde, fechaHasta);
    return;
  }

  const suma = temperaturas.reduce((acc, value) => acc + value, 0);
  const media = suma / temperaturas.length;
  const min = Math.min(...temperaturas);
  const max = Math.max(...temperaturas);

  registrosEl.textContent = String(temperaturas.length);
  mediaEl.textContent = `${media.toFixed(1)} °C`;
  rangoEl.textContent = `${min.toFixed(1)} - ${max.toFixed(1)} °C`;
}

function formatRango(desde, hasta) {
  if (desde && hasta) return `${desde} → ${hasta}`;
  if (desde) return `Desde ${desde}`;
  if (hasta) return `Hasta ${hasta}`;
  return "Sin rango";
}
