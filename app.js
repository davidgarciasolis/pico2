let chart;
let activeRequest = 0;
let activeController = null;

const API_URL = "https://api.mueblesavenida.com/items/temperaturas";

const dateFormatter = new Intl.DateTimeFormat("es-ES", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

const dateOnlyFormatter = new Intl.DateTimeFormat("es-ES", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

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
  params.set("fields", "fecha,temperatura,humedad");
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
  const ultimaActualizacion = document.getElementById("ultima-actualizacion");
  const fechaDesdeInput = document.getElementById("fecha-desde");
  const fechaHastaInput = document.getElementById("fecha-hasta");
  const btnActualizar = document.getElementById("btn-actualizar");

  const fechaDesde = fechaDesdeInput.value;
  const fechaHasta = fechaHastaInput.value;

  if (fechaDesde && fechaHasta && fechaDesde > fechaHasta) {
    estado.textContent = "La fecha inicial no puede ser mayor que la fecha final.";
    return;
  }

  if (activeController) {
    activeController.abort();
  }

  activeController = new AbortController();
  const requestId = ++activeRequest;

  setLoadingState(true, btnActualizar, fechaDesdeInput, fechaHastaInput);
  estado.textContent = "Cargando datos...";
  ultimaActualizacion.textContent = "";

  try {
    const query = buildDateRangeParams(fechaDesde, fechaHasta);
    const res = await fetch(`${API_URL}?${query}`, { signal: activeController.signal });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const json = await res.json();

    if (requestId !== activeRequest) {
      return;
    }

    const datos = Array.isArray(json?.data) ? json.data : Array.isArray(json) ? json : [];
    const datosOrdenados = datos
      .filter((dato) => dato && (dato.fecha || dato.timestamp))
      .sort((a, b) => new Date(a.fecha || a.timestamp) - new Date(b.fecha || b.timestamp));

    const datosValidos = datosOrdenados.filter(
      (dato) =>
        tieneValorNumerico(dato.temperatura) || tieneValorNumerico(dato.humedad),
    );

    if (!datosValidos.length) {
      estado.textContent = "No hay registros válidos en el rango seleccionado.";
      ultimaActualizacion.textContent = formatRangeLabel(fechaDesde, fechaHasta);
      actualizarResumen([], [], fechaDesde, fechaHasta, null);
      dibujarGrafica([], [], []);
      return;
    }

    const labels = datosValidos.map((dato) => formatChartLabel(dato.fecha || dato.timestamp));
    const temperaturas = datosValidos.map((dato) =>
      tieneValorNumerico(dato.temperatura) ? Number(dato.temperatura) : null,
    );
    const humedades = datosValidos.map((dato) =>
      tieneValorNumerico(dato.humedad) ? Number(dato.humedad) : null,
    );
    const ultimoDato = datosValidos[datosValidos.length - 1];

    estado.textContent = `Mostrando ${datosValidos.length} registros entre ${formatDisplayRange(
      fechaDesde,
      fechaHasta,
    )}.`;
    ultimaActualizacion.textContent = `Última lectura: ${formatDateTime(
      ultimoDato.fecha || ultimoDato.timestamp,
    )}`;

    actualizarResumen(temperaturas, humedades, fechaDesde, fechaHasta, ultimoDato);
    dibujarGrafica(labels, temperaturas, humedades);
  } catch (err) {
    if (err.name === "AbortError") {
      return;
    }

    console.error("Error cargando datos:", err);
    estado.textContent = "Error al obtener datos de la API.";
    ultimaActualizacion.textContent = "No se pudo actualizar la vista.";
    actualizarResumen([], [], fechaDesde, fechaHasta, null);
    dibujarGrafica([], [], []);
  } finally {
    if (requestId === activeRequest) {
      setLoadingState(false, btnActualizar, fechaDesdeInput, fechaHastaInput);
    }
  }
}

function setLoadingState(isLoading, button, ...inputs) {
  button.disabled = isLoading;
  button.textContent = isLoading ? "Actualizando..." : "Actualizar datos";
  inputs.forEach((input) => {
    input.disabled = isLoading;
  });
}

function dibujarGrafica(labels, temperaturas, humedades) {
  const canvas = document.getElementById("grafica");
  const ctx = canvas.getContext("2d");

  if (chart) {
    chart.destroy();
  }

  if (!labels.length) {
    chart = new Chart(ctx, {
      type: "line",
      data: { labels: [], datasets: [] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
        },
        scales: {
          y: {
            grid: { display: false },
            ticks: { display: false },
          },
          x: {
            grid: { display: false },
            ticks: { display: false },
          },
        },
      },
    });
    return;
  }

  const temperaturaGradient = ctx.createLinearGradient(0, 0, 0, canvas.height || 360);
  temperaturaGradient.addColorStop(0, "rgba(234, 88, 12, 0.28)");
  temperaturaGradient.addColorStop(1, "rgba(234, 88, 12, 0.02)");

  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Temperatura (°C)",
          data: temperaturas,
          yAxisID: "temperatura",
          borderColor: "#ea580c",
          backgroundColor: temperaturaGradient,
          tension: 0.33,
          fill: true,
          borderWidth: 3,
          pointRadius: 2,
          pointHoverRadius: 5,
          pointBackgroundColor: "#ffffff",
          pointBorderColor: "#ea580c",
          pointHoverBorderWidth: 3,
        },
        {
          label: "Humedad (%)",
          data: humedades,
          yAxisID: "humedad",
          borderColor: "#0284c7",
          backgroundColor: "transparent",
          tension: 0.33,
          fill: false,
          borderWidth: 3,
          pointRadius: 2,
          pointHoverRadius: 5,
          pointBackgroundColor: "#ffffff",
          pointBorderColor: "#0284c7",
          pointHoverBorderWidth: 3,
          spanGaps: true,
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
          display: true,
          position: "top",
          labels: {
            boxWidth: 12,
            usePointStyle: true,
            color: "#475569",
          },
        },
        tooltip: {
          displayColors: false,
          backgroundColor: "rgba(15, 23, 42, 0.96)",
          borderColor: "rgba(148, 163, 184, 0.22)",
          borderWidth: 1,
          titleColor: "#ffffff",
          bodyColor: "#e5eefb",
          padding: 12,
        },
      },
      scales: {
        temperatura: {
          type: "linear",
          position: "left",
          grid: {
            color: "rgba(148, 163, 184, 0.2)",
          },
          ticks: {
            color: "#475569",
            padding: 8,
            callback: (value) => `${value} °C`,
          },
        },
        humedad: {
          type: "linear",
          position: "right",
          min: 0,
          max: 100,
          grid: {
            drawOnChartArea: false,
          },
          ticks: {
            color: "#0284c7",
            padding: 8,
            callback: (value) => `${value} %`,
          },
        },
        x: {
          grid: {
            display: false,
          },
          ticks: {
            color: "#475569",
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 6,
          },
        },
      },
    },
  });
}

