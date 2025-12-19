# 🚀 Pub-Sub Log Aggregator - UAS Sistem Terdistribusi

**Tema**: Pub-Sub Log Aggregator dengan Idempotent Consumer, Deduplication, dan Transaksi/Kontrol Konkurensi

## 🎬 Video Demo

**YouTube Link**: [Video Demonstrasi UAS Sistem Terdistribusi]([https://youtu.be/hwyleKo0hqY])

📹 **Duration**: ~22 menit  
📝 **Mencakup**:
- Arsitektur multi-service dan design decisions
- Build & deployment dengan Docker Compose
- Live demonstration idempotency & deduplication
- Transaksi dan concurrent processing
- Persistence testing (restart container)
- Observability (logging & metrics)
- Full test suite execution (20 tests)


---

## 📋 Overview

Sistem distributed log aggregator yang mendukung:
- ✅ **Idempotent Consumer**: Event yang sama tidak diproses ulang
- ✅ **Deduplication**: Persistent dedup store dengan unique constraint (topic, event_id)
- ✅ **ACID Transactions**: Transaksi untuk consistency dan isolation
- ✅ **Concurrency Control**: Safe concurrent processing dengan multiple workers
- ✅ **Persistence**: Data aman meski container di-recreate (named volumes)
- ✅ **At-least-once Delivery**: Publisher bisa kirim duplikat, sistem tetap konsisten

---

## 🏗️ Arsitektur

```
┌─────────────────────────────────────────────────────────┐
│                 Pub-Sub Log Aggregator                   │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐         ┌──────────────────┐          │
│  │  Publisher   │────────>│   Aggregator     │          │
│  │              │  HTTP   │                  │          │
│  │ - Generator  │         │ - FastAPI        │          │
│  │ - Duplikasi  │         │ - Event Queue    │          │
│  │   30%        │         │ - Consumer       │          │
│  └──────────────┘         │ - Dedup Store    │          │
│                           └──────────────────┘          │
│                                     │                     │
│                                     v                     │
│                           ┌──────────────────┐          │
│                           │  SQLite Database │          │
│                           │                  │          │
│                           │ - processed_     │          │
│                           │   events table   │          │
│                           │ - UNIQUE(topic,  │          │
│                           │   event_id)      │          │
│                           │ - stats table    │          │
│                           └──────────────────┘          │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

---

## 🎯 Fitur Utama

### 1. Idempotency & Deduplication
- Menggunakan **unique constraint** pada `(topic, event_id)`
- **INSERT OR IGNORE** pattern untuk idempotent writes
- Persistent dedup store (survive container restart)

### 2. Transactions & Concurrency
- **ACID transactions** dengan SQLite
- **Isolation level**: READ_COMMITTED (configurable)
- **Atomic operations**: upsert dengan conflict resolution
- **Safe concurrent processing**: multiple workers tanpa race conditions

### 3. Persistence
- **Named volume** untuk SQLite database
- **WAL mode** untuk better concurrency
- Data tetap ada setelah `docker-compose down` dan `up`

### 4. Observability
- **GET /stats**: received, unique_processed, duplicate_dropped, topics, uptime
- **GET /events**: daftar processed events dengan filtering & pagination
- **GET /health**: health check endpoint
- **Logging**: structured logging untuk audit trail

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (untuk local testing)

### 1. Build & Run dengan Docker Compose

```bash
# Build images dan start services
docker compose up --build

# Atau run di background
docker compose up -d --build

# Check logs
docker compose logs -f aggregator
docker compose logs -f publisher

# Check status
docker compose ps
```

### 2. Akses Aggregator

```bash
# Health check
curl http://localhost:8080/health

# Get statistics
curl http://localhost:8080/stats

# Get processed events
curl "http://localhost:8080/events?limit=10"

# Get events by topic
curl "http://localhost:8080/events?topic=logs&limit=5"
```

### 3. Manual Publish (Optional)

```bash
# Publish single event
curl -X POST http://localhost:8080/publish \
  -H 'Content-Type: application/json' \
  -d '{
    "events": {
      "topic": "test",
      "event_id": "manual-test-1",
      "timestamp": "2025-11-12T00:00:00Z",
      "source": "manual-test",
      "payload": {"message": "test event"}
    }
  }'

# Publish batch events
curl -X POST http://localhost:8080/publish \
  -H 'Content-Type: application/json' \
  -d '{
    "events": [
      {
        "topic": "logs",
        "event_id": "batch-1",
        "timestamp": "2025-11-12T00:00:00Z",
        "source": "batch-test",
        "payload": {"message": "event 1"}
      },
      {
        "topic": "logs",
        "event_id": "batch-2",
        "timestamp": "2025-11-12T00:00:01Z",
        "source": "batch-test",
        "payload": {"message": "event 2"}
      }
    ]
  }'
