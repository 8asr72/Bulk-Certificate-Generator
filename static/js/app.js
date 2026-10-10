/**
 * AeroCert Bulk Certificate Generation Studio - Client Application
 */

const API_BASE = '/api/v1';
const API_KEY = 'dev-test-api-key-bulk-cert-platform';

const state = {
  templates: [],
  selectedTemplate: null,
  activeJobs: [],
  currentJobId: null,
  pollingInterval: null,
};

// UI Elements
const elements = {
  templateSelect: document.getElementById('template-select'),
  previewRecipient: document.getElementById('preview-recipient'),
  previewTitle: document.getElementById('preview-title'),
  previewIssuer: document.getElementById('preview-issuer'),
  previewDate: document.getElementById('preview-date'),
  recipientsContainer: document.getElementById('recipients-container'),
  btnAddRow: document.getElementById('btn-add-row'),
  btnLoadDemo: document.getElementById('btn-load-demo'),
  btnGenerate: document.getElementById('btn-generate'),
  fileInput: document.getElementById('file-input'),
  dropzone: document.getElementById('dropzone'),
  methodFormBtn: document.getElementById('method-form-btn'),
  methodUploadBtn: document.getElementById('method-upload-btn'),
  formMethodSection: document.getElementById('form-method-section'),
  uploadMethodSection: document.getElementById('upload-method-section'),
  jobsContainer: document.getElementById('jobs-container'),
  verifyInput: document.getElementById('verify-code-input'),
  btnVerify: document.getElementById('btn-verify'),
  verifyResult: document.getElementById('verify-result'),
  statTotalIssued: document.getElementById('stat-total-issued'),
  statActiveTemplates: document.getElementById('stat-active-templates'),
  statSystemHealth: document.getElementById('stat-system-health'),
};

// Helper: Toast Notifications
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span> <span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// 1. Navigation & Tabs
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const targetId = btn.getAttribute('data-tab');
      const target = document.getElementById(targetId);
      if (target) target.classList.add('active');
    });
  });

  // Method Switcher in Studio
  elements.methodFormBtn.addEventListener('click', () => {
    elements.methodFormBtn.classList.add('active');
    elements.methodUploadBtn.classList.remove('active');
    elements.formMethodSection.style.display = 'block';
    elements.uploadMethodSection.style.display = 'none';
  });

  elements.methodUploadBtn.addEventListener('click', () => {
    elements.methodUploadBtn.classList.add('active');
    elements.methodFormBtn.classList.remove('active');
    elements.formMethodSection.style.display = 'none';
    elements.uploadMethodSection.style.display = 'block';
  });
}

// 2. Fetch Templates
async function loadTemplates() {
  try {
    const res = await fetch(`${API_BASE}/templates/`, {
      headers: { 'X-API-Key': API_KEY }
    });
    if (!res.ok) throw new Error('Failed to fetch templates');
    const data = await res.json();
    state.templates = data;
    elements.statActiveTemplates.textContent = data.length;

    elements.templateSelect.innerHTML = '';
    data.forEach(tpl => {
      const opt = document.createElement('option');
      opt.value = tpl.id;
      opt.textContent = `${tpl.name} (v${tpl.version})`;
      elements.templateSelect.appendChild(opt);
    });

    if (data.length > 0) {
      state.selectedTemplate = data[0];
      updateLivePreview();
    }
  } catch (err) {
    console.error(err);
    showToast('Failed to load certificate templates', 'error');
  }
}

// 3. Live Preview Synchronizer
function updateLivePreview() {
  if (state.selectedTemplate) {
    elements.previewTitle.textContent = state.selectedTemplate.title;
    elements.previewIssuer.textContent = state.selectedTemplate.issuer_name;
  }
  const firstRow = elements.recipientsContainer.querySelector('.recipient-row');
  if (firstRow) {
    const nameInput = firstRow.querySelector('.input-name');
    elements.previewRecipient.textContent = nameInput && nameInput.value.trim() ? nameInput.value.trim() : 'Jane Doe';
  }
  const today = new Date().toISOString().split('T')[0];
  elements.previewDate.textContent = `Issued on: ${today}`;
}

