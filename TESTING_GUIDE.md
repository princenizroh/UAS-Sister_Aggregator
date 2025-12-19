# 📘 TESTING GUIDE - UAS Pub-Sub Log Aggregator

## ⚠️ PENTING: Testing Checklist

Dokumen ini berisi **instruksi lengkap** untuk testing semua requirement UAS.
**HARUS dijalankan semua** untuk memastikan tidak ada error!

---

## 🔧 Prerequisites

1. **Docker Desktop** (Windows/Mac) atau **Docker Engine** (Linux)
   ```powershell
   # Check Docker
   docker --version
   docker compose version
   ```

2. **Python 3.11+** (untuk unit tests)
   ```powershell
   python --version
   ```

3. **Optional: K6** (untuk load testing)
   ```powershell
   # Windows (Chocolatey)
   choco install k6
   
   # Or download from https://k6.io/docs/get-started/installation/
   ```

---

## 🚀 Step-by-Step Testing

### STEP 1: Build Docker Images

```powershell
cd C:\Users\princ\OneDrive\obsidian-note\Contents\College\Sister\UAS-Project

# Build semua images
docker compose build

# Verify images created
docker images | Select-String "uas-"
```

**Expected Output**:
```
uas-aggregator   latest   ...
uas-publisher    latest   ...
```

**✅ PASS Criteria**: Both images built successfully without errors

---

### STEP 2: Start Services

```powershell
# Start services
docker compose up -d

# Check status
docker compose ps

# Check logs
docker compose logs -f aggregator
```

**Expected Output**:
```
NAME              STATUS         PORTS
uas-aggregator    Up (healthy)   0.0.0.0:8080->8080/tcp
uas-publisher     Up             
```

**Wait 5-10 seconds** untuk aggregator fully ready.

**✅ PASS Criteria**: 
- Aggregator shows "RUNNING" in logs
- Health check passing
- No error messages

---

### STEP 3: Test Health Endpoint

```powershell
# Test health
curl http://localhost:8080/health

# Or with Invoke-RestMethod
Invoke-RestMethod -Uri "http://localhost:8080/health" | ConvertTo-Json
```

**Expected Output**:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-12T00:00:00.000000",
  "uptime_seconds": 10
}
```

**✅ PASS Criteria**: Status code 200, status = "healthy"

---

### STEP 4: Test POST /publish (Single Event)

```powershell
# Create test event
$body = @{
    events = @{
        topic = "test"
        event_id = "test-001"
        timestamp = "2025-11-12T00:00:00Z"
        source = "manual-test"
        payload = @{
            message = "Test event 1"
            level = "INFO"
        }
    }
} | ConvertTo-Json -Depth 10

# Send request
$response = Invoke-RestMethod -Uri "http://localhost:8080/publish" `
    -Method POST `
    -Body $body `
    -ContentType "application/json"

$response | ConvertTo-Json
```

**Expected Output**:
```json
{
  "status": "accepted",
  "received": 1,
  "queued": 1,
  "message": "Received 1 events, queued 1 for processing"
}
```

**✅ PASS Criteria**: 
- Status = "accepted"
- received = 1
- queued = 1

---

### STEP 5: Test POST /publish (Batch Events)

```powershell
# Create batch
$batch = @{
    events = @(
        @{
            topic = "logs"
            event_id = "batch-001"
            timestamp = "2025-11-12T00:00:00Z"
            source = "batch-test"
            payload = @{ message = "Event 1" }
        },
        @{
            topic = "logs"
            event_id = "batch-002"
            timestamp = "2025-11-12T00:00:01Z"
            source = "batch-test"
            payload = @{ message = "Event 2" }
        },
        @{
            topic = "metrics"
            event_id = "batch-003"
            timestamp = "2025-11-12T00:00:02Z"
            source = "batch-test"
            payload = @{ message = "Event 3" }
        }
    )
} | ConvertTo-Json -Depth 10

$response = Invoke-RestMethod -Uri "http://localhost:8080/publish" `
    -Method POST `
    -Body $batch `
    -ContentType "application/json"

