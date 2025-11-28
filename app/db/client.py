import httpx
from app.config import get_settings

settings = get_settings()

SUPABASE_API = f"{settings.supabase_url}/rest/v1"

TIMEOUT_CONFIG = httpx.Timeout(
    connect=10.0,
    read=15.0,
    write=10.0,
    pool=15.0
)


def get_supabase_headers() -> dict[str, str]:
    return {
        "apikey": settings.supabase_key,
        "Authorization": f"Bearer {settings.supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


class SupabaseClient:
    def __init__(self):
        self.api_url = SUPABASE_API
        self.headers = get_supabase_headers()
        self.timeout = TIMEOUT_CONFIG

    async def get(
        self,
        table: str,
        params: dict[str, str] | None = None
    ) -> list[dict]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.api_url}/{table}",
                params=params or {},
                headers=self.headers
            )
            resp.raise_for_status()
            return resp.json()

    async def get_one(
        self,
        table: str,
        params: dict[str, str]
    ) -> dict | None:
        result = await self.get(table, params)
        return result[0] if result else None

    async def insert(
        self,
        table: str,
        data: dict | list[dict]
    ) -> list[dict]:
        payload = data if isinstance(data, list) else [data]
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.api_url}/{table}",
                headers=self.headers,
                json=payload
            )
            resp.raise_for_status()
            return resp.json()

    async def update(
        self,
        table: str,
        params: dict[str, str],
        data: dict
    ) -> list[dict]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.patch(
                f"{self.api_url}/{table}",
                params=params,
                headers=self.headers,
                json=data
            )
            resp.raise_for_status()
            return resp.json()

    async def delete(
        self,
        table: str,
        params: dict[str, str]
    ) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.delete(
                f"{self.api_url}/{table}",
                params=params,
                headers=self.headers
            )
            resp.raise_for_status()


supabase_client = SupabaseClient()

