#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

import os
import argparse
import subprocess
import sys
import argcomplete

# 1. Get the absolute path of the directory containing this script (e.g., /.../CATalyst/scripts)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 2. Go one level up to find the project root (e.g., /.../CATalyst)
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
# 3. Build your asset paths absolutely from the project root
DATA_DIR = os.path.join(PROJECT_ROOT, "assets", "data")

# --- Custom Completer ---
def pdf_file_completer(prefix, parsed_args, **kwargs):
    """Suggests only .pdf files from the assets/data/raw directory."""
    target_dir = os.path.join(DATA_DIR, "raw")
    if not os.path.exists(target_dir):
        return []
    return [f for f in os.listdir(target_dir) if f.lower().endswith('.pdf') and f.startswith(prefix)]


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

def extract_pdf(input_pdf, q_first, q_last, a_first, a_last):
    # Ensure the input file exists
    if not os.path.exists(input_pdf):
        print(f"Error: The file '{input_pdf}' does not exist.")
        sys.exit(1)

    
    base_name = os.path.splitext(os.path.basename(input_pdf))[0]
    questions_output = os.path.join(DATA_DIR, "raw", f"{base_name}_questions.txt")
    answers_output = os.path.join(DATA_DIR, "raw", f"{base_name}_answers.txt")

    print(f"Processing '{input_pdf}'...")

    # --- 1. Extract Questions ---
    print(f"Extracting Questions (Pages {q_first} to {q_last})...")
    q_args = [
        "-layout", 
        "-nodiag", 
        "-f", str(q_first), 
        "-l", str(q_last), 
        input_pdf, 
        questions_output
    ]
    run_pdftotext(q_args)
    print(f"  -> Saved to {questions_output}")

    # --- 2. Extract Answers ---
    a_last_str = str(a_last) if a_last else "End"
    print(f"Extracting Answers (Pages {a_first} to {a_last_str})...")
    
    a_args = [
        "-nodiag", 
        "-f", str(a_first)
    ]
    # If a_last is provided, append it. Otherwise, pdftotext extracts to the end of the document.
    if a_last:
        a_args.extend(["-l", str(a_last)])
        
    a_args.extend([input_pdf, answers_output])
    
    run_pdftotext(a_args)
    print(f"  -> Saved to {answers_output}")

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
                        help="Filename of the input PDF (script will look in assets/data/raw/)").completer = pdf_file_completer
                        
    parser.add_argument("-qf", "--q-first", type=int, default=1, help="First page of the questions (Default: 1)")
    parser.add_argument("-ql", "--q-last", type=int, required=True, help="Last page of the questions (Required)")
    parser.add_argument("-af", "--a-first", type=int, help="First page of the answers (Defaults to q-last + 1)")
    parser.add_argument("-al", "--a-last", type=int, help="Last page of the answers (Optional, defaults to the end of the document)")

    # CRITICAL: Trigger autocomplete before parse_args
    argcomplete.autocomplete(parser)

    args = parser.parse_args()
    
    # Automatically prepend the directory path
    input_filepath = os.path.join(DATA_DIR, "raw", args.input)

    # Automatically calculate the first page of answers if not explicitly provided
    ans_first = args.a_first if args.a_first else (args.q_last + 1)

    extract_pdf(
        input_pdf=input_filepath,
        q_first=args.q_first,
        q_last=args.q_last,
        a_first=ans_first,
        a_last=args.a_last
    )