$response | ConvertTo-Json
```

**Expected Output**:
```json
{
  "status": "accepted",
  "received": 3,
  "queued": 3,
  "message": "Received 3 events, queued 3 for processing"
}
```

**✅ PASS Criteria**: received = 3, queued = 3

---

### STEP 6: Test GET /stats

```powershell
# Wait for processing
Start-Sleep -Seconds 2

# Get stats
$stats = Invoke-RestMethod -Uri "http://localhost:8080/stats"
$stats | ConvertTo-Json
```

**Expected Output**:
```json
{
  "received": 4,
  "unique_processed": 4,
  "duplicate_dropped": 0,
  "topics": ["test", "logs", "metrics"],
  "uptime_seconds": 30,
  "queue_size": 0
}
```

**✅ PASS Criteria**:
- received >= 4
- unique_processed >= 4
- topics contains test entries

---

### STEP 7: Test Deduplication (CRITICAL!)

```powershell
# Send same event twice
$dupEvent = @{
    events = @{
        topic = "dedup-test"
        event_id = "DUPLICATE-TEST-123"
        timestamp = "2025-11-12T00:00:00Z"
        source = "dedup-test"
        payload = @{ test = "duplicate" }
    }
} | ConvertTo-Json -Depth 10

# First send
Write-Host "Sending first time..."
Invoke-RestMethod -Uri "http://localhost:8080/publish" -Method POST -Body $dupEvent -ContentType "application/json"

Start-Sleep -Seconds 1

# Get stats before duplicate
$statsBefore = Invoke-RestMethod -Uri "http://localhost:8080/stats"
Write-Host "Before duplicate - Dropped: $($statsBefore.duplicate_dropped)"

# Second send (duplicate)
Write-Host "Sending duplicate..."
Invoke-RestMethod -Uri "http://localhost:8080/publish" -Method POST -Body $dupEvent -ContentType "application/json"

Start-Sleep -Seconds 1

# Get stats after duplicate
$statsAfter = Invoke-RestMethod -Uri "http://localhost:8080/stats"
Write-Host "After duplicate - Dropped: $($statsAfter.duplicate_dropped)"

# Check if duplicate_dropped increased
$increased = $statsAfter.duplicate_dropped - $statsBefore.duplicate_dropped
Write-Host "Duplicate dropped increased by: $increased"
```

**Expected Behavior**:
- First send: processed successfully
- Second send: detected as duplicate
- `duplicate_dropped` counter increases by 1

**✅ PASS Criteria**: duplicate_dropped increases by exactly 1

---

### STEP 8: Test GET /events

```powershell
# Get all events
$events = Invoke-RestMethod -Uri "http://localhost:8080/events?limit=10"
$events | ConvertTo-Json -Depth 5

# Get events by topic
$topicEvents = Invoke-RestMethod -Uri "http://localhost:8080/events?topic=logs&limit=5"
$topicEvents | ConvertTo-Json -Depth 5
```

**Expected Output**:
```json
{
  "events": [
    {
      "id": 1,
      "topic": "logs",
      "event_id": "batch-001",
      "timestamp": "2025-11-12T00:00:00Z",
      "source": "batch-test",
      "payload": {"message": "Event 1"},
      "processed_at": "2025-11-12T00:00:05.123456"
    }
  ],
  "total": 5,
  "limit": 10,
  "offset": 0
}
```

**✅ PASS Criteria**:
- Returns array of events
- total >= 0
- Filtering by topic works

---

### STEP 9: Test Persistence (CRITICAL!)

```powershell
# Get current stats
$statsBefore = Invoke-RestMethod -Uri "http://localhost:8080/stats"
Write-Host "Stats before restart:"
$statsBefore | ConvertTo-Json

# Stop containers (keep volumes!)
docker compose down
Write-Host "Containers stopped. Waiting..."
Start-Sleep -Seconds 3