```

---

## 🧪 Testing

### Run Unit Tests

```bash
# Install test dependencies
cd tests
pip install -r requirements.txt

# Run all tests
pytest test_aggregator.py -v

# Run with coverage
pytest test_aggregator.py -v --cov=../aggregator/src --cov-report=html

# Run specific test
pytest test_aggregator.py::test_dedup_store_concurrent_processing -v
```

### Test Scenarios Covered

1. ✅ **Event Model Validation** (Test 1-4)
2. ✅ **Deduplication Logic** (Test 5-7)
3. ✅ **Statistics Tracking** (Test 8)
4. ✅ **Concurrent Processing** (Test 9)
5. ✅ **Persistence After Restart** (Test 10)
6. ✅ **Batch Processing** (Test 15)
7. ✅ **Topic Filtering** (Test 16)
8. ✅ **Pagination** (Test 17)
9. ✅ **High Volume Processing** (Test 18)
10. ✅ **Duplicate Rate Accuracy** (Test 19)
11. ✅ **Transaction Rollback** (Test 20)

**Total: 20 tests** ✅

---

## 🔬 Testing Idempotency & Deduplication

### Test 1: Basic Deduplication

```bash
# Start services
docker compose up -d

# Wait for publisher to finish
docker compose logs -f publisher

# Check stats
curl http://localhost:8080/stats
```

Expected output:
```json
{
  "received": 20000,
  "unique_processed": 14000,
  "duplicate_dropped": 6000,
  "duplicate_rate": 30.0,
  "topics": ["logs", "metrics", "events", "alerts", "traces"],
  "uptime_seconds": 120,
  "queue_size": 0
}
```

### Test 2: Persistence After Container Recreate

```bash
# Check current stats
curl http://localhost:8080/stats

# Stop and remove containers (keep volumes)
docker compose down

# Start again
docker compose up -d aggregator

# Check stats (should be same)
curl http://localhost:8080/stats

# Try to send duplicate event
curl -X POST http://localhost:8080/publish \
  -H 'Content-Type: application/json' \
  -d '{
    "events": {
      "topic": "logs",
      "event_id": "duplicate-test",
      "timestamp": "2025-11-12T00:00:00Z",
      "source": "test",
      "payload": {}
    }
  }'

# Send again (should be dropped)
curl -X POST http://localhost:8080/publish \
  -H 'Content-Type: application/json' \
  -d '{
    "events": {
      "topic": "logs",
      "event_id": "duplicate-test",
      "timestamp": "2025-11-12T00:00:00Z",
      "source": "test",
      "payload": {}
    }
  }'

# Check duplicate_dropped increased by 1
curl http://localhost:8080/stats
```

### Test 3: Concurrent Processing

```bash
# Run multiple publishers simultaneously
docker compose up -d --scale publisher=3

# All should process without race conditions
docker compose logs -f aggregator | grep "DUPLICATE DETECTED (race)"
```

---

## 📊 Performance Testing dengan K6

```bash
# Install K6
# Windows (chocolatey): choco install k6
# Linux: sudo apt-get install k6
# Mac: brew install k6

# Run load test
k6 run k6/load_test.js

# Expected results:
# - Throughput: > 1000 req/sec
# - Latency p95: < 100ms
# - Success rate: > 99%
```

---

## 🎓 Keterkaitan dengan Bab 1-13

### Bab 1-2: Karakteristik & Arsitektur
- **Pub-Sub pattern** untuk decoupling producer-consumer
- **Microservices** dengan Docker Compose orchestration

### Bab 3-4: Komunikasi & Penamaan
- **HTTP/REST API** untuk inter-service communication
- **UUID** untuk collision-resistant event_id
- **Topic-based** routing

### Bab 5: Waktu & Ordering
- **ISO8601 timestamp** untuk event ordering
- **At-least-once delivery** dengan timestamp tracking

### Bab 6: Toleransi Kegagalan
- **Retry logic** di publisher
- **Persistent storage** untuk crash tolerance
- **Graceful shutdown** handling

### Bab 7: Konsistensi & Replikasi
- **Eventual consistency** dengan deduplication
- **Idempotency** untuk consistency guarantees

### **Bab 8-9: Transaksi & Kontrol Konkurensi** ⭐
- **ACID transactions** dengan SQLite
- **Isolation level** (READ_COMMITTED)
- **Unique constraints** untuk conflict resolution
- **INSERT OR IGNORE** untuk idempotent upsert
- **Concurrent-safe** operations
- **No lost updates** dengan atomic increments

### Bab 10-11: Keamanan & Penyimpanan
- **Network isolation** dengan Docker network
- **Non-root user** di container
- **Named volumes** untuk persistent storage

### Bab 12-13: Sistem Web & Koordinasi
- **FastAPI** untuk RESTful API
- **Docker Compose** untuk orchestration
- **Health checks** untuk liveness/readiness
- **Structured logging** untuk observability

---

## 📁 Struktur Project

```
UAS-Project/
├── aggregator/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   └── src/
│       ├── __init__.py
│       ├── config.py
│       ├── models.py
│       └── dedup_store.py
├── publisher/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
├── tests/
│   ├── requirements.txt
│   └── test_aggregator.py
├── k6/
│   └── load_test.js
├── docs/
│   └── report.md
├── docker-compose.yml
└── README.md
```

---

## 🔧 Configuration

### Environment Variables (Aggregator)

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8080` | Server port |
| `DB_PATH` | `/var/lib/aggregator/dedup.db` | SQLite database path |
| `ISOLATION_LEVEL` | `READ_COMMITTED` | Transaction isolation level |
| `QUEUE_MAX_SIZE` | `10000` | Maximum queue size |
| `LOG_LEVEL` | `INFO` | Logging level |
| `NUM_WORKERS` | `3` | Number of consumer workers |

