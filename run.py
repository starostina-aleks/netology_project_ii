import sys
import asyncio

if __name__ == "__main__":
    # Переключаем цикл событий ДО старта Uvicorn
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    import uvicorn
    # Запускаем Uvicorn программно
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)