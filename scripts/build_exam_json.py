#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import argcomplete
import fitz

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from path_utils import find_project_root, list_relative_files, resolve_under

PROJECT_ROOT = find_project_root(__file__)
DATA_DIR = PROJECT_ROOT / "assets" / "data"
RAW_PYQ_DIR = DATA_DIR / "raw" / "pyqs"
JSON_DIR = DATA_DIR / "json"
IMAGE_DIR = DATA_DIR / "images"

SYSTEM_PROMPT = (
    "You are an expert data processor for an exam simulator. "
    "I have attached an image of a page from an exam paper and a draft JSON array of the "
    "questions found on this page. The draft JSON has OCR errors, broken mathematical formatting, "
    "and column bleeds. Read the image carefully and fix the text in the JSON. Format all math, "
    "equations, and chemical formulas using LaTeX wrapped in $ and $$. Add a detailed, "
    "step-by-step educational explanation for the correct answer, and assign a relevant academic "
    "topic_tag. Return ONLY the corrected JSON array, with no markdown code blocks or "
    "conversational text."
)

QUESTION_PATTERN = re.compile(r"^\s*(\d+)\.\s+(.*)")
OPTION_PATTERN = re.compile(r"^\s*\(([A-D])\)\s*(.*)")
DIRECTION_PATTERN = re.compile(r"^\s*Direction:\s*(.*)", re.IGNORECASE)
PAGE_QUESTION_PATTERN = re.compile(r"(?m)^\s*(\d+)\.\s+")
ANSWER_PAIR_PATTERN = re.compile(r"\b(\d+)\s+([A-D])\b", re.IGNORECASE)
DEFAULT_MODEL = "gemini-1.5-flash"


@dataclass
class PageSlice:
    page_number: int
    image_path: Path
    detected_question_numbers: list[int]


def questions_file_completer(prefix, parsed_args, **kwargs):
    return [path for path in list_relative_files(RAW_PYQ_DIR, "*questions.txt") if path.startswith(prefix)]

def answers_file_completer(prefix, parsed_args, **kwargs):
    return [path for path in list_relative_files(RAW_PYQ_DIR, "*answers.txt") if path.startswith(prefix)]


def pdf_file_completer(prefix, parsed_args, **kwargs):
    return [path for path in list_relative_files(RAW_PYQ_DIR, "*.pdf") if path.startswith(prefix)]


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def normalize_text(text: str | None) -> str | None:
    if not text:
        return text
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_image_path(local_dir: Path, web_dir: str, base_name: str) -> str | None:
    for ext in [".jpeg", ".jpg", ".png"]:
        candidate = local_dir / f"{base_name}{ext}"
        if candidate.exists():
            return f"{web_dir}/{base_name}{ext}"
    return None


def detect_question_images(year: int, test_code: str, question_number: int) -> list[str] | None:
    local_check_dir = IMAGE_DIR / f"{year}_{test_code}"
    web_asset_path = f"/assets/data/images/{year}_{test_code}"
    question_images = []

    first_image = get_image_path(local_check_dir, web_asset_path, f"Q{question_number}")
    if first_image:
        question_images.append(first_image)

    index = 1
    while True:
        image_path = get_image_path(local_check_dir, web_asset_path, f"Q{question_number}_{index}")
        if not image_path:
            break
        question_images.append(image_path)
        index += 1

    return question_images or None


