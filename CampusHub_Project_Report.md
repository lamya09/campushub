# PROJECT REPORT
## CampusHub — Hybrid University Student, Course & Academic Management System
**Database Technologies:** MySQL 8.0 (RDBMS) + MongoDB (NoSQL Document Store)  
**Backend & Frontend:** Python Flask, MySQL Connector/Python, PyMongo, HTML5, CSS3, ES6 JavaScript  
**Date of Submission:** October 26, 2026

---

## 1. Abstract
**CampusHub** is a full-stack, role-based University Student & Course Management System engineered using a **Polyglot Persistence (Hybrid RDBMS + NoSQL)** architecture. Structured transactional entities—such as students, faculty, courses, enrollments, grades, daily attendance records, and role-based user accounts—are managed in **MySQL 8.0** with strict 3NF normalization, foreign-key referential integrity, row-level locking (`SELECT ... FOR UPDATE`) for concurrent course enrollment, analytical SQL Views, and automated `AFTER UPDATE`/`DELETE` Audit Triggers.

To complement the relational backbone, **MongoDB (`CampusHub_NoSQL`)** is integrated as a document store for semi-structured and hierarchical data: course announcements with dynamic tag arrays (`course_announcements`), student course ratings and reviews (`course_feedback`), nested lecture attendance session documents (`attendance_sessions`), event-driven audit logs (`audit_logs`), and cached student transcript documents (`student_transcripts`). The system provides three isolated role-based portals (**Admin Dashboard**, **Faculty Portal**, and **Student Portal**) secured with Werkzeug PBKDF2 password hashing and Flask session guards.

---

## 2. Problem Statement & Objectives
### 2.1 Problem Statement
Traditional university management systems rely solely on flat spreadsheets or single-paradigm databases that struggle when handling both **strict ACID transactions** (such as preventing course over-enrollment when seats fill up) and **flexible, nested document workloads** (such as course announcements with tags, multi-dimensional student course reviews, and hierarchical session logs).

### 2.2 Objectives
1. **Relational Integrity & ACID Concurrency Control:** Enforce normalized relational schemas in MySQL with pessimistic row locking (`SELECT ... FOR UPDATE`) during student enrollment to prevent race conditions and capacity overflow.
2. **Database Programmability (Views & Triggers):** Utilize SQL Views (`CourseEnrollmentSummary`, `StudentCourseDetails`) for complex multi-table reporting and `AFTER UPDATE`/`AFTER DELETE` Triggers for tamper-evident audit logging.
3. **Polyglot Persistence with MongoDB (NoSQL):** Store hierarchical and schema-flexible entities in MongoDB collections (`course_announcements`, `course_feedback`, `attendance_sessions`, `student_transcripts`, `audit_logs`).
4. **Role-Based Multi-Portal Access:** Provide dedicated, session-guarded workflows for **Administrators**, **Faculty Members**, and **Students**.

---

## 3. System Architecture (Hybrid RDBMS + NoSQL)

```
+-------------------------------------------------------------------------+
|                        CLIENT PRESENTATION LAYER                        |
|  Admin Portal (/)     Faculty Portal (/faculty-portal)   Student Portal |
|  HTML5 + Modern CSS3 (Inter & Outfit) + Vanilla ES6 Fetch REST Client   |
+------------------------------------+------------------------------------+
                                     | REST JSON APIs (Session Guarded)
                                     v
+-------------------------------------------------------------------------+
|                    APPLICATION LAYER (Python Flask)                     |
|  • Role-Based Auth Guard (@app.before_request + PBKDF2 Password Hash)   |
|  • MySQL Connection Pool (db.py — MySQLConnectionPool, size=5)          |
|  • MongoDB Document Layer (mongo_db.py — PyMongo + JSON Doc Engine)     |
+--------------------+-------------------------------+--------------------+
                     |                               |
     Structured ACID | SQL Queries                   | BSON / JSON Documents
                     v                               v
+------------------------------------+   +--------------------------------+
|      RELATIONAL DB: MySQL 8.0      |   |   NoSQL DB: MongoDB Store      |
|      Database: CampusHub           |   |   Database: CampusHub_NoSQL    |
|  • Tables: Students, Faculty,      |   |  • course_announcements        |
|    Courses, Enrollments, Grades,   |   |  • course_feedback             |
|    Attendance, Users, AuditLog     |   |  • attendance_sessions         |
|  • Views: CourseEnrollmentSummary, |   |  • student_transcripts         |
|    StudentCourseDetails            |   |  • audit_logs                  |
|  • Triggers: 4 Audit Triggers      |   |                                |
+------------------------------------+   +--------------------------------+
```

