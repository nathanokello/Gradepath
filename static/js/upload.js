// ==========================================================================
// upload.js: Drag & drop dataset upload, client validation, report display
// ==========================================================================

document.addEventListener('DOMContentLoaded', () => {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const errorBox = document.getElementById('upload-error');
  const loadingBox = document.getElementById('upload-loading');
  const reportPanel = document.getElementById('upload-report-panel');

  const repFilename = document.getElementById('rep-filename');
  const repTypeText = document.getElementById('rep-type-text');
  const repMetaName = document.getElementById('rep-meta-name');
  const repMetaDetails = document.getElementById('rep-meta-details');
  const repRowsInOut = document.getElementById('rep-rows-in-out');
  const repDups = document.getElementById('rep-dups');
  const repFixed = document.getElementById('rep-fixed');
  const repMissing = document.getElementById('rep-missing');
  const btnDashboard = document.getElementById('btn-open-dashboard');

  // Trigger file browser when dropzone is clicked
  dropzone.addEventListener('click', () => {
    fileInput.click();
  });

  // Drag and drop events
  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('dragover');
    });
  });

  // Handle dropped files
  dropzone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFile(files[0]);
    }
  });

  // Handle selected file from dialog
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      handleFile(fileInput.files[0]);
    }
  });

  // Main file validation and upload pipeline
  async function handleFile(file) {
    errorBox.style.display = 'none';
    reportPanel.style.display = 'none';

    // File extension validation
    const validExtensions = ['.csv', '.xlsx'];
    const fileName = file.name.toLowerCase();
    const isValidExtension = validExtensions.some(ext => fileName.endsWith(ext));

    if (!isValidExtension) {
      errorBox.textContent = 'Invalid file type. Only .csv and .xlsx files are supported.';
      errorBox.style.display = 'flex';
      return;
    }

    // Max 5 MB check
    const maxSizeBytes = 5 * 1024 * 1024;
    if (file.size > maxSizeBytes) {
      errorBox.textContent = 'File exceeds maximum allowed size of 5 MB.';
      errorBox.style.display = 'flex';
      return;
    }

    // Build FormData and submit
    const formData = new FormData();
    formData.append('dataset', file);

    loadingBox.style.display = 'block';

    try {
      const response = await fetch('/upload', {
        method: 'POST',
        body: formData
      });

      const result = await response.json();
      loadingBox.style.display = 'none';

      if (!response.ok || !result.success) {
        errorBox.textContent = result.error || 'Failed to process dataset.';
        errorBox.style.display = 'flex';
        return;
      }

      // Populate cleaning report fields
      const report = result.report;
      repFilename.textContent = report.filename;
      repMetaName.textContent = report.filename;

      if (report.data_type === 2) {
        repTypeText.textContent = 'Type 2 · includes actual GPA & grade';
      } else {
        repTypeText.textContent = 'Type 1 · behavioural factors only';
      }

      repMetaDetails.textContent = `${report.rows_in} rows · ${report.columns_count} columns`;
      repRowsInOut.textContent = `${report.rows_in} → ${report.rows_out}`;
      repDups.textContent = report.duplicates_removed;
      repFixed.textContent = report.values_fixed;
      repMissing.textContent = '0';

      btnDashboard.href = result.redirect_url;
      reportPanel.style.display = 'block';

    } catch (err) {
      loadingBox.style.display = 'none';
      errorBox.textContent = 'Network or server error while uploading file.';
      errorBox.style.display = 'flex';
    }
  }
});