def finalize_question(question: dict[str, Any], year: int, test_code: str) -> dict[str, Any]:
    q_text = question["question"]["stem"] or ""
    q_num = question["question_number"]

    inline_match = re.match(r"^Direction:\s*(.*?\.)(\s+|$)(.*)", q_text, re.IGNORECASE | re.DOTALL)
    if inline_match:
        question["question"]["direction"] = inline_match.group(1)
        question["question"]["stem"] = inline_match.group(3)
    else:
        fallback_match = re.match(r"^Direction:\s*(.*)", q_text, re.IGNORECASE | re.DOTALL)
        if fallback_match:
            question["question"]["direction"] = fallback_match.group(1)
            question["question"]["stem"] = ""

    question["question"]["direction"] = normalize_text(question["question"]["direction"])
    question["question"]["stem"] = normalize_text(question["question"]["stem"])
    question["question"]["images"] = detect_question_images(year, test_code, q_num)

    local_check_dir = IMAGE_DIR / f"{year}_{test_code}"
    web_asset_path = f"/assets/data/images/{year}_{test_code}"

    for option_key in ["A", "B", "C", "D"]:
        option = question["options"][option_key]
        option["text"] = normalize_text(option["text"])
        option_image = get_image_path(local_check_dir, web_asset_path, f"Q{q_num}{option_key}")
        if option_image:
            option["image"] = option_image
            option["text"] = None
        elif option["text"] == "":
            option["text"] = None

    q_text_lower = (question["question"]["stem"] or "").lower()
    direction_lower = (question["question"]["direction"] or "").lower()
    has_question_images = question["question"]["images"] is not None
    has_option_images = any(
        question["options"][option]["image"] is not None for option in ["A", "B", "C", "D"]
    )

    if "read the given passage" in direction_lower:
        question["question"]["format"] = "shared_passage"
    elif has_question_images or has_option_images:
        question["question"]["format"] = "visual_reasoning"
    elif "statement:" in q_text_lower or "assumption:" in q_text_lower:
        question["question"]["format"] = "statement_assumption"
    elif "course of action" in q_text_lower or "problem:" in q_text_lower:
        question["question"]["format"] = "course_of_action"
    else:
        question["question"]["format"] = "standard_mcq"

    if question["question"]["stem"] == "":
        question["question"]["stem"] = None

    return question


def parse_answer_key(answer_path: Path) -> dict[int, str]:
    try:
        raw_text = answer_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Error: Answer key file not found: {answer_path}")
        sys.exit(1)

    answer_dict: dict[int, str] = {}

    matches = ANSWER_PAIR_PATTERN.findall(raw_text)
    if matches:
        for question_number, option in matches:
            answer_dict[int(question_number)] = option.upper()
        return answer_dict

    tokens = [line.strip() for line in raw_text.splitlines() if line.strip()]
    for index in range(len(tokens) - 1):
        current_token = tokens[index]
        next_token = tokens[index + 1]
        if current_token.isdigit() and re.match(r"^[A-D]$", next_token.upper()):
            answer_dict[int(current_token)] = next_token.upper()

    return answer_dict


