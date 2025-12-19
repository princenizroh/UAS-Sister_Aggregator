"""
Data models untuk Pub-Sub Log Aggregator
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
import uuid


class Event(BaseModel):
    """
    Event model sesuai spesifikasi UAS.
    
    Fields:
        topic: Nama topic/kategori event
        event_id: ID unik untuk deduplication (collision-resistant)
        timestamp: Timestamp ISO8601
        source: Sumber event
        payload: Data payload (dict)
    """
    topic: str = Field(..., description="Topic/kategori event")
    event_id: str = Field(..., description="ID unik untuk deduplication")
    timestamp: str = Field(..., description="Timestamp ISO8601")
    source: str = Field(..., description="Sumber event")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event payload")
    
    @field_validator('event_id')
    @classmethod
    def validate_event_id(cls, v):
        """Validasi event_id tidak boleh kosong."""
        if not v or len(v.strip()) == 0:
            raise ValueError("event_id tidak boleh kosong")
        return v.strip()
    
    @field_validator('topic')
    @classmethod
    def validate_topic(cls, v):
        """Validasi topic tidak boleh kosong."""
        if not v or len(v.strip()) == 0:
            raise ValueError("topic tidak boleh kosong")
        return v.strip()
    
    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v):
        """Validasi timestamp format ISO8601."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except Exception:
            raise ValueError("timestamp harus format ISO8601")
        return v
    
    @field_validator('source')
    @classmethod
    def validate_source(cls, v):
        """Validasi source tidak boleh kosong."""
        if not v or len(v.strip()) == 0:
            raise ValueError("source tidak boleh kosong")
        return v.strip()


class PublishRequest(BaseModel):
    """
    Request untuk publish events.
    
    Supports single event atau batch events.
    """
    events: Union[Event, List[Event]] = Field(..., description="Single event atau list of events")
    
    @field_validator('events')
    @classmethod
    def validate_events(cls, v):
        """Ensure events is always a list internally."""
        if isinstance(v, Event):
            return [v]
        if isinstance(v, list) and len(v) == 0:
            raise ValueError("events list tidak boleh kosong")
        return v


class PublishResponse(BaseModel):
    """Response dari publish endpoint."""
    status: str = Field(..., description="Status: accepted/rejected")
    received: int = Field(..., description="Jumlah events yang diterima")
    queued: int = Field(..., description="Jumlah events yang masuk queue")
    message: str = Field(..., description="Detail message")


class ProcessedEvent(BaseModel):
    """
    Processed event dari database.
    """
    id: int
    topic: str
    event_id: str
    timestamp: str
    source: str
    payload: Dict[str, Any]
    processed_at: str


class EventsResponse(BaseModel):
    """Response dari GET /events."""
    events: List[ProcessedEvent] = Field(..., description="List of processed events")
    total: int = Field(..., description="Total events (untuk pagination)")
    limit: int = Field(..., description="Limit yang digunakan")
    offset: int = Field(..., description="Offset yang digunakan")


class Stats(BaseModel):
    """
    Statistics dari aggregator.
    
    Fields:
        received: Total events yang diterima
        unique_processed: Total unique events yang diproses
        duplicate_dropped: Total duplicate events yang di-drop
        topics: List of topics yang ada
        uptime_seconds: Uptime dalam detik
        queue_size: Current queue size
    """
    received: int = Field(..., description="Total events received")
    unique_processed: int = Field(..., description="Total unique events processed")
    duplicate_dropped: int = Field(..., description="Total duplicate events dropped")
    topics: List[str] = Field(..., description="List of topics")
    uptime_seconds: int = Field(..., description="Uptime in seconds")
    queue_size: int = Field(default=0, description="Current queue size")
    
    @property
    def duplicate_rate(self) -> float:
        """Calculate duplicate rate."""
        if self.received == 0:
            return 0.0
        return (self.duplicate_dropped / self.received) * 100
    
    @property
    def processing_rate(self) -> float:
        """Calculate processing rate."""
        if self.received == 0:
            return 0.0
        return (self.unique_processed / self.received) * 100