# Start again
docker compose up -d
Write-Host "Containers restarted. Waiting for health..."
Start-Sleep -Seconds 10

# Get stats after restart
$statsAfter = Invoke-RestMethod -Uri "http://localhost:8080/stats"
Write-Host "Stats after restart:"
$statsAfter | ConvertTo-Json

# Verify stats persisted
if ($statsAfter.unique_processed -eq $statsBefore.unique_processed) {
    Write-Host "✓ PERSISTENCE TEST PASSED!" -ForegroundColor Green
} else {
    Write-Host "✗ PERSISTENCE TEST FAILED!" -ForegroundColor Red
}

# Try to send previous duplicate again
$dupEvent = @{
    events = @{
        topic = "dedup-test"
        event_id = "DUPLICATE-TEST-123"
        timestamp = "2025-11-12T00:00:00Z"
        source = "dedup-test"
        payload = @{ test = "duplicate" }
    }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://localhost:8080/publish" -Method POST -Body $dupEvent -ContentType "application/json"
Start-Sleep -Seconds 1

$statsAfterDup = Invoke-RestMethod -Uri "http://localhost:8080/stats"
if ($statsAfterDup.duplicate_dropped -gt $statsAfter.duplicate_dropped) {
    Write-Host "✓ DEDUP PERSISTENCE TEST PASSED!" -ForegroundColor Green
} else {
    Write-Host "✗ DEDUP PERSISTENCE TEST FAILED!" -ForegroundColor Red
}
```

**✅ PASS Criteria**:
- Stats persist after container restart
- Previous duplicates still detected after restart
- No data loss

---

### STEP 10: Test Publisher (20k Events with 30% Duplicates)

```powershell
# Start publisher
docker compose up -d publisher

# Monitor logs
docker compose logs -f publisher

# Wait for completion (about 2-3 minutes)
# Look for "Publisher finished" message

# Get final stats
$finalStats = Invoke-RestMethod -Uri "http://localhost:8080/stats"
$finalStats | ConvertTo-Json

# Calculate duplicate rate
$dupRate = ($finalStats.duplicate_dropped / $finalStats.received) * 100
Write-Host "Duplicate Rate: $([math]::Round($dupRate, 2))%"
```

**Expected Output**:
```
Total events sent: 20000
Duplicates generated: 6000
Duplicate rate: 30.00%
```

**✅ PASS Criteria**:
- received >= 20000
- duplicate_rate >= 25% and <= 35%
- No errors in logs
- unique_processed + duplicate_dropped = received

---

### STEP 11: Test Concurrency (Multiple Workers)

```powershell
# Send concurrent requests
$jobs = @()

1..10 | ForEach-Object {
    $job = Start-Job -ScriptBlock {
        param($index)
        $body = @{
            events = @{
                topic = "concurrent-test"
                event_id = "concurrent-$($index)-$(Get-Random)"
                timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
                source = "concurrent-test-$index"
                payload = @{ worker = $index }
            }
        } | ConvertTo-Json -Depth 10
        
        Invoke-RestMethod -Uri "http://localhost:8080/publish" `
            -Method POST `
            -Body $body `
            -ContentType "application/json"
    } -ArgumentList $_
    
    $jobs += $job
}

# Wait for all jobs
$jobs | Wait-Job
$jobs | Receive-Job
$jobs | Remove-Job

Write-Host "All concurrent requests completed"

# Verify no race conditions in logs
docker compose logs aggregator | Select-String "DUPLICATE DETECTED (race)"
```

**✅ PASS Criteria**:
- All requests succeed
- No race conditions detected
- Stats remain consistent

---

### STEP 12: Run Unit Tests

```powershell
cd tests

# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest test_aggregator.py -v

# Run with coverage
pytest test_aggregator.py -v --cov=../aggregator/src --cov-report=html
```

**Expected Output**:
```
test_event_model_valid PASSED
test_event_model_empty_event_id PASSED
...
test_transaction_rollback_on_error PASSED

========== 20 passed in 5.32s ==========
```

**✅ PASS Criteria**: All 20 tests pass

---

### STEP 13: Performance Test dengan K6 (Optional)

```powershell
cd k6

# Run K6 load test
k6 run load_test.js

# Or with custom settings
k6 run load_test.js --vus 100 --duration 2m
```

**Expected Output**:
```
✓ single publish status is 200
✓ batch publish status is 200
...

http_req_duration..........: avg=45ms p95=120ms
http_reqs..................: 50000 (833/s)
errors.....................: 0.02%
```

**✅ PASS Criteria**:
- p95 latency < 500ms
- Error rate < 1%
- Throughput > 500 req/s

---

## 📊 Final Validation Checklist

After all tests, verify:

```powershell
# Get final stats
$stats = Invoke-RestMethod -Uri "http://localhost:8080/stats"

Write-Host "========== FINAL VALIDATION =========="
Write-Host "Received: $($stats.received)"
Write-Host "Unique Processed: $($stats.unique_processed)"
Write-Host "Duplicate Dropped: $($stats.duplicate_dropped)"
Write-Host "Duplicate Rate: $([math]::Round(($stats.duplicate_dropped / $stats.received) * 100, 2))%"
Write-Host "Topics: $($stats.topics -join ', ')"
Write-Host "======================================"

# Verify equation
$total = $stats.unique_processed + $stats.duplicate_dropped
if ($total -eq $stats.received) {
    Write-Host "✓ CONSISTENCY CHECK PASSED" -ForegroundColor Green
    Write-Host "  unique_processed + duplicate_dropped = received" -ForegroundColor Green
} else {
    Write-Host "✗ CONSISTENCY CHECK FAILED" -ForegroundColor Red
    Write-Host "  Expected: $($stats.received), Got: $total" -ForegroundColor Red
}

# Check persistence
docker compose down
Start-Sleep -Seconds 3
docker compose up -d
Start-Sleep -Seconds 10

$statsAfter = Invoke-RestMethod -Uri "http://localhost:8080/stats"
if ($statsAfter.unique_processed -eq $stats.unique_processed) {
    Write-Host "✓ PERSISTENCE CHECK PASSED" -ForegroundColor Green
} else {
    Write-Host "✗ PERSISTENCE CHECK FAILED" -ForegroundColor Red
}
```

---

## ✅ ALL TESTS MUST PASS!

**Requirements**:
1. ✅ All 20 unit tests pass
2. ✅ Health endpoint returns healthy
3. ✅ POST /publish accepts events
4. ✅ Deduplication works correctly
5. ✅ Stats are accurate
6. ✅ Events are retrievable
7. ✅ Persistence works after restart
8. ✅ Publisher sends 20k+ events
9. ✅ Duplicate rate ~ 30%
10. ✅ Concurrent requests work
11. ✅ No race conditions
12. ✅ Data consistency maintained

---

## 🐛 Troubleshooting

### Issue: Container won't start

```powershell
# Check logs
docker compose logs aggregator

# Rebuild
docker compose build --no-cache
docker compose up -d
```

### Issue: Database locked

```powershell
# Stop all containers
docker compose down

# Remove volumes
docker compose down -v

# Restart
docker compose up --build
```

### Issue: Tests fail

```powershell
# Ensure aggregator is running
docker compose ps

# Check Python version
python --version  # Should be 3.11+

# Reinstall dependencies
pip install -r tests/requirements.txt --force-reinstall
```

---

## 🎯 Success Criteria Summary

**System must**:
- ✅ Process ≥20,000 events
- ✅ Handle ≥30% duplicate rate correctly
- ✅ Maintain data consistency
- ✅ Survive container restarts
- ✅ Pass all 20 unit tests
- ✅ Handle concurrent requests safely
- ✅ Provide accurate statistics
- ✅ No data loss
- ✅ No race conditions

**All tests documented here MUST PASS before submission!**

---

Last updated: 2025-11-12
