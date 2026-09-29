from flask import Flask, jsonify, render_template_string
import json
import os
import ssl
import time
import urllib.request
import urllib.error
import urllib.parse

app = Flask(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

NAMESPACE = os.getenv("NAMESPACE", "hardened-app")

KUBERNETES_API = os.getenv(
    "KUBERNETES_API",
    "https://kubernetes.default.svc"
)

PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "http://monitoring-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090"
)

GRAFANA_URL = os.getenv(
    "GRAFANA_URL",
    "http://monitoring-grafana.monitoring.svc.cluster.local:80"
)

SERVICE_ACCOUNT_TOKEN_PATH = (
    "/var/run/secrets/kubernetes.io/serviceaccount/token"
)

SERVICE_ACCOUNT_CA_PATH = (
    "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
)


# ============================================================
# KUBERNETES AUTHENTICATION
# ============================================================

def get_kubernetes_token():

    try:

        with open(
            SERVICE_ACCOUNT_TOKEN_PATH,
            "r"
        ) as f:

            return f.read().strip()

    except Exception:

        return None


def get_kubernetes_ssl_context():

    try:

        return ssl.create_default_context(
            cafile=SERVICE_ACCOUNT_CA_PATH
        )

    except Exception:

        return ssl.create_default_context()


def kubernetes_request(path):

    token = get_kubernetes_token()

    if not token:

        raise RuntimeError(
            "Kubernetes service account token not found"
        )

    url = KUBERNETES_API + path

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )

    context = get_kubernetes_ssl_context()

    with urllib.request.urlopen(
        request,
        context=context,
        timeout=5
    ) as response:

        return json.loads(
            response.read().decode("utf-8")
        )


# ============================================================
# KUBERNETES POD STATUS
# ============================================================

def get_pod_status():

    try:

        # Only count hardened application pods.
        # cpu-load is intentionally excluded.
        data = kubernetes_request(
            f"/api/v1/namespaces/{NAMESPACE}/pods"
        )

        pods = data.get("items", [])

        app_pods = []

        for pod in pods:

            labels = (
                pod.get("metadata", {})
                .get("labels", {})
            )

            # Application deployment pods use app=hardened-app.
            if labels.get("app") == "hardened-app":

                app_pods.append(pod)

        total = len(app_pods)

        running = sum(
            1
            for pod in app_pods
            if pod.get("status", {}).get("phase") == "Running"
        )

        return {
            "running": running,
            "total": total,
            "status": (
                "Healthy"
                if running == total and total > 0
                else "Warning"
            )
        }

    except Exception as e:

        print(
            "Pod status error:",
            e
        )

        return {
            "running": 0,
            "total": 0,
            "status": "Offline"
        }


# ============================================================
# KUBERNETES NODE STATUS
# ============================================================

def get_node_status():

    try:

        data = kubernetes_request(
            "/api/v1/nodes"
        )

        nodes = data.get(
            "items",
            []
        )

        total = len(nodes)

        ready = 0

        for node in nodes:

            conditions = (
                node.get("status", {})
                .get("conditions", [])
            )

            for condition in conditions:

                if (
                    condition.get("type") == "Ready"
                    and condition.get("status") == "True"
                ):

                    ready += 1

                    break

        return {
            "ready": ready,
            "total": total,
            "status": (
                "Healthy"
                if ready == total and total > 0
                else "Warning"
            )
        }

    except Exception as e:

        print(
            "Node status error:",
            e
        )

        return {
            "ready": 0,
            "total": 0,
            "status": "Offline"
        }


# ============================================================
# GENERIC HTTP GET
# ============================================================

def http_get(url):

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json"
        },
        method="GET"
    )

    with urllib.request.urlopen(
        request,
        timeout=5
    ) as response:

        return response.read().decode("utf-8")


# ============================================================
# PROMETHEUS INSTANT QUERY
# ============================================================