// 4. Recipient Form Builder
function createRecipientRow(name = '', email = '', ref = '') {
  const row = document.createElement('div');
  row.className = 'recipient-row';
  row.innerHTML = `
    <input type="text" class="input-name" placeholder="Full Name" value="${name}" required />
    <input type="email" class="input-email" placeholder="recipient@example.com" value="${email}" required />
    <input type="text" class="input-ref" placeholder="Ref (e.g. ID-001)" value="${ref}" />
    <button type="button" class="btn-remove-row" title="Remove">&times;</button>
  `;

  row.querySelector('.input-name').addEventListener('input', updateLivePreview);
  row.querySelector('.btn-remove-row').addEventListener('click', () => {
    if (elements.recipientsContainer.querySelectorAll('.recipient-row').length > 1) {
      row.remove();
      updateLivePreview();
    } else {
      showToast('At least one recipient row is required', 'info');
    }
  });

  elements.recipientsContainer.appendChild(row);
  updateLivePreview();
}

function loadDemoRecipients() {
  elements.recipientsContainer.innerHTML = '';
  const demos = [
    { name: 'Dr. Evelyn Reed', email: 'evelyn.reed@example.com', ref: 'ACAD-2026-01' },
    { name: 'Prof. Alexander Montgomery Featherstone-Smythe III', email: 'alex.featherstone@example.com', ref: 'ACAD-2026-02' },
    { name: 'Marcus Aurelius Sterling', email: 'marcus.sterling@example.com', ref: 'ACAD-2026-03' },
    { name: 'Elena Rostova', email: 'elena.rostova@example.com', ref: 'ACAD-2026-04' }
  ];
  demos.forEach(d => createRecipientRow(d.name, d.email, d.ref));
  showToast('Loaded 4 demonstration recipients', 'success');
}

// 5. File Upload Handling
function initFileUpload() {
  const dropzone = elements.dropzone;
  const fileInput = elements.fileInput;

  dropzone.addEventListener('click', () => fileInput.click());
  
  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      handleFileSelected(fileInput.files[0]);
    }
  });
}

function handleFileSelected(file) {
  const allowed = ['.csv', '.xlsx'];
  const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
  if (!allowed.includes(ext)) {
    showToast(`Invalid file type: ${file.name}. Only .csv or .xlsx accepted.`, 'error');
    return;
  }
  document.getElementById('selected-file-name').textContent = `Ready: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
  showToast(`Attached file: ${file.name}`, 'info');
}

// 6. Certificate Generation Submissions
async function submitGenerationJob() {
  const isUploadMode = elements.methodUploadBtn.classList.contains('active');
  const templateId = elements.templateSelect.value;
  const policy = document.getElementById('acceptance-policy').value;

  if (!templateId) {
    showToast('Please select a valid certificate template', 'error');
    return;
  }

  elements.btnGenerate.disabled = true;
  elements.btnGenerate.innerHTML = '<span>Processing...</span>';

  try {
    let result;
    if (isUploadMode) {
      const file = elements.fileInput.files[0];
      if (!file) throw new Error('Please select or drop a CSV/XLSX file first');

      const formData = new FormData();
      formData.append('file', file);
      formData.append('template_id', templateId);
      formData.append('acceptance_policy', policy);

      const res = await fetch(`${API_BASE}/certificates/upload`, {
        method: 'POST',
        headers: { 'X-API-Key': API_KEY },
        body: formData
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.message || 'File upload failed');
      }
      result = await res.json();
    } else {
      const rows = elements.recipientsContainer.querySelectorAll('.recipient-row');
      const recipients = [];
      rows.forEach(r => {
        const name = r.querySelector('.input-name').value.trim();
        const email = r.querySelector('.input-email').value.trim();
        const ref = r.querySelector('.input-ref').value.trim();
        if (name && email) {
          recipients.push({ name, email, external_reference: ref || null });
        }
      });

      if (recipients.length === 0) throw new Error('Add at least one recipient with Name and Email');

      const payload = {
        template_id: templateId,
        acceptance_policy: policy,
        recipients
      };

      const res = await fetch(`${API_BASE}/certificates/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': API_KEY
        },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.message || 'Generation failed');
      }
      result = await res.json();
    }

    showToast(`Batch submitted! Job ID: ${result.job_id.substring(0, 8)}...`, 'success');
    
    // Switch to Jobs tab and monitor
    document.querySelector('[data-tab="tab-jobs"]').click();
    trackJob(result.job_id);

  } catch (err) {
    console.error(err);
    showToast(err.message || 'Failed to submit batch job', 'error');
  } finally {
    elements.btnGenerate.disabled = false;
    elements.btnGenerate.innerHTML = '<span>Generate Certificates Now</span>';
  }
}

