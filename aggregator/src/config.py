"""
Configuration management untuk Pub-Sub Log Aggregator
"""

import os
import logging


class Config:
    """
    Configuration dengan environment variables.
    
    Semua konfigurasi dapat di-override via environment variables.
    """
    
    # Server configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8080"))
    
    # Database configuration
    DB_PATH: str = os.getenv("DB_PATH", "/var/lib/aggregator/dedup.db")
    
    # Isolation level: READ_COMMITTED, SERIALIZABLE
    # READ_COMMITTED: lebih cepat, tapi bisa phantom reads
    # SERIALIZABLE: paling strict, tapi lebih lambat
    # Kita pilih READ_COMMITTED karena sudah cukup dengan unique constraints
    ISOLATION_LEVEL: str = os.getenv("ISOLATION_LEVEL", "READ_COMMITTED")
    
    # Queue configuration
    QUEUE_MAX_SIZE: int = int(os.getenv("QUEUE_MAX_SIZE", "10000"))
    QUEUE_PUT_TIMEOUT: float = float(os.getenv("QUEUE_PUT_TIMEOUT", "1.0"))
    
    # Logging configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Worker configuration (untuk concurrent processing)
    NUM_WORKERS: int = int(os.getenv("NUM_WORKERS", "3"))
    
    @classmethod
    def get_log_level(cls) -> int:
        """Convert log level string to logging level."""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        return level_map.get(cls.LOG_LEVEL.upper(), logging.INFO)
    
    @classmethod
    def print_config(cls):
        """Print configuration untuk debugging."""
        print("\n" + "="*60)
        print("PUB-SUB LOG AGGREGATOR - CONFIGURATION")
        print("="*60)
        print(f"Host: {cls.HOST}:{cls.PORT}")
        print(f"Database: {cls.DB_PATH}")
        print(f"Isolation Level: {cls.ISOLATION_LEVEL}")
        print(f"Queue Max Size: {cls.QUEUE_MAX_SIZE}")
        print(f"Log Level: {cls.LOG_LEVEL}")
        print(f"Workers: {cls.NUM_WORKERS}")
        print("="*60 + "\n")
