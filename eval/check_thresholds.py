import os
import sys
import glob
import json
import yaml


class EvaluationError(Exception):
    """Кастомное исключение для ошибок валидации и конфигурации."""
    pass


def get_latest_run() -> str:
    """Находит самый последний файл запуска в папке eval/runs/."""
    run_dir = os.path.join("eval", "runs")
    if not os.path.exists(run_dir):
        raise EvaluationError(f"Директория {run_dir} не найдена.")

    all_items = glob.glob(os.path.join(run_dir, "*"))
    files = [f for f in all_items if os.path.isfile(f)]

    if not files:
        raise EvaluationError(f"В директории {run_dir} нет файлов запусков.")

    return max(files, key=os.path.getmtime)


def load_yaml_config() -> dict:
    """Загружает пороги из eval/thresholds.yaml."""
    yaml_path = os.path.join("eval", "thresholds.yaml")

    if not os.path.exists(yaml_path):
        raise EvaluationError(f"Конфигурационный файл {yaml_path} не найден.")

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            thresholds = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise EvaluationError(f"Ошибка синтаксиса в YAML-файле: {e}")

    if not thresholds or not isinstance(thresholds, dict):
        raise EvaluationError(f"Файл {yaml_path} пуст или имеет неверный формат (ожидался словарь).")

    return thresholds


def main():
    try:
        # 1. Загрузка конфигурации и поиск файла
        thresholds = load_yaml_config()
        latest_run_path = get_latest_run()
        print(f"Проверяем результаты из: {latest_run_path}")

        # 2. Чтение JSON результатов
        with open(latest_run_path, "r", encoding="utf-8") as f:
            run_data = json.load(f)

    except EvaluationError as e:
        print(f"Ошибка конфигурации: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Ошибка чтения JSON-файла результатов: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Непредвиденная ошибка: {e}")
        sys.exit(1)

    # 3. Валидация порогов
    metrics = run_data.get("aggregates", run_data)
    failed = False

    for metric_name, threshold_value in thresholds.items():
        if metric_name not in metrics:
            print(f"Метрика '{metric_name}' отсутствует в файле результатов.")
            failed = True
            continue

        actual_value = metrics[metric_name]
        if actual_value < threshold_value:
            print(
                f"Метрика [{metric_name}]: "
                f"ожидалось >= {threshold_value}, получено {actual_value}"
            )
            failed = True
        else:
            print(f"Успешно: [{metric_name}] = {actual_value} (>= {threshold_value})")

    if failed:
        print("\nПроверка порогов не пройдена!")
        sys.exit(1)

    print("\nВсе пороги успешно пройдены!")
    sys.exit(0)


if __name__ == "__main__":
    main()