function actualizarResumen(temperaturas, humedades, fechaDesde, fechaHasta, ultimoDato) {
  const registrosEl = document.getElementById("metric-registros");
  const temperaturaMediaEl = document.getElementById("metric-temperatura-media");
  const humedadMediaEl = document.getElementById("metric-humedad-media");
  const rangoEl = document.getElementById("metric-rango");
  const temperaturasValidas = temperaturas.filter(Number.isFinite);
  const humedadesValidas = humedades.filter(Number.isFinite);

  if (!temperaturasValidas.length && !humedadesValidas.length) {
    registrosEl.textContent = "0";
    temperaturaMediaEl.textContent = "--";
    humedadMediaEl.textContent = "--";
    rangoEl.textContent = formatRangeLabel(fechaDesde, fechaHasta);
    return;
  }

  const mediaTemperatura = calcularMedia(temperaturasValidas);
  const mediaHumedad = calcularMedia(humedadesValidas);
  const min = temperaturasValidas.length ? Math.min(...temperaturasValidas) : null;
  const max = temperaturasValidas.length ? Math.max(...temperaturasValidas) : null;

  registrosEl.textContent = String(Math.max(temperaturasValidas.length, humedadesValidas.length));
  temperaturaMediaEl.textContent = Number.isFinite(mediaTemperatura)
    ? `${mediaTemperatura.toFixed(1)} °C`
    : "--";
  humedadMediaEl.textContent = Number.isFinite(mediaHumedad) ? `${mediaHumedad.toFixed(1)} %` : "--";

  if (ultimoDato && temperaturasValidas.length) {
    rangoEl.textContent = `${min.toFixed(1)} - ${max.toFixed(1)} °C`;
  } else {
    rangoEl.textContent = formatRangeLabel(fechaDesde, fechaHasta);
  }
}

function calcularMedia(valores) {
  if (!valores.length) return null;
  return valores.reduce((acc, value) => acc + value, 0) / valores.length;
}

function tieneValorNumerico(valor) {
  return valor !== null && valor !== "" && valor !== undefined && Number.isFinite(Number(valor));
}

function formatRangeLabel(desde, hasta) {
  if (desde && hasta) return `${desde} → ${hasta}`;
  if (desde) return `Desde ${desde}`;
  if (hasta) return `Hasta ${hasta}`;
  return "Sin rango";
}

function formatDisplayRange(desde, hasta) {
  if (desde && hasta) return `${formatDateTime(desde)} y ${formatDateTime(hasta)}`;
  if (desde) return `desde ${formatDateTime(desde)}`;
  if (hasta) return `hasta ${formatDateTime(hasta)}`;
  return "sin rango";
}

function formatChartLabel(value) {
  return formatDateTime(value, dateFormatter);
}

function formatDateTime(value, formatter = dateOnlyFormatter) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Fecha no disponible";
  }

  return formatter.format(date);
}
