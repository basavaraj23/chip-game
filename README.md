# Chip Game

Chip Game is a lightweight demo stack that showcases a tiny chip-collecting game backed by Flask, a one-page frontend, and a Kubernetes deployment bundle that provisions Redis, PostgreSQL, and Kafka via Strimzi. The repository is intentionally small so you can experiment with local development, container builds, or Argo CD + Helm based GitOps workflows.

## Repository layout

| Path | Description |
| --- | --- |
| `chip-backend/` | Flask 3.x API that records chip collections, publishes them to Kafka, and keeps a leaderboard derived from the topic stream. Includes a Dockerfile for container builds. |
| `chip-frontend/` | Static HTML/JS page that calls the backend’s `/api/collect` endpoint. Ships with an Nginx-based Dockerfile. |
| `build/helm/chip-applications/` | Umbrella Helm chart (type `application`) that defines Argo CD Applications for every dependency and workload. Installing this chart in the `argocd` namespace bootstraps the full stack. |
| `build/helm/kafka-cluster/` | Strimzi `Kafka` + `KafkaTopic` manifests parameterized for the project (cluster name, version, retention, etc.). |
| `build/helm/postgres-cluster/` | CloudNativePG cluster definition consumed by the umbrella chart. |
| `build/helm/chip-backend/`, `build/helm/chip-frontend/` | Simple Helm charts that deploy the two workloads inside Kubernetes. |

## Backend service

The backend exposes:

- `POST /api/collect` – accepts `{player, chips}` JSON, publishes the move to Kafka, and echoes a confirmation.
- `GET /api/leaderboard` – returns the top players aggregated from Kafka (falls back to sample data if Kafka is unavailable).
- `GET /healthz` and `GET /livez` – HTTP probes used by Kubernetes.

Key environment variables (set via Helm values or your shell):

| Variable | Purpose | Default |
| --- | --- | --- |
| `KAFKA_BROKERS` | Comma-separated bootstrap brokers | empty (Kafka disabled) |
| `KAFKA_TOPIC` | Topic to publish/consume chip moves | `chip-moves` |
| `KAFKA_GROUP_ID` | Consumer group for leaderboard aggregation | `chip-backend` |
| `KAFKA_AUTO_OFFSET_RESET` | Strimzi-compatible offset reset policy | `latest` |

When `KAFKA_BROKERS` is not provided, the service still responds but aggregates scores only in-memory.

### Run locally

```bash
cd chip-backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export KAFKA_BROKERS=chip-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092
export KAFKA_TOPIC=chip-moves
python app.py
```

The backend listens on `http://localhost:8080`.

## Frontend

`chip-frontend/index.html` is a minimal static page. For local testing, open the file in a browser or serve it via any static file server:

```bash
cd chip-frontend
python -m http.server 8000
```

Set `API_BASE_URL` in the page (or via `window.API_BASE_URL`) if the backend is not at `http://localhost:8080`.

## Container builds

Both services include Dockerfiles:

```bash
# Backend
cd chip-backend
docker build -t chip-backend:local .

# Frontend
cd ../chip-frontend
docker build -t chip-frontend:local .
```

Push the images to the registry of your choice before syncing the Helm releases in Kubernetes.

## Kubernetes / Argo CD deployment

1. Prepare a cluster with Argo CD installed in the `argocd` namespace.
2. Allow Argo CD to pull this repository:
   ```bash
   argocd repo add git@github.com:basavaraj23/chip-game.git \
     --name chip-game --ssh-private-key-path ~/.ssh/github_chip_game
   ```
   Alternatively create a secret:
   ```bash
   kubectl create secret generic repo-github-chip-game \
     --from-literal=url=git@github.com:basavaraj23/chip-game.git \
     --from-literal=name=chip-game \
     --from-file=sshPrivateKey=~/.ssh/github_chip_game \
     -n argocd
   kubectl label secret repo-github-chip-game argocd.argoproj.io/secret-type=repository -n argocd
   ```
3. Install the umbrella chart:
   ```bash
   helm upgrade --install chip-applications ./build/helm/chip-applications -n argocd
   ```

What gets created (via Argo Application-of-Applications):

