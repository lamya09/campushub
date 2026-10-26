/* =========================================================
   CampusHub — Frontend Application (app.js)
   All API calls use fetch() with the Flask backend.
   No hardcoded data arrays — everything comes from the DB.
   ========================================================= */

'use strict';

// ── Utility helpers ───────────────────────────────────────────────────────

const $ = id => document.getElementById(id);
const el = (tag, attrs = {}, ...children) => {
  const e = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else e.setAttribute(k, v);
  });
  children.forEach(c => c && e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c));
  return e;
};

// ── Toast system ──────────────────────────────────────────────────────────

const toastContainer = $('toast-container');

function toast(msg, type = 'info') {
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  const t = el('div', { class: `toast ${type}` });
  t.innerHTML = `<span class="toast-icon">${icons[type]}</span>
                 <span class="toast-msg">${msg}</span>
                 <button class="toast-dismiss" onclick="this.parentElement.remove()">×</button>`;
  toastContainer.appendChild(t);
  setTimeout(() => t.remove(), 5000);
}

// ── API wrapper ───────────────────────────────────────────────────────────

async function api(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  const json = await res.json();
  if (!json.success) throw new Error(json.message || 'Unknown error');
  return json;
}

// ── Navigation ────────────────────────────────────────────────────────────

const sections = document.querySelectorAll('.section');
const navItems  = document.querySelectorAll('.nav-item');

function navigate(sectionId) {
  sections.forEach(s => s.classList.toggle('active', s.id === sectionId));
  navItems.forEach(n => n.classList.toggle('active', n.dataset.section === sectionId));
  const h = document.querySelector('.topbar h2');
  const labels = {
    'sec-dashboard':   '🏛️ Dashboard',
    'sec-students':    '👩‍🎓 Students',
    'sec-faculty':     '👨‍🏫 Faculty',
    'sec-courses':     '📚 Courses',
    'sec-enrollments': '📋 Enrollments',
    'sec-grades':      '📊 Grades',
    'sec-reports':     '📈 Reports',
    'sec-users':       '🛡️ User Management',
    'sec-audit':       '⚡ Audit Trail',
    'sec-nosql':       '🍃 MongoDB NoSQL Store',
  };
  if (h) h.textContent = labels[sectionId] || 'CampusHub';

  // Lazy-load section data
  switch (sectionId) {
    case 'sec-dashboard':   loadDashboard(); break;
    case 'sec-students':    loadStudents(); break;
    case 'sec-faculty':     loadFaculty(); break;
    case 'sec-courses':     loadCourses(); loadFacultyOptions(); break;
    case 'sec-enrollments': loadEnrollments(); loadStudentOptions(); loadCourseOptions(); break;
    case 'sec-grades':      loadGrades(); loadEnrollmentOptions(); break;
    case 'sec-reports':     showReport('enrollment-summary'); break;
    case 'sec-users':       loadUsers(); break;
    case 'sec-audit':       loadAuditLogs(); break;
    case 'sec-nosql':       loadNoSQLOverview(); break;
  }
}

navItems.forEach(n => n.addEventListener('click', () => navigate(n.dataset.section)));

// ── Modal helper ──────────────────────────────────────────────────────────

let _activeModal = null;

function openModal(id) {
  const m = $(id);
  if (!m) return;
  m.classList.add('open');
  _activeModal = m;
}

function closeModal(id) {
  const m = id ? $(id) : _activeModal;
  if (m) m.classList.remove('open');
}

document.addEventListener('keydown', e => e.key === 'Escape' && closeModal());
document.querySelectorAll('.modal-overlay').forEach(m =>
  m.addEventListener('click', e => { if (e.target === m) closeModal(m.id); })
);

// ── Empty state helper ────────────────────────────────────────────────────

function emptyState(icon, text) {
  return `<tr><td colspan="100" class="loading-row">
    <div class="empty-state"><div class="icon">${icon}</div><p>${text}</p></div>
  </td></tr>`;
}

function loadingRow() {
  return `<tr><td colspan="100" class="loading-row"><div class="spinner"></div></td></tr>`;
}

// ── Score badge helper ─────────────────────────────────────────────────────

function scoreBadge(score) {
  if (score === null || score === undefined) return '<span class="badge badge-secondary">—</span>';
  const s = parseFloat(score);
  const cls = s >= 90 ? 'score-a' : s >= 75 ? 'score-b' : s >= 60 ? 'score-c' : s >= 40 ? 'score-d' : 'score-f';
  return `<span class="score-pill ${cls}">${s.toFixed(1)}</span>`;
}

function statusBadge(status) {
  const map = { Active: 'badge-success', Dropped: 'badge-danger', Completed: 'badge-info' };
  return `<span class="badge ${map[status] || 'badge-secondary'}">${esc(status || '—')}</span>`;
}

// ── Date formatter ────────────────────────────────────────────────────────
function fmtDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

// ==========================================================================
// DASHBOARD
// ==========================================================================