def prometheus_query(query):

    try:

        encoded_query = urllib.parse.urlencode({
            "query": query
        })

        url = (
            PROMETHEUS_URL
            + "/api/v1/query?"
            + encoded_query
        )

        raw = http_get(url)

        data = json.loads(raw)

        if data.get("status") != "success":

            return 0.0

        result = (
            data.get("data", {})
            .get("result", [])
        )

        if not result:

            return 0.0

        value = result[0].get(
            "value",
            []
        )

        if len(value) < 2:

            return 0.0

        return float(value[1])

    except Exception as e:

        print(
            "Prometheus query error:",
            e
        )

        return 0.0


# ============================================================
# PROMETHEUS RANGE QUERY
# ============================================================

def prometheus_range_query(
    query,
    minutes=10,
    step=10
):

    try:

        end = int(
            time.time()
        )

        start = (
            end -
            (minutes * 60)
        )

        params = urllib.parse.urlencode({
            "query": query,
            "start": start,
            "end": end,
            "step": step
        })

        url = (
            PROMETHEUS_URL
            + "/api/v1/query_range?"
            + params
        )

        raw = http_get(url)

        data = json.loads(raw)

        if data.get("status") != "success":

            return []

        results = (
            data.get("data", {})
            .get("result", [])
        )

        if not results:

            return []

        values = (
            results[0]
            .get("values", [])
        )

        history = []

        for item in values:

            if len(item) < 2:

                continue

            try:

                value = float(
                    item[1]
                )

                if value != value:

                    continue

                value = max(
                    0.0,
                    min(
                        100.0,
                        value
                    )
                )

                history.append(
                    round(
                        value,
                        2
                    )
                )

            except Exception:

                continue

        return history

    except Exception as e:

        print(
            "Prometheus range query error:",
            e
        )

        return []


# ============================================================
# CPU USAGE
# ============================================================

def get_cpu_usage():

    query = """
    100 * (
        1 -
        avg(
            rate(
                node_cpu_seconds_total{
                    mode="idle"
                }[1m]
            )
        )
    )
    """

    value = prometheus_query(
        query
    )

    return round(
        max(
            0.0,
            min(
                100.0,
                value
            )
        ),
        2
    )


# ============================================================
# CPU HISTORICAL DATA
# ============================================================

def get_cpu_history():

    query = """
    100 * (
        1 -
        avg(
            rate(
                node_cpu_seconds_total{
                    mode="idle"
                }[1m]
            )
        )
    )
    """

    return prometheus_range_query(
        query,
        minutes=10,
        step=10
    )


# ============================================================
# MEMORY USAGE
# ============================================================

def get_memory_usage():

    query = """
    100 *
    (
        sum(
            container_memory_working_set_bytes{
                container!="",
                image!=""
            }
        )
        /
        sum(
            kube_node_status_allocatable{
                resource="memory",
                unit="byte"
            }
        )
    )
    """

    value = prometheus_query(query)

    return round(
        max(
            0.0,
            min(
                100.0,
                value
            )
        ),
        2
    )

def get_memory_history():

    query = """
    100 *
    (
        sum(
            container_memory_working_set_bytes{
                container!="",
                image!=""
            }
        )
        /
        sum(
            kube_node_status_allocatable{
                resource="memory",
                unit="byte"
            }
        )
    )
    """

    return prometheus_range_query(
        query,
        minutes=10,
        step=10
    )


# ============================================================
# PROMETHEUS HEALTH
# ============================================================

def get_prometheus_health():

    try:

        response = http_get(
            PROMETHEUS_URL
            + "/-/healthy"
        )

        if response:

            return "Healthy"

    except Exception as e:

        print(
            "Prometheus health error:",
            e
        )

    return "Offline"


# ============================================================
# GRAFANA HEALTH
# ============================================================

def get_grafana_health():

    try:

        raw = http_get(
            GRAFANA_URL
            + "/api/health"
        )

        data = json.loads(
            raw
        )

        if data.get(
            "database"
        ) == "ok":

            return "Healthy"

        if data.get(
            "status"
        ) == "ok":

            return "Healthy"

    except Exception as e:

        print(
            "Grafana health error:",
            e
        )

    return "Offline"


# ============================================================
# MONITORING DATA
# ============================================================

