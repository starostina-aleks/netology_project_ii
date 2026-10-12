import sqlite3
import os
# Получаем путь к текущему файлу, идем на уровень выше к корню проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "tools","knowledge_base.db")


def search_documents(query: str, department: str, doc_type: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Формируем SQL-запрос с фильтрами
    #sql = "SELECT title, content, department, doc_type FROM documents WHERE LOWER(title) LIKE LOWER(?)"
    #params = [f'%{query}%']
    words = query.split()

    # 2. Строим часть SQL-запроса с несколькими LIKE через OR
    # Получится что-то вроде: (title LIKE ? OR title LIKE ? OR ...)
    like_conditions = " OR ".join(["title LIKE ?" for _ in words])

    # Базовая часть запроса
    sql = f"SELECT title, content, department, doc_type FROM documents WHERE ({like_conditions})"

    # 3. Подготавливаем параметры: каждое слово оборачиваем в % %
    params = [f'%{word}%' for word in words]

    if department != 'any':
        sql += " AND LOWER(department) = LOWER(?)"
        params.append(department)

    if doc_type != 'any':
        sql += " AND LOWER(doc_type) = LOWER(?)"
        params.append(doc_type)

    cursor.execute(sql, params)
    results = cursor.fetchall()
    conn.close()

    return results


