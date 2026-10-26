/**
 * student.js — Client logic for the CampusHub Student Portal
 * Talks exclusively to /api/student/* endpoints.
 */

let _studentDashboardData = null;
let _studentGradesData    = [];

// ── Utilities ────────────────────────────────────────────────────────────────

function showToast(msg, type = 'success') {
  const c   = document.getElementById('toast-container');
  const div = document.createElement('div');
  div.className = `toast toast-${type}`;
  div.textContent = msg;
  c.appendChild(div);
  setTimeout(() => div.remove(), 3500);
}

async function apiFetch(url, opts = {}) {
  const res  = await fetch(url, opts);
  const json = await res.json();
  if (!json.success) throw new Error(json.message || 'Request failed');
  return json;
}

function scorePill(score) {
  if (score === null || score === undefined) return '<span class="badge badge-gray">N/G</span>';
  const s = parseFloat(score);
  let cls, letter;
  if (s >= 90)      { cls = 'gl-a'; letter = 'A'; }
  else if (s >= 80) { cls = 'gl-b'; letter = 'B'; }
  else if (s >= 70) { cls = 'gl-c'; letter = 'C'; }
  else if (s >= 60) { cls = 'gl-d'; letter = 'D'; }
  else              { cls = 'gl-f'; letter = 'F'; }
  return `<span class="grade-letter ${cls}">${letter}</span>`;
}

function letterOnly(score) {
  if (score === null || score === undefined) return 'N/G';
  const s = parseFloat(score);
  if (s >= 90) return 'A';
  if (s >= 80) return 'B';
  if (s >= 70) return 'C';
  if (s >= 60) return 'D';
  return 'F';
}

function statusBadge(status) {
  const map = { Active: 'badge-success', Dropped: 'badge-danger', Completed: 'badge-info' };
  return `<span class="badge ${map[status] || 'badge-gray'}">${status}</span>`;
}

function attendanceBadge(pct, totalSessions) {
  if (!totalSessions || pct === null || pct === undefined) {
    return '<span class="badge badge-gray">No sessions</span>';
  }
  const p = parseFloat(pct);
  if (p < 75) {
    return `<span class="badge badge-danger" title="Below 75% requirement">⚠️ ${p}% (Low)</span>`;
  }
  return `<span class="badge badge-success">✅ ${p}%</span>`;
}

function fmt(dt) {
  if (!dt) return '—';
  return new Date(dt).toLocaleDateString('en-IN', { year:'numeric', month:'short', day:'numeric' });
}

// ── Tab navigation ────────────────────────────────────────────────────────────

document.querySelectorAll('.portal-nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.portal-nav-item').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.portal-section').forEach(x => x.classList.remove('active'));
    item.classList.add('active');
    const tab = document.getElementById(item.dataset.tab);
    if (tab) tab.classList.add('active');

    if (item.dataset.tab === 'tab-overview')   loadStudentDashboard();
    if (item.dataset.tab === 'tab-catalog')    loadStudentCatalog();
    if (item.dataset.tab === 'tab-courses')    loadStudentCourses();
    if (item.dataset.tab === 'tab-grades')     loadStudentGrades();
    if (item.dataset.tab === 'tab-attendance') loadStudentAttendance();
    if (item.dataset.tab === 'tab-nosql')      loadStudentNoSQLFeed();
  });
});

// ── Dashboard / Overview ──────────────────────────────────────────────────────

