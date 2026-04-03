#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

import re
import json
import argparse
import sys
import argcomplete
from path_utils import find_project_root, list_relative_files, resolve_under

PROJECT_ROOT = find_project_root(__file__)
DATA_DIR = PROJECT_ROOT / "assets" / "data"
RAW_PYQ_DIR = DATA_DIR / "raw" / "pyqs"
JSON_DIR = DATA_DIR / "json"
IMAGE_DIR = DATA_DIR / "images"

# --- Custom Completer ---
def txt_file_completer(prefix, parsed_args, **kwargs):
    """Suggests only .txt files from the assets/data/raw/pyqs directory."""
    return [path for path in list_relative_files(RAW_PYQ_DIR, "*.txt") if path.startswith(prefix)]

def normalize_text(text):
    """Cleans OCR/PDF text by removing newlines and squashing redundant spaces."""
    if not text:
        return text
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_image_path(local_dir, web_dir, base_name):
    """Checks for various image extensions and returns the web path if found."""
    for ext in [".jpeg", ".jpg"]:
        if (local_dir / f"{base_name}{ext}").exists():
            return f"{web_dir}/{base_name}{ext}"
    return None

def clean_and_append_question(question, db_list, year, test_code):
    """Post-processes the question and links images by scanning the local directory."""
    if not question:
        return
        
    q_text = question["question"]["stem"] or ""
    q_num = question["question_number"]
    
    # 1. Handle Inline Directions
    inline_match = re.match(r'^Direction:\s*(.*?\.)(\s+|$)(.*)', q_text, re.IGNORECASE | re.DOTALL)
    
    if inline_match:
        question["question"]["direction"] = inline_match.group(1)
        question["question"]["stem"] = inline_match.group(3)
    else:
        fallback_match = re.match(r'^Direction:\s*(.*)', q_text, re.IGNORECASE | re.DOTALL)
        if fallback_match:
            question["question"]["direction"] = fallback_match.group(1)
            question["question"]["stem"] = ""

    # 2. Normalize and Clean Text Fields
    if question["question"]["direction"]:
        question["question"]["direction"] = normalize_text(question["question"]["direction"])
        
    question["question"]["stem"] = normalize_text(question["question"]["stem"])
    
    for opt in ["A", "B", "C", "D"]:
        if question["options"][opt]["text"]:
            question["options"][opt]["text"] = normalize_text(question["options"][opt]["text"])

    # 3. Dynamic Filesystem Image Detection
    local_check_dir = IMAGE_DIR / f"{year}_{test_code}"
    web_asset_path = f"/assets/data/images/{year}_{test_code}"
    
    # --- Check for Question Images (Arrays) ---
    question_images = []
    
    # Check for the classic single image first
    img_path = get_image_path(local_check_dir, web_asset_path, f"Q{q_num}")
    if img_path:
        question_images.append(img_path)
    
    # Check for sequential images
    idx = 1
    while True:
        img_path = get_image_path(local_check_dir, web_asset_path, f"Q{q_num}_{idx}")
        if img_path:
            question_images.append(img_path)
            idx += 1
        else:
            break

    # Assign array if we found any images, otherwise null
    question["question"]["images"] = question_images if question_images else None

    # Check for Option Images
    for opt in ["A", "B", "C", "D"]:
        img_path = get_image_path(local_check_dir, web_asset_path, f"Q{q_num}{opt}")
        if img_path:
            question["options"][opt]["image"] = img_path
            # SECURITY: If there is an image in the option, the text value MUST be null
            question["options"][opt]["text"] = None
        else:
            # If no image is present, but text is an empty string, clean it up to null
            if question["options"][opt]["text"] == "":
                question["options"][opt]["text"] = None

    # 4. Auto-Detect Question Format
    q_text_lower = question["question"]["stem"].lower() if question["question"]["stem"] else ""
    dir_text_lower = question["question"]["direction"].lower() if question["question"]["direction"] else ""
    
    has_q_images = question["question"]["images"] is not None
    has_opt_images = any(question["options"][opt]["image"] is not None for opt in ["A", "B", "C", "D"])
    
    if "read the given passage" in dir_text_lower:
        question["question"]["format"] = "shared_passage"
    elif has_q_images or has_opt_images:
        question["question"]["format"] = "visual_reasoning"
    elif "statement:" in q_text_lower or "assumption:" in q_text_lower:
        question["question"]["format"] = "statement_assumption"
    elif "course of action" in q_text_lower or "problem:" in q_text_lower:
        question["question"]["format"] = "course_of_action"
    else:
        question["question"]["format"] = "standard_mcq"

    # Final conversion of empty string to Null
    question["question"]["stem"] = question["question"]["stem"] if question["question"]["stem"] != "" else None
    
    db_list.append(question)


