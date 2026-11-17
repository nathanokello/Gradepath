// ==========================================================================
// predict.js: Client-side interaction for single student GPA prediction
// ==========================================================================

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('predict-form');
  const studyRange = document.getElementById('f-study');
  const studyVal = document.getElementById('f-study-val');
  const resetBtn = document.getElementById('btn-reset');
  const errorBox = document.getElementById('form-error');

  const emptyState = document.getElementById('result-empty');
  const liveState = document.getElementById('result-live');

  const gpaEl = document.getElementById('res-gpa');
  const badgeEl = document.getElementById('res-badge');
  const rangeEl = document.getElementById('res-range');
  const dominantEl = document.getElementById('res-dominant');
  const factorsEl = document.getElementById('res-factors');

  // Update slider numerical readout in real time
  studyRange.addEventListener('input', () => {
    studyVal.textContent = parseFloat(studyRange.value).toFixed(1);
  });

  // Reset form handler
  resetBtn.addEventListener('click', () => {
    form.reset();
    studyVal.textContent = parseFloat(studyRange.value).toFixed(1);
    errorBox.style.display = 'none';
    liveState.style.display = 'none';
    emptyState.style.display = 'flex';
  });

  // Form submission handler
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorBox.style.display = 'none';

    // Gather and parse values
    const payload = {
      StudyTimeWeekly: parseFloat(studyRange.value),
      Absences: parseInt(document.getElementById('f-absences').value, 10),
      ParentalSupport: parseInt(document.getElementById('f-support').value, 10),
      ParentalEducation: parseInt(document.getElementById('f-education').value, 10),
      Tutoring: document.getElementById('f-tutoring').checked ? 1 : 0,
      Extracurricular: document.getElementById('f-extracurricular').checked ? 1 : 0,
      Sports: document.getElementById('f-sports').checked ? 1 : 0,
      Music: document.getElementById('f-music').checked ? 1 : 0,
      Volunteering: document.getElementById('f-volunteering').checked ? 1 : 0
    };

    // Quick client-side check
    if (isNaN(payload.Absences) || payload.Absences < 0 || payload.Absences > 29) {
      errorBox.textContent = 'Absences must be an integer between 0 and 29.';
      errorBox.style.display = 'block';
      return;
    }

    try {
      const response = await fetch('/predict', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        errorBox.textContent = data.error || 'Prediction failed. Please verify your inputs.';
        errorBox.style.display = 'block';
        return;
      }

      // Render the result
      emptyState.style.display = 'none';
      liveState.style.display = 'flex';

      gpaEl.textContent = data.predicted_gpa.toFixed(2);
      badgeEl.textContent = data.letter_grade;
      badgeEl.className = `grade-badge grade-${data.letter_grade}`;

      rangeEl.textContent = `${data.range_min.toFixed(2)} – ${data.range_max.toFixed(2)}`;
      dominantEl.textContent = data.dominant_factor;

      // Render top 4 feature importance meters
      factorsEl.innerHTML = '';
      const topFactors = data.feature_importances.slice(0, 4);

      topFactors.forEach(factor => {
        const factorRow = document.createElement('div');
        factorRow.className = 'factor-row';
        factorRow.innerHTML = `<span>${factor.feature}</span><strong>${factor.percentage}%</strong>`;

        const meter = document.createElement('div');
        meter.className = 'meter';
        meter.style.marginBottom = '8px';
        meter.innerHTML = `<span style="width: ${Math.max(factor.percentage, 4)}%"></span>`;

        factorsEl.appendChild(factorRow);
        factorsEl.appendChild(meter);
      });

    } catch (err) {
      errorBox.textContent = 'Network or server error while predicting GPA.';
      errorBox.style.display = 'block';
    }
  });
});

