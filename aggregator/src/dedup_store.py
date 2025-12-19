
import aiosqlite
import asyncio
import logging
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime

from .config import Config

logger = logging.getLogger(__name__)


class DedupStore:
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        logger.info(f"Dedup store initialized with db_path: {db_path}")
    
    async def initialize(self):
        self.db = await aiosqlite.connect(
            self.db_path,
            isolation_level=None  # Autocommit off, manual transaction control
        )
        
        # Set isolation level
        if Config.ISOLATION_LEVEL == "SERIALIZABLE":
            await self.db.execute("PRAGMA read_uncommitted = 0")
        
        # Enable WAL mode untuk better concurrency
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA synchronous=NORMAL")
        
        # Create processed_events table dengan unique constraint
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS processed_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                event_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                payload TEXT NOT NULL,
                processed_at TEXT NOT NULL,
                UNIQUE(topic, event_id)
            )
        """)
        
        # Create index untuk faster lookups
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_topic_event_id 
            ON processed_events(topic, event_id)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_topic 
            ON processed_events(topic)
        """)
        
        # Create stats table
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                received INTEGER NOT NULL DEFAULT 0,
                unique_processed INTEGER NOT NULL DEFAULT 0,
                duplicate_dropped INTEGER NOT NULL DEFAULT 0
            )
        """)
        
        # Initialize stats if not exists
        await self.db.execute("""
            INSERT OR IGNORE INTO stats (id, received, unique_processed, duplicate_dropped)
            VALUES (1, 0, 0, 0)
        """)
        
        await self.db.commit()
        
        logger.info("Database schema initialized")
    
    async def is_duplicate(self, topic: str, event_id: str) -> bool:
        async with self.db.execute(
            "SELECT 1 FROM processed_events WHERE topic = ? AND event_id = ? LIMIT 1",
            (topic, event_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None
    
    async def mark_processed(
        self,
        topic: str,
        event_id: str,
        timestamp: str,
        source: str,
        payload: str
    ) -> bool:
        processed_at = datetime.utcnow().isoformat()
        
        try:
            # BEGIN TRANSACTION
            await self.db.execute("BEGIN IMMEDIATE")
            
            # Idempotent INSERT with conflict resolution
            # INSERT OR IGNORE: jika constraint violation, ignore dan return
            cursor = await self.db.execute("""
                INSERT OR IGNORE INTO processed_events 
                (topic, event_id, timestamp, source, payload, processed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (topic, event_id, timestamp, source, payload, processed_at))
            
            # Check if actually inserted (rowcount > 0) or ignored (rowcount = 0)
            inserted = cursor.rowcount > 0
            
            # COMMIT TRANSACTION
            await self.db.commit()
            
            return inserted
            
        except Exception as e:
            # ROLLBACK on error
            await self.db.rollback()
            logger.error(f"Error marking event as processed: {e}", exc_info=True)
            return False
    
    async def increment_received(self, count: int = 1):
        async with self._lock:
            try:
                await self.db.execute(
                    "UPDATE stats SET received = received + ? WHERE id = 1",
                    (count,)
                )
                await self.db.commit()
            except Exception as e:
                await self.db.rollback()
                logger.error(f"Error incrementing received: {e}")
    
    async def increment_unique_processed(self):
        async with self._lock:
            try:
                await self.db.execute(
                    "UPDATE stats SET unique_processed = unique_processed + 1 WHERE id = 1"
                )
                await self.db.commit()
            except Exception as e:
                await self.db.rollback()
                logger.error(f"Error incrementing unique_processed: {e}")
    
    async def increment_duplicate_dropped(self):
        async with self._lock:
            try:
                await self.db.execute(
                    "UPDATE stats SET duplicate_dropped = duplicate_dropped + 1 WHERE id = 1"
                )
                await self.db.commit()
            except Exception as e:
                await self.db.rollback()
                logger.error(f"Error incrementing duplicate_dropped: {e}")
    
    async def get_stats(self) -> Dict[str, int]:
        async with self.db.execute(
            "SELECT received, unique_processed, duplicate_dropped FROM stats WHERE id = 1"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    'received': row[0],
                    'unique_processed': row[1],
                    'duplicate_dropped': row[2]
                }
            return {'received': 0, 'unique_processed': 0, 'duplicate_dropped': 0}
    
    async def get_events(
        self,
        topic: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        if topic:
            query = """
                SELECT id, topic, event_id, timestamp, source, payload, processed_at
                FROM processed_events
                WHERE topic = ?
                ORDER BY processed_at DESC
                LIMIT ? OFFSET ?
            """
            params = (topic, limit, offset)
        else:
            query = """
                SELECT id, topic, event_id, timestamp, source, payload, processed_at
                FROM processed_events
                ORDER BY processed_at DESC
                LIMIT ? OFFSET ?
            """
            params = (limit, offset)
        
        events = []
        async with self.db.execute(query, params) as cursor:
            async for row in cursor:
                events.append({
                    'id': row[0],
                    'topic': row[1],
                    'event_id': row[2],
                    'timestamp': row[3],
                    'source': row[4],
                    'payload': json.loads(row[5]),
                    'processed_at': row[6]
                })
        
        return events
    
    async def count_events(self, topic: Optional[str] = None) -> int:
        if topic:
            query = "SELECT COUNT(*) FROM processed_events WHERE topic = ?"
            params = (topic,)
        else:
            query = "SELECT COUNT(*) FROM processed_events"
            params = ()
        
        async with self.db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    
    async def get_topics(self) -> List[str]:
        topics = []
        async with self.db.execute(
            "SELECT DISTINCT topic FROM processed_events ORDER BY topic"
        ) as cursor:
            async for row in cursor:
                topics.append(row[0])
        return topics
    
    async def health_check(self) -> bool:
        try:
            async with self.db.execute("SELECT 1") as cursor:
                await cursor.fetchone()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise
    
    async def close(self):
        if self.db:
            await self.db.close()
            logger.info("Database connection closed")
