"""Load and validate business datasets from Neon PostgreSQL database."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

import pandas as pd
import psycopg2
from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor

from app.data_access.schema import DATASETS, RELATIONSHIPS

LOGGER = logging.getLogger(__name__)


class DatabaseConnectionError(Exception):
    """Raised when database connection or query fails."""


class PostgresDataStore:
    """Load business datasets from Neon PostgreSQL and expose read-only views."""

    def __init__(
        self,
        database_url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
    ) -> None:
        """Initialize connection pool to Neon PostgreSQL database."""
        if not database_url:
            raise ValueError("database_url cannot be empty")
        
        self._database_url = database_url
        try:
            # Create connection pool for better performance
            self._connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=pool_size + max_overflow,
                dsn=database_url,
            )
            LOGGER.info(
                "PostgreSQL connection pool created: min=1, max=%d",
                pool_size + max_overflow,
            )
            # Test connection and validate schema
            self._validate_schema()
        except (psycopg2.Error, Exception) as exc:
            raise DatabaseConnectionError(
                f"Failed to connect to Neon PostgreSQL: {exc}"
            ) from exc

    @contextmanager
    def _get_connection(self) -> Iterator[psycopg2.extensions.connection]:
        """Get a connection from the pool and ensure it's returned."""
        connection = None
        try:
            connection = self._connection_pool.getconn()
            yield connection
        except psycopg2.Error as exc:
            if connection:
                connection.rollback()
            raise DatabaseConnectionError(f"Database error: {exc}") from exc
        finally:
            if connection:
                self._connection_pool.putconn(connection)

    def _validate_schema(self) -> None:
        """Verify that all required tables exist in the database."""
        required_tables = set(DATASETS.keys())
        
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
                existing_tables = {row[0] for row in cursor.fetchall()}
        
        missing_tables = required_tables - existing_tables
        if missing_tables:
            raise DatabaseConnectionError(
                f"Missing required tables in database: {sorted(missing_tables)}. "
                "Run the schema migration script first."
            )
        
        LOGGER.info("Database schema validation passed: all tables exist")

    def _validate_relationships(self) -> None:
        """Verify foreign key relationships are valid (optional check)."""
        # This could be expanded to check referential integrity
        # For now, we rely on PostgreSQL foreign key constraints
        pass

    @property
    def dataset_names(self) -> tuple[str, ...]:
        """Return the approved dataset names."""
        return tuple(DATASETS.keys())

    def get_frame(self, dataset_name: str) -> pd.DataFrame:
        """Return a DataFrame for an allowlisted dataset from PostgreSQL."""
        if dataset_name not in DATASETS:
            raise ValueError(f"Unknown dataset '{dataset_name}'.")
        
        schema = DATASETS[dataset_name]
        
        # Build column list for SELECT statement
        columns = list(schema.fields.keys())
        column_list = ", ".join(columns)
        
        query = f"SELECT {column_list} FROM {dataset_name}"
        
        try:
            with self._get_connection() as conn:
                # Use pandas read_sql for efficient DataFrame creation
                df = pd.read_sql(query, conn)
                
                # Convert date columns to datetime (same as JsonDataStore behavior)
                if dataset_name == "orders" and "order_date" in df.columns:
                    df["order_date"] = pd.to_datetime(
                        df["order_date"], format="%Y-%m-%d"
                    )
                
                LOGGER.debug(
                    "Loaded dataset '%s' with %d rows from PostgreSQL",
                    dataset_name,
                    len(df),
                )
                
                return df
                
        except (psycopg2.Error, Exception) as exc:
            raise DatabaseConnectionError(
                f"Failed to load dataset '{dataset_name}': {exc}"
            ) from exc

    def close(self) -> None:
        """Close all connections in the pool."""
        if hasattr(self, "_connection_pool") and self._connection_pool:
            self._connection_pool.closeall()
            LOGGER.info("PostgreSQL connection pool closed")

    def __del__(self) -> None:
        """Ensure connections are closed when object is destroyed."""
        try:
            self.close()
        except Exception:
            pass  # Suppress errors during cleanup
