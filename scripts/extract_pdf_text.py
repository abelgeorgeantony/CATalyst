#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

import re
import os
import argparse
import subprocess
import sys
import tempfile

try:
    import fitz
except ImportError:
    fitz = None

# Try the standard Python 3.4+ built-in first
try:
    from pathlib import Path
# Fallback to the pip-installed backport for older versions
except ImportError:
    from pathlib2 import Path
import argcomplete
from path_utils import find_project_root, list_relative_files, resolve_under

PROJECT_ROOT = find_project_root(__file__)
DATA_DIR = PROJECT_ROOT / "assets" / "data"

def pdf_file_completer(prefix, parsed_args, **kwargs):
    """Suggests any .pdf files from the assets/data/raw/pyqs/<year>/ directories."""
    target_dir = DATA_DIR / "raw" / "pyqs"
    return [path for path in list_relative_files(target_dir, "*.pdf") if path.startswith(prefix)]


def run_pdftotext(args_list):
    """Executes the pdftotext command and handles errors."""
    try:
        # Run the command and capture output
        subprocess.run(["pdftotext"] + args_list, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        print("Error: 'pdftotext' is not installed or not in your system's PATH.")
        print("Please install poppler-utils (Linux) or XpdfReader (Windows/Mac).")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error executing pdftotext: {e.stderr.decode('utf-8')}")
        sys.exit(1)


def clean_extracted_text_file(filepath):
    """Remove common PDF extraction control-character junk from a text file."""
    with filepath.open("r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    cleaned_content = content.replace("\f", "\n")
    cleaned_content = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", cleaned_content)

    if cleaned_content != content:
        with filepath.open("w", encoding="utf-8") as f:
            f.write(cleaned_content)


def format_answers_file(filepath):
    """Parses the grid layout and formats it strictly with alternating lines."""
    with filepath.open("r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Regex: Find a number, followed by whitespace, followed by A, B, C, or D
    matches = re.findall(r'\b(\d+)\s+([A-D])\b', content, re.IGNORECASE)

    if not matches:
        return

    # Sort the pairs numerically based on the question number
    sorted_matches = sorted(matches, key=lambda x: int(x[0]))

    # Overwrite the file with the strict vertical format
    with filepath.open("w", encoding="utf-8") as f:
        for num, ans in sorted_matches:
            # changed the space to \n here 👇
            f.write(f"{num}\n{ans.upper()}\n")


def create_sanitized_pdf(input_pdf, answer_first_page, answer_last_page):
    """Redact the header area on answer pages and return a temporary PDF path."""
    if fitz is None:
        print("Error: PyMuPDF is required for answer-page redaction but is not installed.")
        print("Install it with: pip install PyMuPDF")
        sys.exit(1)

    temp_pdf_path = None
    doc = None

    try:
        doc = fitz.open(input_pdf)
        page_count = len(doc)

        if page_count == 0:
            raise ValueError("The PDF has no pages.")

        start_idx = answer_first_page - 1
        end_idx = (answer_last_page - 1) if answer_last_page else (page_count - 1)

        if start_idx < 0 or start_idx >= page_count:
            raise ValueError(
                f"Answer start page {answer_first_page} is outside the document page range 1-{page_count}."
            )
        if end_idx < start_idx or end_idx >= page_count:
            last_page_label = answer_last_page if answer_last_page else page_count
            raise ValueError(
                f"Answer end page {last_page_label} is outside the valid range {answer_first_page}-{page_count}."
            )

        for page_num in range(start_idx, end_idx + 1):
            page = doc[page_num]
            header_boxes = page.search_for("SI No") + page.search_for("Key")

            if header_boxes:
                lowest_header_y = max(box.y1 for box in header_boxes)
                dynamic_height = lowest_header_y + 1
                header_rect = fitz.Rect(0, 0, page.rect.width, dynamic_height)
                page.add_redact_annot(header_rect, fill=(1, 1, 1))
                page.apply_redactions()
            else:
                print(
                    f"  -> Warning: Headers not found on page {page_num + 1}. "
                    "Skipping redaction."
                )

        temp_fd, temp_pdf_path = tempfile.mkstemp(suffix=".pdf")
        os.close(temp_fd)
        doc.save(temp_pdf_path)
        return temp_pdf_path

    except Exception as exc:
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)
        print(f"Error preparing sanitized PDF: {exc}")
        sys.exit(1)

    finally:
        if doc is not None:
            doc.close()


def extract_pdf(input_pdf, q_first, q_last, a_first, a_last):
    # Ensure the input file exists
    if not input_pdf.exists():
        print(f"Error: The file '{input_pdf}' does not exist.")
        sys.exit(1)

    if q_first < 1 or q_last < q_first:
        print("Error: Question page range is invalid.")
        sys.exit(1)
    if a_first < 1:
        print("Error: Answer start page must be 1 or greater.")
        sys.exit(1)
    if a_last is not None and a_last < a_first:
        print("Error: Answer end page cannot be earlier than answer start page.")
        sys.exit(1)

    
    # 1. Get the exact directory where the input PDF is located
    pdf_dir = input_pdf.parent
    # 2. Get the filename without the .pdf extension
    base_name = input_pdf.stem
    # 3. Save the text files into that exact same directory
    questions_output = pdf_dir / f"{base_name}_questions.txt"
    answers_output = pdf_dir / f"{base_name}_answers.txt"

    print(f"Processing '{input_pdf}'...")
    a_last_str = str(a_last) if a_last else "End"
    print(f"Sanitizing headers on answer pages ({a_first} to {a_last_str})...")
    temp_pdf_path = create_sanitized_pdf(str(input_pdf), a_first, a_last)

    try:
        # --- 1. Extract Questions ---
        print(f"Extracting Questions (Pages {q_first} to {q_last})...")
        q_args = [
            "-layout", 
            "-nodiag", 
            "-f", str(q_first), 
            "-l", str(q_last), 
            temp_pdf_path, 
            questions_output
        ]
        run_pdftotext(q_args)
        clean_extracted_text_file(questions_output)
        print(f"  -> Saved to {questions_output}")

        # --- 2. Extract Answers ---
        print(f"Extracting Answers (Pages {a_first} to {a_last_str})...")
        
        a_args = [
            "-layout",
            "-nodiag", 
            "-f", str(a_first)
        ]
        # If a_last is provided, append it. Otherwise, pdftotext extracts to the end of the document.
        if a_last:
            a_args.extend(["-l", str(a_last)])
            
        a_args.extend([temp_pdf_path, answers_output])
        
        run_pdftotext(a_args)
        clean_extracted_text_file(answers_output)
        # Format the file perfectly for the DB
        format_answers_file(answers_output)
        print(f"  -> Saved to {answers_output}")
    finally:
        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)

    # --- 3. Print Post-Extraction Instructions ---
    print("\n" + "="*60)
    print(" EXTRACTION COMPLETE! MANUAL VERIFICATION REQUIRED.")
    print("="*60)
    print("Before proceeding, the DB Creator MUST complete these steps:")
    print("\n  1. VERIFY IMAGES:")
    print("     Ensure all pictures, diagrams, and graphical options from")
    print("     the PDF are correctly extracted, cropped, and saved in")
    print("     the specific image directory using the required file format.")
    print("\n  2. CLEAN ANSWERS FILE:")
    print("     Open the generated answers.txt file. Make extra sure it is")
    print("     strictly formatted with ONLY question numbers and their")
    print("     options (e.g., '1 A'). Delete any titles, headers, page")
    print("     numbers, or extraneous text.")
    print("\n  3. REVIEW QUESTIONS FILE:")
    print("     Open the generated questions.txt file and do a quick")
    print("     visual glance to ensure there are no glaring issues,")
    print("     garbled characters, or major formatting errors.")
    print("\nNEXT STEPS:")
    print("Only AFTER all manual checks above are complete, run the")
    print("remaining scripts in this EXACT order:")
    print("  First  -> questions_to_json.py")
    print("  Second -> inject_answers.py")
    print("="*60 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract questions and answers from a PDF using pdftotext.")
    
    # Attach the completer to the input argument
    parser.add_argument("-i", "--input", required=True, 
                        help="Filename of the input PDF (script will look in assets/data/raw/pyqs/)").completer = pdf_file_completer
                        
    parser.add_argument("-qf", "--q-first", type=int, default=1, help="First page of the questions (Default: 1)")
    parser.add_argument("-ql", "--q-last", type=int, required=True, help="Last page of the questions (Required)")
    parser.add_argument("-af", "--a-first", type=int, help="First page of the answers (Defaults to q-last + 1)")
    parser.add_argument("-al", "--a-last", type=int, help="Last page of the answers (Optional, defaults to the end of the document)")

    # CRITICAL: Trigger autocomplete before parse_args
    argcomplete.autocomplete(parser)

    args = parser.parse_args()
    
    # Automatically prepend the directory path
    input_filepath = resolve_under(DATA_DIR / "raw" / "pyqs", args.input)

    # Automatically calculate the first page of answers if not explicitly provided
    ans_first = args.a_first if args.a_first else (args.q_last + 1)

    extract_pdf(
        input_pdf=input_filepath,
        q_first=args.q_first,
        q_last=args.q_last,
        a_first=ans_first,
        a_last=args.a_last
    )
