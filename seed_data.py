#!/usr/bin/env python3
"""
seed_data.py — Populate CampusHub with rich courses, enrollments, grades,
attendance sessions, and trigger audit logs for all pre-existing students
and faculty.

Usage:
    source venv/bin/activate
    python seed_data.py
"""

import os
import random
from datetime import date, timedelta
from dotenv import load_dotenv
import mysql.connector

load_dotenv()


def get_conn():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", 3306)),
        database=os.environ.get("DB_NAME", "CampusHub"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
    )


def main():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    print("1️⃣  Ensuring tables, views, and triggers exist...")

    # Ensure Enrollments status ENUM matches
    try:
        cur.execute(
            "ALTER TABLE Enrollments MODIFY COLUMN status ENUM('Active','Dropped','Completed','Enrolled') NOT NULL DEFAULT 'Active'"
        )
        cur.execute("UPDATE Enrollments SET status = 'Active' WHERE status = 'Enrolled'")
        cur.execute(
            "ALTER TABLE Enrollments MODIFY COLUMN status ENUM('Active','Dropped','Completed') NOT NULL DEFAULT 'Active'"
        )
    except Exception:
        pass

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS Attendance (
            attendance_id INT AUTO_INCREMENT PRIMARY KEY,
            enrollment_id INT NOT NULL,
            session_date  DATE NOT NULL,
            status        ENUM('Present', 'Absent', 'Late') NOT NULL DEFAULT 'Present',
            remarks       VARCHAR(255) DEFAULT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_enrollment_date (enrollment_id, session_date),
            FOREIGN KEY (enrollment_id) REFERENCES Enrollments(enrollment_id) ON DELETE CASCADE
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS AuditLog (
            log_id      INT AUTO_INCREMENT PRIMARY KEY,
            table_name  VARCHAR(50) NOT NULL,
            action_type ENUM('INSERT', 'UPDATE', 'DELETE') NOT NULL,
            record_id   INT NOT NULL,
            old_value   TEXT,
            new_value   TEXT,
            changed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE OR REPLACE VIEW CourseEnrollmentSummary AS
        SELECT c.course_id, c.course_code, c.course_name, c.department, c.capacity,
               f.full_name AS faculty_name,
               COUNT(e.enrollment_id) AS enrolled_count
        FROM Courses c
        LEFT JOIN Faculty f ON c.faculty_id = f.faculty_id
        LEFT JOIN Enrollments e ON c.course_id = e.course_id AND e.status = 'Active'
        GROUP BY c.course_id, c.course_code, c.course_name, c.department, c.capacity, f.full_name
        """
    )

    cur.execute(
        """
        CREATE OR REPLACE VIEW StudentCourseDetails AS
        SELECT s.student_id, s.full_name AS student_name, s.department AS student_department,
               s.year_of_study, c.course_code, c.course_name, c.department AS course_department,
               e.enrollment_date, e.status AS enrollment_status, g.score, g.remarks
        FROM Students s
        JOIN Enrollments e ON s.student_id = e.student_id
        JOIN Courses c ON e.course_id = c.course_id
        LEFT JOIN Grades g ON e.enrollment_id = g.enrollment_id
        """
    )

    # Recreate triggers
    for trig in [
        "trg_grades_after_update",
        "trg_grades_after_delete",
        "trg_enrollments_after_update",
        "trg_enrollments_after_delete",
    ]:
        cur.execute(f"DROP TRIGGER IF EXISTS {trig}")

    cur.execute(
        """
        CREATE TRIGGER trg_grades_after_update
        AFTER UPDATE ON Grades
        FOR EACH ROW
        BEGIN
            INSERT INTO AuditLog (table_name, action_type, record_id, old_value, new_value)
            VALUES (
                'Grades', 'UPDATE', OLD.grade_id,
                CONCAT('enrollment_id=', OLD.enrollment_id, ', score=', OLD.score, ', remarks=', IFNULL(OLD.remarks, 'NULL')),
                CONCAT('enrollment_id=', NEW.enrollment_id, ', score=', NEW.score, ', remarks=', IFNULL(NEW.remarks, 'NULL'))
            );
        END
        """
    )

    cur.execute(
        """
        CREATE TRIGGER trg_grades_after_delete
        AFTER DELETE ON Grades
        FOR EACH ROW
        BEGIN
            INSERT INTO AuditLog (table_name, action_type, record_id, old_value, new_value)
            VALUES (
                'Grades', 'DELETE', OLD.grade_id,
                CONCAT('enrollment_id=', OLD.enrollment_id, ', score=', OLD.score, ', remarks=', IFNULL(OLD.remarks, 'NULL')),
                NULL
            );
        END
        """
    )

    cur.execute(
        """
        CREATE TRIGGER trg_enrollments_after_update
        AFTER UPDATE ON Enrollments
        FOR EACH ROW
        BEGIN
            IF OLD.status <> NEW.status THEN
                INSERT INTO AuditLog (table_name, action_type, record_id, old_value, new_value)
                VALUES (
                    'Enrollments', 'UPDATE', OLD.enrollment_id,
                    CONCAT('student_id=', OLD.student_id, ', course_id=', OLD.course_id, ', status=', OLD.status),
                    CONCAT('student_id=', NEW.student_id, ', course_id=', NEW.course_id, ', status=', NEW.status)
                );
            END IF;
        END
        """
    )

    cur.execute(
        """
        CREATE TRIGGER trg_enrollments_after_delete
        AFTER DELETE ON Enrollments
        FOR EACH ROW
        BEGIN
            INSERT INTO AuditLog (table_name, action_type, record_id, old_value, new_value)
            VALUES (
                'Enrollments', 'DELETE', OLD.enrollment_id,
                CONCAT('student_id=', OLD.student_id, ', course_id=', OLD.course_id, ', status=', OLD.status),
                NULL
            );
        END
        """
    )
    conn.commit()

    # 2. Fetch existing Faculty & ensure at least 5 faculty members exist
    cur.execute("SELECT * FROM Faculty ORDER BY faculty_id")
    faculty_list = cur.fetchall()
    if len(faculty_list) < 5:
        extra_faculty = [
            ("Dr. Vikram Mehta", "vikram.mehta@campushub.edu", "Electronics"),
            ("Dr. Neha Kapoor", "neha.kapoor@campushub.edu", "Mathematics"),
            ("Dr. Arjun Rao", "arjun.rao@campushub.edu", "Computer Science"),
            ("Dr. Kavita Iyer", "kavita.iyer@campushub.edu", "Information Technology"),
            ("Dr. संजय Kulkarni", "sanjay.kulkarni@campushub.edu", "Mechanical"),
        ]
        existing_emails = {f["email"].lower() for f in faculty_list}
        for fn, em, dp in extra_faculty:
            if len(faculty_list) >= 5:
                break
            if em.lower() not in existing_emails:
                cur.execute(
                    "INSERT INTO Faculty (full_name, email, department) VALUES (%s,%s,%s)",
                    (fn, em, dp),
                )
                existing_emails.add(em.lower())
                conn.commit()
                cur.execute("SELECT * FROM Faculty ORDER BY faculty_id")
                faculty_list = cur.fetchall()

    cur.execute("SELECT * FROM Students ORDER BY student_id")
    student_list = cur.fetchall()
    if len(student_list) < 5:
        extra_students = [
            ("Aarav Patel", "aarav.patel@campushub.edu", "Computer Science", 3),
            ("Diya Verma", "diya.verma@campushub.edu", "Information Technology", 2),
            ("Rohan Desai", "rohan.desai@campushub.edu", "Computer Science", 4),
            ("Anaya Gupta", "anaya.gupta@campushub.edu", "Electronics", 2),
            ("Kabir Singh", "kabir.singh@campushub.edu", "Mathematics", 1),
        ]
        for fn, em, dp, yr in extra_students:
            cur.execute(
                "INSERT IGNORE INTO Students (full_name, email, department, year_of_study) VALUES (%s,%s,%s,%s)",
                (fn, em, dp, yr),
            )
        conn.commit()
        cur.execute("SELECT * FROM Students ORDER BY student_id")
        student_list = cur.fetchall()

    # 3. Add rich courses & evenly divide ALL courses across the 5 faculty members
    print("2️⃣  Adding courses and dividing evenly across all 5 faculty members...")
    extra_courses = [
        ("CS301", "Database Management Systems", 4, "Computer Science", 40),
        ("CS302", "Operating Systems", 4, "Computer Science", 35),
        ("IT204", "Full-Stack Web Development", 3, "Information Technology", 45),
        ("CS401", "Machine Learning & AI", 4, "Computer Science", 30),
        ("EC202", "Digital Signal Processing", 3, "Electronics", 35),
        ("MA201", "Linear Algebra & Probability", 3, "Mathematics", 50),
    ]
    for idx, (code, name, cred, dept, cap) in enumerate(extra_courses):
        fac_id = faculty_list[idx % len(faculty_list)]["faculty_id"]
        cur.execute("SELECT course_id FROM Courses WHERE course_code = %s", (code,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO Courses (course_code, course_name, credits, department, faculty_id, capacity) VALUES (%s,%s,%s,%s,%s,%s)",
                (code, name, cred, dept, fac_id, cap),
            )
    conn.commit()

    # Evenly redistribute all courses across the 5 faculty members (round-robin)
    cur.execute("SELECT * FROM Courses ORDER BY course_id")
    course_list = cur.fetchall()
    for c_idx, course in enumerate(course_list):
        assigned_fac_id = faculty_list[c_idx % len(faculty_list)]["faculty_id"]
        cur.execute(
            "UPDATE Courses SET faculty_id = %s WHERE course_id = %s",
            (assigned_fac_id, course["course_id"]),
        )
    conn.commit()

    cur.execute("SELECT * FROM Courses ORDER BY course_id")
    course_list = cur.fetchall()

    # 4. Enroll every existing student in 3 to 4 courses
    print("3️⃣  Enrolling existing students into courses...")
    for s_idx, stu in enumerate(student_list):
        sid = stu["student_id"]
        # Pick 4 courses for each student
        chosen_courses = [
            course_list[(s_idx + offset) % len(course_list)]
            for offset in range(min(4, len(course_list)))
        ]
        for c_offset, crs in enumerate(chosen_courses):
            cid = crs["course_id"]
            cur.execute(
                "SELECT enrollment_id FROM Enrollments WHERE student_id = %s AND course_id = %s",
                (sid, cid),
            )
            if not cur.fetchone():
                enr_date = (date.today() - timedelta(days=30 - c_offset * 3)).isoformat()
                status = "Completed" if c_offset == 3 else "Active"
                cur.execute(
                    "INSERT INTO Enrollments (student_id, course_id, enrollment_date, status) VALUES (%s,%s,%s,%s)",
                    (sid, cid, enr_date, status),
                )
    conn.commit()

    # 5. Populate Grades for enrollments
    print("4️⃣  Adding grades & remarks for enrollments...")
    cur.execute("SELECT enrollment_id, student_id, course_id, status FROM Enrollments ORDER BY enrollment_id")
    all_enrollments = cur.fetchall()

    sample_scores = [
        (94.5, "Outstanding performance & project work"),
        (88.0, "Very strong analytical understanding"),
        (82.5, "Good lab and midterm performance"),
        (76.0, "Consistent effort, room to improve in finals"),
        (91.0, "Excellent SQL and schema design"),
        (68.5, "Passed; needs review on advanced topics"),
        (85.0, "Great class participation"),
    ]

    for idx, enr in enumerate(all_enrollments):
        eid = enr["enrollment_id"]
        cur.execute("SELECT grade_id FROM Grades WHERE enrollment_id = %s", (eid,))
        if not cur.fetchone():
            score, remark = sample_scores[idx % len(sample_scores)]
            cur.execute(
                "INSERT INTO Grades (enrollment_id, score, remarks) VALUES (%s, %s, %s)",
                (eid, score, remark),
            )
    conn.commit()

    # 6. Populate Attendance sessions (8 sessions per enrollment)
    print("5️⃣  Adding daily attendance sessions...")
    session_dates = [
        (date.today() - timedelta(days=days_ago)).isoformat()
        for days_ago in [18, 16, 14, 11, 9, 7, 4, 2]
    ]

    for idx, enr in enumerate(all_enrollments):
        eid = enr["enrollment_id"]
        # Make every 4th enrollment have low attendance (~62.5%) so the <75% warning badge shows up!
        low_attendance_course = (idx % 4 == 2)
        for d_idx, s_date in enumerate(session_dates):
            if low_attendance_course:
                status = "Absent" if d_idx in (1, 3, 5) else "Present"
                remark = "Missed lecture" if status == "Absent" else None
            else:
                if d_idx == 4 and idx % 2 == 0:
                    status = "Late"
                    remark = "Arrived 10 mins late"
                elif d_idx == 2 and idx % 5 == 0:
                    status = "Absent"
                    remark = "Medical leave"
                else:
                    status = "Present"
                    remark = None

            cur.execute(
                """
                INSERT INTO Attendance (enrollment_id, session_date, status, remarks)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE status = VALUES(status), remarks = VALUES(remarks)
                """,
                (eid, s_date, status, remark),
            )
    conn.commit()

    # 7. Fire a couple of updates so AuditLog has sample trigger entries
    print("6️⃣  Generating sample trigger events for Audit Trail...")
    cur.execute("SELECT COUNT(*) AS cnt FROM AuditLog")
    if cur.fetchone()["cnt"] == 0 and all_enrollments:
        cur.execute("SELECT grade_id, score FROM Grades ORDER BY grade_id LIMIT 2")
        for g in cur.fetchall():
            new_s = min(100.0, float(g["score"]) + 1.5)
            cur.execute(
                "UPDATE Grades SET score = %s, remarks = 'Re-evaluated after quiz bonus' WHERE grade_id = %s",
                (new_s, g["grade_id"]),
            )
        conn.commit()

    # 8. Auto-link any Users accounts with NULL linked_id
    print("7️⃣  Verifying student/faculty user account links...")
    if student_list:
        cur.execute(
            "UPDATE Users SET linked_id = %s WHERE role = 'student' AND linked_id IS NULL",
            (student_list[0]["student_id"],),
        )
    if faculty_list:
        cur.execute(
            "UPDATE Users SET linked_id = %s WHERE role = 'faculty' AND linked_id IS NULL",
            (faculty_list[0]["faculty_id"],),
        )
    conn.commit()

    # 9. Seed MongoDB (NoSQL) collections
    print("8️⃣  Seeding MongoDB NoSQL collections (Announcements, Feedback, Session Docs, Transcripts)...")
    import mongo_db

    fac_by_id = {f["faculty_id"]: f["full_name"] for f in faculty_list}

    # 9a. Course Announcements
    if not mongo_db.list_announcements():
        sample_anns = [
            (0, "Midterm Practical Exam & Normalization Viva", "Please review 3NF/BCNF decomposition, SQL transactions (SELECT FOR UPDATE), and MongoDB document modeling before next week's viva.", "Exam", ["Midterm", "Viva", "RDBMS + NoSQL"]),
            (1, "Lab 4 Submission: Indexing & Query Optimization", "Upload your EXPLAIN query execution plans and composite index benchmarks by Friday 5:00 PM.", "Important", ["Lab", "Assignment"]),
            (2, "Guest Lecture: Polyglot Persistence in FinTech", "Mandatory seminar in Auditorium B on how banks combine relational ACID ledgers with NoSQL document stores.", "Normal", ["Seminar", "Industry"]),
            (3, "Project Milestone 2: Triggers & Stored Views", "Ensure your AFTER UPDATE and AFTER DELETE audit triggers are tested with sample grade updates.", "Important", ["Project", "Triggers"]),
            (4, "Updated Lecture Slides & Practice Problem Set", "Slides for Week 7–9 and practice problem sets have been uploaded to the course repository.", "Normal", ["Slides", "Study Material"]),
            (5, "Final Project Presentation Schedule", "Live project demonstrations will be evaluated on both relational schema integrity and NoSQL collection design.", "Exam", ["Final Demo", "Evaluation"]),
        ]
        for c_idx, title, msg, prio, tags in sample_anns:
            c = course_list[c_idx % len(course_list)]
            f_name = fac_by_id.get(c["faculty_id"], "Faculty")
            mongo_db.add_announcement(
                course_id=c["course_id"],
                course_code=c["course_code"],
                course_name=c["course_name"],
                faculty_id=c["faculty_id"],
                faculty_name=f_name,
                title=title,
                message=msg,
                priority=prio,
                tags=tags,
            )

    # 9b. Course Feedback & Reviews
    sample_reviews = [
        (5, "Moderate", ["Hands-on Labs", "Clear Explanations", "Industry Relevant"], "The combination of SQL transactions and MongoDB document design made database concepts super clear."),
        (5, "Challenging", ["Great Projects", "Well Structured"], "Challenging assignments, especially concurrency control and triggers, but learned a ton!"),
        (4, "Moderate", ["Helpful Faculty", "Practical Examples"], "Very well-paced lectures with real-world schema optimization examples."),
        (5, "Easy", ["Interactive", "Good Notes"], "Loved the live coding demos and clear breakdown of normalization rules."),
        (4, "Challenging", ["Deep Concepts", "Exam Focused"], "Thorough coverage of indexing, B-trees, and aggregation pipelines."),
    ]
    for idx, enr in enumerate(all_enrollments[:10]):
        stu = next((s for s in student_list if s["student_id"] == enr["student_id"]), student_list[0])
        crs = next((c for c in course_list if c["course_id"] == enr["course_id"]), course_list[0])
        rating, diff, tags, comment = sample_reviews[idx % len(sample_reviews)]
        mongo_db.upsert_course_feedback(
            course_id=crs["course_id"],
            course_code=crs["course_code"],
            course_name=crs["course_name"],
            student_id=stu["student_id"],
            student_name=stu["full_name"],
            rating=rating,
            difficulty=diff,
            tags=tags,
            comment=comment,
        )

    # 9c. Sync nested Attendance Session documents into MongoDB
    for c in course_list[:5]:
        cid = c["course_id"]
        for s_date in session_dates[-2:]:
            cur.execute(
                """
                SELECT e.enrollment_id, s.student_id, s.full_name AS student_name,
                       a.status, a.remarks
                FROM Attendance a
                JOIN Enrollments e ON a.enrollment_id = e.enrollment_id
                JOIN Students s ON e.student_id = s.student_id
                WHERE e.course_id = %s AND a.session_date = %s
                """,
                (cid, s_date),
            )
            recs = cur.fetchall()
            if recs:
                mongo_db.sync_attendance_session_doc(
                    course_id=cid,
                    course_code=c["course_code"],
                    course_name=c["course_name"],
                    session_date=s_date,
                    faculty_id=c["faculty_id"],
                    records=recs,
                )

    # 9d. Cache Student Transcript documents in MongoDB
    for stu in student_list:
        sid = stu["student_id"]
        cur.execute(
            """
            SELECT c.course_code, c.course_name, c.credits,
                   e.status AS enrollment_status, g.score, g.remarks
            FROM Enrollments e
            JOIN Courses c ON e.course_id = c.course_id
            LEFT JOIN Grades g ON e.enrollment_id = g.enrollment_id
            WHERE e.student_id = %s
            """,
            (sid,),
        )
        c_rows = cur.fetchall()
        scored = [r for r in c_rows if r["score"] is not None]
        avg_s = round(sum(float(r["score"]) for r in scored) / len(scored), 2) if scored else None
        tot_cr = sum(int(r["credits"]) for r in scored)
        gp_sum = 0.0
        for r in scored:
            sc = float(r["score"])
            gp = 4.0 if sc >= 90 else 3.0 if sc >= 80 else 2.0 if sc >= 70 else 1.0 if sc >= 60 else 0.0
            gp_sum += gp * int(r["credits"])
        w_gpa = round(gp_sum / tot_cr, 2) if tot_cr else None
        mongo_db.cache_student_transcript_doc(stu, w_gpa, avg_s, tot_cr, c_rows)

    # 9e. Mirror MySQL AuditLog into MongoDB audit_logs collection
    if mongo_db.get_mongo_db()["audit_logs"].count_documents({}) == 0:
        cur.execute("SELECT * FROM AuditLog ORDER BY log_id DESC LIMIT 10")
        for al in cur.fetchall():
            mongo_db.log_nosql_audit_event(
                table_name=al["table_name"],
                action_type=al["action_type"],
                record_id=al["record_id"],
                old_value=al["old_value"],
                new_value=al["new_value"],
                actor="mysql_trigger",
                changed_at=str(al["changed_at"]),
            )

    m_stat = mongo_db.get_mongo_status()
    print("\n✅  Database (MySQL + MongoDB) seeded successfully!")
    print(f"    • Students (MySQL)       : {len(student_list)}")
    print(f"    • Faculty (MySQL)        : {len(faculty_list)}")
    print(f"    • Courses (MySQL)        : {len(course_list)}")
    print(f"    • Enrollments (MySQL)    : {len(all_enrollments)}")
    print(f"    • Attendance (MySQL)     : {len(all_enrollments) * len(session_dates)} session logs")
    print(f"    • MongoDB Total Documents: {m_stat['total_documents']} across 5 collections ({m_stat['collections']})")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