def get_monitoring_data():

    pods = get_pod_status()

    nodes = get_node_status()

    prometheus = (
        get_prometheus_health()
    )

    grafana = (
        get_grafana_health()
    )

    cpu = get_cpu_usage()

    memory = get_memory_usage()

    cpu_history = (
        get_cpu_history()
    )

    memory_history = (
        get_memory_history()
    )

    monitoring_status = (
        "Healthy"
        if (
            prometheus == "Healthy"
            and
            grafana == "Healthy"
        )
        else "Offline"
    )

    return {

        "namespace": NAMESPACE,

        "pods": pods,

        "nodes": nodes,

        "prometheus": prometheus,

        "grafana": grafana,

        "monitoring": monitoring_status,

        "cpu": cpu,

        "memory": memory,

        "cpu_history": cpu_history,

        "memory_history": memory_history,

    }


# ============================================================
# HEALTH ROUTES
# ============================================================

@app.route("/health")
def health():

    return jsonify({
        "status": "healthy"
    })


@app.route("/ready")
def ready():

    return jsonify({
        "status": "ready"
    })


@app.route("/monitoring-data")
def monitoring_data():

    return jsonify(
        get_monitoring_data()
    )


# ============================================================
# DASHBOARD UI
# ============================================================

@app.route("/")
def dashboard():

    return render_template_string("""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>
Security Hardened K8s Platform
</title>

<style>

* {
    box-sizing: border-box;
}

body {

    margin: 0;

    background: #0f172a;

    color: #e5e7eb;

    font-family:
        Inter,
        Arial,
        Helvetica,
        sans-serif;

    min-height: 100vh;
}

.container {

    width: 100%;

    max-width: 1110px;

    margin: 0 auto;

    padding: 28px 20px 20px;
}


/* =========================================================
   HEADER
   ========================================================= */

.header {

    background: #111827;

    border: 1px solid #293548;

    border-radius: 10px;

    padding: 20px 18px;

    margin-bottom: 16px;

    box-shadow:
        0 8px 25px rgba(0,0,0,0.12);
}

.header h1 {

    margin: 0;

    font-size: 24px;

    font-weight: 800;

    letter-spacing: -0.5px;
}

.subtitle {

    margin-top: 5px;

    color: #94a3b8;

    font-size: 13px;
}

.health-badge {

    display: inline-flex;

    align-items: center;

    gap: 6px;

    margin-top: 12px;

    padding: 6px 12px;

    border-radius: 20px;

    background: #064e3b;

    color: #6ee7b7;

    font-size: 12px;

    font-weight: 700;
}

.health-dot {

    width: 6px;

    height: 6px;

    background: #34d399;

    border-radius: 50%;
}


/* =========================================================
   STATUS CARDS
   ========================================================= */

.status-grid {

    display: grid;

    grid-template-columns:
        repeat(4, 1fr);

    gap: 12px;

    margin-bottom: 14px;
}

.card {

    background: #111827;

    border: 1px solid #293548;

    border-radius: 9px;

    padding: 14px 15px;

    min-height: 74px;
}

.card-label {

    color: #8492a6;

    font-size: 11px;

    text-transform: uppercase;

    margin-bottom: 7px;
}

.card-value {

    color: #f1f5f9;

    font-size: 20px;

    font-weight: 750;
}

.healthy {

    color: #5ee7b7 !important;
}

.warning {

    color: #fbbf24 !important;
}

.offline {

    color: #e5e7eb !important;
}


/* =========================================================
   METRIC CARDS
   ========================================================= */

.metric-grid {

    display: grid;

    grid-template-columns:
        repeat(4, 1fr);

    gap: 12px;

    margin-bottom: 14px;
}

.metric-card {

    background: #111827;

    border: 1px solid #293548;

    border-radius: 9px;

    padding: 14px 15px;

    min-height: 74px;
}

.metric-title {

    color: #8492a6;

    font-size: 11px;

    text-transform: uppercase;

    margin-bottom: 7px;
}

.metric-value {

    color: #f1f5f9;

    font-size: 20px;

    font-weight: 750;
}


/* =========================================================
   CHART GRID
   ========================================================= */

.chart-grid {

    display: grid;

    grid-template-columns:
        repeat(2, 1fr);

    gap: 12px;
}

.chart-card {

    background: #111827;

    border: 1px solid #293548;

    border-radius: 9px;

    padding: 14px 15px;

    min-width: 0;
}

.chart-title {

    color: #8492a6;

    font-size: 11px;

    text-transform: uppercase;

    margin-bottom: 10px;
}

.graph-container {

    position: relative;

    width: 100%;

    height: 230px;

    min-height: 230px;

    background: #020617;

    border: 1px solid #111827;

    border-radius: 8px;

    padding: 8px;

    overflow: hidden;
}

.graph-container canvas {

    display: block;

    width: 100% !important;

    height: 100% !important;
}


/* =========================================================
   FOOTER
   ========================================================= */

.footer {

    text-align: center;

    color: #64748b;

    font-size: 11px;

    padding: 14px 0 4px;
}


/* =========================================================
   RESPONSIVE
   ========================================================= */

@media (max-width: 900px) {

    .status-grid,
    .metric-grid {

        grid-template-columns:
            repeat(2, 1fr);
    }

    .chart-grid {

        grid-template-columns: 1fr;
    }
}

@media (max-width: 550px) {

    .container {

        padding: 15px 10px;
    }

    .status-grid,
    .metric-grid {

        grid-template-columns: 1fr;
    }

    .header h1 {

        font-size: 20px;
    }
}

</style>

</head>


<body>

<div class="container">


<!-- ======================================================
     HEADER
======================================================= -->

<div class="header">

    <h1>
        SECURITY HARDENED K8S PLATFORM
    </h1>

    <div class="subtitle">
        DevOps & Cloud Engineer | Kubernetes Security & Monitoring
    </div>

    <div class="health-badge">

        <span class="health-dot"></span>

        <span id="overall-status">
            Healthy
        </span>

    </div>

</div>


<!-- ======================================================
     STATUS CARDS
======================================================= -->

<div class="status-grid">

    <div class="card">

        <div class="card-label">
            API
        </div>

        <div
            id="api-status"
            class="card-value healthy"
        >
            Healthy
        </div>

    </div>


    <div class="card">

        <div class="card-label">
            Security
        </div>

        <div
            id="security-status"
            class="card-value healthy"
        >
            Protected
        </div>

    </div>


    <div class="card">

        <div class="card-label">
            Monitoring
        </div>

        <div
            id="monitoring-status"
            class="card-value"
        >
            Loading
        </div>

    </div>


    <div class="card">

        <div class="card-label">
            Namespace
        </div>

        <div
            id="namespace"
            class="card-value"
        >
            hardened-app
        </div>

    </div>


    <div class="card">

        <div class="card-label">
            Pods
        </div>

        <div
            id="pods"
            class="card-value"
        >
            0 / 0
        </div>

    </div>


    <div class="card">

        <div class="card-label">
            Nodes
        </div>

        <div
            id="nodes"
            class="card-value"
        >
            0 / 0
        </div>

    </div>


    <div class="card">

        <div class="card-label">
            Prometheus
        </div>

        <div
            id="prometheus"
            class="card-value"
        >
            Loading
        </div>

    </div>


    <div class="card">

        <div class="card-label">
            Grafana
        </div>

        <div
            id="grafana"
            class="card-value"
        >
            Loading
        </div>

    </div>

</div>


<!-- ======================================================
     METRIC CARDS
======================================================= -->

<div class="metric-grid">


    <div class="metric-card">

        <div class="metric-title">
            CPU Usage
        </div>

        <div
            id="cpu-value"
            class="metric-value"
        >
            0%
        </div>

    </div>


    <div class="metric-card">

        <div class="metric-title">
            Memory Usage
        </div>

        <div
            id="memory-value"
            class="metric-value"
        >
            0%
        </div>

    </div>


    <div class="metric-card">

        <div class="metric-title">
            Platform
        </div>

        <div class="metric-value">
            Kubernetes
        </div>

    </div>


    <div class="metric-card">

        <div class="metric-title">
            Security
        </div>

        <div class="metric-value healthy">
            RBAC + NetworkPolicy
        </div>

    </div>

</div>


<!-- ======================================================
     CHARTS
======================================================= -->

<div class="chart-grid">


    <!-- CPU -->

    <div class="chart-card">

        <div class="chart-title">
            CPU UTILIZATION
        </div>

        <div class="graph-container">

            <canvas id="cpuChart"></canvas>

        </div>

    </div>


    <!-- MEMORY -->

    <div class="chart-card">

        <div class="chart-title">
            MEMORY UTILIZATION
        </div>

        <div class="graph-container">

            <canvas id="memoryChart"></canvas>

        </div>

    </div>

</div>


<div class="footer">

    Security Hardened Kubernetes Platform
    |
    Prometheus
    |
    Grafana
    |
    RBAC
    |
    NetworkPolicy

</div>


</div>


<script>

/* ==========================================================
   GRAPH DATA
========================================================== */

const cpuData = [];

const memoryData = [];

const MAX_POINTS = 30;


/* ==========================================================
   CANVAS PREPARATION
========================================================== */

function prepareCanvas(canvas) {

    const parent =
        canvas.parentElement;

    const rect =
        parent.getBoundingClientRect();

    const width =
        Math.max(
            Math.floor(
                rect.width - 16
            ),
            280
        );

    const height =
        Math.max(
            Math.floor(
                rect.height - 16
            ),
            180
        );

    const dpr =
        window.devicePixelRatio || 1;

    canvas.width =
        Math.floor(
            width * dpr
        );

    canvas.height =
        Math.floor(
            height * dpr
        );

    canvas.style.width =
        width + "px";

    canvas.style.height =
        height + "px";

    const ctx =
        canvas.getContext("2d");

    ctx.setTransform(
        dpr,
        0,
        0,
        dpr,
        0,
        0
    );

    return {
        ctx,
        width,
        height
    };
}


/* ==========================================================
   DRAW GRAPH
========================================================== */

function drawGraph(
    canvasId,
    data,
    lineColor
) {

    const canvas =
        document.getElementById(
            canvasId
        );

    if (!canvas) {

        return;
    }

    const {
        ctx,
        width,
        height
    } = prepareCanvas(canvas);


    /* Background */

    ctx.fillStyle =
        "#020617";

    ctx.fillRect(
        0,
        0,
        width,
        height
    );


    /* Graph padding */

    const left = 34;

    const right = 10;

    const top = 15;

    const bottom = 15;

    const graphWidth =
        width -
        left -
        right;

    const graphHeight =
        height -
        top -
        bottom;


    /* ======================================================
       HORIZONTAL GRID
    ====================================================== */

    const levels = [
        100,
        75,
        50,
        25,
        0
    ];

    ctx.font =
        "11px Arial";

    levels.forEach(
        level => {

            const y =
                top +
                (
                    (100 - level)
                    / 100
                ) *
                graphHeight;

            ctx.beginPath();

            ctx.moveTo(
                left,
                y
            );

            ctx.lineTo(
                width - right,
                y
            );

            ctx.strokeStyle =
                "#253044";

            ctx.lineWidth = 1;

            ctx.stroke();

            ctx.fillStyle =
                "#64748b";

            ctx.textAlign =
                "right";

            ctx.textBaseline =
                "middle";

            ctx.fillText(
                level + "%",
                left - 5,
                y
            );

        }
    );


    /* ======================================================
       NO DATA
    ====================================================== */

    if (
        !data ||
        data.length === 0
    ) {

        ctx.fillStyle =
            "#64748b";

        ctx.font =
            "12px Arial";

        ctx.textAlign =
            "center";

        ctx.textBaseline =
            "middle";

        ctx.fillText(
            "Waiting for monitoring data...",
            width / 2,
            height / 2
        );

        return;
    }


    /* ======================================================
       CALCULATE POINTS
    ====================================================== */

    const points =
        data.map(
            (value, index) => {

                const x =
                    data.length === 1
                        ? left +
                          graphWidth / 2
                        : left +
                          (
                              index /
                              (
                                  data.length -
                                  1
                              )
                          ) *
                          graphWidth;

                const safeValue =
                    Math.max(
                        0,
                        Math.min(
                            100,
                            Number(value) || 0
                        )
                    );

                const y =
                    top +
                    (
                        (100 - safeValue)
                        / 100
                    ) *
                    graphHeight;

                return {
                    x,
                    y,
                    value:
                        safeValue
                };

            }
        );


    /* ======================================================
       AREA
    ====================================================== */

    if (
        points.length >= 2
    ) {

        ctx.beginPath();

        ctx.moveTo(
            points[0].x,
            height - bottom
        );

        points.forEach(
            point => {

                ctx.lineTo(
                    point.x,
                    point.y
                );

            }
        );

        ctx.lineTo(
            points[
                points.length - 1
            ].x,
            height - bottom
        );

        ctx.closePath();

        ctx.fillStyle =
            lineColor === "cpu"
                ? "rgba(34,197,94,0.10)"
                : "rgba(167,139,250,0.10)";

        ctx.fill();

    }


    /* ======================================================
       ZIG-ZAG LINE
    ====================================================== */

    ctx.beginPath();

    points.forEach(
        (point, index) => {

            if (
                index === 0
            ) {

                ctx.moveTo(
                    point.x,
                    point.y
                );

            } else {

                ctx.lineTo(
                    point.x,
                    point.y
                );

            }

        }
    );

    ctx.strokeStyle =
        lineColor === "cpu"
            ? "#22c55e"
            : "#a78bfa";

    ctx.lineWidth = 3;

    ctx.lineJoin =
        "miter";

    ctx.lineCap =
        "round";

    ctx.stroke();


    /* ======================================================
       DATA POINTS
    ====================================================== */

    points.forEach(
        point => {

            ctx.beginPath();

            ctx.arc(
                point.x,
                point.y,
                2.5,
                0,
                Math.PI * 2
            );

            ctx.fillStyle =
                lineColor === "cpu"
                    ? "#22c55e"
                    : "#a78bfa";

            ctx.fill();

        }
    );


    /* ======================================================
       CURRENT POINT
    ====================================================== */

    const latest =
        points[
            points.length - 1
        ];

    ctx.beginPath();

    ctx.arc(
        latest.x,
        latest.y,
        4,
        0,
        Math.PI * 2
    );

    ctx.fillStyle =
        lineColor === "cpu"
            ? "#22c55e"
            : "#a78bfa";

    ctx.fill();

}


/* ==========================================================
   STATUS COLOR ONLY
========================================================== */

function setStatusColor(
    elementId,
    value
) {

    const element =
        document.getElementById(
            elementId
        );

    if (!element) {

        return;
    }

    element.classList.remove(
        "healthy",
        "warning",
        "offline"
    );

    if (
        value === "Healthy"
    ) {

        element.classList.add(
            "healthy"
        );

    } else if (
        value === "Warning"
    ) {

        element.classList.add(
            "warning"
        );

    } else {

        element.classList.add(
            "offline"
        );

    }

}


/* ==========================================================
   UPDATE MONITORING
========================================================== */

async function loadMonitoringData() {

    try {

        const response =
            await fetch(
                "/monitoring-data",
                {
                    cache: "no-store"
                }
            );

        if (!response.ok) {

            throw new Error(
                "Monitoring API failed"
            );
        }

        const data =
            await response.json();


        /* ==================================================
           NAMESPACE
        ================================================== */

        document.getElementById(
            "namespace"
        ).textContent =
            data.namespace ||
            "hardened-app";


        /* ==================================================
           PODS
        ================================================== */

        const runningPods =
            data.pods?.running ?? 0;

        const totalPods =
            data.pods?.total ?? 0;

        document.getElementById(
            "pods"
        ).textContent =
            `${runningPods} / ${totalPods}`;

        setStatusColor(
            "pods",
            data.pods?.status ||
            "Offline"
        );


        /* ==================================================
           NODES
        ================================================== */

        const readyNodes =
            data.nodes?.ready ?? 0;

        const totalNodes =
            data.nodes?.total ?? 0;

        document.getElementById(
            "nodes"
        ).textContent =
            `${readyNodes} / ${totalNodes}`;

        setStatusColor(
            "nodes",
            data.nodes?.status ||
            "Offline"
        );


        /* ==================================================
           PROMETHEUS
        ================================================== */

        const prometheus =
            data.prometheus ||
            "Offline";

        setStatusColor(
            "prometheus",
            prometheus
        );

        document.getElementById(
            "prometheus"
        ).textContent =
            prometheus;


        /* ==================================================
           GRAFANA
        ================================================== */

        const grafana =
            data.grafana ||
            "Offline";

        setStatusColor(
            "grafana",
            grafana
        );

        document.getElementById(
            "grafana"
        ).textContent =
            grafana;


        /* ==================================================
           MONITORING
        ================================================== */

        const monitoring =
            data.monitoring ||
            "Offline";

        setStatusColor(
            "monitoring-status",
            monitoring
        );

        document.getElementById(
            "monitoring-status"
        ).textContent =
            monitoring;


        /* ==================================================
           CPU CURRENT VALUE
        ================================================== */

        const cpu =
            Number(
                data.cpu
            ) || 0;

        document.getElementById(
            "cpu-value"
        ).textContent =
            cpu.toFixed(2)
            + "%";


        /* ==================================================
           CPU HISTORICAL DATA
        ================================================== */

        const cpuHistory =
            Array.isArray(
                data.cpu_history
            )
                ? data.cpu_history
                : [];

        cpuData.length = 0;

        cpuHistory.forEach(
            value => {

                const number =
                    Number(value);

                if (
                    Number.isFinite(
                        number
                    )
                ) {

                    cpuData.push(
                        Math.max(
                            0,
                            Math.min(
                                100,
                                number
                            )
                        )
                    );

                }

            }
        );


        if (
            cpuData.length >
            MAX_POINTS
        ) {

            cpuData.splice(
                0,
                cpuData.length -
                MAX_POINTS
            );

        }


        drawGraph(
            "cpuChart",
            cpuData,
            "cpu"
        );


        /* ==================================================
           MEMORY CURRENT VALUE
        ================================================== */

        const memory =
            Number(
                data.memory
            ) || 0;

        document.getElementById(
            "memory-value"
        ).textContent =
            memory.toFixed(2)
            + "%";


        /* ==================================================
           MEMORY HISTORICAL DATA
        ================================================== */

        const memoryHistory =
            Array.isArray(
                data.memory_history
            )
                ? data.memory_history
                : [];

        memoryData.length = 0;

        memoryHistory.forEach(
            value => {

                const number =
                    Number(value);

                if (
                    Number.isFinite(
                        number
                    )
                ) {

                    memoryData.push(
                        Math.max(
                            0,
                            Math.min(
                                100,
                                number
                            )
                        )
                    );

                }

            }
        );


        if (
            memoryData.length >
            MAX_POINTS
        ) {

            memoryData.splice(
                0,
                memoryData.length -
                MAX_POINTS
            );

        }


        drawGraph(
            "memoryChart",
            memoryData,
            "memory"
        );


        /* ==================================================
           OVERALL STATUS
        ================================================== */

        if (
            data.prometheus ===
                "Healthy"
            &&
            data.grafana ===
                "Healthy"
        ) {

            document.getElementById(
                "overall-status"
            ).textContent =
                "Healthy";

        } else {

            document.getElementById(
                "overall-status"
            ).textContent =
                "Monitoring Warning";

        }

    } catch (error) {

        console.error(
            "Monitoring error:",
            error
        );

        setStatusColor(
            "monitoring-status",
            "Offline"
        );

        setStatusColor(
            "prometheus",
            "Offline"
        );

        setStatusColor(
            "grafana",
            "Offline"
        );

    }

}


/* ==========================================================
   INITIAL GRAPH
========================================================== */

drawGraph(
    "cpuChart",
    [],
    "cpu"
);

drawGraph(
    "memoryChart",
    [],
    "memory"
);


/* ==========================================================
   FIRST LOAD
========================================================== */

loadMonitoringData();


/* ==========================================================
   LIVE UPDATE
========================================================== */

setInterval(
    loadMonitoringData,
    10000
);


/* ==========================================================
   RESPONSIVE GRAPH
========================================================== */

window.addEventListener(
    "resize",
    function() {

        drawGraph(
            "cpuChart",
            cpuData,
            "cpu"
        );

        drawGraph(
            "memoryChart",
            memoryData,
            "memory"
        );

    }
);

</script>

</body>

</html>
""")


# ============================================================
# APPLICATION START
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )