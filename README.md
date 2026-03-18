# CATalyst

This project aims to be a practice ground for me to get a good rank in CUSAT CAT(MCA).

Will I become a laughing stock for doing crazy things like this and still not getting into cusat? Only time will tell...\
The worst case that can happen when you do something improbable is the same as if you hadn't done anything, but the best case might surprise you!


## To use this software
Most people would only need to start the deno server:
```bash
git clone https://github.com/abelgeorgeantony/CATalyst.git
```
```bash
cd CATalyst
```
```bash
deno run server.ts
```
And then open `localhost:8080` in a web browser.

## Setup and Dependencies

To utilize the PDF conversion scripts provided in this repository, you will need to install `poppler-utils`. On Debian-based systems, you can install this via the command line:

    sudo apt install poppler-utils

**Important note regarding `pdftotext`:**
Depending on your specific package version, the `pdftotext` utility included with `poppler-utils` may not support the `-nodiag` flag. If you encounter an unrecognized flag error during execution, you will need to manually remove or bypass the `-nodiag` flag in the relevant Python conversion scripts before running them.

## Adding Custom Questions and Answers

To add custom questions and answers that are not currently included in this repository:

If you are trying to add a previous year question paper officially provided by CUSAT, you first need to convert the PDF into a suitable form/structure for the application to use. 
* Please refer to [the JSON schema](./assets/data/pyq_schema.json) for the required format. 
* You should also take a look at the already [formatted data](./assets/data/json/) to understand the expected structure.

### PDF conversions

I have already provided some Python scripts that will help in converting the PDFs to the JSON structure. However, manual human analysis is still required to maintain the robustness of the data.

* **Standard PDFs:** If the PDF has interactable/selectable text, the scripts can process it.
* **Scanned or Low-Quality PDFs:** If the content/text in the PDF is not interactable/selectable, or if the content is of low quality, then the scripts are of no use to you. In these cases, you must use OCR to extract the text content.