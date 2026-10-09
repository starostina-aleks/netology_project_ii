import json
import os
from typing import Dict, List, Set
import logging

logger = logging.getLogger(__name__)

class SynonymService:
    def __init__(self, file_path: str = "var/synonyms.json"):
        """
        Инициализация сервиса работы со словарем синонимов.
        """
        self.file_path = file_path
        # Создаем логгер с именем текущего класса
        self._ensure_storage_exists()

    def _ensure_storage_exists(self) -> None:
        """Внутренний метод: создает пустой файл словаря, если он отсутствует."""
        if not os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
                logger.info(f"Создан новый пустой файл словаря: {self.file_path}")
            except IOError as e:
                logger.error(f"Не удалось создать файл хранилища {self.file_path}: {str(e)}")
                raise

    def load_dictionary(self) -> Dict[str, List[str]]:
        """
        Читает и возвращает текущее состояние словаря из JSON.
        """
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            # Логируем критическую ошибку структуры JSON (файл поврежден)
            logger.error(f"Ошибка парсинга JSON в файле {self.file_path}. Структура нарушена: {str(e)}")
            return {}
        except IOError as e:
            # Логируем ошибку доступа к файлу (например, заблокирован процессом)
            logger.error(f"Ошибка ввода-вывода при чтении файла {self.file_path}: {str(e)}")
            return {}

    def add_synonym(self, abbreviation: str, synonyms: List[str]) -> str:
        """
        Добавляет новые термины в строго однонаправленную структуру словаря.
        """
        if not abbreviation or not synonyms:
            logger.warning("Попытка добавить пустое правило или пустой список терминов.")
            return "Ошибка: Входные данные не могут быть пустыми."

        dictionary = self.load_dictionary()
        key = abbreviation.strip().lower()

        if key not in dictionary:
            dictionary[key] = []

        added_count = 0
        for term in synonyms:
            term_clean = term.strip()
            if term_clean not in dictionary[key]:
                dictionary[key].append(term_clean)
                added_count += 1

        if added_count > 0:
            try:
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump(dictionary, f, ensure_ascii=False, indent=2)
                # Логируем успешное административное действие (Audit Trail)
                logger.info(f"Словарь успешно обновлен. Для ключа '{key}' добавлено терминов: {added_count}")
            except IOError as e:
                logger.error(f"Не удалось сохранить обновленный словарь в {self.file_path}: {str(e)}")
                return "Ошибка при сохранении данных в файл."
        else:
            logger.info(f"Попытка добавления дубликатов для ключа '{key}'. Файл не перезаписывался.")
            return f"Попытка добавления дубликатов для ключа '{key}'. Файл не перезаписывался."

        return f"Успешно. Для аббревиатуры '{key}' добавлено {added_count} официальных терминов."

    def expand_query(self, user_query: str) -> str:
        """
        Выполняет умное двунаправленное расширение поискового запроса.
        """
        dictionary = self.load_dictionary()
        if not dictionary:
            return user_query

        lowered_query = user_query.lower()
        found_extensions: List[str] = []

        all_values: Set[str] = set()
        for values in dictionary.values():
            all_values.update(values)
        sorted_values = sorted(list(all_values), key=len, reverse=True)
        sorted_keys = sorted(dictionary.keys(), key=len, reverse=True)

        # --- ЧАСТЬ A: ОБРАТНЫЙ ПОИСК ---
        query_for_keys_check = lowered_query
        for val in sorted_values:
            val_lower = val.lower()
            if f" {val_lower} " in f" {query_for_keys_check} ":
                for key, values in dictionary.items():
                    if val in values:
                        found_extensions.append(key.upper())
                query_for_keys_check = query_for_keys_check.replace(val_lower, " ")

        # --- ЧАСТЬ B: ПРЯМОЙ ПОИСК ---
        query_for_values_check = lowered_query
        for key in sorted_keys:
            if f" {key} " in f" {query_for_values_check} ":
                found_extensions.extend(dictionary[key])
                query_for_values_check = query_for_values_check.replace(key, " ")

        if found_extensions:
            unique_extensions: List[str] = []
            for ext in found_extensions:
                if ext.lower() not in lowered_query and ext not in unique_extensions:
                    unique_extensions.append(ext)

            if unique_extensions:
                extended_result = f"{user_query} {' '.join(unique_extensions)}"
                # Логируем факт расширения (полезно для отладки качества RAG)
                logger.debug(f"Запрос '{user_query}' успешно расширен синонимами: {unique_extensions}")
                return extended_result

        return user_query

