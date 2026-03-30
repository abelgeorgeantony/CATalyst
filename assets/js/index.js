document.addEventListener("DOMContentLoaded", () => {

    // DOM Elements
    const els = {
        testSelect: document.getElementById('test-select'),
        yearSelect: document.getElementById('year-select'),
        testDetails: document.getElementById("test-details-log"),
        startBtn: document.getElementById('start-btn'),
        errorLog: document.getElementById('error-log')
    };

    let examMetadata = [];

    // Initialize
    fetchMetadata();

    function fetchMetadata() {
        fetch('assets/data/json/metadata.json')
            .then(response => {
                if (!response.ok) throw new Error("Metadata file not found or inaccessible.");
                return response.json();
            })
            .then(data => {
                examMetadata = data;
                console.log(examMetadata)
                populateTestCodes();
            })
            .catch(err => {
                showError(`SYSTEM FAILURE: ${err.message}`);
                els.testSelect.innerHTML = '<option value="">-- OFFLINE --</option>';
            });
    }

    // Call this from fetchMetadata() instead of populateYears()
    function populateTestCodes() {
        // Extract unique test codes to avoid duplicates in the dropdown
        const uniqueTests = [];
        const seenCodes = new Set();

        examMetadata.forEach(item => {
            if (!seenCodes.has(item.test_code)) {
                seenCodes.add(item.test_code);
                uniqueTests.push({ code: item.test_code, name: item.course_name });
            }
        });

        els.testSelect.innerHTML = '<option value="">-- Select Test Code --</option>';

        uniqueTests.forEach(test => {
            const opt = document.createElement('option');
            opt.value = test.code;
            opt.innerText = `${test.code} (${test.name})`;
            els.testSelect.appendChild(opt);
        });

        els.testSelect.disabled = false;
    }

    // Handle Test Code Selection
    els.testSelect.addEventListener('change', (e) => {
        const selectedCode = e.target.value;

        if (!selectedCode) {
            els.startBtn.disabled = true;
            els.testDetails.innerHTML = "";
            els.yearSelect.disabled = true;
            els.yearSelect.innerHTML = '<option value="">Waiting for test selection...</option>';
            return;
        }

        // Filter metadata to find all years where this specific test was conducted
        const availableYears = examMetadata.filter(item => item.test_code == selectedCode);

        // Sort years descending (newest first)
        availableYears.sort((a, b) => b.year - a.year);

        els.yearSelect.innerHTML = '<option value="">-- Select Year --</option>';
        availableYears.forEach(test => {
            const opt = document.createElement('option');
            // Store the JSON filename on the year option now
            opt.value = test.filename;
            // Attach metadata as data attributes
            opt.dataset.totalQuestions = test.total_questions;
            opt.dataset.totalTime = test.total_time;
            opt.dataset.maximumMarks = test.maximum_marks;
            if (test.marking_scheme) {
                opt.dataset.reward = test.marking_scheme.reward;
                opt.dataset.penalty = test.marking_scheme.penalty;
                opt.dataset.unanswered = test.marking_scheme.unanswered;
            }
            opt.innerText = test.year;
            els.yearSelect.appendChild(opt);
        });

        els.yearSelect.disabled = false;
    });

    // Handle Year Selection
    els.yearSelect.addEventListener('change', (e) => {
        if (e.target.value) {
            const selectedOption = e.target.options[e.target.selectedIndex];
            const meta = selectedOption.dataset;

            const duration = { hours: (parseInt(meta.totalTime) / 60), minutes: (parseInt(meta.totalTime) % 60) };
            const formatter = new Intl.DurationFormat("en-US", { style: "short" });
            const totaltime = formatter.format(duration);
            els.testDetails.innerHTML = "Total questions: " + meta.totalQuestions + "<br>Total time: " + totaltime + "<br>Maximum marks: " + meta.maximumMarks + "<br>Reward for correct answer: " + meta.reward + "<br>Penalty for wrong answer: " + meta.penalty + "<br>For skipping: " + meta.unanswered;

            // Because we stored the filename in the year's value, the Start button is ready
            els.startBtn.disabled = false;
        } else {
            els.testDetails.innerHTML = "";
            els.startBtn.disabled = true;
        }
    });

    // Handle Submission
    els.startBtn.addEventListener('click', () => {
        // Now grab the target JSON from the yearSelect element instead of testSelect
        const targetJson = els.yearSelect.value;
        if (targetJson) {
            window.location.href = `practice.html?paper=${encodeURIComponent(targetJson)}`;
        }
    });

    function showError(msg) {
        els.errorLog.style.display = 'block';
        els.errorLog.innerText = msg;
    }
});