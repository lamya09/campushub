/**
 * faculty.js — Client logic for the CampusHub Faculty Portal
 * Talks exclusively to /api/faculty/* endpoints.
 */

// ── Utilities ────────────────────────────────────────────────────────────────

function showToast(msg, type = 'success') {
  const c   = document.getElementById('toast-container');
  const div = document.createElement('div');
  div.className = `toast toast-${type}`;
  div.textContent = msg;
  c.appendChild(div);
  setTimeout(() => div.remove(), 3800);
}

async function apiFetch(url, opts = {}) {
  const res  = await fetch(url, opts);
  const json = await res.json();
  if (!json.success) throw new Error(json.message || 'Request failed');
  return json.data !== undefined ? json.data : json;
}

function scorePill(score) {
  if (score === null || score === undefined) return '<span class="sp-ng score-pill">N/G</span>';
  const s = parseFloat(score);
  let cls, label;
  if (s >= 90)      { cls = 'sp-a'; label = `${s}% · A`; }
  else if (s >= 80) { cls = 'sp-b'; label = `${s}% · B`; }
  else if (s >= 70) { cls = 'sp-c'; label = `${s}% · C`; }
  else if (s >= 60) { cls = 'sp-d'; label = `${s}% · D`; }
  else              { cls = 'sp-f'; label = `${s}% · F`; }
  return `<span class="score-pill ${cls}">${label}</span>`;
}

function letterGrade(score) {
  if (score === null || score === undefined) return '—';
  const s = parseFloat(score);
  if (s >= 90) return 'A';
  if (s >= 80) return 'B';
  if (s >= 70) return 'C';
  if (s >= 60) return 'D';
  return 'F';
}

function capacityBar(enrolled, capacity) {
  const pct  = capacity > 0 ? Math.round((enrolled / capacity) * 100) : 0;
  const cls  = pct >= 100 ? 'danger' : pct >= 80 ? 'warning' : 'success';
  return `<div style="display:flex;align-items:center;gap:8px;">
    <div style="flex:1;height:8px;background:#eee;border-radius:4px;overflow:hidden;">
      <div style="width:${pct}%;height:100%;background:var(--${cls === 'success' ? 'success' : cls === 'warning' ? 'warning' : 'danger'});border-radius:4px;"></div>
    </div>
    <span style="font-size:.78rem;color:#666;">${enrolled}/${capacity}</span>
  </div>`;
}

function attBadge(pct, total) {
  if (!total || pct === null || pct === undefined) {
    return '<span class="badge badge-gray">No sessions</span>';
  }
  const p = parseFloat(pct);
  if (p < 75) {
    return `<span class="badge badge-danger">⚠️ ${p}% (${total} sess)</span>`;
  }
  return `<span class="badge badge-success">✅ ${p}% (${total} sess)</span>`;
}

// ── Globals ───────────────────────────────────────────────────────────────────
let _courses     = [];   // cached faculty courses for select dropdowns
let _attStudents = [];   // current attendance sheet students

// ── Tab navigation ────────────────────────────────────────────────────────────

document.querySelectorAll('.portal-nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.portal-nav-item').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.portal-section').forEach(x => x.classList.remove('active'));
    item.classList.add('active');
    const tab = document.getElementById(item.dataset.tab);
    if (tab) tab.classList.add('active');

    if (item.dataset.tab === 'tab-courses')    loadFacultyCourses();
    if (item.dataset.tab === 'tab-roster')     populateCourseSelects();
    if (item.dataset.tab === 'tab-attendance') populateCourseSelects();
    if (item.dataset.tab === 'tab-nosql')      { populateCourseSelects(); loadFacultyNoSQLFeed(); }
  });
});

// ── Overview ──────────────────────────────────────────────────────────────────