def parse_questions_to_json(filepath, year, course_name, test_code, total_time, reward, penalty, unanswered):
    try:
        with filepath.open("r", encoding="utf-8") as file:
            lines = file.readlines()
    except FileNotFoundError:
        print(f"Error: The input file '{filepath}' was not found.")
        sys.exit(1)

    local_check_dir = IMAGE_DIR / f"{year}_{test_code}"
    if not local_check_dir.exists():
        print(f"Warning: The image directory '{local_check_dir}' does not exist. No images will be linked.")

    # Paper Metadata (Initialized dynamically)
    database = {
        "paper_metadata": {
            "course_name": course_name,
            "test_code": test_code,
            "year": year,
            "total_time": total_time,
            "total_questions": 0,
            "maximum_marks": 0,
            "marking_scheme": {
                "reward": reward,
                "penalty": penalty,
                "unanswered": unanswered
            }
        },
        "questions": []
    }

    question_pattern = re.compile(r'^\s*(\d+)\.\s+(.*)')
    option_pattern = re.compile(r'^\s*\(([A-D])\)\s*(.*)')
    direction_pattern = re.compile(r'^\s*Direction:\s*(.*)', re.IGNORECASE)

    current_question = None
    current_direction = None
    direction_end_q = None 
    current_target = "BUFFER" 
    current_option = None
    floating_buffer = []      

    for line in lines:
        stripped_line = line.strip()
        
        if not stripped_line:
            if current_target == "OPTION":
                current_target = "BUFFER"
            continue

        dir_match = direction_pattern.match(stripped_line)
        if dir_match:
            current_direction = dir_match.group(1).strip()
            current_target = "DIRECTION"
            floating_buffer = [] 
            
            range_match = re.search(r'(\d+)\s*-\s*(\d+)', current_direction)
            if range_match:
                direction_end_q = int(range_match.group(2))
            else:
                if current_question:
                    direction_end_q = current_question.get("question_number", 0) + 5 
                else:
                    direction_end_q = 5
            continue

        q_match = question_pattern.match(stripped_line)
        if q_match:
            # Multi-line question check: if we have a question but missing options
            if current_question:
                opts = current_question["options"]
                # FIX: Count options that have been touched (even if they are empty strings "")
                filled_opts = sum(1 for k in opts if opts[k]["text"] is not None)
                
                if filled_opts < 2:
                    if current_target == "QUESTION" and current_question["question"]["stem"] is not None:
                        current_question["question"]["stem"] += f"\n{stripped_line}"
                    elif current_target == "DIRECTION" and current_direction is not None:
                        current_direction += f"\n{stripped_line}"
                    elif current_target == "BUFFER":
                        floating_buffer.append(stripped_line)
                    continue

            if current_question:
                clean_and_append_question(current_question, database["questions"], year, test_code)

            q_num = int(q_match.group(1))
            q_text = q_match.group(2).strip()

            if floating_buffer:
                q_text = "\n".join(floating_buffer) + "\n" + q_text
                floating_buffer = []

            if direction_end_q and q_num > direction_end_q:
                current_direction = None
                direction_end_q = None

            current_question = {
                "question_number": q_num,
                "question": {
                    "format": None,
                    "direction": current_direction, 
                    "stem": q_text,
                    "images": None
                },
                "options": {
                    "A": {"text": None, "image": None},
                    "B": {"text": None, "image": None},
                    "C": {"text": None, "image": None},
                    "D": {"text": None, "image": None}
                },
                "correct_answer": None,
                "topic_tag": "Uncategorized",
                "explanation": None
            }

            current_target = "QUESTION"
            current_option = None
            continue

        opt_match = option_pattern.match(stripped_line)
        if opt_match and current_question:
            opt_letter = opt_match.group(1).upper()
            opt_text = opt_match.group(2).strip()
            
            if opt_letter in current_question["options"]:
                # FIX: Set the text to the extracted text (even if it's empty `""`). 
                # This explicitly registers the option as "seen" to prevent the next question from being swallowed.
                current_question["options"][opt_letter]["text"] = opt_text

            current_option = opt_letter 
            current_target = "OPTION"
            continue

        if current_target == "OPTION" and current_question and current_option:
            if current_question["options"][current_option]["text"] is not None:
                current_question["options"][current_option]["text"] += f" {stripped_line}"
            else:
                current_question["options"][current_option]["text"] = stripped_line

        elif current_target == "QUESTION" and current_question and current_question["question"]["stem"] is not None:
            current_question["question"]["stem"] += f"\n{stripped_line}"
            
        elif current_target == "DIRECTION" and current_direction is not None:
            current_direction += f"\n{stripped_line}"
            
        elif current_target == "BUFFER":
            floating_buffer.append(stripped_line)

    if current_question:
        if floating_buffer and current_target == "BUFFER" and current_question["question"]["stem"] is not None:
            current_question["question"]["stem"] += "\n" + "\n".join(floating_buffer)
        clean_and_append_question(current_question, database["questions"], year, test_code)

    # --- DYNAMICALLY CALCULATE TOTALS ---
    total_q = len(database["questions"])
    database["paper_metadata"]["total_questions"] = total_q
    database["paper_metadata"]["maximum_marks"] = total_q * reward
    # ------------------------------------

    return database


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert exam questions from text to JSON. Auto-detects Year and Test Code from filename: <year>_<test_code>_questions.txt")
    
    # Attach the completer to the input argument
    parser.add_argument("-q", "--questions", required=True, 
                        help="Input filename in format <year>_<test_code>_questions.txt (script will look in assets/data/raw/pyqs/)").completer = txt_file_completer
                        
    parser.add_argument("-c", "--course", required=True, help="Course name (e.g., MCA)")
    
    parser.add_argument("-m", "--minutes", type=int, required=True, help="Total time allowed for the exam in minutes")
    
    # Optional flags for marking scheme
    parser.add_argument("-r", "--reward", type=int, default=3, help="Marks rewarded for correct answer (Default: 3)")
    parser.add_argument("-p", "--penalty", type=int, default=-1, help="Marks deducted for wrong answer (Default: -1)")
    parser.add_argument("-u", "--unanswered", type=int, default=0, help="Marks for unanswered question (Default: 0)")

    # CRITICAL: Trigger autocomplete before parse_args
    argcomplete.autocomplete(parser)

    args = parser.parse_args()

    # Automatically prepend the directory path
    question_filepath = resolve_under(RAW_PYQ_DIR, args.questions)
    
    # --- FILENAME PARSING LOGIC ---
    base_filename = question_filepath.stem
    filename_parts = base_filename.split("_")
    
    if len(filename_parts) < 2:
        print(f"Error: The filename '{args.questions}' does not match the expected format '<year>_<test_code>_questions.ext'")
        print("Example of correct format: 2025_501_questions.txt")
        sys.exit(1)
        
    try:
        parsed_year = int(filename_parts[0])
    except ValueError:
        print(f"Error: The year part of the filename '{filename_parts[0]}' is not a valid integer.")
        sys.exit(1)
        
    parsed_test_code = filename_parts[1]
    parsed_course = args.course.upper()
    # ------------------------------
    
    # Dynamically construct the new JSON filename (<year>_<test_code>_db.json)
    json_filename = f"{parsed_year}_{parsed_test_code}_db.json"
    json_filepath = JSON_DIR / json_filename
    
    json_filepath.parent.mkdir(parents=True, exist_ok=True)

    print(f"Detected parameters -> Year: {parsed_year}, Course: {parsed_course}, Test Code: {parsed_test_code}")

    parsed_data = parse_questions_to_json(
        filepath=question_filepath, 
        year=parsed_year, 
        course_name=parsed_course, 
        test_code=parsed_test_code,
        total_time=args.minutes,
        reward=args.reward,
        penalty=args.penalty,
        unanswered=args.unanswered
    )
    
    # --- Verification Step ---
    parsed_questions = parsed_data["questions"] 
    present_numbers = {q.get("question_number") for q in parsed_questions if q.get("question_number") is not None}
    expected_numbers = set(range(1, 151))
    skipped_numbers = sorted(list(expected_numbers - present_numbers))
    
    print("\n--- Parsing Verification ---")
    if skipped_numbers:
        print(f"WARNING: {len(skipped_numbers)} questions were skipped/missing!")
        print(f"Missing Question Numbers: {skipped_numbers}")
    else:
        print("SUCCESS: All 150 questions were parsed and accounted for.")
    print("----------------------------\n")
    
    with json_filepath.open("w", encoding="utf-8") as json_file:
        json.dump(parsed_data, json_file, indent=4, ensure_ascii=False)
        
    print(f"Saved to {json_filepath}")
