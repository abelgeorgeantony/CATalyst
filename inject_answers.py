import json
import re
import argparse
import sys

def parse_answer_key(filepath):
    """Parses the flat text file into a dictionary of {question_number: 'A/B/C/D'}"""
    answer_dict = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            # Read all lines, remove whitespace, and drop empty lines
            tokens = [line.strip() for line in f.readlines() if line.strip()]
    except FileNotFoundError:
        print(f"Error: The answer key file '{filepath}' was not found.")
        sys.exit(1)

    # Scan through the tokens to find pairs of [Number] followed by [A, B, C, or D]
    for i in range(len(tokens) - 1):
        current_token = tokens[i]
        next_token = tokens[i+1]
        
        if current_token.isdigit() and re.match(r'^[A-D]$', next_token.upper()):
            q_num = int(current_token)
            correct_option = next_token.upper()
            answer_dict[q_num] = correct_option

    return answer_dict

def inject_answers_into_json(json_filepath, answer_filepath):
    # 1. Generate the answer mapping from the text file
    answers = parse_answer_key(answer_filepath)
    print(f"Extracted {len(answers)} answers from the answer key text file.")

    # 2. Load the existing JSON database
    try:
        with open(json_filepath, 'r', encoding='utf-8') as f:
            database = json.load(f)
    except FileNotFoundError:
        print(f"Error: The JSON file '{json_filepath}' was not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: '{json_filepath}' is not a valid JSON file.")
        sys.exit(1)

    # 3. Inject the answers into the JSON
    updated_count = 0
    for question in database.get("questions", []):
        q_num = question.get("question_number")
        
        # If the question number exists in our parsed answers, update it
        if q_num in answers:
            question["correct_answer"] = answers[q_num]
            updated_count += 1

    # 4. Save the updated JSON back to the same file (overwriting it)
    with open(json_filepath, 'w', encoding='utf-8') as f:
        json.dump(database, f, indent=4, ensure_ascii=False)

    print(f"Successfully injected {updated_count} answers into '{json_filepath}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inject correct answers into an existing MCA JSON database.")
    parser.add_argument("-j", "--json", required=True, help="Path to the existing JSON file (e.g., mca_2025_questions.json)")
    parser.add_argument("-a", "--answers", required=True, help="Path to the answer key text file (e.g., answers_2025.txt)")

    args = parser.parse_args()

    inject_answers_into_json(json_filepath=args.json, answer_filepath=args.answers)