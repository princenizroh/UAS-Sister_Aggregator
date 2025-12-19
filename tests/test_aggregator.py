"""
Unit tests untuk Pub-Sub Log Aggregator

Test coverage:
1. Event model validation
2. Deduplication logic
3. Persistence setelah restart
4. Concurrent processing
5. Transaction handling
6. API endpoints
7. Statistics consistency
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
import httpx
from datetime import datetime
import uuid
import json

# Import modules to test
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'aggregator'))

from src.models import Event, PublishRequest
from src.dedup_store import DedupStore
from src.config import Config


# TEST 1-4: Event Model Validation Tests

def test_event_model_valid():
    """Test 1: Valid event creation."""
    event = Event(
        topic="test-topic",
        event_id="test-id-123",
        timestamp=datetime.utcnow().isoformat() + "Z",
        source="test-source",
        payload={"key": "value"}
    )
    
    assert event.topic == "test-topic"
    assert event.event_id == "test-id-123"
    assert event.source == "test-source"
    assert event.payload == {"key": "value"}


def test_event_model_empty_event_id():
    """Test 2: Event with empty event_id should fail."""
    with pytest.raises(ValueError, match="event_id tidak boleh kosong"):
        Event(
            topic="test-topic",
            event_id="",
            timestamp=datetime.utcnow().isoformat() + "Z",
            source="test-source",
            payload={}
        )


def test_event_model_empty_topic():
    """Test 3: Event with empty topic should fail."""
    with pytest.raises(ValueError, match="topic tidak boleh kosong"):
        Event(
            topic="",
            event_id="test-id",
            timestamp=datetime.utcnow().isoformat() + "Z",
            source="test-source",
            payload={}
        )


def test_event_model_invalid_timestamp():
    """Test 4: Event with invalid timestamp should fail."""
    with pytest.raises(ValueError, match="timestamp harus format ISO8601"):
        Event(
            topic="test-topic",
            event_id="test-id",
            timestamp="invalid-timestamp",
            source="test-source",
            payload={}
        )


# TEST 5-10: Dedup Store Tests

@pytest_asyncio.fixture
async def dedup_store():
    """Fixture untuk DedupStore dengan temporary database."""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
        db_path = tmp.name
    
    store = DedupStore(db_path)
    await store.initialize()
    
    yield store
    
    await store.close()
    os.unlink(db_path)


@pytest.mark.asyncio
async def test_dedup_store_initialization(dedup_store):
    """Test 5: Dedup store initialization."""
    # Check if stats table exists and initialized
    stats = await dedup_store.get_stats()
    assert stats['received'] == 0
    assert stats['unique_processed'] == 0
    assert stats['duplicate_dropped'] == 0


@pytest.mark.asyncio
async def test_dedup_store_mark_processed(dedup_store):
    """Test 6: Mark event as processed."""
    topic = "test-topic"
    event_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    source = "test-source"
    payload = json.dumps({"test": "data"})
    
    # First time should succeed
    success = await dedup_store.mark_processed(topic, event_id, timestamp, source, payload)
    assert success == True
    
    # Second time should fail (duplicate)
    success = await dedup_store.mark_processed(topic, event_id, timestamp, source, payload)
    assert success == False


@pytest.mark.asyncio
async def test_dedup_store_is_duplicate(dedup_store):
    """Test 7: Check duplicate detection."""
    topic = "test-topic"
    event_id = str(uuid.uuid4())
    
    # Should not be duplicate initially
    is_dup = await dedup_store.is_duplicate(topic, event_id)
    assert is_dup == False
    
    # Mark as processed
    await dedup_store.mark_processed(
        topic, event_id, 
        datetime.utcnow().isoformat(),
        "test-source",
        json.dumps({})
    )
    
    # Should be duplicate now
    is_dup = await dedup_store.is_duplicate(topic, event_id)
    assert is_dup == True


@pytest.mark.asyncio
async def test_dedup_store_statistics(dedup_store):
    """Test 8: Statistics tracking."""
    # Increment counters
    await dedup_store.increment_received(5)
    await dedup_store.increment_unique_processed()
    await dedup_store.increment_unique_processed()
    await dedup_store.increment_duplicate_dropped()
    
    stats = await dedup_store.get_stats()
    assert stats['received'] == 5
    assert stats['unique_processed'] == 2
    assert stats['duplicate_dropped'] == 1


@pytest.mark.asyncio
async def test_dedup_store_concurrent_processing(dedup_store):
    """Test 9: Concurrent processing safety."""
    topic = "test-topic"
    event_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    source = "test-source"
    payload = json.dumps({"test": "data"})
    
    # Simulate concurrent writes
    async def mark():
        return await dedup_store.mark_processed(topic, event_id, timestamp, source, payload)
    
    # Run 10 concurrent tasks trying to process same event
    results = await asyncio.gather(*[mark() for _ in range(10)])
    
    # Only one should succeed, rest should fail
    success_count = sum(1 for r in results if r == True)
    assert success_count == 1, "Only one concurrent write should succeed"


@pytest.mark.asyncio
async def test_dedup_store_persistence():
    """Test 10: Persistence after restart."""
    # Create temporary database
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
        db_path = tmp.name
    
    try:
        # First session: create and add data
        store1 = DedupStore(db_path)
        await store1.initialize()
        
        event_id = str(uuid.uuid4())
        await store1.mark_processed(
            "test-topic",
            event_id,
            datetime.utcnow().isoformat(),
            "test-source",
            json.dumps({})
        )
        await store1.increment_unique_processed()
        
        await store1.close()
        
        # Second session: reopen and verify data persisted
        store2 = DedupStore(db_path)
        await store2.initialize()
        
        # Check if event is still marked as processed
        is_dup = await store2.is_duplicate("test-topic", event_id)
        assert is_dup == True, "Event should still be marked as processed after restart"
        
        # Check stats persisted
        stats = await store2.get_stats()
        assert stats['unique_processed'] == 1, "Stats should persist after restart"
        
        await store2.close()
        
    finally:
        os.unlink(db_path)


# TEST 11-14: API Integration Tests

@pytest.mark.asyncio
async def test_api_health_endpoint():
    """Test 11: Health endpoint."""
    # Note: This test requires aggregator to be running
    # In real scenario, use test containers or mock
    pass  # Implement with test container


@pytest.mark.asyncio
async def test_api_publish_endpoint():
    """Test 12: Publish endpoint."""
    # Note: This test requires aggregator to be running
    pass  # Implement with test container


@pytest.mark.asyncio
async def test_api_stats_endpoint():
    """Test 13: Stats endpoint."""
    # Note: This test requires aggregator to be running
    pass  # Implement with test container


@pytest.mark.asyncio
async def test_api_events_endpoint():
    """Test 14: Events endpoint."""
    # Note: This test requires aggregator to be running
    pass  # Implement with test container


# TEST 15-17: Batch Processing Tests

@pytest.mark.asyncio
async def test_batch_processing(dedup_store):
    """Test 15: Batch event processing."""
    # Process multiple events
    events = []
    for i in range(10):
        event_id = str(uuid.uuid4())
        success = await dedup_store.mark_processed(
            f"topic-{i % 3}",
            event_id,
            datetime.utcnow().isoformat(),
            "test-source",
            json.dumps({"index": i})
        )
        if success:
            events.append(event_id)
    
    assert len(events) == 10, "All unique events should be processed"


@pytest.mark.asyncio
async def test_topic_filtering(dedup_store):
    """Test 16: Topic filtering."""
    # Add events to different topics
    for i in range(5):
        await dedup_store.mark_processed(
            "topic-A",
            str(uuid.uuid4()),
            datetime.utcnow().isoformat(),
            "test-source",
            json.dumps({})
        )
    
    for i in range(3):
        await dedup_store.mark_processed(
            "topic-B",
            str(uuid.uuid4()),
            datetime.utcnow().isoformat(),
            "test-source",
            json.dumps({})
        )
    
    # Get events for topic-A
    events_a = await dedup_store.get_events(topic="topic-A", limit=100)
    assert len(events_a) == 5
    
    # Get events for topic-B
    events_b = await dedup_store.get_events(topic="topic-B", limit=100)
    assert len(events_b) == 3


@pytest.mark.asyncio
async def test_pagination(dedup_store):
    """Test 17: Pagination."""
    # Add 20 events
    for i in range(20):
        await dedup_store.mark_processed(
            "test-topic",
            str(uuid.uuid4()),
            datetime.utcnow().isoformat(),
            "test-source",
            json.dumps({"index": i})
        )
    
    # Get first page
    page1 = await dedup_store.get_events(limit=10, offset=0)
    assert len(page1) == 10
    
    # Get second page
    page2 = await dedup_store.get_events(limit=10, offset=10)
    assert len(page2) == 10
    
    # Ensure no overlap
    ids1 = {e['id'] for e in page1}
    ids2 = {e['id'] for e in page2}
    assert len(ids1.intersection(ids2)) == 0, "Pages should not overlap"


# TEST 18-20: Stress Tests

@pytest.mark.asyncio
async def test_high_volume_processing(dedup_store):
    """Test 18: High volume event processing."""
    import time
    
    num_events = 1000
    start_time = time.time()
    
    # Process 1000 events
    for i in range(num_events):
        await dedup_store.mark_processed(
            f"topic-{i % 10}",
            str(uuid.uuid4()),
            datetime.utcnow().isoformat(),
            "test-source",
            json.dumps({"index": i})
        )
        await dedup_store.increment_unique_processed()
    
    elapsed = time.time() - start_time
    throughput = num_events / elapsed
    
    print(f"\nProcessed {num_events} events in {elapsed:.2f}s ({throughput:.2f} events/sec)")
    
    # Verify stats
    stats = await dedup_store.get_stats()
    assert stats['unique_processed'] == num_events


@pytest.mark.asyncio
async def test_duplicate_rate_accuracy(dedup_store):
    """Test 19: Duplicate rate accuracy."""
    total_events = 100
    expected_duplicates = 30
    
    # Generate events
    event_ids = [str(uuid.uuid4()) for _ in range(total_events - expected_duplicates)]
    
    # Add some duplicates
    event_ids.extend(event_ids[:expected_duplicates])
    
    # Shuffle
    import random
    random.shuffle(event_ids)
    
    # Process all events
    unique_count = 0
    duplicate_count = 0
    
    for event_id in event_ids:
        success = await dedup_store.mark_processed(
            "test-topic",
            event_id,
            datetime.utcnow().isoformat(),
            "test-source",
            json.dumps({})
        )
        
        if success:
            unique_count += 1
        else:
            duplicate_count += 1
    
    assert unique_count == total_events - expected_duplicates
    assert duplicate_count == expected_duplicates


@pytest.mark.asyncio
async def test_transaction_rollback_on_error(dedup_store):
    """Test 20: Transaction rollback on error."""
    # This test verifies that failed transactions don't corrupt data
    
    # Get initial count
    initial_count = await dedup_store.count_events()
    
    # Try to process event with valid data
    event_id = str(uuid.uuid4())
    success = await dedup_store.mark_processed(
        "test-topic",
        event_id,
        datetime.utcnow().isoformat(),
        "test-source",
        json.dumps({"data": "valid"})
    )
    
    assert success == True
    
    # Verify count increased
    new_count = await dedup_store.count_events()
    assert new_count == initial_count + 1
    
    # Trying to insert same event should fail but not corrupt data
    success = await dedup_store.mark_processed(
        "test-topic",
        event_id,
        datetime.utcnow().isoformat(),
        "test-source",
        json.dumps({"data": "duplicate"})
    )
    
    assert success == False
    
    # Count should remain the same
    final_count = await dedup_store.count_events()
    assert final_count == new_count


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