def parse_questions_draft(
    questions_path: Path,
    year: int,
    course_name: str,
    test_code: str,
    total_time: int,
    reward: int,
    penalty: int,
    unanswered: int,
) -> dict[str, Any]:
    try:
        lines = questions_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        print(f"Error: Question file not found: {questions_path}")
        sys.exit(1)

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
                "unanswered": unanswered,
            },
        },
        "questions": [],
    }

    current_question = None
    current_direction = None
    direction_end_q = None
    current_target = "BUFFER"
    current_option = None
    floating_buffer: list[str] = []

    for line in lines:
        stripped_line = line.strip()

        if not stripped_line:
            if current_target == "OPTION":
                current_target = "BUFFER"
            continue

        direction_match = DIRECTION_PATTERN.match(stripped_line)
        if direction_match:
            current_direction = direction_match.group(1).strip()
            current_target = "DIRECTION"
            floating_buffer = []

            range_match = re.search(r"(\d+)\s*-\s*(\d+)", current_direction)
            if range_match:
                direction_end_q = int(range_match.group(2))
            elif current_question:
                direction_end_q = current_question.get("question_number", 0) + 5
            else:
                direction_end_q = 5
            continue

        question_match = QUESTION_PATTERN.match(stripped_line)
        if question_match:
            if current_question:
                filled_options = sum(
                    1
                    for option_name in current_question["options"]
                    if current_question["options"][option_name]["text"] is not None
                )
                if filled_options < 2:
                    if current_target == "QUESTION" and current_question["question"]["stem"] is not None:
                        current_question["question"]["stem"] += f"\n{stripped_line}"
                    elif current_target == "DIRECTION" and current_direction is not None:
                        current_direction += f"\n{stripped_line}"
                    elif current_target == "BUFFER":
                        floating_buffer.append(stripped_line)
                    continue

            if current_question:
                database["questions"].append(finalize_question(current_question, year, test_code))

            question_number = int(question_match.group(1))
            question_text = question_match.group(2).strip()

            if floating_buffer:
                question_text = "\n".join(floating_buffer) + "\n" + question_text
                floating_buffer = []

            if direction_end_q and question_number > direction_end_q:
                current_direction = None
                direction_end_q = None

            current_question = {
                "question_number": question_number,
                "question": {
                    "format": None,
                    "direction": current_direction,
                    "stem": question_text,
                    "images": None,
                },
                "options": {
                    "A": {"text": None, "image": None},
                    "B": {"text": None, "image": None},
                    "C": {"text": None, "image": None},
                    "D": {"text": None, "image": None},
                },
                "correct_answer": None,
                "topic_tag": "Uncategorized",
                "explanation": None,
            }
            current_target = "QUESTION"
            current_option = None
            continue

        option_match = OPTION_PATTERN.match(stripped_line)
        if option_match and current_question:
            option_letter = option_match.group(1).upper()
            option_text = option_match.group(2).strip()
            if option_letter in current_question["options"]:
                current_question["options"][option_letter]["text"] = option_text
            current_option = option_letter
            current_target = "OPTION"
            continue

        if current_target == "OPTION" and current_question and current_option:
            existing_value = current_question["options"][current_option]["text"]
            if existing_value is not None:
                current_question["options"][current_option]["text"] += f" {stripped_line}"
            else:
                current_question["options"][current_option]["text"] = stripped_line
        elif current_target == "QUESTION" and current_question and current_question["question"]["stem"] is not None:
            current_question["question"]["stem"] += f"\n{stripped_line}"
        elif current_target == "DIRECTION" and current_direction is not None:
            current_direction += f"\n{stripped_line}"
        else:
            floating_buffer.append(stripped_line)

    if current_question:
        if floating_buffer and current_question["question"]["stem"] is not None:
            current_question["question"]["stem"] += "\n" + "\n".join(floating_buffer)
        database["questions"].append(finalize_question(current_question, year, test_code))

    total_questions = len(database["questions"])
    database["paper_metadata"]["total_questions"] = total_questions
    database["paper_metadata"]["maximum_marks"] = total_questions * reward

    return database


def inject_answers(database: dict[str, Any], answer_map: dict[int, str]) -> None:
    updated_count = 0
    for question in database["questions"]:
        question_number = question["question_number"]
        if question_number in answer_map:
            question["correct_answer"] = answer_map[question_number]
            updated_count += 1

    print(
        f"Phase 1: injected answers for {updated_count} of "
        f"{len(database['questions'])} parsed questions."
    )


def create_genai_client() -> Any:
    load_env_file(PROJECT_ROOT / "scripts" / "venv" / ".env")
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if genai is None or types is None:
        print("Error: google-genai is not installed. Add it to your environment first.")
        sys.exit(1)

    if not api_key:
        print("Error: Missing GOOGLE_API_KEY or GEMINI_API_KEY.")
        print("Add it to your shell environment or inside venv/ as a .env file.")
        sys.exit(1)

    return genai.Client(api_key=api_key)


