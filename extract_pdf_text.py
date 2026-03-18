import os
import argparse
import subprocess
import sys

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

    # Determine file paths (this will automatically resolve to assets/data/raw/)
    dir_name = os.path.dirname(input_pdf) or '.'
    base_name = os.path.splitext(os.path.basename(input_pdf))[0]
    
    questions_output = os.path.join(dir_name, f"{base_name}_questions.txt")
    answers_output = os.path.join(dir_name, f"{base_name}_answers.txt")

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

    print("\nExtraction Complete! Before running the JSON parser and Answer Injector you must ABSOLUTELY make sure the text files came out nicely.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract questions and answers from a PDF using pdftotext.")
    
    parser.add_argument("-i", "--input", required=True, help="Filename of the input PDF (script will look in assets/data/raw/)")
    parser.add_argument("-qf", "--q-first", type=int, default=1, help="First page of the questions (Default: 1)")
    parser.add_argument("-ql", "--q-last", type=int, required=True, help="Last page of the questions (Required)")
    parser.add_argument("-af", "--a-first", type=int, help="First page of the answers (Defaults to q-last + 1)")
    parser.add_argument("-al", "--a-last", type=int, help="Last page of the answers (Optional, defaults to the end of the document)")

    args = parser.parse_args()

    # Automatically prepend the directory path
    input_filepath = os.path.join("assets", "data", "raw", args.input)

    # Automatically calculate the first page of answers if not explicitly provided
    ans_first = args.a_first if args.a_first else (args.q_last + 1)

    extract_pdf(
        input_pdf=input_filepath,
        q_first=args.q_first,
        q_last=args.q_last,
        a_first=ans_first,
        a_last=args.a_last
    )