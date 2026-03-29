#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

import re
import json
import argparse
import sys
import os
import argcomplete

# --- Dynamic Path Resolution ---
# 1. Get the absolute path of the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 2. Go one level up to find the project root
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
# 3. Build your asset paths absolutely from the project root
DATA_DIR = os.path.join(PROJECT_ROOT, "assets", "data")

# --- Custom Completer ---
def txt_file_completer(prefix, parsed_args, **kwargs):
    """Suggests only .txt files from the assets/data/raw directory."""
    target_dir = os.path.join(DATA_DIR, "raw")
    if not os.path.exists(target_dir):
        return []
    return [f for f in os.listdir(target_dir) if f.lower().endswith('.txt') and f.startswith(prefix)]

def normalize_text(text):
    """Cleans OCR/PDF text by removing newlines and squashing redundant spaces."""
    if not text:
        return text
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def clean_and_append_question(question, db_list, year, course_name):
    """Post-processes the question and links images by scanning the local directory."""
    if not question:
        return
        
    q_text = question["question_text"] or ""
    q_num = question["question_number"]
    
    # 1. Handle Inline Directions
    inline_match = re.match(r'^Direction:\s*(.*?\.)(\s+|$)(.*)', q_text, re.IGNORECASE | re.DOTALL)
    
    if inline_match:
        question["direction_text"] = inline_match.group(1)
        question["question_text"] = inline_match.group(3)
    else:
        fallback_match = re.match(r'^Direction:\s*(.*)', q_text, re.IGNORECASE | re.DOTALL)
        if fallback_match:
            question["direction_text"] = fallback_match.group(1)
            question["question_text"] = ""

    # 2. Normalize and Clean All Text Fields
    if question["direction_text"]:
        question["direction_text"] = normalize_text(question["direction_text"])
        
    question["question_text"] = normalize_text(question["question_text"])
    
    if question["textual_options"]:
        for key, val in question["textual_options"].items():
            question["textual_options"][key] = normalize_text(val)

    # 3. Dynamic Filesystem Image Detection
    local_check_dir = os.path.join(DATA_DIR, "images", f"{year}_{course_name}")
    # We keep web_asset_path relative because this gets written to the JSON for the Jekyll frontend
    web_asset_path = f"/assets/data/images/{year}_{course_name}"
    
    # --- Check for Question Images (Arrays) ---
    question_images = []
    
    # Check for the classic single image first
    if os.path.exists(os.path.join(local_check_dir, f"Q{q_num}.jpeg")):
        question_images.append(f"{web_asset_path}/Q{q_num}.jpeg")
    
    # Check for sequential images
    idx = 1
    while os.path.exists(os.path.join(local_check_dir, f"Q{q_num}_{idx}.jpeg")):
        question_images.append(f"{web_asset_path}/Q{q_num}_{idx}.jpeg")
        idx += 1

    # Assign array if we found any images, otherwise null
    question["question_images"] = question_images if question_images else None

    # Check for Graphical Options
    found_graphical_opts = {}
    possible_options = list(question["textual_options"].keys()) if question["textual_options"] else ["A", "B", "C", "D"]
    
    for opt in possible_options:
        if os.path.exists(os.path.join(local_check_dir, f"Q{q_num}{opt}.jpeg")):
            found_graphical_opts[opt] = f"{web_asset_path}/Q{q_num}{opt}.jpeg"
            
    if found_graphical_opts:
        question["graphical_options"] = found_graphical_opts
        if question["textual_options"] and len(found_graphical_opts) == len(question["textual_options"]):
            question["textual_options"] = None
    else:
        question["graphical_options"] = None

    # 4. Auto-Detect Question Format
    q_text_lower = question["question_text"].lower() if question["question_text"] else ""
    dir_text_lower = question["direction_text"].lower() if question["direction_text"] else ""
    
    if "read the given passage" in dir_text_lower:
        question["question_format"] = "shared_passage"
    elif question.get("question_images") is not None or question.get("graphical_options") is not None:
        question["question_format"] = "visual_reasoning"
    elif "statement:" in q_text_lower or "assumption:" in q_text_lower:
        question["question_format"] = "statement_assumption"
    elif "course of action" in q_text_lower or "problem:" in q_text_lower:
        question["question_format"] = "course_of_action"
    else:
        question["question_format"] = "standard_mcq"

    # Final conversion of empty string to Null
    question["question_text"] = question["question_text"] if question["question_text"] != "" else None
    
    db_list.append(question)