def slice_pdf_to_images(pdf_path: Path, temp_dir: Path, zoom: float = 2.0) -> list[PageSlice]:
    print(f"Phase 2: slicing PDF pages from {pdf_path}...")
    page_slices: list[PageSlice] = []
    document = fitz.open(str(pdf_path))

    try:
        for page_index in range(document.page_count):
            page_number = page_index + 1
            page = document[page_index]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            image_path = temp_dir / f"page_{page_number:03d}.png"
            pixmap.save(str(image_path))

            page_text = page.get_text("text")
            detected_numbers = sorted(
                {
                    int(match)
                    for match in PAGE_QUESTION_PATTERN.findall(page_text)
                }
            )
            page_slices.append(
                PageSlice(
                    page_number=page_number,
                    image_path=image_path,
                    detected_question_numbers=detected_numbers,
                )
            )
    finally:
        document.close()

    print(f"Phase 2: created {len(page_slices)} page images in {temp_dir}.")
    return page_slices


def find_next_detected_start(page_slices: list[PageSlice], page_index: int) -> tuple[int | None, int | None]:
    for next_index in range(page_index + 1, len(page_slices)):
        if page_slices[next_index].detected_question_numbers:
            return next_index, min(page_slices[next_index].detected_question_numbers)
    return None, None


def build_page_question_chunks(
    questions: list[dict[str, Any]],
    page_slices: list[PageSlice],
    default_chunk_size: int,
) -> list[tuple[PageSlice, list[dict[str, Any]]]]:
    questions_sorted = sorted(questions, key=lambda item: item["question_number"])
    index_by_question_number = {
        question["question_number"]: index for index, question in enumerate(questions_sorted)
    }
    remaining_index = 0
    mapped_chunks: list[tuple[PageSlice, list[dict[str, Any]]]] = []

    for page_index, page_slice in enumerate(page_slices):
        if remaining_index >= len(questions_sorted):
            mapped_chunks.append((page_slice, []))
            continue

        next_detected_page_index, next_detected_start = find_next_detected_start(page_slices, page_index)
        next_boundary = len(questions_sorted)
        if next_detected_start in index_by_question_number:
            next_boundary = index_by_question_number[next_detected_start]

        if page_slice.detected_question_numbers:
            end_index = next_boundary
            if end_index <= remaining_index:
                end_index = min(remaining_index + default_chunk_size, len(questions_sorted))
        else:
            end_index = min(remaining_index + default_chunk_size, next_boundary)
            if end_index <= remaining_index:
                end_index = min(remaining_index + default_chunk_size, len(questions_sorted))

        if (
            next_detected_page_index is not None
            and next_detected_start in index_by_question_number
            and next_boundary > remaining_index
            and next_detected_page_index > page_index + 1
        ):
            remaining_pages_until_boundary = next_detected_page_index - page_index
            remaining_questions_until_boundary = next_boundary - remaining_index
            spread_size = max(
                1,
                (remaining_questions_until_boundary + remaining_pages_until_boundary - 1)
                // remaining_pages_until_boundary,
            )
            if not page_slice.detected_question_numbers:
                end_index = min(remaining_index + spread_size, next_boundary)

        chunk = questions_sorted[remaining_index:end_index]
        mapped_chunks.append((page_slice, chunk))
        remaining_index = end_index

    return mapped_chunks


def extract_response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return text.strip()

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        parts = getattr(content, "parts", None) or []
        text_parts = [part.text for part in parts if getattr(part, "text", None)]
        if text_parts:
            return "\n".join(text_parts).strip()

    raise ValueError("LLM returned no text content.")


def parse_model_json_array(raw_text: str) -> list[dict[str, Any]]:
    cleaned = raw_text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    start_index = cleaned.find("[")
    end_index = cleaned.rfind("]")
    if start_index == -1 or end_index == -1 or end_index < start_index:
        raise ValueError("Model response does not contain a JSON array.")

    parsed = json.loads(cleaned[start_index : end_index + 1])
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict) and isinstance(parsed.get("questions"), list):
        return parsed["questions"]
    raise ValueError("Model response JSON is not an array.")


