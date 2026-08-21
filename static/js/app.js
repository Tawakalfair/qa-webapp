/**
 * QA Automata - Main Frontend Application Logic
 */

// Sistem Toast Notification Universal
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    
    let bgColor = 'bg-emerald-600 border-emerald-700';
    let icon = '✅';

    if (type === 'warning') {
        bgColor = 'bg-amber-500 border-amber-600';
        icon = '⚠️';
    } else if (type === 'error') {
        bgColor = 'bg-red-600 border-red-700';
        icon = '❌';
    }

    // 🟢 HAPUS: transition-all, duration-300, dan animate-bounce
    toast.className = `flex items-center gap-3 ${bgColor} text-white text-xs font-bold px-4 py-3 rounded-xl shadow-xl border`;
    toast.innerHTML = `<span class="text-base">${icon}</span> <span>${message}</span>`;
    
    container.appendChild(toast);

    // 🟢 HAPUS: animasi fade-out (opacity-0, translate-y-2). Langsung remove() saja.
    setTimeout(() => {
        toast.remove();
    }, 4000);
}

function showSuccessToast(message) {
    showToast(message, 'success');
}

function showWarningToast(message) {
    showToast(message, 'warning');
}

function showErrorToast(message) {
    showToast(message, 'error');
}

// ---------------------------------------------------------
// ERROR HANDLING & CONSOLE LOGGING
// ---------------------------------------------------------

// 1. Tangkap Error HTMX (4xx / 5xx Status Code)
document.addEventListener('htmx:responseError', (event) => {
    console.error('[HTMX Response Error]:', event.detail);
    const status = event.detail.xhr.status;
    let errorMsg = `Gagal memproses permintaan (HTTP ${status}).`;

    try {
        const responseJson = JSON.parse(event.detail.xhr.responseText);
        if (responseJson.detail) {
            errorMsg = typeof responseJson.detail === 'string' 
                ? responseJson.detail 
                : JSON.stringify(responseJson.detail);
        }
    } catch (e) {
        // Fallback jika response bukan JSON
    }

    showErrorToast(errorMsg);
});

// 2. Tangkap Error Jaringan HTMX (Network Failure)
document.addEventListener('htmx:sendError', (event) => {
    console.error('[HTMX Network Error]:', event.detail);
    showErrorToast('Koneksi terputus! Gagal menghubungi server.');
});

// 3. Deteksi Notifikasi dari URL Query Parameters (saat Redirect Halaman)
document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const msg = urlParams.get('msg');
    const type = urlParams.get('type') || 'success';

    if (msg) {
        showToast(msg, type);
        
        urlParams.delete('msg');
        urlParams.delete('type');
        const newUrl = window.location.pathname + (urlParams.toString() ? '?' + urlParams.toString() : '');
        window.history.replaceState({}, '', newUrl);
    }
});

// 4. Deteksi Notifikasi via Custom Event (HTMX HX-Trigger)
document.addEventListener('showToast', (evt) => {
    let detail = evt.detail;
    if (typeof detail === 'string') {
        try { detail = JSON.parse(detail); } catch(e){}
    }
    if (detail) {
        const msg = detail.message || (typeof detail === 'string' ? detail : '');
        const type = detail.type || 'success';
        if (msg) showToast(msg, type);
    }
});

// ---------------------------------------------------------
// EXPORT & MODAL HELPERS
// ---------------------------------------------------------

