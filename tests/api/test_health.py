from httpx import AsyncClient


class TestHealth:
    async def test_health_returns_200(self, test_client: AsyncClient):
        response = await test_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "service": "order-service"}