def call_llm_for_page(
    client: Any,
    model_name: str,
    page_slice: PageSlice,
    draft_chunk: list[dict[str, Any]],
    max_retries: int,
) -> list[dict[str, Any]]:
    if not draft_chunk:
        return []

    prompt_text = (
        f"Page number: {page_slice.page_number}\n"
        "Correct the draft JSON chunk against the attached exam page image.\n\n"
        f"Draft JSON:\n{json.dumps(draft_chunk, indent=2, ensure_ascii=False)}"
    )
    image_bytes = page_slice.image_path.read_bytes()

    content = types.Content(
        role="user",
        parts=[
            types.Part.from_text(text=prompt_text),
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
        ],
    )

    config = None
    try:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0,
        )
    except Exception:
        prompt_text = f"{SYSTEM_PROMPT}\n\n{prompt_text}"
        content = types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=prompt_text),
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            ],
        )

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            print(
                f"Phase 3: processing page {page_slice.page_number} "
                f"with {len(draft_chunk)} draft questions (attempt {attempt}/{max_retries})..."
            )
            response = client.models.generate_content(
                model=model_name,
                contents=[content],
                config=config,
            )
            response_text = extract_response_text(response)
            corrected_chunk = parse_model_json_array(response_text)
            print(f"  -> page {page_slice.page_number} corrected successfully.")
            return corrected_chunk
        except Exception as exc:
            last_error = exc
            if attempt == max_retries:
                break

            backoff_seconds = min(30, 2 ** (attempt - 1))
            print(
                f"  -> page {page_slice.page_number} attempt {attempt} failed: {exc}. "
                f"Retrying in {backoff_seconds}s..."
            )
            time.sleep(backoff_seconds)

    raise RuntimeError(
        f"LLM correction failed for page {page_slice.page_number} after {max_retries} attempts: {last_error}"
    )