// 7. Live Job Tracker & Status Polling
async function trackJob(jobId) {
  state.currentJobId = jobId;
  await pollJobStatus(jobId);

  if (state.pollingInterval) clearInterval(state.pollingInterval);
  state.pollingInterval = setInterval(async () => {
    const isDone = await pollJobStatus(jobId);
    if (isDone) {
      clearInterval(state.pollingInterval);
    }
  }, 1500);
}

async function pollJobStatus(jobId) {
  try {
    const res = await fetch(`${API_BASE}/certificates/jobs/${jobId}`, {
      headers: { 'X-API-Key': API_KEY }
    });
    if (!res.ok) return true;
    const job = await res.json();
    renderJobCard(job);

    const isTerminal = ['COMPLETED', 'PARTIAL_SUCCESS', 'FAILED'].includes(job.status);
    if (isTerminal) {
      updateTotalStats();
      return true;
    }
    return false;
  } catch (e) {
    console.error('Polling error', e);
    return true;
  }
}

function renderJobCard(job) {
  let card = document.getElementById(`job-card-${job.id}`);
  if (!card) {
    card = document.createElement('div');
    card.id = `job-card-${job.id}`;
    card.className = 'job-card';
    elements.jobsContainer.prepend(card);
  }

  const badgeClass = job.status === 'COMPLETED' ? 'badge-completed'
    : job.status === 'PROCESSING' ? 'badge-processing'
    : job.status === 'FAILED' ? 'badge-failed'
    : 'badge-pending';

  const recipientRows = (job.recipients || []).map(r => `
    <tr>
      <td><strong>${r.name}</strong></td>
      <td>${r.email}</td>
      <td><code>${r.certificate_number || 'Pending'}</code></td>
      <td>
        <span class="badge ${r.status === 'SUCCESS' ? 'badge-success' : r.status === 'FAILED' ? 'badge-failed' : 'badge-pending'}">
          ${r.status}
        </span>
      </td>
      <td>
        ${r.status === 'SUCCESS' ? `
          <a href="${API_BASE}/certificates/${r.id}/download" class="btn btn-sm btn-primary" download>
            📥 Download PDF
          </a>
        ` : (r.error_message ? `<span style="color:var(--color-error); font-size:0.75rem;">${r.error_message}</span>` : '—')}
      </td>
    </tr>
  `).join('');

  card.innerHTML = `
    <div class="job-card-header">
      <div>
        <span class="job-id-tag">Job: ${job.id}</span>
        <span class="badge ${badgeClass}" style="margin-left:0.5rem;">${job.status}</span>
      </div>
      <div style="display:flex; gap:0.5rem;">
        ${job.successful_records > 0 ? `
          <a href="${API_BASE}/certificates/jobs/${job.id}/download-all" class="btn btn-sm btn-success" download>
            📦 Download All (ZIP)
          </a>
        ` : ''}
        ${job.failed_records > 0 ? `
          <a href="${API_BASE}/certificates/jobs/${job.id}/failures.csv" class="btn btn-sm btn-secondary" download>
            ⚠️ Failure Report (CSV)
          </a>
        ` : ''}
      </div>
    </div>

    <div style="display:flex; justify-content:space-between; font-size:0.84rem; color:var(--text-muted);">
      <span>Progress: ${job.progress_percentage}% (${job.successful_records} of ${job.total_records} successful)</span>
      <span>Created: ${new Date(job.created_at).toLocaleTimeString()}</span>
    </div>

    <div class="progress-track">
      <div class="progress-fill" style="width: ${job.progress_percentage}%"></div>
    </div>

    <div class="data-table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th>Recipient Name</th>
            <th>Email</th>
            <th>Serial Number</th>
            <th>Status</th>
            <th>Deliverable</th>
          </tr>
        </thead>
        <tbody>
          ${recipientRows}
        </tbody>
      </table>
    </div>
  `;
}