---

## 4. Relational Database Design (MySQL 8.0)

### 4.1 Relational Schema (3NF Normalized)
| Table Name | Primary Key | Foreign Keys / Constraints | Purpose |
|---|---|---|---|
| `Students` | `student_id` | `email UNIQUE`, `year_of_study CHECK (1..6)` | Master student registry |
| `Faculty` | `faculty_id` | `email UNIQUE` | University faculty directory (5 faculty) |
| `Courses` | `course_id` | `course_code UNIQUE`, `faculty_id -> Faculty` | Course catalog with seat capacity & credits |
| `Enrollments` | `enrollment_id` | `student_id -> Students`, `course_id -> Courses` | Maps students to courses (`Active`/`Dropped`/`Completed`) |
| `Grades` | `grade_id` | `enrollment_id UNIQUE -> Enrollments` | Stores numerical score (`0–100`) and faculty remarks |
| `Attendance` | `attendance_id` | `enrollment_id -> Enrollments`, `UNIQUE(enrollment_id, session_date)` | Daily lecture attendance (`Present`/`Absent`/`Late`) |
| `Users` | `user_id` | `username UNIQUE`, `role ENUM('admin','student','faculty')` | Role-based authentication & `linked_id` mapping |
| `AuditLog` | `log_id` | Populated by MySQL Triggers | Tracks `OLD` and `NEW` values on updates and deletes |

### 4.2 Industry-Standard RDBMS Features Implemented
1. **Connection Pooling (`db.py`):** Uses `mysql.connector.pooling.MySQLConnectionPool(pool_size=5)` to reuse TCP connections efficiently.
2. **ACID Transaction with Row-Level Locking (`SELECT ... FOR UPDATE`):**
   When a student or admin enrolls a student in a course, the backend executes:
   ```sql
   SELECT capacity FROM Courses WHERE course_id = %s FOR UPDATE;
   SELECT COUNT(*) AS cnt FROM Enrollments WHERE course_id = %s AND status = 'Active';
   ```
   If `active_count >= capacity` or a duplicate active enrollment exists, the transaction executes `conn.rollback()` and returns HTTP `409 Conflict`. Otherwise, it inserts the enrollment and executes `conn.commit()`.
3. **Pre-Computed SQL Views:**
   - `CourseEnrollmentSummary`: Joins `Courses`, `Faculty`, and `Enrollments` with `GROUP BY` to compute live seat utilization.
   - `StudentCourseDetails`: Joins `Students`, `Enrollments`, `Courses`, and `Grades` for comprehensive academic reporting.
4. **Automated Database Triggers (`AFTER UPDATE` & `AFTER DELETE`):**
   Four MySQL triggers (`trg_grades_after_update`, `trg_grades_after_delete`, `trg_enrollments_after_update`, `trg_enrollments_after_delete`) automatically capture any modification or deletion of grades and enrollment statuses into the `AuditLog` table.

---

## 5. NoSQL Platform Design (MongoDB — `CampusHub_NoSQL`)

### 5.1 Why MongoDB is Used Alongside MySQL
While MySQL enforces strict relational schemas for enrollments and grading, several university workflows involve **hierarchical arrays, variable tags, and document-centric reads**. Storing these in MongoDB avoids expensive multi-table joins for tag arrays and nested session snapshots.

### 5.2 MongoDB Collections & Document Schemas

#### 1. `course_announcements` Collection
Stores faculty announcements with priority levels and array tags:
```json
{
  "_id": "8f4b2c91a3d04e71b29104ac",
  "course_id": 1,
  "course_code": "CS201",
  "course_name": "Database Management Systems",
  "faculty_id": 1,
  "faculty_name": "Dr. Aditi Sharma",
  "title": "Midterm Practical Exam & Normalization Viva",
  "message": "Please review 3NF/BCNF decomposition, SQL transactions (SELECT FOR UPDATE), and MongoDB document modeling.",
  "priority": "Exam",
  "tags": ["Midterm", "Viva", "RDBMS + NoSQL"],
  "created_at": "2026-10-26T17:18:15"
}
```

