import sqlite3


def init_db():
    conn = sqlite3.connect('knowledge_base.db')
    cursor = conn.cursor()

    # Создаем таблицу согласно вашей схеме
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            department TEXT,
            doc_type TEXT
        )
    ''')

    # Добавляем тестовые данные
    sample_data = [
        ('Правила оформления отпуска', 'Текст регламента......', 'hr', 'policy'),
        ('Настройка VPN', 'Инструкция по ИТ......', 'it', 'instruction'),
        ('Годовой отчет 2023', 'Данные за год......', 'finance', 'report'),
        ('Политика конфиденциальности', 'Информация о конфиденциальности...', 'legal', 'policy'),
        ('Руководство пользователя', 'Полное руководство....', 'support', 'documentation'),
        ('Анализ рынка', 'Аналитический отчет о рынке...', 'marketing', 'report'),
        ('Оценка производительности', 'Результаты оценок...', 'hr', 'evaluation'),
        ('Руководство по кадровым вопросам', 'Инструкция по работе с кадрами...', 'hr', 'manual'),
        ('Гид по оплате труда', 'Важно для личного состава...', 'finance', 'guide'),
        ('Обновление программного обеспечения', 'Инструкция по обновлению...', 'it', 'instruction'),
        ('Отчет о расходах', 'Таблица затрат....', 'finance', 'report'),
        ('Рекомендации по безопасности', 'Требования безопасности...', 'it', 'policy'),
        ('Календарь отпусков', 'График отпусков на 2023 год....', 'hr', 'calendar'),
        ('Обучение сотрудников', 'План обучения на год....', 'training', 'training'),
        ('Политика по работе из дома', 'Правила работы из дома...', 'hr', 'policy'),
        ('Порядок оформления командировок', 'Инструкция по командировкам...', 'hr', 'instruction'),
        ('План маркетинга', 'Стратегия маркетинга на год...', 'marketing', 'plan'),
        ('Стандарты обслуживания клиентов', 'Критерии обслуживания...', 'support', 'standards'),
        ('Отчет по проекту', 'Отчет по текущему проекту...', 'project', 'report'),
        ('Регламент работы с клиентами', 'Процедуры работы с клиентами...', 'support', 'policy'),
    ]

    cursor.executemany('INSERT INTO documents (title, content, department, doc_type) VALUES (?,?,?,?)', sample_data)
    conn.commit()
    conn.close()


init_db()