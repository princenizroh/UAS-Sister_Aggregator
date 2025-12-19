# Pub-Sub Log Aggregator - Main Application
# UAS Sistem Terdistribusi
#
# Fitur:
# - Idempotent consumer dengan deduplication
# - Transaksi ACID dengan isolation level
# - Concurrent processing yang aman
# - Persistent storage dengan SQLite

import asyncio
import logging
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
import uvicorn

from src.config import Config
from src.dedup_store import DedupStore
from src.models import Event, PublishRequest, PublishResponse, Stats, EventsResponse

# Setup logging
logging.basicConfig(
    level=Config.get_log_level(),
    format=Config.LOG_FORMAT
)
logger = logging.getLogger(__name__)

# Global variables
dedup_store: Optional[DedupStore] = None
event_queue: asyncio.Queue = None
start_time: datetime = datetime.utcnow()
consumer_task: Optional[asyncio.Task] = None


async def event_consumer():
    logger.info("Event consumer started")
    
    while True:
        try:
            # Get event from queue
            event: Event = await event_queue.get()
            
            # Check if duplicate (dalam transaksi untuk atomicity)
            is_dup = await dedup_store.is_duplicate(event.topic, event.event_id)
            
            if is_dup:
                # Event sudah pernah diproses, drop
                await dedup_store.increment_duplicate_dropped()
                logger.warning(
                    f"DUPLICATE DROPPED - topic: {event.topic}, "
                    f"event_id: {event.event_id}, source: {event.source}"
                )
            else:
                # Event baru, process dalam transaksi
                import json
                payload_json = json.dumps(event.payload)
                
                success = await dedup_store.mark_processed(
                    event.topic,
                    event.event_id,
                    event.timestamp,
                    event.source,
                    payload_json
                )
                
                if success:
                    await dedup_store.increment_unique_processed()
                    logger.info(
                        f"EVENT PROCESSED - topic: {event.topic}, "
                        f"event_id: {event.event_id}, source: {event.source}"
                    )
                else:
                    # Race condition: event sudah diproses saat kita check
                    # Ini bisa terjadi dengan multiple workers
                    await dedup_store.increment_duplicate_dropped()
                    logger.warning(
                        f"DUPLICATE DETECTED (race) - topic: {event.topic}, "
                        f"event_id: {event.event_id}"
                    )
            
            # Mark task done
            event_queue.task_done()
            
        except Exception as e:
            logger.error(f"Error in event consumer: {str(e)}", exc_info=True)
            await asyncio.sleep(0.1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global dedup_store, event_queue, consumer_task, start_time
    
    logger.info("Starting Pub-Sub Log Aggregator...")
    Config.print_config()
    
    # Initialize dedup store dengan persistent SQLite
    dedup_store = DedupStore(db_path=Config.DB_PATH)
    await dedup_store.initialize()
    
    # Initialize event queue
    event_queue = asyncio.Queue(maxsize=Config.QUEUE_MAX_SIZE)
    
    # Start consumer task
    consumer_task = asyncio.create_task(event_consumer())
    
    start_time = datetime.utcnow()
    
    logger.info("Aggregator started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down aggregator...")
    
    # Cancel consumer task
    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
    
    # Close dedup store
    if dedup_store:
        await dedup_store.close()
    
    logger.info("Aggregator stopped")


# Create FastAPI app
app = FastAPI(
    title="Pub-Sub Log Aggregator",
    description="Distributed log aggregator dengan idempotent consumer dan deduplication",
    version="1.0.0",
    lifespan=lifespan
)


@app.post("/publish", response_model=PublishResponse)
async def publish_events(request: PublishRequest):
    try:
        events = request.events if isinstance(request.events, list) else [request.events]
        
        # Increment received counter
        await dedup_store.increment_received(len(events))
        
        # Add events to queue untuk processing
        queued_count = 0
        for event in events:
            try:
                # Non-blocking put dengan timeout
                await asyncio.wait_for(
                    event_queue.put(event),
                    timeout=Config.QUEUE_PUT_TIMEOUT
                )
                queued_count += 1
            except asyncio.TimeoutError:
                logger.warning(f"Queue full, dropping event {event.event_id}")
        
        return PublishResponse(
            status="accepted",
            received=len(events),
            queued=queued_count,
            message=f"Received {len(events)} events, queued {queued_count} for processing"
        )
        
    except Exception as e:
        logger.error(f"Error publishing events: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events", response_model=EventsResponse)
async def get_events(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    try:
        events = await dedup_store.get_events(
            topic=topic,
            limit=limit,
            offset=offset
        )
        
        total = await dedup_store.count_events(topic=topic)
        
        return EventsResponse(
            events=events,
            total=total,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        logger.error(f"Error getting events: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats", response_model=Stats)
async def get_stats():
    try:
        stats = await dedup_store.get_stats()
        
        # Calculate uptime
        uptime_seconds = (datetime.utcnow() - start_time).total_seconds()
        
        # Get topics
        topics = await dedup_store.get_topics()
        
        return Stats(
            received=stats['received'],
            unique_processed=stats['unique_processed'],
            duplicate_dropped=stats['duplicate_dropped'],
            topics=topics,
            uptime_seconds=int(uptime_seconds),
            queue_size=event_queue.qsize() if event_queue else 0
        )
        
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    try:
        # Check database connection
        await dedup_store.health_check()
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": int((datetime.utcnow() - start_time).total_seconds())
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=Config.HOST,
        port=Config.PORT,
        log_level=Config.LOG_LEVEL.lower(),
        reload=False
    )
