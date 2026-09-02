from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# 1. Задаем конфигурацию для русского языка
configuration = {
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "ru", "model_name": "ru_core_news_md"}],
}

# 2. Правильный способ создания движка через NlpEngineProvider
# Мы передаем словарь в аргумент nlp_configuration
provider = NlpEngineProvider(nlp_configuration=configuration)
nlp_engine = provider.create_engine()

# 3. Передаем созданный движок в анализатор и разрешаем русский язык
analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["ru"])
anonymizer = AnonymizerEngine()

# === ДОБАВЛЯЕМ КАРТЫ СЮДА ===
# Создаем паттерн для поиска 16 цифр карты (через пробелы или дефисы)
card_pattern = Pattern(
    name="card_pattern",
    regex=r"\b(?:\d{4}[\s\-]?){3}\d{4}\b",
    score=0.85
)

# Создаем распознаватель для сущности "BANK_CARD" на русском языке
card_recognizer = PatternRecognizer(
    supported_entity="BANK_CARD",
    supported_language="ru",
    patterns=[card_pattern]
)

# Регистрируем его в общем движке анализатора
analyzer.registry.add_recognizer(card_recognizer)
# ============================

# 2. Функция маскирования с кастомными плейсхолдерами
def redact_pii_presidio(text: str, language="ru") -> str:

    analyzer_results = analyzer.analyze(text=text, language=language,
                                        entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "BANK_CARD", "BANK_CARD","LOCATION","IP_ADDRESS"],)



    anonymized_result = anonymizer.anonymize(
        text=text,
        analyzer_results=analyzer_results,
        operators={"DEFAULT": OperatorConfig("replace", {"new_value": "[PII]"})},
    )

    return anonymized_result.text