async function loadFacultyDashboard() {
  try {
    const d = await apiFetch('/api/faculty/dashboard');

    document.getElementById('f-welcome-name').textContent =
      `Welcome, ${d.profile.full_name}!`;
    document.getElementById('f-dept').textContent =
      `Department of ${d.profile.department}`;

    document.getElementById('f-stat-courses').textContent  = d.course_count;
    document.getElementById('f-stat-students').textContent = d.student_count;
    document.getElementById('f-stat-graded').textContent   = d.graded_count;

    const courses = await apiFetch('/api/faculty/my-courses');
    _courses = courses;
    populateCourseSelects();

    const tbody = document.getElementById('f-overview-courses');
    if (!courses.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-row">No courses assigned yet</td></tr>';
      return;
    }
    tbody.innerHTML = courses.map(c => `
      <tr>
        <td><strong>${c.course_code}</strong></td>
        <td>${c.course_name}</td>
        <td>${c.department}</td>
        <td><span class="badge badge-info">${c.credits} cr</span></td>
        <td>${capacityBar(c.enrolled_count, c.capacity)}</td>
        <td>${c.capacity}</td>
        <td style="display:flex;gap:6px;flex-wrap:wrap;">
          <button class="btn btn-sm btn-primary" onclick="goToRoster(${c.course_id})">👥 Grades</button>
          <button class="btn btn-sm btn-outline" onclick="goToAttendance(${c.course_id})">📅 Attendance</button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// ── My Courses tab ────────────────────────────────────────────────────────────

async function loadFacultyCourses() {
  const tbody = document.getElementById('f-courses-tbody');
  tbody.innerHTML = '<tr><td colspan="7" class="loading-row"><div class="spinner"></div></td></tr>';
  try {
    const data = await apiFetch('/api/faculty/my-courses');
    _courses = data;
    populateCourseSelects();

    if (!data.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-row">No courses assigned to you yet</td></tr>';
      return;
    }
    tbody.innerHTML = data.map(c => `
      <tr>
        <td><strong>${c.course_code}</strong></td>
        <td>${c.course_name}</td>
        <td>${c.department}</td>
        <td><span class="badge badge-info">${c.credits} cr</span></td>
        <td>${capacityBar(c.enrolled_count, c.capacity)}</td>
        <td>${c.capacity}</td>
        <td style="display:flex;gap:6px;flex-wrap:wrap;">
          <button class="btn btn-sm btn-primary" onclick="goToRoster(${c.course_id})">
            👥 Roster &amp; Grades
          </button>
          <button class="btn btn-sm btn-outline" onclick="goToAttendance(${c.course_id})">
            📅 Attendance
          </button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-row" style="color:#c62828">${e.message}</td></tr>`;
  }
}

// ── Populate Course Dropdowns ────────────────────────────────────────────────

function populateCourseSelects() {
  ['f-roster-select', 'f-att-course', 'f-ann-course'].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const val = sel.value;
    sel.innerHTML = '<option value="">— Choose a course —</option>' +
      _courses.map(c =>
        `<option value="${c.course_id}" ${c.course_id == val ? 'selected' : ''}>${c.course_code} — ${c.course_name}</option>`
      ).join('');
  });
}

function goToRoster(courseId) {
  document.querySelectorAll('.portal-nav-item').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.portal-section').forEach(x => x.classList.remove('active'));
  document.querySelector('[data-tab="tab-roster"]').classList.add('active');
  document.getElementById('tab-roster').classList.add('active');

  populateCourseSelects();
  document.getElementById('f-roster-select').value = courseId;
  loadRoster(courseId);
}

function goToAttendance(courseId) {
  document.querySelectorAll('.portal-nav-item').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.portal-section').forEach(x => x.classList.remove('active'));
  document.querySelector('[data-tab="tab-attendance"]').classList.add('active');
  document.getElementById('tab-attendance').classList.add('active');

  populateCourseSelects();
  document.getElementById('f-att-course').value = courseId;
  loadAttendanceSheet();
}

// ── Roster & Grading ─────────────────────────────────────────────────────────

