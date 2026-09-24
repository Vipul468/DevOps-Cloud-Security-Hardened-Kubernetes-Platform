from flask import Flask, jsonify, render_template_string
import json
import os
import ssl
import urllib.request
import urllib.error
import urllib.parse

app = Flask(__name__)

# =========================================================
# CONFIGURATION
# =========================================================

NAMESPACE = "hardened-app"

KUBERNETES_API = "https://kubernetes.default.svc"

SERVICE_ACCOUNT_TOKEN = (
    "/var/run/secrets/kubernetes.io/serviceaccount/token"
)

SERVICE_ACCOUNT_CA = (
    "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
)

PROMETHEUS_URL = (
    "http://monitoring-kube-prometheus-prometheus."
    "monitoring.svc.cluster.local:9090"
)

GRAFANA_URL = (
    "http://monitoring-grafana."
    "monitoring.svc.cluster.local"
)


# =========================================================
# KUBERNETES AUTHENTICATION
# =========================================================

def get_kubernetes_token():

    try:

        with open(
            SERVICE_ACCOUNT_TOKEN,
            "r"
        ) as file:

            token = file.read().strip()

            return token if token else None

    except Exception as e:

        print("ServiceAccount token error:", e)

        return None


def get_kubernetes_ssl_context():

    try:

        if os.path.exists(SERVICE_ACCOUNT_CA):

            return ssl.create_default_context(
                cafile=SERVICE_ACCOUNT_CA
            )

    except Exception as e:

        print("Kubernetes CA error:", e)

    return None


# =========================================================
# KUBERNETES API REQUEST
# =========================================================

def kubernetes_request(path):

    token = get_kubernetes_token()

    if not token:

        print("Kubernetes token not available")

        return None

    url = KUBERNETES_API + path

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    try:

        request = urllib.request.Request(
            url,
            headers=headers
        )

        ssl_context = get_kubernetes_ssl_context()

        if not ssl_context:

            print(
                "Kubernetes CA certificate not available"
            )

            return None

        with urllib.request.urlopen(
            request,
            timeout=5,
            context=ssl_context
        ) as response:

            return json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as e:

        print(
            "Kubernetes API HTTP error:",
            e.code,
            e.reason
        )

        return None

    except Exception as e:

        print(
            "Kubernetes API error:",
            e
        )

        return None


# =========================================================
# POD STATUS
# =========================================================

def get_pod_status():

    data = kubernetes_request(
        f"/api/v1/namespaces/{NAMESPACE}/pods"
    )

    if not data:

        return {
            "running": 0,
            "total": 0
        }

    items = data.get(
        "items",
        []
    )

    running = 0

    for pod in items:

        phase = (
            pod
            .get("status", {})
            .get("phase")
        )

        if phase == "Running":

            running += 1

    return {
        "running": running,
        "total": len(items)
    }


# =========================================================
# NODE STATUS
# =========================================================

def get_node_status():

    data = kubernetes_request(
        "/api/v1/nodes"
    )

    if not data:

        return {
            "ready": 0,
            "total": 0
        }

    items = data.get(
        "items",
        []
    )

    ready = 0

    for node in items:

        conditions = (
            node
            .get("status", {})
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
        "total": len(items)
    }


# =========================================================
# GENERIC HTTP GET
# =========================================================

def http_get(
    url,
    headers=None,
    timeout=5
):

    try:

        request = urllib.request.Request(
            url,
            headers=headers or {}
        )

        with urllib.request.urlopen(
            request,
            timeout=timeout
        ) as response:

            return {
                "status": response.status,
                "data": response.read().decode(
                    "utf-8"
                )
            }

    except Exception as e:

        return {
            "status": 0,
            "error": str(e)
        }


# =========================================================
# PROMETHEUS
# =========================================================

