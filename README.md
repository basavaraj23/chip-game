
---

# WCC Kind Cluster — Argo CD Deployment Guide

This document provides **step-by-step instructions** to provision and manage the following operators on a **Kind (Kubernetes-in-Docker)** cluster using **Argo CD** and **Helm**:

- **CloudNativePG (PostgreSQL Operator)**
- **Kafka Operator (Strimzi)**
- **Redis Operator (Bitnami)**
- Managed via **Argo CD** using a Helm chart (`chip-applications`)

---

## Prerequisites

Ensure the following are installed locally:

- [Kind](https://kind.sigs.k8s.io/)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [Helm](https://helm.sh/docs/intro/install/)
- [Argo CD CLI](https://argo-cd.readthedocs.io/en/stable/cli_installation/)

---

## Step 1: Create Kind Cluster

If an old cluster exists, delete it first:

```bash
kind delete cluster --name wcc
````

Create a new cluster:

```bash
kind create cluster --name wcc
```

---

## Step 2: Create Namespaces

Create required namespaces:

```bash
kubectl create ns datastores || true
kubectl create ns apps || true
kubectl create namespace argocd
```

---

## Step 3: Install Argo CD

Apply the official Argo CD manifest:

```bash
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.1.9/manifests/install.yaml
```

Wait for the Argo CD server to be ready:

```bash
kubectl -n argocd rollout status deploy/argocd-server
```

---

## Step 4: Deploy Applications via Helm

Deploy the Helm umbrella chart (`chip-applications`) that includes:

* CloudNativePG Operator
* Strimzi Kafka Operator
* Bitnami Redis

The bundled Kafka chart (`build/helm/kafka-cluster`) targets Strimzi 0.48 with the default ZooKeeper ensemble, which matches the operator deployed in this guide.

```bash
helm upgrade --install chip-applications ./build/helm/chip-applications -n argocd
```

> Make sure Argo CD can reach the Bitbucket repo first, for example:
>```bash
>argocd repo add ssh://git@bitbucket.org/popreachinc/wcc.git \
>  --name wcc --ssh-private-key-path ~/.ssh/bitbucket_key
>```
>Once added, Argo CD will track branch `CHIP-314-wcc-redis-kafka-and-postgresql` (set in the chart values).

If you manage repository credentials via `kubectl`, create the secret instead of using the Argo CD CLI:
```bash
kubectl create secret generic repo-bitbucket-wcc \
  --from-literal=url=ssh://git@bitbucket.org/popreachinc/wcc.git \
  --from-literal=name=wcc \
  --from-file=sshPrivateKey=~/.ssh/bitbucket_key \
  -n argocd
kubectl label secret repo-bitbucket-wcc argocd.argoproj.io/secret-type=repository -n argocd
```

With the secret in place, Argo CD pulls chart content from branch `CHIP-314-wcc-redis-kafka-and-postgresql`.

---

## Step 5: Retrieve Argo CD Admin Password

Get the auto-generated admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d; echo
```

Example output:

```
7vgxzuaryY-LtqhV
```

---

## Step 6: Access Argo CD UI

Port-forward the Argo CD server service:

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
```

Access the dashboard at:

[https://localhost:8080](https://localhost:8080)

Login credentials:

* **Username:** `admin`
* **Password:** (use the value retrieved above)

---

## Step 7: Verify Application Deployments

List all Argo CD applications:

```bash
kubectl -n argocd get applications.argoproj.io
```

Check specific operators:

```bash
kubectl -n argocd get applications.argoproj.io | grep -i kafka
kubectl -n argocd describe application strimzi-operator
kubectl -n argocd describe application cloudnativepg-operator
kubectl -n argocd describe application redis
kubectl -n argocd describe application kafka-cluster
```

---

## Verification

---

## Step 8: Run Service Smoke Tests (Optional)

Track the Argo CD application first:

```bash
kubectl -n argocd get applications.argoproj.io service-tests
kubectl -n argocd describe application service-tests
```

Prefer the UI? Port-forward Argo CD and open https://localhost:8080, then inspect the `service-tests` tile.

The umbrella chart now creates a `service-tests` Argo CD application that provisions short-lived workloads to exercise Redis, PostgreSQL, and Kafka.

1. Wait until the `service-tests` application appears in Argo CD and finishes syncing (it is set to auto-sync).
2. Check the verification jobs with `kubectl get jobs -A | grep smoketest`.
3. Inspect the job logs for additional detail, for example `kubectl -n datastores logs job/wcc-pg-test-smoketest` or `kubectl -n kafka logs job/wcc-kafka-smoketest`.

What gets deployed:
- A CloudNativePG `Cluster` named `wcc-pg-test` (namespace `datastores`) and a job that creates a table, inserts a row, and queries it back.
- A Redis smoke-test job that authenticates with the Bitnami release, writes a key, and reads it back.
- A Strimzi-backed topic (`wcc-test-topic`), SCRAM user, and job that produces and consumes a unique message.

Disable the tests by setting `serviceTests.enabled=false` (or by removing the application in Argo CD) once you are done.

---


After successful synchronization in Argo CD UI, verify operator pods:

```bash
kubectl get pods -A | grep -E "cnpg|strimzi|redis"
```

Expected namespaces:

* `cnpg-system` → CloudNativePG Operator
* `kafka` → Strimzi Operator
* `datastores` → Redis Operator

---

## Cleanup

To remove everything:

```bash
kind delete cluster --name wcc
```

---

## Notes

* `chip-applications` chart should contain Helm subcharts or Argo CD `Application` manifests for each operator.
* For production or CI/CD use, sync policies can be automated with:

  ```yaml
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
  ```

---

### References

* [Argo CD Docs](https://argo-cd.readthedocs.io/)
* [CloudNativePG Operator](https://cloudnative-pg.io/)
* [Strimzi Kafka Operator](https://strimzi.io/)
* [Bitnami Redis Helm Chart](https://bitnami.com/stack/redis/helm)

---

**Author:** Garden City Games — DevOps
**Cluster Name:** `wcc`
**Last Updated:** October 2025

```

---
