// frontend/js/upload.js
import { uploadPaper } from './api.js';

export function initUpload(dropZoneEl, onResult, onError) {
  // Drag-over styling
  dropZoneEl.addEventListener('dragover', e => {
    e.preventDefault();
    dropZoneEl.classList.add('drag-over');
  });
  dropZoneEl.addEventListener('dragleave', () => {
    dropZoneEl.classList.remove('drag-over');
  });

  // Drop handler
  dropZoneEl.addEventListener('drop', async e => {
    e.preventDefault();
    dropZoneEl.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (!file || !file.name.endsWith('.pdf')) {
      onError('Hanya file PDF yang diterima.');
      return;
    }
    await _process(file, onResult, onError, dropZoneEl);
  });

  // Click-to-browse
  dropZoneEl.querySelector('#browse-btn')?.addEventListener('click', () => {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = '.pdf';
    input.onchange = async e => {
      const file = e.target.files[0];
      if (file) await _process(file, onResult, onError, dropZoneEl);
    };
    input.click();
  });
}

async function _process(file, onResult, onError, el) {
  _setLoading(el, true, file.name);
  try {
    const result = await uploadPaper(file);
    _setLoading(el, false);
    onResult(result);
  } catch (err) {
    _setLoading(el, false);
    onError(err.message);
  }
}

function _setLoading(el, loading, filename = '') {
  const label = el.querySelector('.upload-label');
  if (!label) return;
  if (loading) {
    label.innerHTML = `
      <div class="upload-spinner"></div>
      <div>Memproses <strong>${filename}</strong>…</div>
      <div class="upload-sub">Ekstraksi LLM sedang berjalan</div>
    `;
  } else {
    label.innerHTML = `
      <div class="upload-icon"></div>
      <div>Drag & drop PDF di sini</div>
      <div class="upload-sub">atau <button id="browse-btn">pilih file</button></div>
    `;
  }
}