def prometheus_query(query):

    try:

        encoded_query = urllib.parse.quote(
            query
        )

        url = (
            PROMETHEUS_URL
            + "/api/v1/query?query="
            + encoded_query
        )

        result = http_get(url)

        if result.get("status") != 200:

            return None

        data = json.loads(
            result.get(
                "data",
                "{}"
            )
        )

        if data.get("status") != "success":

            return None

        results = (
            data
            .get("data", {})
            .get("result", [])
        )

        if not results:

            return None

        value = results[0].get(
            "value",
            [None, "0"]
        )[1]

        return float(value)

    except Exception as e:

        print(
            "Prometheus query error:",
            e
        )

        return None


def check_prometheus():

    result = http_get(
        PROMETHEUS_URL
        + "/-/healthy"
    )

    return result.get("status") == 200


# =========================================================
# GRAFANA
# =========================================================

def check_grafana():

    result = http_get(
        GRAFANA_URL
        + "/api/health"
    )

    return result.get("status") == 200


# =========================================================
# MONITORING DATA
# =========================================================

def get_monitoring_data():

    pods = get_pod_status()

    nodes = get_node_status()

    prometheus = check_prometheus()

    grafana = check_grafana()

    cpu = 0

    memory = 0

    if prometheus:

        cpu_query = """
        100 * (
            1 -
            avg(
                rate(
                    node_cpu_seconds_total{
                        mode="idle"
                    }[5m]
                )
            )
        )
        """

        memory_query = """
        100 * (
            1 -
            (
                sum(node_memory_MemAvailable_bytes)
                /
                sum(node_memory_MemTotal_bytes)
            )
        )
        """

        cpu_value = prometheus_query(
            cpu_query
        )

        memory_value = prometheus_query(
            memory_query
        )

        if cpu_value is not None:

            cpu = round(
                max(
                    0,
                    min(
                        100,
                        cpu_value
                    )
                ),
                2
            )

        if memory_value is not None:

            memory = round(
                max(
                    0,
                    min(
                        100,
                        memory_value
                    )
                ),
                2
            )

    return {
        "cpu": cpu,

        "memory": memory,

        "pods": pods,

        "nodes": nodes,

        "monitoring": {
            "active": (
                prometheus
                or grafana
            ),

            "prometheus": prometheus,

            "grafana": grafana
        }
    }


# =========================================================
# HEALTH API
# =========================================================

@app.route("/health")
def health():

    return jsonify({

        "status": "healthy",

        "service":
            "security-hardened-k8s-platform"
    })


# =========================================================
# MONITORING API
# =========================================================

