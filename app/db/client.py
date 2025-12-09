import httpx
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()

SUPABASE_API = f"{settings.supabase_url}/rest/v1"

TIMEOUT_CONFIG = httpx.Timeout(
    connect=10.0,
    read=15.0,
    write=10.0,
    pool=15.0
)

LIMITS_CONFIG = httpx.Limits(
    max_keepalive_connections=20,
    max_connections=100,
    keepalive_expiry=30.0
)


def get_supabase_headers() -> dict[str, str]:
    return {
        "apikey": settings.supabase_key,
        "Authorization": f"Bearer {settings.supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


class SupabaseClient:
    """
    Клиент для работы с Supabase REST API.
    Использует глобальный пул HTTP-соединений для эффективности.
    """
    
    def __init__(self) -> None:
        self.api_url = SUPABASE_API
        self.headers = get_supabase_headers()
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получить или создать HTTP клиент."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=TIMEOUT_CONFIG,
                limits=LIMITS_CONFIG,
                http2=True
            )
            logger.debug("Created new HTTP client for Supabase")
        return self._client
    
    async def close(self) -> None:
        """Закрыть HTTP клиент."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.info("Supabase HTTP client closed")

    async def get(
        self,
        table: str,
        params: dict[str, str] | None = None
    ) -> list[dict]:
        """
        Получить записи из таблицы.
        
        Args:
            table: Имя таблицы
            params: Параметры запроса (фильтры, сортировка, лимит)
        
        Returns:
            Список записей
        """
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{self.api_url}/{table}",
                params=params or {},
                headers=self.headers
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Supabase GET error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Supabase request error: {e}")
            raise

    async def get_with_count(
        self,
        table: str,
        params: dict[str, str] | None = None
    ) -> tuple[list[dict], int]:
        """
        Получить записи с общим количеством (для пагинации).
        
        Returns:
            Кортеж (записи, общее количество)
        """
        client = await self._get_client()
        headers = {**self.headers, "Prefer": "count=exact"}
        
        try:
            resp = await client.get(
                f"{self.api_url}/{table}",
                params=params or {},
                headers=headers
            )
            resp.raise_for_status()
            
            content_range = resp.headers.get("content-range", "")
            total = 0
            if "/" in content_range:
                try:
                    total = int(content_range.split("/")[1])
                except (ValueError, IndexError):
                    total = len(resp.json())
            
            return resp.json(), total
        except httpx.HTTPStatusError as e:
            logger.error(f"Supabase GET error: {e.response.status_code} - {e.response.text}")
            raise

    async def get_one(
        self,
        table: str,
        params: dict[str, str]
    ) -> dict | None:
        """Получить одну запись или None."""
        result = await self.get(table, params)
        return result[0] if result else None

    async def insert(
        self,
        table: str,
        data: dict | list[dict]
    ) -> list[dict]:
        """
        Вставить записи в таблицу.
        
        Args:
            table: Имя таблицы
            data: Данные для вставки (словарь или список словарей)
        
        Returns:
            Вставленные записи
        """
        payload = data if isinstance(data, list) else [data]
        client = await self._get_client()
        
        try:
            resp = await client.post(
                f"{self.api_url}/{table}",
                headers=self.headers,
                json=payload
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Supabase INSERT error: {e.response.status_code} - {e.response.text}")
            raise

    async def update(
        self,
        table: str,
        params: dict[str, str],
        data: dict
    ) -> list[dict]:
        """
        Обновить записи в таблице.
        
        Args:
            table: Имя таблицы
            params: Фильтры для выбора записей
            data: Новые данные
        
        Returns:
            Обновлённые записи
        """
        client = await self._get_client()
        
        try:
            resp = await client.patch(
                f"{self.api_url}/{table}",
                params=params,
                headers=self.headers,
                json=data
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Supabase UPDATE error: {e.response.status_code} - {e.response.text}")
            raise

    async def delete(
        self,
        table: str,
        params: dict[str, str]
    ) -> None:
        """
        Удалить записи из таблицы.
        
        Args:
            table: Имя таблицы
            params: Фильтры для выбора записей
        """
        client = await self._get_client()
        
        try:
            resp = await client.delete(
                f"{self.api_url}/{table}",
                params=params,
                headers=self.headers
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Supabase DELETE error: {e.response.status_code} - {e.response.text}")
            raise


supabase_client = SupabaseClient()


@asynccontextmanager
async def get_supabase() -> AsyncGenerator[SupabaseClient, None]:
    """Context manager для получения клиента (для тестирования)."""
    yield supabase_client