async function loadRoster(courseId) {
  if (!courseId) {
    document.getElementById('f-roster-panel').classList.remove('open');
    return;
  }
  const course  = _courses.find(c => c.course_id == courseId);
  const panel   = document.getElementById('f-roster-panel');
  const titleEl = document.getElementById('f-roster-title');
  const tbody   = document.getElementById('f-roster-tbody');

  panel.classList.add('open');
  titleEl.textContent = course ? `${course.course_code} — ${course.course_name}` : 'Students';
  tbody.innerHTML = '<tr><td colspan="8" class="loading-row"><div class="spinner"></div></td></tr>';

  try {
    const data = await apiFetch(`/api/faculty/course/${courseId}/students`);
    if (!data.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty-row">No students enrolled in this course</td></tr>';
      return;
    }

    tbody.innerHTML = data.map(s => {
      const hasGrade  = s.grade_id !== null;
      const scoreDisp = hasGrade ? scorePill(s.score) : '<span class="sp-ng score-pill">Not graded</span>';
      const gradeDisp = hasGrade ? letterGrade(s.score) : '—';

      return `
        <tr id="row-${s.enrollment_id}">
          <td><strong>${s.student_name}</strong></td>
          <td style="font-size:.8rem">${s.email}</td>
          <td>Yr ${s.year_of_study}</td>
          <td><span class="badge badge-${s.status === 'Active' ? 'success' : s.status === 'Dropped' ? 'danger' : 'info'}">${s.status}</span></td>
          <td id="score-cell-${s.enrollment_id}">${scoreDisp}</td>
          <td id="grade-cell-${s.enrollment_id}">${gradeDisp}</td>
          <td id="remarks-cell-${s.enrollment_id}">${s.remarks || '—'}</td>
          <td>
            ${hasGrade
              ? `<button class="btn btn-sm btn-outline" onclick="showEditGrade(${s.enrollment_id},${s.grade_id},${s.score},'${(s.remarks||'').replace(/'/g,"\\'")}')">✏️ Edit</button>`
              : `<button class="btn btn-sm btn-primary" onclick="showAddGrade(${s.enrollment_id})">+ Grade</button>`
            }
          </td>
        </tr>
      `;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-row" style="color:#c62828">${e.message}</td></tr>`;
  }
}

// ── Inline grade forms ────────────────────────────────────────────────────────

function showAddGrade(enrollmentId) {
  removeInlineForm();

  const row = document.getElementById(`row-${enrollmentId}`);
  const formRow = document.createElement('tr');
  formRow.id = 'inline-grade-form';
  formRow.className = 'grade-form-row';
  formRow.innerHTML = `
    <td colspan="8">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:4px 0;">
        <span style="font-weight:600;font-size:.85rem;">Enter Grade:</span>
        <input type="number" id="ig-score" class="grade-input" placeholder="Score (0–100)" min="0" max="100" step="0.1" />
        <input type="text" id="ig-remarks" class="remarks-input" placeholder="Remarks (optional)" />
        <button class="btn btn-sm btn-primary" onclick="submitAddGrade(${enrollmentId})">💾 Save</button>
        <button class="btn btn-sm btn-outline" onclick="removeInlineForm()">✕ Cancel</button>
      </div>
    </td>
  `;
  row.insertAdjacentElement('afterend', formRow);
  document.getElementById('ig-score').focus();
}

function showEditGrade(enrollmentId, gradeId, currentScore, currentRemarks) {
  removeInlineForm();

  const row = document.getElementById(`row-${enrollmentId}`);
  const formRow = document.createElement('tr');
  formRow.id = 'inline-grade-form';
  formRow.className = 'grade-form-row';
  formRow.innerHTML = `
    <td colspan="8">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:4px 0;">
        <span style="font-weight:600;font-size:.85rem;">Update Grade:</span>
        <input type="number" id="ig-score" class="grade-input" value="${currentScore}" min="0" max="100" step="0.1" />
        <input type="text" id="ig-remarks" class="remarks-input" value="${currentRemarks}" placeholder="Remarks (optional)" />
        <button class="btn btn-sm btn-primary" onclick="submitEditGrade(${gradeId}, ${enrollmentId})">💾 Update</button>
        <button class="btn btn-sm btn-outline" onclick="removeInlineForm()">✕ Cancel</button>
      </div>
    </td>
  `;
  row.insertAdjacentElement('afterend', formRow);
  document.getElementById('ig-score').focus();
}

function removeInlineForm() {
  const existing = document.getElementById('inline-grade-form');
  if (existing) existing.remove();
}