def merge_corrected_question(existing: dict[str, Any], corrected: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(existing)
    merged["question_number"] = existing["question_number"]

    corrected_question = corrected.get("question", {})
    if isinstance(corrected_question, dict):
        for key in ["format", "direction", "stem"]:
            if key in corrected_question and corrected_question[key] is not None:
                merged["question"][key] = corrected_question[key]
        if corrected_question.get("images"):
            merged["question"]["images"] = corrected_question["images"]

    corrected_options = corrected.get("options", {})
    if isinstance(corrected_options, dict):
        for option_key in ["A", "B", "C", "D"]:
            option_patch = corrected_options.get(option_key)
            if not isinstance(option_patch, dict):
                continue
            if "text" in option_patch:
                merged["options"][option_key]["text"] = option_patch["text"]
            if option_patch.get("image"):
                merged["options"][option_key]["image"] = option_patch["image"]

    for key in ["correct_answer", "topic_tag", "explanation"]:
        if key in corrected and corrected[key] is not None:
            merged[key] = corrected[key]

    return merged


def merge_corrected_chunk(master_database: dict[str, Any], corrected_chunk: list[dict[str, Any]]) -> None:
    questions_by_number = {
        question["question_number"]: question for question in master_database["questions"]
    }

    for corrected_question in corrected_chunk:
        question_number = corrected_question.get("question_number")
        if not isinstance(question_number, int):
            print("  -> warning: skipping corrected question without a valid question_number.")
            continue

        existing_question = questions_by_number.get(question_number)
        if not existing_question:
            print(f"  -> warning: corrected question {question_number} is not present in the draft.")
            continue

        merged_question = merge_corrected_question(existing_question, corrected_question)
        existing_question.clear()
        existing_question.update(merged_question)


def save_database(database: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(database, indent=4, ensure_ascii=False), encoding="utf-8")


def build_database(args: argparse.Namespace) -> Path:
    print("Phase 1: building heuristic draft in memory...")
    questions_path = resolve_under(RAW_PYQ_DIR, args.questions)
    answers_path = resolve_under(RAW_PYQ_DIR, args.answers)
    pdf_path = resolve_under(RAW_PYQ_DIR, args.pdf)

    for label, path in [("questions", questions_path), ("answers", answers_path), ("pdf", pdf_path)]:
        if not path.exists():
            print(f"Error: {label} input was not found: {path}")
            sys.exit(1)

    draft_database = parse_questions_draft(
        questions_path=questions_path,
        year=args.year,
        course_name=args.course.upper(),
        test_code=args.test_code,
        total_time=args.minutes,
        reward=args.reward,
        penalty=args.penalty,
        unanswered=args.unanswered,
    )
    answer_map = parse_answer_key(answers_path)
    inject_answers(draft_database, answer_map)
    print(
        f"Phase 1: draft contains {draft_database['paper_metadata']['total_questions']} questions "
        f"for {draft_database['paper_metadata']['course_name']} {args.year}."
    )

    client = create_genai_client()

    temp_dir_obj = tempfile.TemporaryDirectory(prefix=f"{args.year}_{args.test_code}_pages_")
    try:
        temp_dir = Path(temp_dir_obj.name)
        page_slices = slice_pdf_to_images(pdf_path, temp_dir, zoom=args.render_zoom)
        page_chunks = build_page_question_chunks(
            draft_database["questions"],
            page_slices,
            default_chunk_size=args.chunk_size,
        )

        for page_slice, draft_chunk in page_chunks:
            if not draft_chunk:
                print(f"Phase 3: skipping page {page_slice.page_number}; no draft questions mapped.")
                continue

            corrected_chunk = call_llm_for_page(
                client=client,
                model_name=args.model,
                page_slice=page_slice,
                draft_chunk=draft_chunk,
                max_retries=args.max_retries,
            )
            merge_corrected_chunk(draft_database, corrected_chunk)

        output_path = JSON_DIR / f"{args.year}_{args.test_code}_db.json"
        print(f"Phase 4: saving final JSON to {output_path}...")
        save_database(draft_database, output_path)
        print("Phase 4: cleanup complete.")
        return output_path
    finally:
        temp_dir_obj.cleanup()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build an exam JSON database by parsing raw text, slicing the source PDF, "
            "and correcting page chunks with a multimodal LLM."
        )
    )

    parser.add_argument(
        "-q",
        "--questions",
        required=True,
        help="Relative path to questions.txt under assets/data/raw/pyqs/",
    ).completer = questions_file_completer
    parser.add_argument(
        "-a",
        "--answers",
        required=True,
        help="Relative path to answers.txt under assets/data/raw/pyqs/",
    ).completer = answers_file_completer
    parser.add_argument(
        "-p",
        "--pdf",
        required=True,
        help="Relative path to the source exam PDF under assets/data/raw/pyqs/",
    ).completer = pdf_file_completer
    parser.add_argument("-y", "--year", type=int, required=True, help="Exam year.")
    parser.add_argument("-t", "--test-code", required=True, help="Exam test code.")
    parser.add_argument("-c", "--course", required=True, help="Course name, e.g. MCA.")
    parser.add_argument(
        "-m",
        "--minutes",
        type=int,
        default=120,
        help="Total time allowed for the exam in minutes. Default: 120",
    )
    parser.add_argument("-r", "--reward", type=int, default=3, help="Marks for a correct answer.")
    parser.add_argument("-n", "--penalty", type=int, default=-1, help="Penalty for a wrong answer.")
    parser.add_argument("-u", "--unanswered", type=int, default=0, help="Marks for unanswered questions.")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Google multimodal model name. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=6,
        help="Fallback number of questions to send per page when detection is weak. Default: 6",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Maximum retry attempts for LLM calls. Default: 5",
    )
    parser.add_argument(
        "--render-zoom",
        type=float,
        default=2.0,
        help="PDF render zoom factor for page PNGs. Default: 2.0",
    )
    return parser


if __name__ == "__main__":
    parser = build_parser()
    argcomplete.autocomplete(parser)
    cli_args = parser.parse_args()

    output_path = build_database(cli_args)
    print(f"Done. Final database written to {output_path}")
