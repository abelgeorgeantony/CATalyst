document.addEventListener("DOMContentLoaded", () => {
  
  const ExamState = {
    paperData: null,
    questions: [],
    currentIndex: 0,
    userAnswers: {}, // key: question_number, value: 'A', 'B', 'C', 'D'
    timeRemainingSec: 0,
    timerInterval: null
  };

  // DOM Elements
  const els = {
    loadingScreen: document.getElementById('loading-screen'),
    errorScreen: document.getElementById('error-screen'),
    errorMessage: document.getElementById('error-message'),
    examContainer: document.getElementById('exam-container'),
    resultsScreen: document.getElementById('results-screen'),
    
    examTitle: document.getElementById('exam-title'),
    examTimer: document.getElementById('exam-timer'),
    
    qNumber: document.getElementById('q-number'),
    qDirection: document.getElementById('q-direction'),
    qStem: document.getElementById('q-stem'),
    qImages: document.getElementById('q-images'),
    optionsPanel: document.getElementById('options-panel'),
    optionButtons: document.querySelectorAll('.option-block'),
    
    btnPrev: document.getElementById('btn-prev'),
    btnNext: document.getElementById('btn-next'),
    btnClear: document.getElementById('btn-clear'),
    btnSubmit: document.getElementById('btn-submit')
  };

  function init() {
    const urlParams = new URLSearchParams(window.location.search);
    const paperFile = urlParams.get('paper');

    if (!paperFile) {
      showError("NO PAPER SPECIFIED IN URL PARAMETERS.");
      return;
    }

    const dataUrl = `assets/data/json/${paperFile}`;
    
    fetch(dataUrl)
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status} - File not found.`);
        return response.json();
      })
      .then(data => {
        ExamState.paperData = data.paper_metadata;
        ExamState.questions = data.questions;
        ExamState.timeRemainingSec = data.paper_metadata.total_time * 60;
        
        setupExam();
      })
      .catch(err => {
        showError(`FAILED TO LOAD DATA: ${err.message}`);
      });
  }

  function setupExam() {
    els.loadingScreen.classList.add('hidden');
    els.examContainer.classList.remove('hidden');

    const meta = ExamState.paperData;
    els.examTitle.innerText = `${meta.year} ${meta.course_name} (${meta.test_code})`;

    // Event Listeners
    els.btnPrev.addEventListener('click', () => navigate(-1));
    els.btnNext.addEventListener('click', () => navigate(1));
    els.btnClear.addEventListener('click', clearSelection);
    els.btnSubmit.addEventListener('click', () => {
      if(confirm("ARE YOU SURE YOU WANT TO SUBMIT?")) submitExam();
    });

    els.optionButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const optionKey = btn.getAttribute('data-option');
        selectOption(optionKey);
      });
    });

    startTimer();
    renderQuestion();
  }

  function renderQuestion() {
    const q = ExamState.questions[ExamState.currentIndex];
    
    // Update Badge
    els.qNumber.innerText = `Q. ${q.question_number} / ${ExamState.paperData.total_questions}`;

    // Direction & Stem
    els.qDirection.innerText = q.question.direction ? `Direction: ${q.question.direction}` : "";
    els.qStem.innerHTML = q.question.stem ? q.question.stem.replace(/\n/g, "<br>") : "";

    // Images
    els.qImages.innerHTML = "";
    if (q.question.images && q.question.images.length > 0) {
      q.question.images.forEach(imgSrc => {
        const img = document.createElement('img');
        img.src = imgSrc;
        img.className = 'question-image';
        els.qImages.appendChild(img);
      });
    }

    // Options
    els.optionButtons.forEach(btn => {
      const optKey = btn.getAttribute('data-option');
      const optData = q.options ? q.options[optKey] : null;
      const contentSpan = btn.querySelector('.option-content');
      
      contentSpan.innerHTML = "";
      btn.classList.remove('selected');

      if (optData) {
        if (optData.text) {
          contentSpan.innerText = optData.text;
        }
        if (optData.image) {
          const img = document.createElement('img');
          img.src = optData.image;
          img.className = 'option-image';
          contentSpan.appendChild(img);
        }
      }

      // Highlight if previously selected
      if (ExamState.userAnswers[q.question_number] === optKey) {
        btn.classList.add('selected');
      }
    });

    // Navigation state
    els.btnPrev.disabled = (ExamState.currentIndex === 0);
    els.btnNext.disabled = (ExamState.currentIndex === ExamState.questions.length - 1);
  }

  function selectOption(optionKey) {
    const q = ExamState.questions[ExamState.currentIndex];
    ExamState.userAnswers[q.question_number] = optionKey;
    renderQuestion(); // Re-render to update the highlight
  }

  function clearSelection() {
    const q = ExamState.questions[ExamState.currentIndex];
    delete ExamState.userAnswers[q.question_number];
    renderQuestion();
  }

  function navigate(direction) {
    const newIndex = ExamState.currentIndex + direction;
    if (newIndex >= 0 && newIndex < ExamState.questions.length) {
      ExamState.currentIndex = newIndex;
      renderQuestion();
    }
  }

  function startTimer() {
    ExamState.timerInterval = setInterval(() => {
      if (ExamState.timeRemainingSec <= 0) {
        clearInterval(ExamState.timerInterval);
        submitExam();
        return;
      }
      
      ExamState.timeRemainingSec--;
      
      const h = Math.floor(ExamState.timeRemainingSec / 3600).toString().padStart(2, '0');
      const m = Math.floor((ExamState.timeRemainingSec % 3600) / 60).toString().padStart(2, '0');
      const s = (ExamState.timeRemainingSec % 60).toString().padStart(2, '0');
      
      els.examTimer.innerText = `${h}:${m}:${s}`;
    }, 1000);
  }

  function submitExam() {
    clearInterval(ExamState.timerInterval);
    els.examContainer.classList.add('hidden');
    els.resultsScreen.classList.remove('hidden');

    let totalScore = 0;
    let correctCount = 0;
    let incorrectCount = 0;
    let unansweredCount = 0;

    const scheme = ExamState.paperData.marking_scheme;

    ExamState.questions.forEach(q => {
      const uAnswer = ExamState.userAnswers[q.question_number];
      const cAnswer = q.correct_answer;

      if (!uAnswer) {
        unansweredCount++;
        totalScore += scheme.unanswered;
      } else if (uAnswer === cAnswer) {
        correctCount++;
        totalScore += scheme.reward;
      } else if (cAnswer !== null) { 
        // Penalize only if there is a valid correct answer defined in the db
        incorrectCount++;
        totalScore += scheme.penalty;
      }
    });

    console.log("============== EXAM RESULTS ==============");
    console.log(`Total Questions: ${ExamState.paperData.total_questions}`);
    console.log(`Attempted: ${correctCount + incorrectCount}`);
    console.log(`Correct: ${correctCount}`);
    console.log(`Incorrect: ${incorrectCount}`);
    console.log(`Unanswered: ${unansweredCount}`);
    console.log(`FINAL SCORE: ${totalScore} / ${ExamState.paperData.maximum_marks}`);
    console.log("==========================================");
  }

  function showError(msg) {
    els.loadingScreen.classList.add('hidden');
    els.examContainer.classList.add('hidden');
    els.errorScreen.classList.remove('hidden');
    els.errorMessage.innerText = msg;
  }

  // Boot
  init();

});