async function submitAddGrade(enrollmentId) {
  const score   = parseFloat(document.getElementById('ig-score').value);
  const remarks = document.getElementById('ig-remarks').value.trim();

  if (isNaN(score) || score < 0 || score > 100) {
    showToast('Score must be between 0 and 100', 'error');
    return;
  }

  try {
    await apiFetch('/api/faculty/grade', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enrollment_id: enrollmentId, score, remarks }),
    });
    showToast('Grade saved successfully!');
    removeInlineForm();
    loadRoster(document.getElementById('f-roster-select').value);
    loadFacultyDashboard();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function submitEditGrade(gradeId, enrollmentId) {
  const score   = parseFloat(document.getElementById('ig-score').value);
  const remarks = document.getElementById('ig-remarks').value.trim();

  if (isNaN(score) || score < 0 || score > 100) {
    showToast('Score must be between 0 and 100', 'error');
    return;
  }

  try {
    await apiFetch(`/api/faculty/grade/${gradeId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ score, remarks }),
    });
    showToast('Grade updated successfully!');
    removeInlineForm();
    loadRoster(document.getElementById('f-roster-select').value);
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// ── Daily Attendance Management ──────────────────────────────────────────────

async function loadAttendanceSheet() {
  const courseId = document.getElementById('f-att-course').value;
  let sessDate   = document.getElementById('f-att-date').value;
  const panel    = document.getElementById('f-att-panel');
  const tbody    = document.getElementById('f-att-tbody');

  if (!sessDate) {
    sessDate = new Date().toISOString().slice(0, 10);
    document.getElementById('f-att-date').value = sessDate;
  }

  if (!courseId) {
    panel.classList.remove('open');
    return;
  }

  const course = _courses.find(c => c.course_id == courseId);
  document.getElementById('f-att-title').textContent =
    `${course ? course.course_code + ' — ' + course.course_name : 'Course'} · ${sessDate}`;
  panel.classList.add('open');
  tbody.innerHTML = '<tr><td colspan="5" class="loading-row"><div class="spinner"></div></td></tr>';

  try {
    const data   = await apiFetch(`/api/faculty/course/${courseId}/attendance?date=${encodeURIComponent(sessDate)}`);
    _attStudents = data.students || [];

    if (!_attStudents.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-row">No active students enrolled in this course</td></tr>';
      return;
    }

    tbody.innerHTML = _attStudents.map(s => {
      const curStatus = s.date_status || 'Present';
      return `
        <tr data-eid="${s.enrollment_id}">
          <td><strong>${s.student_name}</strong></td>
          <td style="font-size:.82rem;">${s.email}</td>
          <td>${attBadge(s.attendance_pct, s.total_sessions)}</td>
          <td>
            <select class="form-select att-status-sel" data-eid="${s.enrollment_id}" style="max-width:140px;padding:6px 10px;">
              <option value="Present" ${curStatus === 'Present' ? 'selected' : ''}>✅ Present</option>
              <option value="Absent"  ${curStatus === 'Absent'  ? 'selected' : ''}>❌ Absent</option>
              <option value="Late"    ${curStatus === 'Late'    ? 'selected' : ''}>⏰ Late</option>
            </select>
          </td>
          <td>
            <input type="text" class="form-control att-remarks-inp" data-eid="${s.enrollment_id}"
                   value="${(s.date_remarks || '').replace(/"/g, '&quot;')}"
                   placeholder="Optional note…" style="max-width:220px;padding:6px 10px;" />
          </td>
        </tr>
      `;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-row" style="color:#c62828">${e.message}</td></tr>`;
  }
}

function markAllAttendance(status) {
  document.querySelectorAll('.att-status-sel').forEach(sel => {
    sel.value = status;
  });
}

async function saveAttendanceSheet() {
  const courseId = document.getElementById('f-att-course').value;
  const sessDate = document.getElementById('f-att-date').value;
  if (!courseId || !sessDate) {
    showToast('Please select a course and date first', 'error');
    return;
  }

  const records = [];
  document.querySelectorAll('#f-att-tbody tr[data-eid]').forEach(tr => {
    const eid     = parseInt(tr.dataset.eid);
    const status  = tr.querySelector('.att-status-sel').value;
    const remarks = tr.querySelector('.att-remarks-inp').value.trim();
    records.push({ enrollment_id: eid, status, remarks });
  });

  if (!records.length) {
    showToast('No students to mark attendance for', 'error');
    return;
  }

  try {
    await apiFetch('/api/faculty/attendance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        course_id:    parseInt(courseId),
        session_date: sessDate,
        records,
      }),
    });
    showToast(`Attendance saved for ${sessDate}!`);
    loadAttendanceSheet();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// ── MongoDB NoSQL: Course Announcements & Student Feedback ──────────────────