async function exportExcel(projectId) {
    const url = '/export/ut-matrix' + (projectId ? '?project_id=' + projectId : '');
    
    try {
        const response = await fetch(url);
        
        if (!response.ok) {
            const data = await response.json();
            const message = data.detail || 'Gagal mengekspor data.';
            console.warn('[Export Excel Warning]:', message);
            showWarningToast(message);
            return;
        }

        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        
        const disposition = response.headers.get('Content-Disposition');
        let filename = 'UT_Document_Matrix.xlsx';
        if (disposition && disposition.includes('filename=')) {
            filename = disposition.split('filename=')[1].replace(/"/g, '');
        }
        
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(downloadUrl);
        
    } catch (err) {
        console.error('[Export Excel Error]:', err);
        showErrorToast('Terjadi kesalahan sistem saat mengunduh laporan Excel.');
    }
}

function openProjectModal() {
    const modal = document.getElementById('project-modal');
    if (modal) modal.classList.remove('hidden');
}

function closeProjectModal() {
    const modal = document.getElementById('project-modal');
    if (modal) modal.classList.add('hidden');
}

function openEditProjectModal(id, name, description) {
    const modal = document.getElementById('edit-project-modal');
    const form = document.getElementById('edit-project-form');
    const nameInput = document.getElementById('edit-project-name');
    const descInput = document.getElementById('edit-project-description');

    if (modal && form && nameInput) {
        form.action = `/projects/${id}/edit`;
        nameInput.value = name;
        descInput.value = description || '';
        modal.classList.remove('hidden');
    }
}

function closeEditProjectModal() {
    const modal = document.getElementById('edit-project-modal');
    if (modal) modal.classList.add('hidden');
}

// ---------------------------------------------------------
// REMOTE SEARCH HANDLER & CLICK OUTSIDE CLOSER
// ---------------------------------------------------------

function handleScenarioSelect(evt, element) {
    if (evt) {
        evt.preventDefault();
        evt.stopPropagation();
    }
    if (!element) return;
    
    const id = element.getAttribute('data-id');
    const name = element.getAttribute('data-name');
    const project = element.getAttribute('data-project');

    const hiddenInput = document.getElementById('selected-scenario-id');
    const searchInput = document.getElementById('scenario-search-input');
    const resultsContainer = document.getElementById('scenario-search-results');

    // 1. Isi data ke kolom input & hapus fokus kursor
    if (hiddenInput) hiddenInput.value = id;
    if (searchInput) {
        searchInput.value = `📁 [${project}] ${name}`;
        searchInput.blur();
    }
    
    // 2. KOSONGKAN DAN TUTUP KOTAK PENCARIAN SECARA PERMANEN
    if (resultsContainer) {
        resultsContainer.innerHTML = '';
        resultsContainer.style.display = 'none';
    }
}

// Menutup popup secara otomatis jika pengguna mengklik area di luar kotak pencarian
document.addEventListener('click', function(event) {
    const searchContainer = document.querySelector('.step-input-select');
    const searchResults = document.getElementById('scenario-search-results');
    
    if (searchResults && searchContainer && !searchContainer.contains(event.target)) {
        searchResults.innerHTML = '';
        searchResults.classList.add('hidden');
    }
});

function toggleStepInputs(commandSelect) {
    if (!commandSelect) return;
    const form = commandSelect.closest('form');
    if (!form) return;

    const targetInput = form.querySelector('input[name="target_selector"]');
    const textInput = form.querySelector('.step-input-text');
    const selectScenarioContainer = form.querySelector('.step-input-select');
    const hiddenScenarioId = form.querySelector('#selected-scenario-id');
    const searchInput = form.querySelector('#scenario-search-input');
    const searchResults = form.querySelector('#scenario-search-results');

    if (searchResults) searchResults.innerHTML = '';

    if (commandSelect.value === 'INCLUDE_SCENARIO') {
        if (targetInput) {
            targetInput.value = '';
            targetInput.placeholder = 'Tidak diperlukan (-)';
            targetInput.disabled = true;
            targetInput.classList.add('bg-slate-100', 'cursor-not-allowed');
        }
        if (textInput) {
            textInput.classList.add('hidden');
            textInput.disabled = true;
        }
        if (selectScenarioContainer) {
            selectScenarioContainer.classList.remove('hidden');
        }
        if (hiddenScenarioId) {
            hiddenScenarioId.disabled = false;
        }
        if (searchInput) {
            searchInput.disabled = false;
            searchInput.focus();
        }
    } else {
        if (targetInput) {
            targetInput.disabled = false;
            targetInput.placeholder = 'Misal: #btn-submit';
            targetInput.classList.remove('bg-slate-100', 'cursor-not-allowed');
        }
        if (textInput) {
            textInput.classList.remove('hidden');
            textInput.disabled = false;
        }
        if (selectScenarioContainer) {
            selectScenarioContainer.classList.add('hidden');
        }
        if (hiddenScenarioId) {
            hiddenScenarioId.disabled = true;
        }
        if (searchInput) {
            searchInput.disabled = true;
        }
    }
}

/**
 * Resets all text inputs after adding a step while preserving the selected command dropdown value.
 * @param {HTMLFormElement} form - The submitted form element.
 * @param {CustomEvent} event - The HTMX after-request event.
 */
function handleStepFormReset(form, event) {
    if (event.detail && event.detail.successful) {
        const cmdSelect = form.querySelector('select[name="command"]');
        const currentCmd = cmdSelect ? cmdSelect.value : '';

        // Clear all text inputs
        form.querySelectorAll('input[type="text"]').forEach(input => input.value = '');

        // Clear hidden scenario search ID
        const hiddenId = document.getElementById('selected-scenario-id');
        if (hiddenId) hiddenId.value = '';

        // Retain the active command selection
        if (cmdSelect && currentCmd) {
            cmdSelect.value = currentCmd;
        }
    }
}

/**
 * Toggles all step selection checkboxes.
 * @param {HTMLInputElement} masterCheckbox
 */
function toggleSelectAllSteps(masterCheckbox) {
    const checkboxes = document.querySelectorAll('.step-checkbox');
    checkboxes.forEach(cb => cb.checked = masterCheckbox.checked);
    updateStepBulkActionState();
}

/**
 * Updates the state and counter of the batch delete toolbar.
 */
function updateStepBulkActionState() {
    const checkedBoxes = document.querySelectorAll('.step-checkbox:checked');
    const allBoxes = document.querySelectorAll('.step-checkbox');
    const toolbar = document.getElementById('step-bulk-toolbar');
    const countLabel = document.getElementById('step-selected-count');
    const masterCheckbox = document.getElementById('select-all-steps');

    if (countLabel) {
        countLabel.textContent = `${checkedBoxes.length} step(s) selected`;
    }

    if (toolbar) {
        if (checkedBoxes.length > 0) {
            toolbar.classList.remove('hidden');
            toolbar.classList.add('flex');
        } else {
            toolbar.classList.add('hidden');
            toolbar.classList.remove('flex');
        }
    }

    if (masterCheckbox && allBoxes.length > 0) {
        masterCheckbox.checked = checkedBoxes.length === allBoxes.length;
    }
}