#### 2. `course_feedback` Collection
Stores 1–5 star ratings, difficulty assessments, tags, and qualitative reviews from students:
```json
{
  "_id": "a19d4e209c834f118b3019ef",
  "course_id": 1,
  "course_code": "CS201",
  "course_name": "Database Management Systems",
  "student_id": 1,
  "student_name": "Aarav Singh",
  "rating": 5,
  "difficulty": "Moderate",
  "tags": ["Hands-on Labs", "Clear Explanations", "Industry Relevant"],
  "comment": "The combination of SQL transactions and MongoDB document design made database concepts super clear.",
  "created_at": "2026-10-26T17:18:15"
}
```

#### 3. `attendance_sessions` Collection
Stores an entire lecture session as a single nested document containing summary metrics and an embedded `records` array:
```json
{
  "course_id": 1,
  "course_code": "CS201",
  "course_name": "Database Management Systems",
  "session_date": "2026-10-24",
  "faculty_id": 1,
  "summary": {
    "total_students": 3,
    "attended": 3,
    "absent": 0,
    "attendance_rate_pct": 100.0
  },
  "records": [
    { "enrollment_id": 1, "student_id": 1, "student_name": "Aarav Singh", "status": "Present", "remarks": null }
  ]
}
```

#### 4. `student_transcripts` & `audit_logs` Collections
Caches nested academic transcripts (`student_profile`, `academic_summary` with 4.0 Weighted GPA, and embedded `courses` array) and mirrors database audit events.

---

## 6. Portal Modules & Functional Walkthrough

### 6.1 Admin Portal (`/`)
- **Executive Dashboard:** Displays 5 KPI cards (Enrolled Students, Active Courses, Course Registrations, Mean Cohort Score, Portal Accounts) and a 2×2 live bento grid (Course Seat Utilization progress bars, Dean's List Top Performers by 4.0 Weighted GPA, Departmental Academic Pulse, and Recent Course Enrollments).
- **CRUD Modules:** Full search, create, update, and delete for **Students**, **Faculty** (5 faculty across departments), **Courses** (12 courses), **Enrollments**, **Grades**, and **Users**.
- **Analytical Reports:** 5 real-time reports powered by SQL Views, `GROUP BY` aggregations, and `NOT EXISTS` subqueries.
- **🍃 NoSQL Store Inspector:** Live view of all 5 MongoDB collections, announcements, student course reviews, and an interactive **BSON/JSON Document Structure Inspector**.
- **⚡ Audit Trail:** Displays real-time trigger logs from `AuditLog`.

### 6.2 Faculty Portal (`/faculty-portal`)
- **My Courses & Roster:** Displays only courses assigned to the logged-in professor with live capacity bars.
- **Inline Grade Entry:** Add or edit student scores (`0–100`) and remarks with server-side ownership verification.
- **Daily Attendance Sheet:** Mark students `Present`, `Absent`, or `Late` by date (with a "Mark All Present" shortcut) — dual-writes to MySQL `Attendance` and MongoDB `attendance_sessions`.
- **📢 Announcements & Feedback (NoSQL):** Publish course announcements to MongoDB and read student star ratings and reviews.

### 6.3 Student Portal (`/student-portal`)
- **Overview & 4.0 Weighted GPA:** Displays active enrollments, Cumulative Weighted GPA (4.0 scale), mean score, and overall attendance percentage.
- **🔍 Self-Service Course Catalog:** Browse university courses, inspect open seats, and click **Enroll** or **Drop** directly.
- **🖨️ Official Printable Transcript:** Generates a formatted university transcript card with one-click PDF/Print export.
- **📅 Attendance Tracker:** Shows per-course attendance breakdown (`Present`, `Late`, `Absent`) with an automatic `⚠️ Low (< 75%)` warning badge when attendance falls below 75%.
- **📢 Announcements & Reviews (NoSQL):** Read faculty announcements and submit 1–5⭐ course feedback into MongoDB.

---

## 7. Conclusion
**CampusHub** demonstrates how modern enterprise applications combine the strengths of **RDBMS (MySQL 8.0)** for transactional consistency, normalized relationships, views, and triggers with **NoSQL (MongoDB)** for flexible, nested document storage.