async function updateTotalStats() {
  try {
    const res = await fetch('/health/ready');
    if (res.ok) {
      elements.statSystemHealth.textContent = 'Operational';
      elements.statSystemHealth.style.color = 'var(--color-success)';
    }
  } catch (e) {}
}

// 8. Public Verification Tool
async function verifyCertificateCode() {
  const code = elements.verifyInput.value.trim();
  if (!code) {
    showToast('Enter a valid verification code', 'error');
    return;
  }

  elements.btnVerify.disabled = true;
  elements.btnVerify.textContent = 'Verifying...';

  try {
    const res = await fetch(`${API_BASE}/certificates/verify/${encodeURIComponent(code)}`);
    const data = await res.json();

    if (data.valid) {
      elements.verifyResult.innerHTML = `
        <div class="verified-credential-card">
          <div class="verified-badge">✓ OFFICIALLY VERIFIED & AUTHENTIC</div>
          <h2 style="font-family:var(--font-heading); font-size:1.5rem; margin-bottom:0.25rem;">${data.title}</h2>
          <p style="color:var(--text-muted); font-size:0.88rem; margin-bottom:1.5rem;">Issued by <strong>${data.issuer_name}</strong></p>
          
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem; font-size:0.88rem; border-top:1px solid rgba(255,255,255,0.08); padding-top:1rem;">
            <div>
              <span style="color:var(--text-dim); display:block; font-size:0.75rem;">RECIPIENT NAME</span>
              <strong style="font-size:1.1rem; color:var(--text-main);">${data.recipient_name}</strong>
            </div>
            <div>
              <span style="color:var(--text-dim); display:block; font-size:0.75rem;">CERTIFICATE NUMBER</span>
              <code style="color:var(--primary-cyan); font-weight:700;">${data.certificate_number}</code>
            </div>
            <div>
              <span style="color:var(--text-dim); display:block; font-size:0.75rem;">ISSUE DATE</span>
              <span>${data.issue_date}</span>
            </div>
            <div>
              <span style="color:var(--text-dim); display:block; font-size:0.75rem;">VERIFIED TIMESTAMP</span>
              <span>${new Date(data.verified_at).toLocaleString()}</span>
            </div>
          </div>
        </div>
      `;
      showToast('Certificate verified successfully!', 'success');
    } else {
      elements.verifyResult.innerHTML = `
        <div class="verified-credential-card" style="border-color:var(--color-error); background:rgba(239,68,68,0.08);">
          <div class="verified-badge" style="background:rgba(239,68,68,0.15); color:var(--color-error); border-color:rgba(239,68,68,0.3);">
            ✕ UNVERIFIED OR INVALID CREDENTIAL
          </div>
          <p style="color:var(--text-muted); font-size:0.9rem;">No active certificate matches this code in our cryptographic registry.</p>
        </div>
      `;
      showToast('Certificate not found or invalid', 'error');
    }
  } catch (err) {
    console.error(err);
    showToast('Failed to reach verification service', 'error');
  } finally {
    elements.btnVerify.disabled = false;
    elements.btnVerify.textContent = 'Verify Credential';
  }
}

// Initialization
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initFileUpload();
  loadTemplates();

  createRecipientRow('Jane Doe', 'jane.doe@example.com', 'REF-2026-001');

  elements.btnAddRow.addEventListener('click', () => createRecipientRow());
  elements.btnLoadDemo.addEventListener('click', loadDemoRecipients);
  elements.btnGenerate.addEventListener('click', submitGenerationJob);
  elements.btnVerify.addEventListener('click', verifyCertificateCode);
  elements.templateSelect.addEventListener('change', () => {
    state.selectedTemplate = state.templates.find(t => t.id === elements.templateSelect.value);
    updateLivePreview();
  });

  updateTotalStats();
});
