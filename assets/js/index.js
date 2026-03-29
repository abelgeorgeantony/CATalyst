document.addEventListener("DOMContentLoaded", () => {
    const paperSelect = document.getElementById("paper-select");
    const startBtn = document.getElementById("start-btn");
    const errorLog = document.getElementById("error-log");

    const METADATA_URL = "assets/data/json/metadata.json"; 

    function showError(message) {
        errorLog.textContent = message;
        errorLog.style.display = "block";
    }

    // Fetch the metadata
    fetch(METADATA_URL)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP Error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            paperSelect.innerHTML = ""; 

            if (!Array.isArray(data) || data.length === 0) {
                paperSelect.innerHTML = `<option value="">No papers available</option>`;
                throw new Error("Metadata file is empty or formatted incorrectly.");
            }

            const defaultOption = document.createElement("option");
            defaultOption.value = "";
            defaultOption.textContent = "--- CHOOSE A PAPER ---";
            paperSelect.appendChild(defaultOption);

            // Populate the dropdown dynamically
            data.forEach(paper => {
                const option = document.createElement("option");
                const targetFile = paper.file || `${paper.year}_${paper.course_name}_db.json`;
                
                option.value = targetFile;
                
                const courseLabel = paper.course_name || "Exam";
                const yearLabel = paper.year || "";
                option.textContent = `${courseLabel}(${yearLabel})`;
                
                paperSelect.appendChild(option);
            });

            paperSelect.disabled = false;

            // Enable start button on selection
            paperSelect.addEventListener("change", (e) => {
                startBtn.disabled = !e.target.value;
            });
        })
        .catch(error => {
            console.error("Failed to load papers:", error);
            paperSelect.innerHTML = `<option value="">Error loading papers</option>`;
            showError("Could not load the question papers. Please ensure metadata.json is generated.");
        });

    // Handle Start click
    startBtn.addEventListener("click", () => {
    const selectedFile = paperSelect.value;
    if (selectedFile) {
        // Redirect to the quiz page, passing the filename in the URL
        window.location.href = `practice.html?paper=${encodeURIComponent(selectedFile)}`;
    }
});
});