async function loadDashboard() {
  try {
    const [statsRes, coursesRes, topRes, deptRes, enrRes] = await Promise.all([
      api('GET', '/api/dashboard/stats'),
      api('GET', '/api/courses').catch(() => ({ data: [] })),
      api('GET', '/api/reports/top-students?limit=6').catch(() => ({ data: [] })),
      api('GET', '/api/reports/department-stats').catch(() => ({ data: [] })),
      api('GET', '/api/enrollments').catch(() => ({ data: [] })),
    ]);

    const data = statsRes.data;
    $('stat-students').textContent    = data.student_count;
    $('stat-courses').textContent     = data.course_count;
    $('stat-enrollments').textContent = data.active_enrollments;
    $('stat-avg-grade').textContent   = data.avg_grade ? data.avg_grade.toFixed(1) + '%' : '—';
    const usersEl = $('stat-users');
    if (usersEl) usersEl.textContent  = data.user_count ?? '—';

    // 1. Course Seat Utilization
    const cTbody = $('dash-courses-tbody');
    if (cTbody) {
      const courses = (coursesRes.data || []).slice(0, 6);
      if (!courses.length) {
        cTbody.innerHTML = '<tr><td colspan="3" class="empty-row">No courses yet</td></tr>';
      } else {
        cTbody.innerHTML = courses.map(c => {
          const enr = Number(c.enrolled_count || 0);
          const cap = Number(c.capacity || 1);
          const pct = Math.min(100, Math.round((enr / cap) * 100));
          const color = pct >= 90 ? '#dc2626' : pct >= 70 ? '#d97706' : '#2563eb';
          return `
            <tr>
              <td><code class="mono" style="font-weight:600;color:var(--primary)">${esc(c.course_code)}</code> · ${esc(c.course_name)}</td>
              <td style="font-size:.8rem;color:var(--text-muted)">${esc(c.faculty_name || 'Unassigned')}</td>
              <td style="min-width:130px;">
                <div style="display:flex;align-items:center;gap:8px;">
                  <div class="progress-track"><div class="progress-fill" style="width:${pct}%;background:${color};"></div></div>
                  <span class="mono" style="font-size:.75rem;color:var(--text-muted);">${enr}/${cap}</span>
                </div>
              </td>
            </tr>`;
        }).join('');
      }
    }

    // 2. Dean's List & Top Performers
    const tTbody = $('dash-top-students-tbody');
    if (tTbody) {
      const top = topRes.data || [];
      if (!top.length) {
        tTbody.innerHTML = '<tr><td colspan="4" class="empty-row">No graded students yet</td></tr>';
      } else {
        tTbody.innerHTML = top.map((s, i) => `
          <tr>
            <td class="mono" style="font-weight:700;color:var(--primary)">#${i + 1}</td>
            <td>
              <div style="font-weight:600;">${esc(s.full_name)}</div>
              <div style="font-size:.73rem;color:var(--text-muted);">${esc(s.department)}</div>
            </td>
            <td><span class="badge badge-info mono">${s.weighted_gpa != null ? Number(s.weighted_gpa).toFixed(2) : '—'}</span></td>
            <td>${scoreBadge(s.avg_score)}</td>
          </tr>`).join('');
      }
    }

    // 3. Departmental Academic Pulse
    const dTbody = $('dash-dept-tbody');
    if (dTbody) {
      const depts = deptRes.data || [];
      if (!depts.length) {
        dTbody.innerHTML = '<tr><td colspan="4" class="empty-row">No department stats yet</td></tr>';
      } else {
        dTbody.innerHTML = depts.map(d => `
          <tr>
            <td><strong>${esc(d.department)}</strong></td>
            <td class="mono">${d.student_count}</td>
            <td class="mono">${d.total_enrollments}</td>
            <td>${scoreBadge(d.avg_score)}</td>
          </tr>`).join('');
      }
    }

    // 4. Recent Course Enrollments
    const eTbody = $('dash-enrollments-tbody');
    if (eTbody) {
      const enrollments = (enrRes.data || []).slice(0, 6);
      if (!enrollments.length) {
        eTbody.innerHTML = '<tr><td colspan="4" class="empty-row">No recent enrollments</td></tr>';
      } else {
        eTbody.innerHTML = enrollments.map(e => `
          <tr>
            <td><strong>${esc(e.student_name)}</strong></td>
            <td><code class="mono" style="color:var(--primary);font-weight:600;">${esc(e.course_code)}</code> · ${esc(e.course_name)}</td>
            <td style="font-size:.78rem;color:var(--text-muted)">${fmtDate(e.enrollment_date)}</td>
            <td>${statusBadge(e.status)}</td>
          </tr>`).join('');
      }
    }
  } catch (e) {
    toast('Failed to load dashboard stats: ' + e.message, 'error');
  }
}

// ==========================================================================
// STUDENTS
// ==========================================================================

let _students = [];

async function loadStudents(q = '') {
  const tbody = $('students-tbody');
  tbody.innerHTML = loadingRow();
  try {
    const url = q ? `/api/students?q=${encodeURIComponent(q)}` : '/api/students';
    const { data } = await api('GET', url);
    _students = data;
    renderStudents(data);
  } catch (e) {
    tbody.innerHTML = emptyState('⚠️', 'Failed to load students: ' + e.message);
  }
}

