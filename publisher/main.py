## Event Publisher - Generator event dengan duplikasi

##Fitur:
# - Generate events dengan proporsi duplikasi yang configurable
# - Send events ke aggregator via HTTP
# - Support batch publishing
# - Configurable throughput

import asyncio
import httpx
import logging
import random
import uuid
from datetime import datetime
from typing import List, Dict, Any
import os
import time

# Configuration
TARGET_URL = os.getenv("TARGET_URL", "http://aggregator:8080/publish")
NUM_EVENTS = int(os.getenv("NUM_EVENTS", "20000"))
DUPLICATE_RATE = float(os.getenv("DUPLICATE_RATE", "0.30"))  # 30% duplikasi
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
DELAY_BETWEEN_BATCHES = float(os.getenv("DELAY_BETWEEN_BATCHES", "0.1"))
TOPICS = os.getenv("TOPICS", "logs,metrics,events,alerts").split(",")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class EventPublisher:
    def __init__(self, target_url: str):
        self.target_url = target_url
        self.event_cache: List[Dict[str, Any]] = []
        self.stats = {
            'sent': 0,
            'duplicates': 0,
            'errors': 0,
            'batches': 0
        }
    
    def generate_event(self, force_duplicate: bool = False) -> Dict[str, Any]:
        if force_duplicate and self.event_cache:
            # Ambil random event dari cache untuk duplikasi
            base_event = random.choice(self.event_cache)
            logger.debug(f"Generating DUPLICATE event: {base_event['event_id']}")
            return base_event.copy()
        
        # Generate new unique event
        topic = random.choice(TOPICS)
        event_id = str(uuid.uuid4())
        
        event = {
            "topic": topic,
            "event_id": event_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": f"publisher-{os.getpid()}",
            "payload": {
                "message": f"Event from publisher at {datetime.utcnow().isoformat()}",
                "level": random.choice(["INFO", "WARNING", "ERROR", "DEBUG"]),
                "metadata": {
                    "host": f"host-{random.randint(1, 10)}",
                    "service": f"service-{random.randint(1, 5)}",
                    "request_id": str(uuid.uuid4())
                }
            }
        }
        
        # Add to cache untuk duplikasi nanti
        self.event_cache.append(event)
        
        # Keep cache size reasonable
        if len(self.event_cache) > 1000:
            self.event_cache.pop(0)
        
        return event
    
    def generate_batch(self, size: int) -> List[Dict[str, Any]]:
        events = []
        
        for _ in range(size):
            # Decide if this should be duplicate
            is_duplicate = random.random() < DUPLICATE_RATE and len(self.event_cache) > 0
            
            event = self.generate_event(force_duplicate=is_duplicate)
            events.append(event)
            
            if is_duplicate:
                self.stats['duplicates'] += 1
        
        return events
    
    async def send_batch(self, events: List[Dict[str, Any]]) -> bool:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.target_url,
                    json={"events": events}
                )
                
                if response.status_code == 200:
                    self.stats['sent'] += len(events)
                    self.stats['batches'] += 1
                    logger.info(
                        f"Batch sent successfully: {len(events)} events, "
                        f"status={response.status_code}"
                    )
                    return True
                else:
                    logger.error(
                        f"Failed to send batch: status={response.status_code}, "
                        f"response={response.text}"
                    )
                    self.stats['errors'] += len(events)
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending batch: {e}", exc_info=True)
            self.stats['errors'] += len(events)
            return False
    
    async def run(self, total_events: int, batch_size: int):
        logger.info(f"Starting publisher...")
        logger.info(f"Target URL: {self.target_url}")
        logger.info(f"Total events: {total_events}")
        logger.info(f"Batch size: {batch_size}")
        logger.info(f"Duplicate rate: {DUPLICATE_RATE * 100}%")
        logger.info(f"Topics: {TOPICS}")
        
        start_time = time.time()
        
        num_batches = (total_events + batch_size - 1) // batch_size
        
        for i in range(num_batches):
            # Calculate batch size for last batch
            current_batch_size = min(batch_size, total_events - i * batch_size)
            
            # Generate and send batch
            events = self.generate_batch(current_batch_size)
            await self.send_batch(events)
            
            # Delay between batches untuk avoid overwhelming aggregator
            if i < num_batches - 1:
                await asyncio.sleep(DELAY_BETWEEN_BATCHES)
            
            # Log progress
            if (i + 1) % 10 == 0:
                logger.info(
                    f"Progress: {i + 1}/{num_batches} batches, "
                    f"{self.stats['sent']} events sent, "
                    f"{self.stats['duplicates']} duplicates generated"
                )
        
        elapsed = time.time() - start_time
        
        # Final stats
        logger.info("\n" + "="*60)
        logger.info("PUBLISHER STATISTICS")
        logger.info("="*60)
        logger.info(f"Total events sent: {self.stats['sent']}")
        logger.info(f"Duplicates generated: {self.stats['duplicates']}")
        logger.info(f"Duplicate rate: {(self.stats['duplicates'] / self.stats['sent'] * 100):.2f}%")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"Batches: {self.stats['batches']}")
        logger.info(f"Elapsed time: {elapsed:.2f}s")
        logger.info(f"Throughput: {self.stats['sent'] / elapsed:.2f} events/sec")
        logger.info("="*60 + "\n")


async def main():
    """Main function."""
    logger.info("Event Publisher starting...")
    
    # Wait for aggregator to be ready
    logger.info("Waiting for aggregator to be ready...")
    await asyncio.sleep(5)
    
    publisher = EventPublisher(TARGET_URL)
    await publisher.run(NUM_EVENTS, BATCH_SIZE)
    
    logger.info("Publisher finished")


if __name__ == "__main__":
    asyncio.run(main())
