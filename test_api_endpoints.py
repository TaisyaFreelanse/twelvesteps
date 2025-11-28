"""Script to test API endpoints"""
import asyncio
import aiohttp
import json
from datetime import datetime

API_BASE = "http://localhost:8000"

async def test_endpoint(method: str, url: str, data: dict = None, headers: dict = None):
    """Test an API endpoint"""
    async with aiohttp.ClientSession() as session:
        try:
            if method == "GET":
                async with session.get(url, headers=headers) as response:
                    status = response.status
                    text = await response.text()
                    return status, text
            elif method == "POST":
                async with session.post(url, json=data, headers=headers) as response:
                    status = response.status
                    text = await response.text()
                    return status, text
            elif method == "PUT":
                async with session.put(url, json=data, headers=headers) as response:
                    status = response.status
                    text = await response.text()
                    return status, text
        except Exception as e:
            return None, str(e)

async def main():
    print("=" * 60)
    print("Тестирование API эндпоинтов")
    print("=" * 60)
    
    # Test 1: Health check or root
    print("\n1. Проверка доступности API...")
    status, text = await test_endpoint("GET", f"{API_BASE}/docs")
    if status == 200:
        print("✅ API доступен")
    else:
        print(f"❌ API недоступен: {status}")
        return
    
    # Test 2: Check if we can get API info
    print("\n2. Проверка документации API...")
    status, text = await test_endpoint("GET", f"{API_BASE}/openapi.json")
    if status == 200:
        print("✅ Документация API доступна")
        try:
            openapi = json.loads(text)
            paths = list(openapi.get("paths", {}).keys())
            print(f"   Найдено эндпоинтов: {len(paths)}")
            print(f"   Примеры: {', '.join(paths[:5])}")
        except:
            pass
    else:
        print(f"⚠️  Документация недоступна: {status}")
    
    # Test 3: List all endpoints from OpenAPI
    print("\n3. Список доступных эндпоинтов:")
    status, text = await test_endpoint("GET", f"{API_BASE}/openapi.json")
    if status == 200:
        try:
            openapi = json.loads(text)
            paths = openapi.get("paths", {})
            for path, methods in sorted(paths.items()):
                method_list = ", ".join(methods.keys())
                print(f"   {method_list.upper():6} {path}")
        except Exception as e:
            print(f"   Ошибка парсинга: {e}")
    
    print("\n" + "=" * 60)
    print("Для полного тестирования:")
    print("1. Откройте http://localhost:8000/docs в браузере")
    print("2. Протестируйте эндпоинты через Swagger UI")
    print("3. Используйте TESTING_CHECKLIST.md для детального тестирования")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())