function renderStudents(rows) {
  const tbody = $('students-tbody');
  if (!rows.length) { tbody.innerHTML = emptyState('👩‍🎓', 'No students found'); return; }
  tbody.innerHTML = rows.map(s => `
    <tr>
      <td>#${s.student_id}</td>
      <td><strong>${esc(s.full_name)}</strong></td>
      <td>${esc(s.email)}</td>
      <td>${esc(s.department)}</td>
      <td><span class="badge badge-info">Year ${s.year_of_study}</span></td>
      <td>${fmtDate(s.created_at)}</td>
      <td class="actions-cell">
        <button class="btn btn-outline btn-sm btn-icon" title="Edit" onclick="editStudent(${s.student_id})">✏️</button>
        <button class="btn btn-danger btn-sm btn-icon" title="Delete" onclick="deleteStudent(${s.student_id}, '${esc(s.full_name)}')">🗑️</button>
      </td>
    </tr>`).join('');
}

function esc(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Add student
$('btn-add-student').addEventListener('click', () => {
  $('student-modal-title').textContent = 'Add Student';
  $('student-form').reset();
  $('student-id-hidden').value = '';
  openModal('student-modal');
});

$('student-form').addEventListener('submit', async e => {
  e.preventDefault();
  const sid = $('student-id-hidden').value;
  const body = {
    full_name:    $('s-full-name').value.trim(),
    email:        $('s-email').value.trim(),
    department:   $('s-department').value.trim(),
    year_of_study: parseInt($('s-year').value),
  };
  try {
    if (sid) {
      await api('PUT', `/api/students/${sid}`, body);
      toast('Student updated successfully', 'success');
    } else {
      await api('POST', '/api/students', body);
      toast('Student added successfully', 'success');
    }
    closeModal('student-modal');
    loadStudents();
  } catch (e) {
    toast(e.message, 'error');
  }
});

async function editStudent(id) {
  try {
    const { data } = await api('GET', `/api/students/${id}`);
    $('student-modal-title').textContent = 'Edit Student';
    $('student-id-hidden').value = id;
    $('s-full-name').value   = data.full_name;
    $('s-email').value       = data.email;
    $('s-department').value  = data.department;
    $('s-year').value        = data.year_of_study;
    openModal('student-modal');
  } catch (e) {
    toast('Could not load student: ' + e.message, 'error');
  }
}

async function deleteStudent(id, name) {
  if (!confirm(`Delete student "${name}"? This will also remove their enrollments and grades.`)) return;
  try {
    await api('DELETE', `/api/students/${id}`);
    toast('Student deleted', 'success');
    loadStudents();
  } catch (e) {
    toast(e.message, 'error');
  }
}

$('student-search-btn').addEventListener('click', () =>
  loadStudents($('student-search').value));
$('student-search').addEventListener('keypress', e =>
  e.key === 'Enter' && loadStudents($('student-search').value));

// ==========================================================================
// FACULTY
// ==========================================================================

async function loadFaculty() {
  const tbody = $('faculty-tbody');
  tbody.innerHTML = loadingRow();
  try {
    const { data } = await api('GET', '/api/faculty');
    if (!data.length) { tbody.innerHTML = emptyState('👨‍🏫', 'No faculty records found'); return; }
    tbody.innerHTML = data.map(f => `
      <tr>
        <td>#${f.faculty_id}</td>
        <td><strong>${esc(f.full_name)}</strong></td>
        <td>${esc(f.email)}</td>
        <td>${esc(f.department)}</td>
        <td class="actions-cell">
          <button class="btn btn-outline btn-sm btn-icon" onclick="editFaculty(${f.faculty_id})">✏️</button>
          <button class="btn btn-danger btn-sm btn-icon" onclick="deleteFaculty(${f.faculty_id}, '${esc(f.full_name)}')">🗑️</button>
        </td>
      </tr>`).join('');
  } catch (e) {
    tbody.innerHTML = emptyState('⚠️', 'Failed to load faculty: ' + e.message);
  }
}

$('btn-add-faculty').addEventListener('click', () => {
  $('faculty-modal-title').textContent = 'Add Faculty Member';
  $('faculty-form').reset();
  $('faculty-id-hidden').value = '';
  openModal('faculty-modal');
});

$('faculty-form').addEventListener('submit', async e => {
  e.preventDefault();
  const fid = $('faculty-id-hidden').value;
  const body = {
    full_name:  $('f-full-name').value.trim(),
    email:      $('f-email').value.trim(),
    department: $('f-department').value.trim(),
  };
  try {
    if (fid) {
      await api('PUT', `/api/faculty/${fid}`, body);
      toast('Faculty updated successfully', 'success');
    } else {
      await api('POST', '/api/faculty', body);
      toast('Faculty added successfully', 'success');
    }
    closeModal('faculty-modal');
    loadFaculty();
  } catch (e) {
    toast(e.message, 'error');
  }
});

async function editFaculty(id) {
  try {
    const { data } = await api('GET', `/api/faculty/${id}`);
    $('faculty-modal-title').textContent = 'Edit Faculty Member';
    $('faculty-id-hidden').value = id;
    $('f-full-name').value   = data.full_name;
    $('f-email').value       = data.email;
    $('f-department').value  = data.department;
    openModal('faculty-modal');
  } catch (e) {
    toast('Could not load faculty record: ' + e.message, 'error');
  }
}

async function deleteFaculty(id, name) {
  if (!confirm(`Delete faculty member "${name}"?`)) return;
  try {
    await api('DELETE', `/api/faculty/${id}`);
    toast('Faculty member deleted', 'success');
    loadFaculty();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ==========================================================================
// COURSES
// ==========================================================================

async function loadFacultyOptions() {
  try {
    const { data } = await api('GET', '/api/faculty');
    const sel = $('c-faculty');
    sel.innerHTML = '<option value="">— None —</option>' +
      data.map(f => `<option value="${f.faculty_id}">${esc(f.full_name)} (${esc(f.department)})</option>`).join('');
  } catch (_) {}
}

async function loadCourses(q = '') {
  const tbody = $('courses-tbody');
  tbody.innerHTML = loadingRow();
  try {
    const url = q ? `/api/courses?q=${encodeURIComponent(q)}` : '/api/courses';
    const { data } = await api('GET', url);
    if (!data.length) { tbody.innerHTML = emptyState('📚', 'No courses found'); return; }
    tbody.innerHTML = data.map(c => `
      <tr>
        <td>#${c.course_id}</td>
        <td><strong>${esc(c.course_code)}</strong></td>
        <td>${esc(c.course_name)}</td>
        <td>${esc(c.department)}</td>
        <td>${c.credits}</td>
        <td>${c.faculty_name ? esc(c.faculty_name) : '<span class="badge badge-secondary">Unassigned</span>'}</td>
        <td>
          <span class="${c.enrolled_count >= c.capacity ? 'badge badge-danger' : 'badge badge-success'}">
            ${c.enrolled_count} / ${c.capacity}
          </span>
        </td>
        <td class="actions-cell">
          <button class="btn btn-outline btn-sm btn-icon" onclick="editCourse(${c.course_id})">✏️</button>
          <button class="btn btn-danger btn-sm btn-icon" onclick="deleteCourse(${c.course_id}, '${esc(c.course_name)}')">🗑️</button>
        </td>
      </tr>`).join('');
  } catch (e) {
    tbody.innerHTML = emptyState('⚠️', 'Failed to load courses: ' + e.message);
  }
}

$('btn-add-course').addEventListener('click', () => {
  $('course-modal-title').textContent = 'Add Course';
  $('course-form').reset();
  $('course-id-hidden').value = '';
  openModal('course-modal');
});

$('course-form').addEventListener('submit', async e => {
  e.preventDefault();
  const cid = $('course-id-hidden').value;
  const fval = $('c-faculty').value;
  const body = {
    course_code: $('c-code').value.trim(),
    course_name: $('c-name').value.trim(),
    department:  $('c-dept').value.trim(),
    credits:     parseInt($('c-credits').value),
    capacity:    parseInt($('c-capacity').value),
    faculty_id:  fval ? parseInt(fval) : null,
  };
  try {
    if (cid) {
      await api('PUT', `/api/courses/${cid}`, body);
      toast('Course updated successfully', 'success');
    } else {
      await api('POST', '/api/courses', body);
      toast('Course added successfully', 'success');
    }
    closeModal('course-modal');
    loadCourses();
  } catch (e) {
    toast(e.message, 'error');
  }
});

async function editCourse(id) {
  try {
    const { data } = await api('GET', `/api/courses/${id}`);
    $('course-modal-title').textContent = 'Edit Course';
    $('course-id-hidden').value = id;
    $('c-code').value     = data.course_code;
    $('c-name').value     = data.course_name;
    $('c-dept').value     = data.department;
    $('c-credits').value  = data.credits;
    $('c-capacity').value = data.capacity;
    $('c-faculty').value  = data.faculty_id || '';
    openModal('course-modal');
  } catch (e) {
    toast('Could not load course: ' + e.message, 'error');
  }
}

async function deleteCourse(id, name) {
  if (!confirm(`Delete course "${name}"? This will also remove all enrollments for this course.`)) return;
  try {
    await api('DELETE', `/api/courses/${id}`);
    toast('Course deleted', 'success');
    loadCourses();
  } catch (e) {
    toast(e.message, 'error');
  }
}

$('course-search-btn').addEventListener('click', () =>
  loadCourses($('course-search').value));
$('course-search').addEventListener('keypress', e =>
  e.key === 'Enter' && loadCourses($('course-search').value));

// ==========================================================================
// ENROLLMENTS
// ==========================================================================

async function loadStudentOptions() {
  try {
    const { data } = await api('GET', '/api/students');
    const sel = $('e-student');
    sel.innerHTML = '<option value="">— Select Student —</option>' +
      data.map(s => `<option value="${s.student_id}">${esc(s.full_name)} (#${s.student_id})</option>`).join('');
  } catch (_) {}
}

async function loadCourseOptions() {
  try {
    const { data } = await api('GET', '/api/courses');
    const sel = $('e-course');
    sel.innerHTML = '<option value="">— Select Course —</option>' +
      data.map(c => `<option value="${c.course_id}">${esc(c.course_code)}: ${esc(c.course_name)} (${c.enrolled_count}/${c.capacity})</option>`).join('');
  } catch (_) {}
}

async function loadEnrollments() {
  const tbody = $('enrollments-tbody');
  tbody.innerHTML = loadingRow();
  try {
    const { data } = await api('GET', '/api/enrollments');
    if (!data.length) { tbody.innerHTML = emptyState('📋', 'No enrollments found'); return; }
    tbody.innerHTML = data.map(en => {
      const badgeMap = { Active: 'badge-success', Dropped: 'badge-danger', Completed: 'badge-info' };
      return `<tr>
        <td>#${en.enrollment_id}</td>
        <td>${esc(en.student_name)}</td>
        <td>${esc(en.course_code)}: ${esc(en.course_name)}</td>
        <td>${fmtDate(en.enrollment_date)}</td>
        <td><span class="badge ${badgeMap[en.status] || 'badge-secondary'}">${esc(en.status)}</span></td>
        <td class="actions-cell">
          <button class="btn btn-outline btn-sm" onclick="changeEnrollmentStatus(${en.enrollment_id}, '${en.status}')">✏️ Status</button>
          <button class="btn btn-danger btn-sm btn-icon" onclick="deleteEnrollment(${en.enrollment_id})">🗑️</button>
        </td>
      </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = emptyState('⚠️', 'Failed to load enrollments: ' + e.message);
  }
}

$('enrollment-form').addEventListener('submit', async e => {
  e.preventDefault();
  const body = {
    student_id:      parseInt($('e-student').value),
    course_id:       parseInt($('e-course').value),
    enrollment_date: $('e-date').value || undefined,
    status:          $('e-status').value,
  };
  if (!body.student_id || !body.course_id) { toast('Please select a student and a course', 'error'); return; }
  try {
    await api('POST', '/api/enrollments', body);
    toast('Student enrolled successfully', 'success');
    $('enrollment-form').reset();
    loadEnrollments();
    loadCourseOptions();
  } catch (e) {
    toast(e.message, 'error');
  }
});

async function changeEnrollmentStatus(id, current) {
  const statuses = ['Active', 'Dropped', 'Completed'].filter(s => s !== current);
  const next = prompt(`Change status from "${current}" to:\n${statuses.map((s,i)=>`${i+1}. ${s}`).join('\n')}\nEnter 1, 2, or new value:`, '');
  if (!next) return;
  const status = statuses[parseInt(next) - 1] || next;
  if (!['Active', 'Dropped', 'Completed'].includes(status)) { toast('Invalid status', 'error'); return; }
  try {
    await api('PUT', `/api/enrollments/${id}`, { status });
    toast('Enrollment status updated', 'success');
    loadEnrollments();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function deleteEnrollment(id) {
  if (!confirm('Remove this enrollment? This will also delete any associated grade.')) return;
  try {
    await api('DELETE', `/api/enrollments/${id}`);
    toast('Enrollment removed', 'success');
    loadEnrollments();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ==========================================================================
// GRADES
// ==========================================================================

async function loadEnrollmentOptions() {
  try {
    const { data } = await api('GET', '/api/enrollments');
    const sel = $('g-enrollment');
    sel.innerHTML = '<option value="">— Select Enrollment —</option>' +
      data.map(en => `<option value="${en.enrollment_id}">${esc(en.student_name)} → ${esc(en.course_code)} (#${en.enrollment_id})</option>`).join('');
  } catch (_) {}
}

async function loadGrades() {
  const tbody = $('grades-tbody');
  tbody.innerHTML = loadingRow();
  try {
    const { data } = await api('GET', '/api/grades');
    if (!data.length) { tbody.innerHTML = emptyState('📊', 'No grades recorded yet'); return; }
    tbody.innerHTML = data.map(g => `
      <tr>
        <td>#${g.grade_id}</td>
        <td>${esc(g.student_name)}</td>
        <td>${esc(g.course_code)}: ${esc(g.course_name)}</td>
        <td>${scoreBadge(g.score)}</td>
        <td>${esc(g.remarks) || '<span style="color:#aaa">—</span>'}</td>
        <td>${fmtDate(g.updated_at)}</td>
        <td class="actions-cell">
          <button class="btn btn-outline btn-sm btn-icon" onclick="editGrade(${g.grade_id}, ${g.score}, '${esc(g.remarks || '')}')">✏️</button>
          <button class="btn btn-danger btn-sm btn-icon" onclick="deleteGrade(${g.grade_id})">🗑️</button>
        </td>
      </tr>`).join('');
  } catch (e) {
    tbody.innerHTML = emptyState('⚠️', 'Failed to load grades: ' + e.message);
  }
}

$('grade-form').addEventListener('submit', async e => {
  e.preventDefault();
  const eid = $('g-enrollment').value;
  if (!eid) { toast('Please select an enrollment', 'error'); return; }
  const body = {
    enrollment_id: parseInt(eid),
    score:   parseFloat($('g-score').value),
    remarks: $('g-remarks').value.trim(),
  };
  try {
    await api('POST', '/api/grades', body);
    toast('Grade recorded successfully', 'success');
    $('grade-form').reset();
    loadGrades();
  } catch (e) {
    toast(e.message, 'error');
  }
});

function editGrade(id, score, remarks) {
  $('edit-grade-id').value      = id;
  $('edit-grade-score').value   = score;
  $('edit-grade-remarks').value = remarks;
  openModal('grade-edit-modal');
}

$('grade-edit-form').addEventListener('submit', async e => {
  e.preventDefault();
  const gid = $('edit-grade-id').value;
  const body = {
    score:   parseFloat($('edit-grade-score').value),
    remarks: $('edit-grade-remarks').value.trim(),
  };
  try {
    await api('PUT', `/api/grades/${gid}`, body);
    toast('Grade updated successfully', 'success');
    closeModal('grade-edit-modal');
    loadGrades();
  } catch (e) {
    toast(e.message, 'error');
  }
});

async function deleteGrade(id) {
  if (!confirm('Delete this grade record?')) return;
  try {
    await api('DELETE', `/api/grades/${id}`);
    toast('Grade deleted', 'success');
    loadGrades();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ==========================================================================
// REPORTS
// ==========================================================================

const reportRenderers = {
  'enrollment-summary': renderEnrollmentSummary,
  'student-course-details': renderStudentCourseDetails,
  'top-students': renderTopStudents,
  'department-stats': renderDeptStats,
  'no-enrollments': renderNoEnrollments,
};

function showReport(key) {
  document.querySelectorAll('.report-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.report === key));
  if (reportRenderers[key]) reportRenderers[key]();
}

document.querySelectorAll('.report-tab').forEach(t =>
  t.addEventListener('click', () => showReport(t.dataset.report)));

async function renderEnrollmentSummary() {
  const tbody = $('report-tbody');
  tbody.innerHTML = loadingRow();
  try {
    const { data } = await api('GET', '/api/reports/enrollment-summary');
    if (!data.length) { tbody.innerHTML = emptyState('📋', 'No data available'); return; }
    const cols = Object.keys(data[0]);
    $('report-thead').innerHTML = '<tr>' + cols.map(c => `<th>${c.replace(/_/g,' ')}</th>`).join('') + '</tr>';
    tbody.innerHTML = data.map(row =>
      '<tr>' + cols.map(c => `<td>${row[c] ?? '—'}</td>`).join('') + '</tr>'
    ).join('');
  } catch (e) {
    tbody.innerHTML = emptyState('⚠️', e.message);
  }
}

async function renderStudentCourseDetails() {
  const tbody = $('report-tbody');
  tbody.innerHTML = loadingRow();
  try {
    const { data } = await api('GET', '/api/reports/student-course-details');
    if (!data.length) { tbody.innerHTML = emptyState('📋', 'No data available'); return; }
    const cols = Object.keys(data[0]);
    $('report-thead').innerHTML = '<tr>' + cols.map(c => `<th>${c.replace(/_/g,' ')}</th>`).join('') + '</tr>';
    tbody.innerHTML = data.map(row =>
      '<tr>' + cols.map(c => {
        const v = row[c];
        if (c === 'score') return `<td>${scoreBadge(v)}</td>`;
        return `<td>${v ?? '—'}</td>`;
      }).join('') + '</tr>'
    ).join('');
  } catch (e) {
    tbody.innerHTML = emptyState('⚠️', e.message);
  }
}

async function renderTopStudents() {
  const tbody = $('report-tbody');
  tbody.innerHTML = loadingRow();
  try {
    const { data } = await api('GET', '/api/reports/top-students?limit=15');
    if (!data.length) { tbody.innerHTML = emptyState('🏆', 'No graded students yet'); return; }
    $('report-thead').innerHTML = '<tr><th>#</th><th>Student</th><th>Department</th><th>Weighted GPA (4.0)</th><th>Avg Score</th><th>Credits</th><th>Graded Courses</th></tr>';
    tbody.innerHTML = data.map((s, i) => `
      <tr>
        <td>${i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : i + 1}</td>
        <td><strong>${esc(s.full_name)}</strong></td>
        <td>${esc(s.department)}</td>
        <td><span class="badge badge-info" style="font-size:.85rem;">🎓 ${s.weighted_gpa !== null && s.weighted_gpa !== undefined ? Number(s.weighted_gpa).toFixed(2) : '—'}</span></td>
        <td>${scoreBadge(s.avg_score)}</td>
        <td>${s.total_credits ?? '—'} cr</td>
        <td>${s.graded_courses}</td>
      </tr>`).join('');
  } catch (e) {
    tbody.innerHTML = emptyState('⚠️', e.message);
  }
}

async function renderDeptStats() {
  const tbody = $('report-tbody');
  tbody.innerHTML = loadingRow();
  try {
    const { data } = await api('GET', '/api/reports/department-stats');
    if (!data.length) { tbody.innerHTML = emptyState('🏛️', 'No department data'); return; }
    $('report-thead').innerHTML = '<tr><th>Department</th><th>Students</th><th>Courses</th><th>Enrollments</th><th>Avg Score</th></tr>';
    tbody.innerHTML = data.map(d => `
      <tr>
        <td><strong>${esc(d.department)}</strong></td>
        <td>${d.student_count}</td>
        <td>${d.course_count}</td>
        <td>${d.total_enrollments}</td>
        <td>${scoreBadge(d.avg_score)}</td>
      </tr>`).join('');
  } catch (e) {
    tbody.innerHTML = emptyState('⚠️', e.message);
  }
}

async function renderNoEnrollments() {
  const tbody = $('report-tbody');
  tbody.innerHTML = loadingRow();
  try {
    const { data } = await api('GET', '/api/reports/students-without-enrollments');
    if (!data.length) {
      tbody.innerHTML = emptyState('🎉', 'All students have active enrollments!');
      $('report-thead').innerHTML = '';
      return;
    }
    $('report-thead').innerHTML = '<tr><th>ID</th><th>Name</th><th>Email</th><th>Department</th><th>Year</th><th>Joined</th></tr>';
    tbody.innerHTML = data.map(s => `
      <tr>
        <td>#${s.student_id}</td>
        <td>${esc(s.full_name)}</td>
        <td>${esc(s.email)}</td>
        <td>${esc(s.department)}</td>
        <td>Year ${s.year_of_study}</td>
        <td>${fmtDate(s.created_at)}</td>
      </tr>`).join('');
  } catch (e) {
    tbody.innerHTML = emptyState('⚠️', e.message);
  }
}

// ==========================================================================
// Bootstrap
// ==========================================================================

// Set today's date as default for enrollment date picker
const dateInput = $('e-date');
if (dateInput) dateInput.valueAsDate = new Date();

// Start on dashboard
navigate('sec-dashboard');

// ==========================================================================
// USERS  (admin portal)
// ==========================================================================

async function loadUsers() {
  const tbody = $('users-tbody');
  tbody.innerHTML = '<tr><td colspan="6" class="loading-row"><div class="spinner"></div></td></tr>';
  try {
    const { data } = await api('GET', '/api/users');
    if (!data.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-row">No user accounts yet. Create one below.</td></tr>';
      return;
    }
    const roleBadge = r => {
      const map = { admin: 'badge-danger', student: 'badge-success', faculty: 'badge-info' };
      return `<span class="badge ${map[r] || 'badge-gray'}">${r}</span>`;
    };
    tbody.innerHTML = data.map(u => `
      <tr>
        <td>${u.user_id}</td>
        <td><strong>${u.username}</strong></td>
        <td>${roleBadge(u.role)}</td>
        <td>${u.linked_id ?? '<em style="color:#bbb">none</em>'}</td>
        <td>${fmtDate(u.created_at)}</td>
        <td style="display:flex;gap:6px;flex-wrap:wrap;">
          <button class="btn btn-sm btn-outline" onclick="openResetPw(${u.user_id}, '${u.username}')">🔑 Reset PW</button>
          <button class="btn btn-sm btn-danger" onclick="deleteUser(${u.user_id}, '${u.username}')">🗑️ Delete</button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-row" style="color:#c62828">${e.message}</td></tr>`;
  }
}

function openUserModal() {
  $('user-form').reset();
  $('linked-id-group').style.display = 'none';
  openModal('user-modal');
}

function toggleLinkedId() {
  const role = $('u-role').value;
  const grp  = $('linked-id-group');
  const lbl  = $('linked-id-label');
  if (role === 'student' || role === 'faculty') {
    grp.style.display = '';
    lbl.textContent = role === 'student'
      ? 'Linked Student ID *'
      : 'Linked Faculty ID *';
  } else {
    grp.style.display = 'none';
  }
}

$('user-form').addEventListener('submit', async e => {
  e.preventDefault();
  const role     = $('u-role').value;
  const linkedId = $('u-linked-id').value;
  const payload  = {
    username:  $('u-username').value.trim(),
    password:  $('u-password').value,
    role,
    linked_id: (role !== 'admin' && linkedId) ? parseInt(linkedId) : null,
  };
  try {
    await api('POST', '/api/users', payload);
    toast('User created successfully!');
    closeModal('user-modal');
    loadUsers();
    loadDashboard();
  } catch (e) {
    toast(e.message, 'error');
  }
});

function openResetPw(uid, username) {
  $('reset-uid').value = uid;
  $('reset-pw-value').value = '';
  openModal('reset-pw-modal');
  document.querySelector('#reset-pw-modal .modal-header h3').textContent =
    `Reset Password — ${username}`;
}

$('reset-pw-form').addEventListener('submit', async e => {
  e.preventDefault();
  const uid = parseInt($('reset-uid').value);
  const pw  = $('reset-pw-value').value;
  try {
    await api('PUT', `/api/users/${uid}/reset-password`, { password: pw });
    toast('Password reset successfully!');
    closeModal('reset-pw-modal');
  } catch (e) {
    toast(e.message, 'error');
  }
});

async function deleteUser(uid, username) {
  if (!confirm(`Delete user account "${username}"? This cannot be undone.`)) return;
  try {
    await api('DELETE', `/api/users/${uid}`);
    toast(`User "${username}" deleted`);
    loadUsers();
    loadDashboard();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ==========================================================================
// AUDIT TRAIL  (MySQL Trigger logs)
// ==========================================================================

async function loadAuditLogs() {
  const tbody = $('audit-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" class="loading-row"><div class="spinner"></div></td></tr>';
  try {
    const { data } = await api('GET', '/api/audit-logs');
    if (!data.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-row">No trigger events recorded yet. Update or delete a grade or enrollment to see trigger logs!</td></tr>';
      return;
    }
    const actBadge = a => {
      const m = { UPDATE: 'badge-warning', DELETE: 'badge-danger', INSERT: 'badge-success' };
      return `<span class="badge ${m[a] || 'badge-info'}">${a}</span>`;
    };
    tbody.innerHTML = data.map(row => `
      <tr>
        <td>#${row.log_id}</td>
        <td><strong>${esc(row.table_name)}</strong></td>
        <td>${actBadge(row.action_type)}</td>
        <td>#${row.record_id}</td>
        <td><code style="font-size:.8rem;color:#c62828;">${esc(row.old_value || '—')}</code></td>
        <td><code style="font-size:.8rem;color:#2e7d32;">${esc(row.new_value || '—')}</code></td>
        <td>${fmtDate(row.changed_at)}</td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-row" style="color:#c62828">${esc(e.message)}</td></tr>`;
  }
}

// ==========================================================================
// MONGODB NOSQL STORE  (Admin view of Announcements, Feedback & Documents)
// ==========================================================================

async function loadNoSQLOverview() {
  const annTbody = $('nosql-ann-tbody');
  const fbTbody  = $('nosql-fb-tbody');
  const pre      = $('nosql-json-preview');
  if (!annTbody) return;

  annTbody.innerHTML = loadingRow();
  fbTbody.innerHTML  = loadingRow();

  try {
    const { data } = await api('GET', '/api/nosql/overview');
    const cols = (data.status && data.status.collections) || {};

    if ($('nosql-cnt-ann')) $('nosql-cnt-ann').textContent = cols.course_announcements ?? 0;
    if ($('nosql-cnt-fb'))  $('nosql-cnt-fb').textContent  = cols.course_feedback ?? 0;
    if ($('nosql-cnt-att')) $('nosql-cnt-att').textContent = cols.attendance_sessions ?? 0;
    if ($('nosql-cnt-tr'))  $('nosql-cnt-tr').textContent  = cols.student_transcripts ?? 0;

    // 1. Announcements
    const anns = data.announcements || [];
    if (!anns.length) {
      annTbody.innerHTML = '<tr><td colspan="4" class="empty-row">No course announcements in MongoDB</td></tr>';
    } else {
      const prioBadge = p => {
        const m = { Exam: 'badge-danger', Important: 'badge-warning', Normal: 'badge-info' };
        return `<span class="badge ${m[p] || 'badge-secondary'}">${esc(p || 'Normal')}</span>`;
      };
      annTbody.innerHTML = anns.map(a => `
        <tr>
          <td>
            <code class="mono" style="font-weight:600;color:var(--primary)">${esc(a.course_code)}</code>
            <div style="font-size:.73rem;color:var(--text-muted)">${esc(a.faculty_name || '')}</div>
          </td>
          <td>
            <div style="font-weight:600;">${esc(a.title)}</div>
            <div style="font-size:.78rem;color:var(--text-muted);">${esc(a.message)}</div>
          </td>
          <td>
            ${prioBadge(a.priority)}
            <div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap;">
              ${(a.tags || []).map(t => `<span class="badge badge-secondary">${esc(t)}</span>`).join('')}
            </div>
          </td>
          <td>
            <button class="btn btn-sm btn-danger" onclick="deleteAdminAnnouncement('${esc(a._id)}')">Delete</button>
          </td>
        </tr>`).join('');
    }

    // 2. Course Feedback
    const fbs = data.feedback || [];
    if (!fbs.length) {
      fbTbody.innerHTML = '<tr><td colspan="4" class="empty-row">No student course reviews in MongoDB</td></tr>';
    } else {
      fbTbody.innerHTML = fbs.map(f => {
        const stars = '⭐'.repeat(Math.max(1, Math.min(5, Number(f.rating || 5))));
        return `
          <tr>
            <td><code class="mono" style="font-weight:600;color:var(--primary)">${esc(f.course_code)}</code></td>
            <td><strong>${esc(f.student_name)}</strong></td>
            <td>
              <span title="${f.rating}/5">${stars}</span>
              <div style="font-size:.72rem;color:var(--text-muted)">${esc(f.difficulty || 'Moderate')}</div>
            </td>
            <td>
              <div style="font-size:.82rem;">${esc(f.comment)}</div>
              <div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap;">
                ${(f.tags || []).map(t => `<span class="badge badge-secondary">${esc(t)}</span>`).join('')}
              </div>
            </td>
          </tr>`;
      }).join('');
    }

    // 3. Raw BSON/JSON Document Inspector
    if (pre) {
      const samplePayload = {
        database: data.status ? data.status.database : 'CampusHub_NoSQL',
        sample_announcement_doc: anns[0] || null,
        sample_feedback_doc: fbs[0] || null,
        sample_attendance_session_doc: (data.attendance_sessions || [])[0] || null,
        sample_transcript_doc: (data.transcripts || [])[0] || null,
      };
      pre.textContent = JSON.stringify(samplePayload, null, 2);
    }
  } catch (e) {
    toast('Failed to load MongoDB collections: ' + e.message, 'error');
  }
}

async function deleteAdminAnnouncement(annId) {
  if (!confirm('Remove this announcement document from MongoDB?')) return;
  try {
    await api('DELETE', `/api/nosql/announcements/${encodeURIComponent(annId)}`);
    toast('Announcement deleted from MongoDB');
    loadNoSQLOverview();
  } catch (e) {
    toast(e.message, 'error');
  }
}
