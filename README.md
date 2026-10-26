# 🏛️ CampusHub — Hybrid RDBMS (MySQL 8.0) & NoSQL (MongoDB) University Management System

A full-stack **Polyglot Persistence** university academic platform built with **Python Flask**, **MySQL 8.0 (Relational ACID Engine)**, **MongoDB (`CampusHub_NoSQL` Document Store)**, and a **3-Portal Role-Based Web Interface** (Admin, Faculty, and Student Portals).

---

## ✨ Key Highlights (Fast Learner Live Project)

| Layer / Module | Industry-Standard Database & Application Features |
| :--- | :--- |
| **🗄️ MySQL 8.0 (RDBMS)** | **9 Normalized (3NF) Tables**, Foreign Key constraints, **4 Automated `AFTER UPDATE` / `AFTER DELETE` Audit Triggers**, **2 Analytical SQL Views**, and **ACID Row-Level Locking (`SELECT ... FOR UPDATE`)** to prevent course overbooking. |
| **🍃 MongoDB (NoSQL)** | **5 BSON/JSON Document Collections** (`course_announcements`, `course_feedback`, `attendance_sessions`, `audit_logs`, `student_transcripts`) + **Multi-Stage Aggregation Pipelines (`$match → $group → $avg → $sort`)** for live course ratings. |
| **🛡️ Admin Portal (`/`)** | **2×2 Executive Bento Grid** (Course Seat Utilization, Dean's List, Departmental Pulse, Recent Enrollments), full entity CRUD, **⚡ Audit Trail Viewer**, and interactive **🍃 MongoDB Document Explorer**. |
| **👨‍🏫 Faculty Portal (`/faculty-portal`)** | Assigned courses overview, student roster grading with auto-calculated letter grades (`A+` to `F`), batch session **Attendance Tracking** (synced to both MySQL & MongoDB), and **Course Broadcast Announcements**. |
| **🎓 Student Portal (`/student-portal`)** | Self-service **Course Catalog Enrollment & Drop**, **Credit-Weighted 4.0 GPA Engine**, **Official Printable Transcript Modal**, per-course **Attendance Tracker (`< 75%` warning badge)**, and **Course Star Reviews**. |

---

## 🔐 Demo Login Credentials (All 3 Portals)

Once the app is running (and seeded via `python seed_data.py`), log in at **`http://localhost:5001/login`**:

| Role | Username | Password | Portal Route | Linked Profile |
| :--- | :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `admin123` | `/` | Full System & Database Admin |
| **Faculty Member** | `faculty1` | `faculty123` | `/faculty-portal` | Dr. Rajesh Kumar (Computer Science) |
| **Student** | `student1` | `student123` | `/student-portal` | Aarav Sharma (Computer Science) |

---

## 🚀 Quick-Start Guide (Run Locally in 3 Minutes)

### 1. Clone the Repository & Create Virtual Environment
```bash
git clone <YOUR_GITHUB_REPO_URL>
cd campushub
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure `.env`
Copy the template and set your local MySQL password:
```bash
cp .env.example .env
```
Edit `.env`:
```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_root_password
DB_NAME=CampusHub
MONGO_URI=mongodb://localhost:27017/
MONGO_DB_NAME=CampusHub_NoSQL
PORT=5001
```
> **Note on MongoDB:** `mongo_db.py` features a **Dual-Mode Hybrid Engine**. If a local `mongod` server is running on port `27017`, it connects via `PyMongo` automatically. If `mongod` is not installed on the evaluator's machine, it seamlessly falls back to a built-in JSON document engine persisted in `mongodb_data/*.json` with zero configuration required!

### 3. Seed Both Databases (MySQL + MongoDB) & Start the Server
```bash
python seed_data.py
python app.py
```
Open **`http://localhost:5001`** in your browser!

---

## 🗄️ Database Architecture Overview

### A. MySQL 8.0 Relational Schema (`CampusHub` — 9 Tables)
Full SQL DDL script available in [`CampusHub_Database.sql`](CampusHub_Database.sql):
1. **`Departments`** — 5 academic departments (`department_id` PK, `department_name` UNIQUE, `hod_name`, `building`)
2. **`Faculty`** — 5 faculty members across departments (`faculty_id` PK, `department_id` FK)
3. **`Students`** — Enrolled student profiles (`student_id` PK, `department_id` FK, `status`)
4. **`Courses`** — 12 courses with credit hours & seat limits (`course_id` PK, `max_capacity`, `department_id` FK, `faculty_id` FK)
5. **`Enrollments`** — Student course registrations (`enrollment_id` PK, `UNIQUE(student_id, course_id)`, `status`)
6. **`Grades`** — Numeric marks & letter grades (`grade_id` PK, `enrollment_id` FK UNIQUE, `marks`, `grade`)
7. **`Attendance`** — Daily class attendance records (`attendance_id` PK, `UNIQUE(enrollment_id, session_date)`, `status`)
8. **`AuditLog`** — Automated compliance history populated by MySQL `AFTER UPDATE` & `AFTER DELETE` triggers
9. **`Users`** — Role-based authentication accounts (`user_id` PK, Werkzeug PBKDF2 `password_hash`, `role`, `linked_id`)

**SQL Views & Triggers Included:**
- **Views:** `View_Student_Performance`, `View_Course_Utilization`
- **Triggers:** `trg_grades_after_update`, `trg_grades_after_delete`, `trg_enrollments_after_update`, `trg_enrollments_after_delete`

### B. MongoDB NoSQL Document Store (`CampusHub_NoSQL` — 5 Collections)
Implemented in [`mongo_db.py`](mongo_db.py) and pre-seeded in [`mongodb_data/`](mongodb_data/):
1. **`course_announcements`** — Faculty course broadcasts with priority levels and nested `tags: [...]` arrays
2. **`course_feedback`** — Student 1–5 star ratings and qualitative reviews (aggregated via `$match → $group → $avg`)
3. **`attendance_sessions`** — Single-document class session rosters containing embedded `records: [...]` arrays
4. **`audit_logs`** — Schema-free security and activity event stream with polymorphic `metadata: {...}` objects
5. **`student_transcripts`** — Denormalized, self-contained academic transcript snapshots with embedded `courses: [...]`

---

## 📂 Project Structure & Deliverables

```text
campushub/
├── app.py                          # Main Flask application, RBAC & 35+ REST API endpoints (MySQL + MongoDB)
├── db.py                           # MySQL 8.0 connection helper
├── mongo_db.py                     # MongoDB NoSQL document layer & aggregation pipeline engine
├── seed_data.py                    # One-click seeder for MySQL (tables/views/triggers) & MongoDB (5 collections)
├── create_user.py                  # CLI utility to create/reset role-based user accounts
├── CampusHub_Database.sql          # Standalone SQL script (DDL, 9 tables, 2 views, 4 triggers)
├── CampusHub_Project_Report.html   # Print-ready Project Report (open in browser -> Save as PDF)
├── CampusHub_Project_Report.md     # Markdown Project Report source
├── CampusHub_Presentation.pptx     # 12-Slide PowerPoint Presentation
├── CampusHub_Presentation.html     # Interactive HTML Slide Deck
├── mongodb_data/                   # Pre-seeded MongoDB JSON document collections
├── templates/                      # Role-specific HTML5 templates (index, faculty_portal, student_portal, login)
└── static/                         # Enterprise CSS (style.css) & portal JS modules (app.js, faculty.js, student.js)
```