### Environment Variables (Publisher)

| Variable | Default | Description |
|----------|---------|-------------|
| `TARGET_URL` | `http://aggregator:8080/publish` | Aggregator URL |
| `NUM_EVENTS` | `20000` | Total events to generate |
| `DUPLICATE_RATE` | `0.30` | Duplicate rate (30%) |
| `BATCH_SIZE` | `100` | Events per batch |
| `DELAY_BETWEEN_BATCHES` | `0.1` | Delay in seconds |

---

## 🐛 Troubleshooting

### Container tidak start

```bash
# Check logs
docker compose logs aggregator

# Rebuild
docker compose build --no-cache

# Clean restart
docker compose down -v
docker compose up --build
```

### Database locked error

```bash
# Check if WAL mode enabled
docker compose exec aggregator python -c "
import sqlite3
conn = sqlite3.connect('/var/lib/aggregator/dedup.db')
cursor = conn.execute('PRAGMA journal_mode')
print(cursor.fetchone())
"
# Should output: ('wal',)
```

### High duplicate rate

```bash
# Check publisher logs
docker compose logs publisher | grep "Duplicate rate"

# Should be around 30%
```

---

## 📺 Video Demo

Link YouTube: [Will be added after recording]

**Duration**: < 25 menit

**Content**:
1. Arsitektur dan design decisions (3 min)
2. Build & run dengan Docker Compose (2 min)
3. Demo idempotency & deduplication (5 min)
4. Demo concurrency control (5 min)
5. Demo persistence (5 min)
6. Observability & metrics (3 min)
7. Kesimpulan & challenges (2 min)

---

## 📝 Laporan

Lihat file: `docs/report.md`

**Content**:
- Teori (T1-T10) dengan sitasi APA 7th
- Design decisions
- Performance metrics
- Test results
- Keterkaitan Bab 1-13

---

## ✅ Checklist Requirements

### Implementasi (70%)
- ✅ Arsitektur multi-service dengan Docker Compose
- ✅ Idempotent consumer dengan dedup store
- ✅ Transactions dengan ACID properties
- ✅ Concurrency control (unique constraints, upsert)
- ✅ Persistent storage dengan volumes
- ✅ API endpoints (POST /publish, GET /events, GET /stats)
- ✅ Event model sesuai spesifikasi
- ✅ At-least-once delivery guarantee
- ✅ 20+ tests (unit & integration)
- ✅ Performance ≥ 20k events dengan ≥30% duplikasi

### Dokumentasi
- ✅ README.md lengkap
- ✅ Code comments & docstrings
- ✅ API documentation
- ✅ Deployment instructions

### Testing
- ✅ 20 unit/integration tests
- ✅ Deduplication tests
- ✅ Persistence tests
- ✅ Concurrency tests
- ✅ Performance tests

---

## 🎯 Key Achievements

1. **100% Idempotency**: Tidak ada event yang diproses ulang
2. **ACID Compliance**: Semua transaksi atomic dan consistent
3. **Concurrency Safe**: Multiple workers tanpa race conditions
4. **Persistent**: Data survive container recreate
5. **High Performance**: Handle 20k+ events dengan latency rendah
6. **Well Tested**: 20 comprehensive tests

---

## 👨‍💻 Author

**Zaky Dio Akbar Pangestu**  
**NIM**: 11221050
**Mata Kuliah**: Sistem Terdistribusi  
**Tahun**: 2025

---