def parse_questions_to_json(filepath, year, course_name, test_code, total_time, reward, penalty, unanswered):
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            lines = file.readlines()
    except FileNotFoundError:
        print(f"Error: The input file '{filepath}' was not found.")
        sys.exit(1)

    local_check_dir = os.path.join(DATA_DIR, "images", f"{year}_{course_name}")
    if not os.path.exists(local_check_dir):
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
            if current_question and (current_question["textual_options"] is not None and len(current_question["textual_options"]) < 2):
                if current_target == "QUESTION" and current_question["question_text"] is not None:
                    current_question["question_text"] += f"\n{stripped_line}"
                elif current_target == "DIRECTION" and current_direction is not None:
                    current_direction += f"\n{stripped_line}"
                elif current_target == "BUFFER":
                    floating_buffer.append(stripped_line)
                continue

            if current_question:
                clean_and_append_question(current_question, database["questions"], year, course_name)

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
                "direction_text": current_direction, 
                "question_text": q_text,
                "question_images": None, 
                "textual_options": {},
                "graphical_options": None,
                "correct_answer": None,
                "topic_tag": "Uncategorized",
                "explanation": None,           
                "question_format": None      
            }

            current_target = "QUESTION"
            current_option = None
            continue

        opt_match = option_pattern.match(stripped_line)
        if opt_match and current_question:
            opt_letter = opt_match.group(1).upper()
            opt_text = opt_match.group(2).strip()
            
            if current_question["textual_options"] is not None:
                current_question["textual_options"][opt_letter] = opt_text

            current_option = opt_letter 
            current_target = "OPTION"
            continue

        if current_target == "OPTION" and current_question and current_question["textual_options"] is not None:
            current_question["textual_options"][current_option] += f" {stripped_line}"

        elif current_target == "QUESTION" and current_question and current_question["question_text"] is not None:
            current_question["question_text"] += f"\n{stripped_line}"
            
        elif current_target == "DIRECTION" and current_direction is not None:
            current_direction += f"\n{stripped_line}"
            
        elif current_target == "BUFFER":
            floating_buffer.append(stripped_line)

    if current_question:
        if floating_buffer and current_target == "BUFFER" and current_question["question_text"] is not None:
            current_question["question_text"] += "\n" + "\n".join(floating_buffer)
        clean_and_append_question(current_question, database["questions"], year, course_name)

    # --- DYNAMICALLY CALCULATE TOTALS ---
    total_q = len(database["questions"])
    database["paper_metadata"]["total_questions"] = total_q
    database["paper_metadata"]["maximum_marks"] = total_q * reward
    # ------------------------------------

    return database

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert exam questions from text to JSON.")
    
    # Attach the completer to the input argument
    parser.add_argument("-q", "--questions", required=True, 
                        help="Input filename (script will look in assets/data/raw/)").completer = txt_file_completer
                        
    parser.add_argument("-y", "--year", type=int, required=True, help="The year of the exam paper")
    parser.add_argument("-c", "--course", type=str.upper, required=True, help="The name of the course (e.g., MCA)")
    parser.add_argument("-t", "--test-code", required=True, help="The CUSAT test code number for this paper")
    parser.add_argument("-m", "--minutes", type=int, required=True, help="Total time allowed for the exam in minutes")
    
    # Optional flags for marking scheme
    parser.add_argument("-r", "--reward", type=int, default=3, help="Marks rewarded for correct answer (Default: 3)")
    parser.add_argument("-p", "--penalty", type=int, default=-1, help="Marks deducted for wrong answer (Default: -1)")
    parser.add_argument("-u", "--unanswered", type=int, default=0, help="Marks for unanswered question (Default: 0)")

    # CRITICAL: Trigger autocomplete before parse_args
    argcomplete.autocomplete(parser)

    args = parser.parse_args()

    # Automatically prepend the directory path
    question_filepath = os.path.join(DATA_DIR, "raw", args.questions)
    
    # Dynamically construct the JSON filename
    json_filename = f"{args.year}_{args.course}_db.json"
    json_filepath = os.path.join(DATA_DIR, "json", json_filename)
    
    os.makedirs(os.path.dirname(json_filepath), exist_ok=True)

    parsed_data = parse_questions_to_json(
        filepath=question_filepath, 
        year=args.year, 
        course_name=args.course, 
        test_code=args.test_code,
        total_time=args.minutes,
        reward=args.reward,
        penalty=args.penalty,
        unanswered=args.unanswered
    )
    
    with open(json_filepath, 'w', encoding='utf-8') as json_file:
        json.dump(parsed_data, json_file, indent=4, ensure_ascii=False)
        
    print(f"Success! Converted {len(parsed_data['questions'])} questions and saved to {json_filepath}")