async function loadStudentDashboard() {
  try {
    const { data: d } = await apiFetch('/api/student/dashboard');
    _studentDashboardData = d;

    document.getElementById('s-welcome-name').textContent =
      `Welcome, ${d.profile.full_name}!`;
    document.getElementById('s-dept-year').textContent =
      `${d.profile.department} · Year ${d.profile.year_of_study} · Student ID #${d.profile.student_id}`;

    document.getElementById('s-stat-active').textContent = d.active_enrollments;
    document.getElementById('s-stat-gpa').textContent =
      d.weighted_gpa !== null && d.weighted_gpa !== undefined ? `${ Number(d.weighted_gpa).toFixed(2) } / 4.0` : '—';
    document.getElementById('s-stat-avg').textContent =
      d.avg_score !== null && d.avg_score !== undefined ? `${d.avg_score}%` : '—';
    document.getElementById('s-stat-attendance').innerHTML =
      d.overall_attendance !== null && d.overall_attendance !== undefined
        ? (d.overall_attendance < 75
            ? `<span style="color:#c62828">${d.overall_attendance}% ⚠️</span>`
            : `${d.overall_attendance}%`)
        : '—';

    const [{ data: grades }, { data: enrollments }] = await Promise.all([
      apiFetch('/api/student/my-grades'),
      apiFetch('/api/student/my-enrollments'),
    ]);
    _studentGradesData = grades;

    const tbody = document.getElementById('s-overview-grades');
    if (!grades.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-row">No courses or grades recorded yet</td></tr>';
    } else {
      tbody.innerHTML = grades.map(g => `
        <tr>
          <td><code class="mono" style="font-weight:600;color:var(--primary)">${g.course_code}</code> · ${g.course_name}</td>
          <td><span class="badge badge-info">${g.credits} cr</span></td>
          <td class="mono">${g.score !== null ? g.score + '%' : '—'}</td>
          <td>${scorePill(g.score)}</td>
          <td class="mono"><strong>${g.grade_points !== null && g.grade_points !== undefined ? Number(g.grade_points).toFixed(1) : '—'}</strong></td>
        </tr>
      `).join('');
    }

    const cTbody = document.getElementById('s-overview-courses');
    if (cTbody) {
      if (!enrollments.length) {
        cTbody.innerHTML = '<tr><td colspan="4" class="empty-row">Not enrolled in any courses yet</td></tr>';
      } else {
        cTbody.innerHTML = enrollments.map(e => `
          <tr>
            <td><code class="mono" style="font-weight:600;color:var(--primary)">${e.course_code}</code> · ${e.course_name}</td>
            <td style="font-size:.8rem;color:var(--text-muted)">${e.faculty_name || 'TBA'}</td>
            <td>${statusBadge(e.status)}</td>
            <td>${attendanceBadge(e.attendance_pct, e.total_sessions)}</td>
          </tr>
        `).join('');
      }
    }
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// ── Course Catalog (Self-Service Enroll / Drop) ──────────────────────────────

async function loadStudentCatalog() {
  const tbody = document.getElementById('s-catalog-tbody');
  tbody.innerHTML = '<tr><td colspan="7" class="loading-row"><div class="spinner"></div></td></tr>';
  try {
    const { data } = await apiFetch('/api/student/catalog');
    if (!data.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-row">No courses available in the catalog</td></tr>';
      return;
    }
    tbody.innerHTML = data.map(c => {
      const enrolled = Number(c.enrolled_count || 0);
      const cap      = Number(c.capacity || 0);
      const isFull   = enrolled >= cap;
      const pct      = cap > 0 ? Math.min(100, Math.round((enrolled / cap) * 100)) : 0;
      const barColor = isFull ? '#dc2626' : pct >= 80 ? '#d97706' : '#16a34a';

      let actionHtml = '';
      if (c.my_status === 'Active') {
        actionHtml = `
          <div style="display:flex;align-items:center;gap:8px;">
            <span class="badge badge-success">Enrolled</span>
            <button class="btn btn-sm btn-danger" onclick="dropCourse(${c.my_enrollment_id}, '${c.course_code}')">Drop</button>
          </div>`;
      } else if (c.my_status === 'Completed') {
        actionHtml = `<span class="badge badge-info">✅ Completed</span>`;
      } else if (isFull) {
        actionHtml = `<span class="badge badge-danger">🔒 Full</span>`;
      } else {
        actionHtml = `<button class="btn btn-sm btn-primary" onclick="enrollInCourse(${c.course_id})">➕ Enroll</button>`;
      }

      return `
        <tr>
          <td><strong>${c.course_code}</strong></td>
          <td>${c.course_name}</td>
          <td>${c.department}</td>
          <td><span class="badge badge-info">${c.credits} cr</span></td>
          <td>${c.faculty_name || '<em style="color:#bbb">TBA</em>'}</td>
          <td>
            <div style="display:flex;align-items:center;gap:8px;min-width:120px;">
              <div style="flex:1;height:8px;background:#e2e8f0;border-radius:4px;overflow:hidden;">
                <div style="width:${pct}%;height:100%;background:${barColor};"></div>
              </div>
              <span style="font-size:.8rem;font-weight:600;">${enrolled}/${cap}</span>
            </div>
          </td>
          <td>${actionHtml}</td>
        </tr>
      `;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-row" style="color:#c62828">${e.message}</td></tr>`;
  }
}

async function enrollInCourse(courseId) {
  try {
    const res = await apiFetch('/api/student/enroll', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ course_id: courseId }),
    });
    showToast(res.message || 'Enrolled successfully!');
    loadStudentCatalog();
    loadStudentDashboard();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function dropCourse(enrollmentId, courseCode) {
  if (!confirm(`Are you sure you want to drop ${courseCode}?`)) return;
  try {
    const res = await apiFetch(`/api/student/drop/${enrollmentId}`, {
      method: 'PUT',
    });
    showToast(res.message || 'Course dropped');
    loadStudentCatalog();
    loadStudentCourses();
    loadStudentDashboard();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// ── My Courses ────────────────────────────────────────────────────────────────

async function loadStudentCourses() {
  const tbody = document.getElementById('s-courses-tbody');
  tbody.innerHTML = '<tr><td colspan="9" class="loading-row"><div class="spinner"></div></td></tr>';
  try {
    const { data } = await apiFetch('/api/student/my-enrollments');
    if (!data.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty-row">You are not enrolled in any courses yet. Visit "Browse Courses" to enroll!</td></tr>';
      return;
    }
    tbody.innerHTML = data.map(e => `
      <tr>
        <td><strong>${e.course_code}</strong></td>
        <td>${e.course_name}</td>
        <td>${e.department}</td>
        <td><span class="badge badge-info">${e.credits} cr</span></td>
        <td>${e.faculty_name || '<em style="color:#bbb">Unassigned</em>'}</td>
        <td>${attendanceBadge(e.attendance_pct, e.total_sessions)}</td>
        <td>${fmt(e.enrollment_date)}</td>
        <td>${statusBadge(e.status)}</td>
        <td>
          ${e.status === 'Active'
            ? `<button class="btn btn-sm btn-danger" onclick="dropCourse(${e.enrollment_id}, '${e.course_code}')">Drop</button>`
            : '<span style="color:#bbb">—</span>'}
        </td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-row" style="color:#c62828">${e.message}</td></tr>`;
  }
}

// ── My Grades & GPA ──────────────────────────────────────────────────────────

async function loadStudentGrades() {
  const tbody = document.getElementById('s-grades-tbody');
  tbody.innerHTML = '<tr><td colspan="9" class="loading-row"><div class="spinner"></div></td></tr>';
  try {
    const { data } = await apiFetch('/api/student/my-grades');
    _studentGradesData = data;
    if (!data.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty-row">No grade data available yet</td></tr>';
      return;
    }
    tbody.innerHTML = data.map(g => `
      <tr>
        <td><strong>${g.course_code}</strong></td>
        <td>${g.course_name}</td>
        <td>${g.credits}</td>
        <td>${statusBadge(g.enrollment_status)}</td>
        <td>${g.score !== null ? g.score + '%' : '—'}</td>
        <td>${scorePill(g.score)}</td>
        <td><strong>${g.grade_points !== null && g.grade_points !== undefined ? Number(g.grade_points).toFixed(1) : '—'}</strong></td>
        <td>${g.remarks || '—'}</td>
        <td>${fmt(g.updated_at)}</td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-row" style="color:#c62828">${e.message}</td></tr>`;
  }
}

// ── Attendance Tracker ────────────────────────────────────────────────────────

async function loadStudentAttendance() {
  const sumTbody = document.getElementById('s-att-summary-tbody');
  const recTbody = document.getElementById('s-att-records-tbody');
  sumTbody.innerHTML = '<tr><td colspan="7" class="loading-row"><div class="spinner"></div></td></tr>';
  recTbody.innerHTML = '<tr><td colspan="4" class="loading-row"><div class="spinner"></div></td></tr>';

  try {
    const { data } = await apiFetch('/api/student/my-attendance');
    const summary  = data.summary || [];
    const records  = data.records || [];

    if (!summary.length) {
      sumTbody.innerHTML = '<tr><td colspan="7" class="empty-row">No active courses found</td></tr>';
    } else {
      sumTbody.innerHTML = summary.map(s => `
        <tr>
          <td><strong>${s.course_code}</strong></td>
          <td>${s.course_name}</td>
          <td>${s.total_sessions || 0}</td>
          <td><span class="badge badge-success">${s.present_count || 0}</span></td>
          <td><span class="badge badge-warning">${s.late_count || 0}</span></td>
          <td><span class="badge badge-danger">${s.absent_count || 0}</span></td>
          <td>${attendanceBadge(s.attendance_pct, s.total_sessions)}</td>
        </tr>
      `).join('');
    }

    if (!records.length) {
      recTbody.innerHTML = '<tr><td colspan="4" class="empty-row">No attendance sessions recorded yet</td></tr>';
    } else {
      const attBadge = st => {
        const m = { Present: 'badge-success', Late: 'badge-warning', Absent: 'badge-danger' };
        return `<span class="badge ${m[st] || 'badge-gray'}">${st}</span>`;
      };
      recTbody.innerHTML = records.map(r => `
        <tr>
          <td><strong>${fmt(r.session_date)}</strong></td>
          <td><strong>${r.course_code}</strong> — ${r.course_name}</td>
          <td>${attBadge(r.status)}</td>
          <td>${r.remarks || '—'}</td>
        </tr>
      `).join('');
    }
  } catch (e) {
    sumTbody.innerHTML = `<tr><td colspan="7" class="empty-row" style="color:#c62828">${e.message}</td></tr>`;
    recTbody.innerHTML = `<tr><td colspan="4" class="empty-row" style="color:#c62828">${e.message}</td></tr>`;
  }
}

// ── Official Printable Transcript ─────────────────────────────────────────────

async function openTranscriptModal() {
  try {
    if (!_studentDashboardData) {
      const { data } = await apiFetch('/api/student/dashboard');
      _studentDashboardData = data;
    }
    const { data: grades } = await apiFetch('/api/student/my-grades');
    _studentGradesData = grades;

    const p = _studentDashboardData.profile;
    document.getElementById('tr-name').textContent  = p.full_name;
    document.getElementById('tr-id').textContent    = p.student_id;
    document.getElementById('tr-dept').textContent  = p.department;
    document.getElementById('tr-year').textContent  = p.year_of_study;
    document.getElementById('tr-email').textContent = p.email;
    document.getElementById('tr-date').textContent  = fmt(new Date().toISOString());

    document.getElementById('tr-credits').textContent = _studentDashboardData.graded_credits || 0;
    document.getElementById('tr-avg').textContent     =
      _studentDashboardData.avg_score !== null ? `${_studentDashboardData.avg_score}%` : '—';
    document.getElementById('tr-gpa').textContent     =
      _studentDashboardData.weighted_gpa !== null ? Number(_studentDashboardData.weighted_gpa).toFixed(2) : '—';

    const tbody = document.getElementById('tr-tbody');
    if (!grades.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-row">No courses on record</td></tr>';
    } else {
      tbody.innerHTML = grades.map(g => `
        <tr>
          <td><strong>${g.course_code}</strong></td>
          <td>${g.course_name}</td>
          <td>${g.credits}</td>
          <td>${g.enrollment_status}</td>
          <td>${g.score !== null ? g.score + '%' : 'In Progress'}</td>
          <td><strong>${letterOnly(g.score)}</strong></td>
          <td>${g.grade_points !== null && g.grade_points !== undefined ? Number(g.grade_points).toFixed(1) : '—'}</td>
        </tr>
      `).join('');
    }

    document.getElementById('transcript-modal').classList.add('open');
  } catch (e) {
    showToast('Failed to generate transcript: ' + e.message, 'error');
  }
}

function closeTranscriptModal() {
  document.getElementById('transcript-modal').classList.remove('open');
}

// ── MongoDB NoSQL: Course Announcements & Reviews ────────────────────────────

async function loadStudentNoSQLFeed() {
  const annTbody = document.getElementById('s-ann-tbody');
  const fbTbody  = document.getElementById('s-fb-tbody');
  const cSelect  = document.getElementById('s-fb-course');
  if (!annTbody) return;

  annTbody.innerHTML = '<tr><td colspan="3" class="loading-row"><div class="spinner"></div></td></tr>';
  fbTbody.innerHTML  = '<tr><td colspan="4" class="loading-row"><div class="spinner"></div></td></tr>';

  try {
    const { data } = await apiFetch('/api/student/nosql/feed');
    const courses = data.my_courses || [];
    const anns    = data.announcements || [];
    const fbs     = data.feedback || [];

    if (cSelect) {
      const curVal = cSelect.value;
      cSelect.innerHTML = '<option value="">— Select your course —</option>' +
        courses.map(c =>
          `<option value="${c.course_id}" ${c.course_id == curVal ? 'selected' : ''}>${c.course_code} — ${c.course_name}</option>`
        ).join('');
    }

    const prioBadge = p => {
      const m = { Exam: 'badge-danger', Important: 'badge-warning', Normal: 'badge-info' };
      return `<span class="badge ${m[p] || 'badge-secondary'}">${p || 'Normal'}</span>`;
    };

    if (!anns.length) {
      annTbody.innerHTML = '<tr><td colspan="3" class="empty-row">No announcements for your courses yet</td></tr>';
    } else {
      annTbody.innerHTML = anns.map(a => `
        <tr>
          <td>
            <code class="mono" style="font-weight:600;color:var(--primary)">${a.course_code}</code>
            <div style="font-size:.73rem;color:var(--text-muted)">${a.faculty_name || ''}</div>
          </td>
          <td>
            <div style="font-weight:600;">${a.title}</div>
            <div style="font-size:.8rem;color:var(--text-muted);">${a.message}</div>
          </td>
          <td>
            ${prioBadge(a.priority)}
            <div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap;">
              ${(a.tags || []).map(t => `<span class="badge badge-secondary">${t}</span>`).join('')}
            </div>
          </td>
        </tr>
      `).join('');
    }

    if (!fbs.length) {
      fbTbody.innerHTML = '<tr><td colspan="4" class="empty-row">No course reviews yet. Be the first to review!</td></tr>';
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

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadStudentDashboard();

  const fbForm = document.getElementById('s-fb-form');
  if (fbForm) {
    fbForm.addEventListener('submit', async e => {
      e.preventDefault();
      const payload = {
        course_id:  parseInt(document.getElementById('s-fb-course').value),
        rating:     parseInt(document.getElementById('s-fb-rating').value),
        difficulty: document.getElementById('s-fb-difficulty').value,
        tags:       document.getElementById('s-fb-tags').value.trim(),
        comment:    document.getElementById('s-fb-comment').value.trim(),
      };
      try {
        await apiFetch('/api/student/nosql/feedback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        showToast('Course review saved to MongoDB!');
        document.getElementById('s-fb-comment').value = '';
        loadStudentNoSQLFeed();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }
});
