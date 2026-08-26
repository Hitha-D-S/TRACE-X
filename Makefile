.PHONY: help up down build logs seed stream test eval bench clean

# ── Default target ──────────────────────────────────────────
help:
	@echo ""
	@echo "  TRACE-X — Real-Time Financial Crime Graph Intelligence"
	@echo "  ======================================================="
	@echo ""
	@echo "  make up          Start all services (Docker Compose)"
	@echo "  make down        Stop all services"
	@echo "  make build       Build/rebuild Docker images"
	@echo "  make logs        Tail all service logs"
	@echo "  make seed        Generate synthetic dataset (seed=42)"
	@echo "  make stream      Start live transaction stream"
	@echo "  make test        Run the full test suite"
	@echo "  make eval        Run detection benchmark evaluation"
	@echo "  make bench       Run latency benchmark"
	@echo "  make clean       Remove volumes and containers"
	@echo ""

# ── Infrastructure ──────────────────────────────────────────
up:
	@cp -n .env.example .env 2>/dev/null || true
	docker compose up -d
	@echo "Services starting... Check health with: make logs"

down:
	docker compose down

build:
	docker compose build --no-cache

logs:
	docker compose logs -f

# ── Data ────────────────────────────────────────────────────
seed:
	cd backend && python scripts/generate_synthetic.py --seed 42 --count 500

stream:
	cd backend && python scripts/stream_producer.py --rate 2 --duration 300

# ── Testing ─────────────────────────────────────────────────
test:
	cd backend && python -m pytest tests/ -v --tb=short

eval:
	cd backend && python evaluation/evaluate.py

bench:
	cd backend && python benchmarks/benchmark.py --n 100

# ── Development (no Docker) ──────────────────────────────────
dev-backend:
	cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

dev-frontend:
	cd frontend && npm run dev

# ── Cleanup ─────────────────────────────────────────────────
clean:
	docker compose down -v --remove-orphans
	@echo "All volumes and containers removed."