@app.route("/monitoring-data")
def monitoring_data():

    return jsonify(
        get_monitoring_data()
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
def dashboard():

    return render_template_string(
r'''
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>
Security Hardened Kubernetes Platform
</title>

<style>

* {
    box-sizing: border-box;
}

body {

    margin: 0;

    background: #0f172a;

    color: #e2e8f0;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

    font-size: 13px;
}

.container {

    max-width: 1100px;

    margin: auto;

    padding: 18px;
}

.header {

    background: #111827;

    border: 1px solid #334155;

    border-radius: 10px;

    padding: 17px;

    margin-bottom: 16px;
}

.header h1 {

    margin: 0 0 6px 0;

    font-size: 21px;
}

.header p {

    margin: 0;

    color: #94a3b8;

    font-size: 12px;
}

.status {

    display: inline-block;

    margin-top: 11px;

    padding: 5px 11px;

    border-radius: 15px;

    background: #064e3b;

    color: #6ee7b7;

    font-size: 12px;

    font-weight: bold;
}

.grid {

    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(190px, 1fr)
        );

    gap: 12px;

    margin-bottom: 14px;
}

.card {

    background: #111827;

    border: 1px solid #334155;

    border-radius: 9px;

    padding: 14px;
}

.card-title {

    color: #94a3b8;

    font-size: 11px;

    margin-bottom: 6px;

    text-transform: uppercase;
}

.value {

    font-size: 19px;

    font-weight: bold;
}

.healthy {

    color: #6ee7b7;
}

.chart-grid {

    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(320px, 1fr)
        );

    gap: 12px;

    margin-top: 3px;
}

.chart-card {

    background: #111827;

    border: 1px solid #334155;

    border-radius: 9px;

    padding: 14px;
}

.chart-title {

    color: #94a3b8;

    font-size: 11px;

    text-transform: uppercase;

    margin-bottom: 8px;
}

.chart {

    height: 220px;

    background: #020617;

    border-radius: 7px;

    padding: 8px;
}

canvas {

    width: 100% !important;

    height: 100% !important;
}

.footer {

    text-align: center;

    color: #64748b;

    margin-top: 16px;

    font-size: 10px;
}

</style>

</head>


<body>


<div class="container">


<div class="header">

<h1>
SECURITY HARDENED K8S PLATFORM
</h1>

<p>
DevOps & Cloud Engineer Security Hardened Kubernetes Platform
</p>

<div class="status">
● Healthy
</div>

</div>


<!-- STATUS CARDS -->

<div class="grid">


<div class="card">

<div class="card-title">
API
</div>

<div
    class="value healthy"
    id="api">
Healthy
</div>

</div>


<div class="card">

<div class="card-title">
Security
</div>

<div class="value healthy">
Protected
</div>

</div>


<div class="card">

<div class="card-title">
Monitoring
</div>

<div
    class="value"
    id="monitoring">
Checking...
</div>

</div>


<div class="card">

<div class="card-title">
Namespace
</div>

<div class="value">
hardened-app
</div>

</div>


</div>


<!-- KUBERNETES -->

<div class="grid">


<div class="card">

<div class="card-title">
Pods
</div>

<div
    class="value"
    id="pods">
0 / 0
</div>

</div>


<div class="card">

<div class="card-title">
Nodes
</div>

<div
    class="value"
    id="nodes">
0 / 0
</div>

</div>


<div class="card">

<div class="card-title">
Prometheus
</div>

<div
    class="value"
    id="prometheus">
Checking...
</div>

</div>


<div class="card">

<div class="card-title">
Grafana
</div>

<div
    class="value"
    id="grafana">
Checking...
</div>

</div>


</div>


<!-- RESOURCE USAGE -->

<div class="grid">


<div class="card">

<div class="card-title">
CPU Usage
</div>

<div
    class="value"
    id="cpu">
0%
</div>

</div>


<div class="card">

<div class="card-title">
Memory Usage
</div>

<div
    class="value"
    id="memory">
0%
</div>

</div>


<div class="card">

<div class="card-title">
Platform
</div>

<div class="value">
Kubernetes
</div>

</div>


<div class="card">

<div class="card-title">
Security
</div>

<div class="value healthy">
RBAC + NetworkPolicy
</div>

</div>


</div>


<!-- SEPARATE CPU AND MEMORY CHARTS -->

<div class="chart-grid">


<!-- CPU CHART -->

<div class="chart-card">

<div class="chart-title">
CPU Utilization
</div>

<div class="chart">

<canvas id="cpuChart"></canvas>

</div>

</div>


<!-- MEMORY CHART -->

<div class="chart-card">

<div class="chart-title">
Memory Utilization
</div>

<div class="chart">

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


/* =========================================================
   MONITORING HISTORY
   ========================================================= */

const cpuData = [];

const memoryData = [];

const maxPoints = 20;


/* =========================================================
   GENERIC GRAPH GRID
   ========================================================= */

function drawGraphGrid(
    ctx,
    w,
    h
) {

    ctx.strokeStyle =
        "#334155";

    ctx.lineWidth = 1;


    for (
        let i = 0;
        i <= 4;
        i++
    ) {

        const y =
            15 +
            (
                (h - 30)
                *
                i
                /
                4
            );


        ctx.beginPath();

        ctx.moveTo(
            30,
            y
        );

        ctx.lineTo(
            w - 10,
            y
        );

        ctx.stroke();

    }


    /* LABELS */

    ctx.fillStyle =
        "#64748b";

    ctx.font =
        "10px Arial";


    ctx.fillText(
        "100%",
        2,
        18
    );

    ctx.fillText(
        "75%",
        7,
        h / 4 + 2
    );

    ctx.fillText(
        "50%",
        7,
        h / 2 + 2
    );

    ctx.fillText(
        "25%",
        7,
        (h * 3 / 4) + 2
    );

    ctx.fillText(
        "0%",
        12,
        h - 8
    );

}


/* =========================================================
   DRAW SINGLE GRAPH LINE
   ========================================================= */

function drawDataLine(
    ctx,
    data,
    w,
    h,
    lineColor
) {

    if (
        data.length < 2
    ) {

        return;

    }


    ctx.beginPath();


    data.forEach(
        (
            value,
            index
        ) => {

            const x =
                30 +
                (
                    (w - 40)
                    *
                    index
                    /
                    (maxPoints - 1)
                );


            const safeValue =
                Math.max(
                    0,
                    Math.min(
                        100,
                        value
                    )
                );


            const y =
                h -
                15 -
                (
                    (h - 30)
                    *
                    safeValue
                    /
                    100
                );


            if (
                index === 0
            ) {

                ctx.moveTo(
                    x,
                    y
                );

            } else {

                ctx.lineTo(
                    x,
                    y
                );

            }

        }
    );


    ctx.lineWidth = 2;

    ctx.strokeStyle =
        lineColor;

    ctx.stroke();

}


/* =========================================================
   CPU GRAPH
   ========================================================= */

function drawCPUChart() {

    const canvas =
        document.getElementById(
            "cpuChart"
        );

    if (!canvas) {

        return;

    }


    const ctx =
        canvas.getContext("2d");

    const w =
        canvas.clientWidth;

    const h =
        canvas.clientHeight;


    if (
        w <= 0 ||
        h <= 0
    ) {

        return;

    }


    canvas.width =
        w * 2;

    canvas.height =
        h * 2;


    ctx.setTransform(
        2,
        0,
        0,
        2,
        0,
        0
    );


    ctx.clearRect(
        0,
        0,
        w,
        h
    );


    drawGraphGrid(
        ctx,
        w,
        h
    );


    drawDataLine(
        ctx,
        cpuData,
        w,
        h,
        "#38bdf8"
    );

}


/* =========================================================
   MEMORY GRAPH
   ========================================================= */

function drawMemoryChart() {

    const canvas =
        document.getElementById(
            "memoryChart"
        );

    if (!canvas) {

        return;

    }


    const ctx =
        canvas.getContext("2d");

    const w =
        canvas.clientWidth;

    const h =
        canvas.clientHeight;


    if (
        w <= 0 ||
        h <= 0
    ) {

        return;

    }


    canvas.width =
        w * 2;

    canvas.height =
        h * 2;


    ctx.setTransform(
        2,
        0,
        0,
        2,
        0,
        0
    );


    ctx.clearRect(
        0,
        0,
        w,
        h
    );


    drawGraphGrid(
        ctx,
        w,
        h
    );


    drawDataLine(
        ctx,
        memoryData,
        w,
        h,
        "#a78bfa"
    );

}


/* =========================================================
   REFRESH DATA
   ========================================================= */

async function refreshData() {


    /* =========================
       API HEALTH
       ========================= */

    try {

        const healthResponse =
            await fetch(
                "/health",
                {
                    cache: "no-store"
                }
            );


        if (
            healthResponse.ok
        ) {

            const healthData =
                await healthResponse.json();


            document.getElementById(
                "api"
            ).textContent =
                healthData.status === "healthy"
                ? "Healthy"
                : "Error";

        } else {

            document.getElementById(
                "api"
            ).textContent =
                "Error";

        }

    } catch (error) {

        console.error(
            "API health error:",
            error
        );


        document.getElementById(
            "api"
        ).textContent =
            "Error";

    }


    /* =========================
       MONITORING DATA
       ========================= */

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
                "Monitoring API returned HTTP "
                + response.status
            );

        }


        const data =
            await response.json();


        /* =========================
           PODS
           ========================= */

        document.getElementById(
            "pods"
        ).textContent =
            data.pods.running
            + " / "
            + data.pods.total;


        /* =========================
           NODES
           ========================= */

        document.getElementById(
            "nodes"
        ).textContent =
            data.nodes.ready
            + " / "
            + data.nodes.total;


        /* =========================
           CPU
           ========================= */

        document.getElementById(
            "cpu"
        ).textContent =
            data.cpu
            + "%";


        /* =========================
           MEMORY
           ========================= */

        document.getElementById(
            "memory"
        ).textContent =
            data.memory
            + "%";


        /* =========================
           PROMETHEUS
           ========================= */

        document.getElementById(
            "prometheus"
        ).textContent =
            data.monitoring.prometheus
            ? "Healthy"
            : "Offline";


        /* =========================
           GRAFANA
           ========================= */

        document.getElementById(
            "grafana"
        ).textContent =
            data.monitoring.grafana
            ? "Healthy"
            : "Offline";


        /* =========================
           MONITORING
           ========================= */

        document.getElementById(
            "monitoring"
        ).textContent =
            data.monitoring.active
            ? "Active"
            : "Offline";


        /* =========================
           CPU HISTORY
           ========================= */

        cpuData.push(
            Number(data.cpu) || 0
        );


        if (
            cpuData.length
            > maxPoints
        ) {

            cpuData.shift();

        }


        /* =========================
           MEMORY HISTORY
           ========================= */

        memoryData.push(
            Number(data.memory) || 0
        );


        if (
            memoryData.length
            > maxPoints
        ) {

            memoryData.shift();

        }


        /* =========================
           DRAW SEPARATE GRAPHS
           ========================= */

        drawCPUChart();

        drawMemoryChart();


    } catch (error) {

        console.error(
            "Monitoring error:",
            error
        );


        /*
         * IMPORTANT:
         * Monitoring failure must NOT
         * change the API card to Error.
         */

        document.getElementById(
            "monitoring"
        ).textContent =
            "Offline";


        document.getElementById(
            "prometheus"
        ).textContent =
            "Offline";


        document.getElementById(
            "grafana"
        ).textContent =
            "Offline";

    }

}


/* =========================================================
   INITIAL LOAD
   ========================================================= */

refreshData();


/* =========================================================
   AUTO REFRESH
   ========================================================= */

setInterval(
    refreshData,
    10000
);


/* =========================================================
   RESPONSIVE GRAPHS
   ========================================================= */

window.addEventListener(
    "resize",
    function () {

        drawCPUChart();

        drawMemoryChart();

    }
);


</script>


</body>

</html>
'''
    )


# =========================================================
# APPLICATION READY API
# =========================================================

@app.route("/ready")
def ready():

    return jsonify({

        "status": "ready",

        "service":
            "security-hardened-k8s-platform"

    })


# =========================================================
# APPLICATION START
# =========================================================

if __name__ == "__main__":

    print(
        "Starting Security Hardened Kubernetes Platform..."
    )

    print(
        "Namespace:",
        NAMESPACE
    )

    print(
        "Kubernetes API:",
        KUBERNETES_API
    )

    print(
        "ServiceAccount token:",
        bool(
            get_kubernetes_token()
        )
    )

    print(
        "ServiceAccount CA:",
        bool(
            get_kubernetes_ssl_context()
        )
    )

    app.run(
        host="0.0.0.0",
        port=5000
    )