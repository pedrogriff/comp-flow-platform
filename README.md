# CompFlow Platform: Enterprise Distributed Compensation Microservice

[![CI/CD](https://github.com/pedrogriff/comp-flow-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/pedrogriff/comp-flow-platform/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type Checked: MyPy Strict](https://img.shields.io/badge/types-mypy%20strict-brightgreen.svg)](https://mypy-lang.org/)
[![Test Coverage: 100% Core](https://img.shields.io/badge/coverage-31%20tests%20passing-brightgreen.svg)]()
[![GitOps: ArgoCD](https://img.shields.io/badge/GitOps-ArgoCD-orange.svg)](https://github.com/pedrogriff/homelab-k8s-talos)
[![Kubernetes: Talos](https://img.shields.io/badge/Kubernetes-Talos%20Baremetal-blue.svg)](https://github.com/pedrogriff/homelab-k8s-talos)

**CompFlow Platform** is a distributed, production-grade **Total Rewards Calibration & Offer Orchestration Microservice**. It combines deterministic policy auditing, dual-lifecycle state machines, and executive decision synthesis to govern:
1. **Current Employee Annual Compensation Planning Cycles**: Salary Merit Increase matrices, Bonus allocations ($\text{Base} \times \text{Target\%} \times \text{IPF} \times \text{CPF}$), Equity Refresh grants, Promotion calibrations, and Departmental Budget Pool depletion.
2. **New Hire Candidate Offer Generation & Approvals**: Location-tiered salary band enforcement (`US_ZONE_1`, `US_ZONE_2`, `US_ZONE_3`), sign-on bonus caps ($50,000 threshold), new hire equity caps, and multi-tier approval routing.
3. **Cloud-Native GitOps & Observability**: PostgreSQL 16 schema with Alembic async migrations, Redis 7 caching & atomic counters, Ingress-NGINX with cert-manager TLS, Prometheus metrics `/metrics`, and ArgoCD GitOps deployment on a bare-metal Talos Kubernetes homelab.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph Clients["Clients & Showcase Ecosystem"]
        Web["playgriff.me / comp-showcase-ui"]
        CLI["comp-flow CLI & Seeder"]
        CI["CI/CD & API Integrations"]
    end

    subgraph Ingress["Talos Kubernetes Ingress & Security"]
        NGINX["Ingress-NGINX (TLS via cert-manager)"]
        Auth["JWT Auth / RBAC Middleware"]
    end

    subgraph Service["CompFlow Microservice (FastAPI Async)"]
        Router["FastAPI Domain Routers (/api/v1)"]
        
        subgraph DomainEngine["Core Business & Orchestration Layer"]
            SM_Cycle["Employee Review State Machine"]
            SM_Offer["Candidate Offer State Machine"]
            AuditEngine["Deterministic Calibration & Audit Agents"]
            FormulaEngine["Merit & Bonus Calculation Formulas"]
        end
    end

    subgraph Data["Persistence & Cache Layer"]
        PG[("PostgreSQL 16 DB\nSQLAlchemy + Alembic")]
        Redis[("Redis 7 Cache &\nAtomic Counters")]
    end

    subgraph GitOps["GitOps & Observability Infrastructure"]
        Argo["ArgoCD GitOps Operator"]
        Prom["Prometheus Scrape /metrics"]
        GHCR["GitHub Container Registry (GHCR)"]
    end

    Clients -->|HTTPS / REST API| NGINX
    NGINX --> Auth
    Auth --> Router
    Router --> DomainEngine
    DomainEngine --> PG
    DomainEngine --> Redis
    GHCR -->|Container Image Sync| Argo
    Argo -->|Declarative Sync| Service
    Service --> Prom
```

---

## 💡 Key Engineering Features

1. **Dual-Lifecycle Rigid State Machines**:
   - **Employee Reviews**: `DRAFT` $\to$ `SUBMITTED` $\to$ `AGENT_AUDITING` $\to$ `AUTO_APPROVED` / `VP_EXCEPTION_REQUIRED` $\to$ `VP_APPROVED` / `FINALIZED`.
   - **Candidate Offers**: `OFFER_DRAFT` $\to$ `AUDIT_PENDING` $\to$ `OFFER_APPROVED` / `VP_EXCEPTION_REQUIRED` $\to$ `OFFER_EXTENDED` $\to$ `OFFER_ACCEPTED` / `OFFER_DECLINED` / `OFFER_RESCINDED`.
2. **100% Deterministic Mathematical Precision**:
   - Fixed-point `Decimal` arithmetic for compa-ratios, bonus formulas, equity grant multiples, and budget depletion rates with zero hallucination.
3. **High-Performance Redis Caching & Atomic Counters**:
   - Sub-millisecond salary band resolution with automatic fallback.
   - Real-time atomic budget burn rate tracking across departments.
4. **JWT Authentication & Fine-Grained RBAC**:
   - Enforces distinct permissions for `HR_ADMIN`, `COMPENSATION_PARTNER`, `PEOPLE_MANAGER`, `EXECUTIVE_APPROVER`, and `RECRUITER`.
5. **Ultra High-Throughput Performance**:
   - Audits **20,000+ complex manager proposals per second** with full rationale synthesis.

---

## 🚀 Quickstart & Local Development

### 1. Run via Docker Compose (PostgreSQL 16 + Redis 7 + API)

```bash
docker compose up --build -d
```

### 2. Run Locally with Virtualenv

```bash
# Install dependencies
pip install -e ".[dev]"

# Initialize PostgreSQL Schema & Alembic Migrations
alembic upgrade head

# Seed Enterprise Demo Data (60 Employees, Bands, Cycles, Offers, Users)
python -m comp_flow.cli seed

# Start FastAPI Microservice Server
python -m comp_flow.cli serve --port 8000 --reload
```

Interactive API documentation will be available at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Prometheus Metrics**: [http://localhost:8000/metrics](http://localhost:8000/metrics)
- **Health Probes**: [http://localhost:8000/healthz](http://localhost:8000/healthz) | [http://localhost:8000/readyz](http://localhost:8000/readyz)

---

## 📡 REST API Surface (`/api/v1`)

| Module | Method & Path | Description | Access Control |
|---|---|---|---|
| **Auth** | `POST /api/v1/auth/login` | Authenticate user and issue JWT | Public |
| **Auth** | `GET /api/v1/auth/me` | Retrieve authenticated user profile | Authenticated |
| **Bands** | `GET /api/v1/bands` | List benchmark salary bands by level/geo | Authenticated |
| **Bands** | `POST /api/v1/bands` | Upsert benchmark salary band | `HR_ADMIN` |
| **Cycles** | `POST /api/v1/cycles` | Create planning cycle & department budgets | `HR_ADMIN` |
| **Cycles** | `GET /api/v1/cycles` | List all active & historic cycles | Authenticated |
| **Cycles** | `GET /api/v1/cycles/{id}/budgets/{dept_id}` | Real-time budget allocation & burn rate | `PEOPLE_MANAGER`, `HR_ADMIN` |
| **Planning** | `POST /api/v1/cycles/{id}/proposals` | Submit manager review proposal | `PEOPLE_MANAGER`, `HR_ADMIN` |
| **Planning** | `POST /api/v1/proposals/{id}/audit` | Run autonomous deterministic agent audit | Authenticated |
| **Planning** | `POST /api/v1/cycles/{id}/batch-audit` | Batch audit department proposals | `PEOPLE_MANAGER`, `HR_ADMIN` |
| **Planning** | `POST /api/v1/proposals/{id}/approve` | Executive approval for VP exception | `EXECUTIVE_APPROVER` |
| **Planning** | `POST /api/v1/cycles/{id}/finalize` | Lock cycle and commit salary/equity | `HR_ADMIN` |
| **Offers** | `POST /api/v1/offers` | Create candidate new hire offer proposal | `RECRUITER`, `HR_ADMIN` |
| **Offers** | `GET /api/v1/offers` | List offers with status/department filters | Authenticated |
| **Offers** | `GET /api/v1/offers/{id}` | Get offer breakdown, compa-ratio, total comp | Authenticated |
| **Offers** | `POST /api/v1/offers/{id}/audit` | Run policy audit on offer package | Authenticated |
| **Offers** | `POST /api/v1/offers/{id}/approve` | Approve offer / sign VP exception | `EXECUTIVE_APPROVER` |
| **Offers** | `POST /api/v1/offers/{id}/extend` | Mark offer letter extended to candidate | `RECRUITER` |
| **Offers** | `POST /api/v1/offers/{id}/decision` | Record candidate response (ACCEPT/DECLINE) | `RECRUITER` |
| **Analytics**| `GET /api/v1/analytics/cycles/{id}` | Compa-ratio distribution & merit by rating | Authenticated |

---

## ⚡ Throughput Benchmark

CompFlow includes a synthetic benchmark testing the ReAct audit loop across 5,000 workforce proposals:

```bash
python -m benchmarks.bench_agent_throughput
```

```text
===========================================================================
CompFlow: Agentic Audit Throughput Benchmark (N = 5,000 Proposals)
===========================================================================
Total Proposals Audited: 5,000
Total Execution Time:    0.2487 seconds
Audit Throughput:        20,107.3 proposals / second
---------------------------------------------------------------------------
Agent Decision Breakdown:
  • VP_EXCEPTION_REQUIRED    : 3,873 (77.5%)
  • REJECTED                 : 1,006 (20.1%)
  • AUTO_APPROVED            : 121 (2.4%)
===========================================================================
```

---

## 🧪 Testing & Verification

```bash
# Run Pytest suite with strict coverage
pytest -v --cov=src/comp_flow --cov-report=term-missing tests/

# Strict Type Checking
mypy src/

# Linter and Formatting Check
ruff check .
ruff format --check .
```

---

## 🚢 GitOps Kubernetes Deployment (`homelab-k8s-talos`)

CompFlow is packaged as a declarative ArgoCD application in the bare-metal Talos Kubernetes homelab repository [`homelab-k8s-talos`](https://github.com/pedrogriff/homelab-k8s-talos):
- **Manifest Location**: `apps/comp-flow-platform/`
- **Database**: PostgreSQL 16 StatefulSet backed by `local-path` PersistentVolumeClaims
- **Cache**: Redis 7 Deployment with memory limits and LRU eviction
- **Microservice**: Multi-replica FastAPI deployment with pod anti-affinity and health checks
- **Ingress & TLS**: NGINX Ingress Controller with Let's Encrypt / local CA certificates managed by `cert-manager` for `https://compflow.10.0.0.170.nip.io` and `https://compflow.homelab.local`
- **GitOps Reconciliation**: Automatically synced and pruned by ArgoCD `homelab-apps` Application

---

## 📄 License
MIT License. Engineered by [Pedro](https://github.com/pedrogriff).
