import collections
import json

input_file = (
    r"C:\Users\maxim\.local\share\garak\garak_runs\baseline.report.jsonl"
)
output_file = "one_top_penetration_per_type.txt"

detectors = [
    "promptinject.AttackRogueString",
    "encoding.DecodeMatch",
    "encoding.DecodeApprox",
]
results_by_detector = collections.defaultdict(list)

print("Анализ лога...")
with open(input_file, "r", encoding="utf-8") as infile:
    for line in infile:
        try:
            data = json.loads(line)
            if data.get("entry_type") == "attempt" and data.get("status") == 2:
                for det in detectors:
                    score = data.get("detector_results", {}).get(det, [])
                    # ИСПРАВЛЕНО: берем первый элемент списка для сравнения с числом
                    if score and isinstance(score, list) and score[0] >= 0.5:
                        results_by_detector[det].append(
                            {
                                "score": score[0],  # Сохраняем сразу как число
                                "in": data["prompt"]["turns"][0]["content"][
                                    "text"
                                ],
                                "out": data["outputs"][0]["text"],
                            }
                        )
        except (json.JSONDecodeError, KeyError, IndexError):
            continue

TOP_N = 3
print({det: len(results_by_detector[det]) for det in detectors})
print("Запись по лучшим примерам каждого вида...")
with open(output_file, "w", encoding="utf-8") as outfile:
    for det in detectors:
        attempts = results_by_detector[det]

        if not attempts:
            continue

        # Сортировка по score
        attempts = sorted(
            attempts,
            key=lambda x: x["score"],
            reverse=True,
        )

        # Удаляем дубликаты по паре (INPUT, OUTPUT)
        unique_attempts = []
        seen = set()

        for attempt in attempts:
            key = (
                attempt["in"].strip(),
                attempt["out"].strip(),
            )

            if key in seen:
                continue

            seen.add(key)
            unique_attempts.append(attempt)

            if len(unique_attempts) == TOP_N:
                break

        outfile.write(f"=== ТИП: {det} ===\n\n")

        for i, attempt in enumerate(unique_attempts, 1):
            outfile.write(
                f"--- Пример {i} (Скор: {attempt['score']}) ---\n"
            )
            outfile.write(f"INPUT:\n{attempt['in']}\n\n")
            outfile.write(f"OUTPUT:\n{attempt['out']}\n")
            outfile.write("=" * 60 + "\n\n")