- Strimzi Kafka Operator (`strimzi-kafka-operator` 0.50.1) scoped to the `kafka` namespace.
- A single-node Kafka 4.1.0 cluster (`chip-kafka`) plus the `chip-moves` topic.
- CloudNativePG operator and a demo PostgreSQL cluster in `datastores`.
- Bitnami Redis (replication mode) in `datastores`.
- The chip backend and frontend workloads in the `chip` namespace.

Each template sets `CreateNamespace` so namespaces are created on sync. Customize values through `build/helm/chip-applications/values.yaml` or Helm `--set`/`-f` overrides (e.g., change Kafka retention, image tags, Redis credentials, etc.).

## Running everything on Kind

Want a local lab? This sequence provisions a Kind cluster and deploys the whole stack:

```bash
# 1) Reset/create the Kind cluster
kind delete cluster --name chip || true
kind create cluster --name chip

# 2) Create namespaces up front
kubectl create namespace argocd || true
kubectl create namespace datastores || true
kubectl create namespace chip || true
kubectl create namespace kafka || true

# 3) Install Argo CD and wait for it
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.1.9/manifests/install.yaml
kubectl -n argocd rollout status deploy/argocd-server

# 4) Configure repo access (CLI or secret as described above)

# 5) Install the umbrella chart
helm upgrade --install chip-applications ./build/helm/chip-applications -n argocd

# 6) Watch Argo applications converge
kubectl -n argocd get applications.argoproj.io
```

Once everything is `Synced/Healthy`, port-forward `chip-backend`/`chip-frontend` and play.

## Verifying the deployment

```bash
kubectl get applications.argoproj.io -n argocd
kubectl get pods -A | grep -E "chip|strimzi|redis|cnpg"
```

To test the app end-to-end:

1. Port-forward the backend: `kubectl -n chip port-forward svc/chip-backend 8080:8080`.
2. Call the API: `curl -XPOST localhost:8080/api/collect -H 'Content-Type: application/json' -d '{"player":"You","chips":5}'`.
3. Fetch the leaderboard: `curl localhost:8080/api/leaderboard`.

## Playing the game

There are two simple ways to try Chip Game once the backend is reachable:

### Via the web UI
1. Port-forward the frontend service: `kubectl -n chip port-forward svc/chip-frontend 8081:80`.
2. Visit `http://localhost:8081` and click **Collect Chips**. Each click issues a POST to the backend and shows the confirmation text.
3. Keep a terminal open with `curl localhost:8080/api/leaderboard` (or watch the backend pod logs) to see scores update.

For local-only testing, open `chip-frontend/index.html` directly in a browser and set `window.API_BASE_URL = 'http://localhost:8080'` in the devtools console if the backend lives elsewhere.

### Via API calls
Use any REST client to hit `POST /api/collect` and `GET /api/leaderboard`. Example:

```bash
curl -X POST http://localhost:8080/api/collect \
  -H 'Content-Type: application/json' \
  -d '{"player":"Tester","chips":12}'
curl http://localhost:8080/api/leaderboard
```

If Kafka is configured (default Helm deploy), the backend streams messages through the `chip-moves` topic and aggregates them asynchronously; without Kafka, scores persist only for the life of the backend process.

## Argo CD UI access

1. Ensure Argo CD is running (`kubectl -n argocd get pods`).
2. Port-forward the API server: `kubectl -n argocd port-forward svc/argocd-server 8080:443`.
3. Open `https://localhost:8080` in a browser (ignore the self-signed cert warning).
4. Login with `admin` and the password from `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d` unless you have rotated credentials.
5. From the UI you can watch `chip-backend`, `chip-frontend`, `strimzi-operator`, `kafka-cluster`, etc., trigger manual syncs, and inspect application logs.

CLI equivalent:

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443 &
argocd login localhost:8080 --username admin --password <password> --insecure
argocd app sync kafka-cluster
```

## Contributing

1. Fork and clone the repo.
2. Create a feature branch off `main`.
3. Keep changes confined to relevant components (backend, frontend, or Helm charts) and add small code comments only where the logic is non-obvious.
4. Open a pull request once tests (or manual checks) pass.

Enjoy building and experimenting with Chip Game!