async function loadFacultyNoSQLFeed() {
  const annTbody = document.getElementById('f-ann-tbody');
  const fbTbody  = document.getElementById('f-fb-tbody');
  if (!annTbody) return;

  annTbody.innerHTML = '<tr><td colspan="4" class="loading-row"><div class="spinner"></div></td></tr>';
  fbTbody.innerHTML  = '<tr><td colspan="4" class="loading-row"><div class="spinner"></div></td></tr>';

  try {
    const data = await apiFetch('/api/faculty/nosql/feed');
    const anns = data.announcements || [];
    const fbs  = data.feedback || [];

    const prioBadge = p => {
      const m = { Exam: 'badge-danger', Important: 'badge-warning', Normal: 'badge-info' };
      return `<span class="badge ${m[p] || 'badge-secondary'}">${p || 'Normal'}</span>`;
    };

    if (!anns.length) {
      annTbody.innerHTML = '<tr><td colspan="4" class="empty-row">No announcements published yet</td></tr>';
    } else {
      annTbody.innerHTML = anns.map(a => `
        <tr>
          <td><code class="mono" style="font-weight:600;color:var(--primary)">${a.course_code}</code></td>
          <td>
            <div style="font-weight:600;">${a.title}</div>
            <div style="font-size:.78rem;color:var(--text-muted);">${a.message}</div>
          </td>
          <td>
            ${prioBadge(a.priority)}
            <div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap;">
              ${(a.tags || []).map(t => `<span class="badge badge-secondary">${t}</span>`).join('')}
            </div>
          </td>
          <td>
            <button class="btn btn-sm btn-danger" onclick="deleteFacultyAnnouncement('${a._id}')">Delete</button>
          </td>
        </tr>
      `).join('');
    }

    if (!fbs.length) {
      fbTbody.innerHTML = '<tr><td colspan="4" class="empty-row">No student reviews submitted for your courses yet</td></tr>';
    } else {
      fbTbody.innerHTML = fbs.map(f => {
        const stars = '⭐'.repeat(Math.max(1, Math.min(5, Number(f.rating || 5))));
        return `
          <tr>
            <td><code class="mono" style="font-weight:600;color:var(--primary)">${f.course_code}</code></td>
            <td><strong>${f.student_name}</strong></td>
            <td>
              <span>${stars}</span>
              <div style="font-size:.72rem;color:var(--text-muted)">${f.difficulty || 'Moderate'}</div>
            </td>
            <td>
              <div style="font-size:.82rem;">${f.comment}</div>
              <div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap;">
                ${(f.tags || []).map(t => `<span class="badge badge-secondary">${t}</span>`).join('')}
              </div>
            </td>
          </tr>
        `;
      }).join('');
    }
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function deleteFacultyAnnouncement(annId) {
  if (!confirm('Delete this announcement from MongoDB?')) return;
  try {
    await apiFetch(`/api/faculty/nosql/announcements/${encodeURIComponent(annId)}`, {
      method: 'DELETE',
    });
    showToast('Announcement deleted');
    loadFacultyNoSQLFeed();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  const dateEl = document.getElementById('f-att-date');
  if (dateEl) dateEl.value = new Date().toISOString().slice(0, 10);

  const annForm = document.getElementById('f-ann-form');
  if (annForm) {
    annForm.addEventListener('submit', async e => {
      e.preventDefault();
      const payload = {
        course_id: parseInt(document.getElementById('f-ann-course').value),
        priority:  document.getElementById('f-ann-priority').value,
        title:     document.getElementById('f-ann-title').value.trim(),
        tags:      document.getElementById('f-ann-tags').value.trim(),
        message:   document.getElementById('f-ann-message').value.trim(),
      };
      try {
        await apiFetch('/api/faculty/nosql/announcements', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        showToast('Announcement published to MongoDB!');
        document.getElementById('f-ann-title').value = '';
        document.getElementById('f-ann-message').value = '';
        loadFacultyNoSQLFeed();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  await loadFacultyDashboard();
});
