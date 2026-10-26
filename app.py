"""
app.py — CampusHub Flask application (with role-based auth).

Roles:
  admin   → full admin dashboard at /
  student → read-only student portal at /student-portal
  faculty → grade-management faculty portal at /faculty-portal

All API endpoints use parameterised SQL.  Credentials come from
environment variables (see .env.example).
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal
from functools import wraps

from dotenv import load_dotenv

load_dotenv()  # must happen before db import

from flask import (
    Flask, redirect, render_template, request, session, url_for
)
from mysql.connector import Error as MySQLError
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_connection
import mongo_db

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-in-production")

# ---------------------------------------------------------------------------
# JSON / response helpers
# ---------------------------------------------------------------------------

def _serial(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")


def ok(data=None, message: str = "OK", status: int = 200):
    payload = {"success": True, "message": message}
    if data is not None:
        payload["data"] = data
    return app.response_class(
        response=json.dumps(payload, default=_serial),
        status=status,
        mimetype="application/json",
    )


def err(message: str, status: int = 400):
    payload = {"success": False, "message": message}
    return app.response_class(
        response=json.dumps(payload),
        status=status,
        mimetype="application/json",
    )

# ---------------------------------------------------------------------------
# Authentication — before_request guard
# ---------------------------------------------------------------------------

_OPEN_PATHS    = {"/login", "/logout"}
_OPEN_PREFIXES = ("/static/",)


@app.before_request
def require_login():
    """Redirect unauthenticated requests; enforce role-based routing."""
    path = request.path

    # Always allow public paths
    if path in _OPEN_PATHS or any(path.startswith(p) for p in _OPEN_PREFIXES):
        return

    # Not logged in
    if "user_id" not in session:
        if path.startswith("/api/"):
            return err("Authentication required. Please log in.", 401)
        return redirect("/login")

    role = session.get("role", "")

    # Students → only student portal + student APIs
    if role == "student":
        if not (path == "/student-portal" or path.startswith("/api/student/")):
            return redirect("/student-portal")

    # Faculty → only faculty portal + faculty APIs
    elif role == "faculty":
        if not (path == "/faculty-portal" or path.startswith("/api/faculty/")):
            return redirect("/faculty-portal")

    # Admin → can access everything; bounce them away from role portals
    elif role == "admin":
        if path in ("/student-portal", "/faculty-portal"):
            return redirect("/")


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if "user_id" in session:
        return _role_redirect(session.get("role"))

    if request.method == "GET":
        return render_template("login.html")

    data     = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return err("Username and password are required")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM Users WHERE username = %s", (username,)
        )
        user = cur.fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            return err("Invalid username or password", 401)

        session.clear()
        session["user_id"]   = user["user_id"]
        session["username"]  = user["username"]
        session["role"]      = user["role"]
        session["linked_id"] = user["linked_id"]
        session.permanent    = True

        return ok(
            {"role": user["role"], "redirect": _role_url(user["role"])},
            "Login successful",
        )
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


def _role_url(role: str) -> str:
    return {"admin": "/", "student": "/student-portal", "faculty": "/faculty-portal"}.get(role, "/login")


def _role_redirect(role: str):
    return redirect(_role_url(role))

# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html",
                           username=session.get("username", "Admin"))


@app.route("/student-portal")
def student_portal():
    return render_template("student_portal.html",
                           username=session.get("username", "Student"))


@app.route("/faculty-portal")
def faculty_portal():
    return render_template("faculty_portal.html",
                           username=session.get("username", "Faculty"))

# ===========================================================================
# DASHBOARD (admin)
# ===========================================================================

@app.route("/api/dashboard/stats")
def dashboard_stats():
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT COUNT(*) AS cnt FROM Students")
        student_count = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) AS cnt FROM Courses")
        course_count = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) AS cnt FROM Enrollments WHERE status = 'Active'")
        active_enrollments = cur.fetchone()["cnt"]
        cur.execute("SELECT AVG(score) AS avg_score FROM Grades")
        row = cur.fetchone()
        avg_grade = round(float(row["avg_score"]), 2) if row["avg_score"] else 0.0
        cur.execute("SELECT COUNT(*) AS cnt FROM Users")
        user_count = cur.fetchone()["cnt"]
        return ok({
            "student_count": student_count,
            "course_count": course_count,
            "active_enrollments": active_enrollments,
            "avg_grade": avg_grade,
            "user_count": user_count,
        })
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()

# ===========================================================================
# STUDENTS (admin)
# ===========================================================================

@app.route("/api/students", methods=["GET"])
def list_students():
    search = request.args.get("q", "").strip()
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        if search:
            like = f"%{search}%"
            cur.execute(
                "SELECT * FROM Students WHERE full_name LIKE %s OR email LIKE %s OR department LIKE %s ORDER BY student_id",
                (like, like, like),
            )
        else:
            cur.execute("SELECT * FROM Students ORDER BY student_id")
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/students", methods=["POST"])
def add_student():
    data = request.get_json(force=True) or {}
    full_name    = (data.get("full_name") or "").strip()
    email        = (data.get("email") or "").strip().lower()
    department   = (data.get("department") or "").strip()
    year_of_study = data.get("year_of_study")

    if not full_name:   return err("full_name is required")
    if not email:       return err("email is required")
    if not department:  return err("department is required")
    try:
        year_of_study = int(year_of_study)
        if year_of_study < 1 or year_of_study > 6:
            raise ValueError
    except (ValueError, TypeError):
        return err("year_of_study must be 1–6")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT student_id FROM Students WHERE email = %s", (email,))
        if cur.fetchone():
            return err(f"Email '{email}' is already registered", 409)
        cur.execute(
            "INSERT INTO Students (full_name, email, department, year_of_study) VALUES (%s,%s,%s,%s)",
            (full_name, email, department, year_of_study),
        )
        conn.commit()
        new_id = cur.lastrowid
        cur.execute("SELECT * FROM Students WHERE student_id = %s", (new_id,))
        return ok(cur.fetchone(), "Student added successfully", 201)
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/students/<int:sid>", methods=["GET"])
def get_student(sid):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM Students WHERE student_id = %s", (sid,))
        row = cur.fetchone()
        return ok(row) if row else err("Student not found", 404)
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/students/<int:sid>", methods=["PUT"])
def update_student(sid):
    data = request.get_json(force=True) or {}
    full_name    = (data.get("full_name") or "").strip()
    email        = (data.get("email") or "").strip().lower()
    department   = (data.get("department") or "").strip()
    year_of_study = data.get("year_of_study")

    if not full_name:  return err("full_name is required")
    if not email:      return err("email is required")
    if not department: return err("department is required")
    try:
        year_of_study = int(year_of_study)
        if year_of_study < 1 or year_of_study > 6:
            raise ValueError
    except (ValueError, TypeError):
        return err("year_of_study must be 1–6")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT student_id FROM Students WHERE student_id = %s", (sid,))
        if not cur.fetchone():
            return err("Student not found", 404)
        cur.execute(
            "SELECT student_id FROM Students WHERE email = %s AND student_id != %s",
            (email, sid),
        )
        if cur.fetchone():
            return err(f"Email '{email}' is used by another student", 409)
        cur.execute(
            "UPDATE Students SET full_name=%s, email=%s, department=%s, year_of_study=%s WHERE student_id=%s",
            (full_name, email, department, year_of_study, sid),
        )
        conn.commit()
        cur.execute("SELECT * FROM Students WHERE student_id = %s", (sid,))
        return ok(cur.fetchone(), "Student updated successfully")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/students/<int:sid>", methods=["DELETE"])
def delete_student(sid):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT student_id FROM Students WHERE student_id = %s", (sid,))
        if not cur.fetchone():
            return err("Student not found", 404)
        cur.execute("DELETE FROM Students WHERE student_id = %s", (sid,))
        conn.commit()
        return ok(message="Student deleted successfully")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()

# ===========================================================================
# FACULTY (admin)
# ===========================================================================

@app.route("/api/faculty", methods=["GET"])
def list_faculty():
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM Faculty ORDER BY faculty_id")
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/faculty", methods=["POST"])
def add_faculty():
    data = request.get_json(force=True) or {}
    full_name  = (data.get("full_name") or "").strip()
    email      = (data.get("email") or "").strip().lower()
    department = (data.get("department") or "").strip()

    if not full_name:  return err("full_name is required")
    if not email:      return err("email is required")
    if not department: return err("department is required")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT faculty_id FROM Faculty WHERE email = %s", (email,))
        if cur.fetchone():
            return err(f"Email '{email}' already exists", 409)
        cur.execute(
            "INSERT INTO Faculty (full_name, email, department) VALUES (%s,%s,%s)",
            (full_name, email, department),
        )
        conn.commit()
        new_id = cur.lastrowid
        cur.execute("SELECT * FROM Faculty WHERE faculty_id = %s", (new_id,))
        return ok(cur.fetchone(), "Faculty member added successfully", 201)
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/faculty/<int:fid>", methods=["GET"])
def get_faculty(fid):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM Faculty WHERE faculty_id = %s", (fid,))
        row = cur.fetchone()
        return ok(row) if row else err("Faculty not found", 404)
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/faculty/<int:fid>", methods=["PUT"])
def update_faculty(fid):
    data = request.get_json(force=True) or {}
    full_name  = (data.get("full_name") or "").strip()
    email      = (data.get("email") or "").strip().lower()
    department = (data.get("department") or "").strip()

    if not full_name:  return err("full_name is required")
    if not email:      return err("email is required")
    if not department: return err("department is required")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT faculty_id FROM Faculty WHERE faculty_id = %s", (fid,))
        if not cur.fetchone():
            return err("Faculty not found", 404)
        cur.execute(
            "SELECT faculty_id FROM Faculty WHERE email = %s AND faculty_id != %s",
            (email, fid),
        )
        if cur.fetchone():
            return err(f"Email '{email}' is used by another faculty member", 409)
        cur.execute(
            "UPDATE Faculty SET full_name=%s, email=%s, department=%s WHERE faculty_id=%s",
            (full_name, email, department, fid),
        )
        conn.commit()
        cur.execute("SELECT * FROM Faculty WHERE faculty_id = %s", (fid,))
        return ok(cur.fetchone(), "Faculty updated successfully")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/faculty/<int:fid>", methods=["DELETE"])
def delete_faculty(fid):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT faculty_id FROM Faculty WHERE faculty_id = %s", (fid,))
        if not cur.fetchone():
            return err("Faculty not found", 404)
        cur.execute("DELETE FROM Faculty WHERE faculty_id = %s", (fid,))
        conn.commit()
        return ok(message="Faculty member deleted successfully")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()

# ===========================================================================
# COURSES (admin)
# ===========================================================================

@app.route("/api/courses", methods=["GET"])
def list_courses():
    search = request.args.get("q", "").strip()
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        base = """
            SELECT c.*, f.full_name AS faculty_name,
                   COUNT(e.enrollment_id) AS enrolled_count
            FROM Courses c
            LEFT JOIN Faculty f ON c.faculty_id = f.faculty_id
            LEFT JOIN Enrollments e ON e.course_id = c.course_id AND e.status = 'Active'
        """
        if search:
            like = f"%{search}%"
            cur.execute(
                base + " WHERE c.course_name LIKE %s OR c.course_code LIKE %s OR c.department LIKE %s GROUP BY c.course_id ORDER BY c.course_id",
                (like, like, like),
            )
        else:
            cur.execute(base + " GROUP BY c.course_id ORDER BY c.course_id")
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/courses", methods=["POST"])
def add_course():
    data = request.get_json(force=True) or {}
    course_code = (data.get("course_code") or "").strip().upper()
    course_name = (data.get("course_name") or "").strip()
    department  = (data.get("department") or "").strip()
    faculty_id  = data.get("faculty_id") or None
    credits     = data.get("credits")
    capacity    = data.get("capacity")

    if not course_code: return err("course_code is required")
    if not course_name: return err("course_name is required")
    if not department:  return err("department is required")
    try:
        credits  = int(credits)
        capacity = int(capacity)
        if credits < 1 or capacity < 1:
            raise ValueError
    except (ValueError, TypeError):
        return err("credits and capacity must be positive integers")
    if faculty_id is not None:
        try:
            faculty_id = int(faculty_id)
        except (ValueError, TypeError):
            return err("faculty_id must be an integer")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT course_id FROM Courses WHERE course_code = %s", (course_code,))
        if cur.fetchone():
            return err(f"Course code '{course_code}' already exists", 409)
        cur.execute(
            "INSERT INTO Courses (course_code, course_name, credits, department, faculty_id, capacity) VALUES (%s,%s,%s,%s,%s,%s)",
            (course_code, course_name, credits, department, faculty_id, capacity),
        )
        conn.commit()
        new_id = cur.lastrowid
        cur.execute(
            "SELECT c.*, f.full_name AS faculty_name FROM Courses c LEFT JOIN Faculty f ON c.faculty_id = f.faculty_id WHERE c.course_id = %s",
            (new_id,),
        )
        return ok(cur.fetchone(), "Course added successfully", 201)
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/courses/<int:cid>", methods=["GET"])
def get_course(cid):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT c.*, f.full_name AS faculty_name FROM Courses c LEFT JOIN Faculty f ON c.faculty_id = f.faculty_id WHERE c.course_id = %s",
            (cid,),
        )
        row = cur.fetchone()
        return ok(row) if row else err("Course not found", 404)
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/courses/<int:cid>", methods=["PUT"])
def update_course(cid):
    data = request.get_json(force=True) or {}
    course_code = (data.get("course_code") or "").strip().upper()
    course_name = (data.get("course_name") or "").strip()
    department  = (data.get("department") or "").strip()
    faculty_id  = data.get("faculty_id") or None
    credits     = data.get("credits")
    capacity    = data.get("capacity")

    if not course_code: return err("course_code is required")
    if not course_name: return err("course_name is required")
    if not department:  return err("department is required")
    try:
        credits  = int(credits)
        capacity = int(capacity)
    except (ValueError, TypeError):
        return err("credits and capacity must be integers")
    if faculty_id is not None:
        try:
            faculty_id = int(faculty_id)
        except (ValueError, TypeError):
            return err("faculty_id must be an integer")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT course_id FROM Courses WHERE course_id = %s", (cid,))
        if not cur.fetchone():
            return err("Course not found", 404)
        cur.execute(
            "SELECT course_id FROM Courses WHERE course_code = %s AND course_id != %s",
            (course_code, cid),
        )
        if cur.fetchone():
            return err(f"Course code '{course_code}' already used", 409)
        cur.execute(
            "UPDATE Courses SET course_code=%s, course_name=%s, credits=%s, department=%s, faculty_id=%s, capacity=%s WHERE course_id=%s",
            (course_code, course_name, credits, department, faculty_id, capacity, cid),
        )
        conn.commit()
        cur.execute(
            "SELECT c.*, f.full_name AS faculty_name FROM Courses c LEFT JOIN Faculty f ON c.faculty_id = f.faculty_id WHERE c.course_id = %s",
            (cid,),
        )
        return ok(cur.fetchone(), "Course updated successfully")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/courses/<int:cid>", methods=["DELETE"])
def delete_course(cid):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT course_id FROM Courses WHERE course_id = %s", (cid,))
        if not cur.fetchone():
            return err("Course not found", 404)
        cur.execute("DELETE FROM Courses WHERE course_id = %s", (cid,))
        conn.commit()
        return ok(message="Course deleted successfully")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()

# ===========================================================================
# ENROLLMENTS (admin)
# ===========================================================================

@app.route("/api/enrollments", methods=["GET"])
def list_enrollments():
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT e.enrollment_id, e.student_id, e.course_id,
                   s.full_name AS student_name,
                   c.course_code, c.course_name,
                   e.enrollment_date, e.status
            FROM Enrollments e
            JOIN Students s ON e.student_id = s.student_id
            JOIN Courses c  ON e.course_id  = c.course_id
            ORDER BY e.enrollment_id DESC
            """
        )
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/enrollments", methods=["POST"])
def enroll_student():
    data = request.get_json(force=True) or {}
    student_id      = data.get("student_id")
    course_id       = data.get("course_id")
    enrollment_date = data.get("enrollment_date") or date.today().isoformat()
    status          = (data.get("status") or "Active").strip()

    if not student_id: return err("student_id is required")
    if not course_id:  return err("course_id is required")
    if status not in ("Active", "Dropped", "Completed"):
        return err("status must be Active, Dropped, or Completed")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT capacity FROM Courses WHERE course_id = %s FOR UPDATE", (course_id,))
        course = cur.fetchone()
        if not course:
            conn.rollback()
            return err("Course not found", 404)

        cur.execute("SELECT student_id FROM Students WHERE student_id = %s", (student_id,))
        if not cur.fetchone():
            conn.rollback()
            return err("Student not found", 404)

        cur.execute(
            "SELECT COUNT(*) AS cnt FROM Enrollments WHERE course_id = %s AND status = 'Active'",
            (course_id,),
        )
        active_count = cur.fetchone()["cnt"]
        if active_count >= course["capacity"]:
            conn.rollback()
            return err(f"Course is full ({active_count}/{course['capacity']})", 409)

        cur.execute(
            "SELECT enrollment_id FROM Enrollments WHERE student_id = %s AND course_id = %s AND status = 'Active'",
            (student_id, course_id),
        )
        if cur.fetchone():
            conn.rollback()
            return err("Student is already enrolled in this course", 409)

        cur.execute(
            "INSERT INTO Enrollments (student_id, course_id, enrollment_date, status) VALUES (%s,%s,%s,%s)",
            (student_id, course_id, enrollment_date, status),
        )
        conn.commit()
        new_id = cur.lastrowid
        cur.execute(
            """
            SELECT e.*, s.full_name AS student_name, c.course_code, c.course_name
            FROM Enrollments e
            JOIN Students s ON e.student_id = s.student_id
            JOIN Courses c  ON e.course_id  = c.course_id
            WHERE e.enrollment_id = %s
            """,
            (new_id,),
        )
        return ok(cur.fetchone(), "Student enrolled successfully", 201)
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/enrollments/<int:eid>", methods=["PUT"])
def update_enrollment(eid):
    data   = request.get_json(force=True) or {}
    status = (data.get("status") or "").strip()
    if status not in ("Active", "Dropped", "Completed"):
        return err("status must be Active, Dropped, or Completed")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT enrollment_id FROM Enrollments WHERE enrollment_id = %s", (eid,))
        if not cur.fetchone():
            return err("Enrollment not found", 404)
        cur.execute("UPDATE Enrollments SET status=%s WHERE enrollment_id=%s", (status, eid))
        conn.commit()
        return ok(message="Enrollment status updated")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/enrollments/<int:eid>", methods=["DELETE"])
def delete_enrollment(eid):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT enrollment_id FROM Enrollments WHERE enrollment_id = %s", (eid,))
        if not cur.fetchone():
            return err("Enrollment not found", 404)
        cur.execute("DELETE FROM Enrollments WHERE enrollment_id = %s", (eid,))
        conn.commit()
        return ok(message="Enrollment deleted successfully")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()

# ===========================================================================
# GRADES (admin)
# ===========================================================================

@app.route("/api/grades", methods=["GET"])
def list_grades():
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT g.grade_id, g.enrollment_id, g.score, g.remarks, g.updated_at,
                   s.full_name AS student_name, c.course_code, c.course_name
            FROM Grades g
            JOIN Enrollments e ON g.enrollment_id = e.enrollment_id
            JOIN Students s    ON e.student_id     = s.student_id
            JOIN Courses c     ON e.course_id      = c.course_id
            ORDER BY g.grade_id DESC
            """
        )
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/grades", methods=["POST"])
def add_grade():
    data          = request.get_json(force=True) or {}
    enrollment_id = data.get("enrollment_id")
    score         = data.get("score")
    remarks       = (data.get("remarks") or "").strip()

    if enrollment_id is None: return err("enrollment_id is required")
    try:
        score = float(score)
        if score < 0 or score > 100:
            raise ValueError
    except (ValueError, TypeError):
        return err("score must be 0–100")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT enrollment_id FROM Enrollments WHERE enrollment_id = %s", (enrollment_id,))
        if not cur.fetchone():
            return err("Enrollment not found", 404)
        cur.execute("SELECT grade_id FROM Grades WHERE enrollment_id = %s", (enrollment_id,))
        if cur.fetchone():
            return err("Grade already exists for this enrollment. Use PUT to update.", 409)
        cur.execute(
            "INSERT INTO Grades (enrollment_id, score, remarks) VALUES (%s,%s,%s)",
            (enrollment_id, score, remarks or None),
        )
        conn.commit()
        new_id = cur.lastrowid
        cur.execute(
            """
            SELECT g.*, s.full_name AS student_name, c.course_code, c.course_name
            FROM Grades g
            JOIN Enrollments e ON g.enrollment_id = e.enrollment_id
            JOIN Students s    ON e.student_id     = s.student_id
            JOIN Courses c     ON e.course_id      = c.course_id
            WHERE g.grade_id = %s
            """,
            (new_id,),
        )
        return ok(cur.fetchone(), "Grade added successfully", 201)
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/grades/<int:gid>", methods=["PUT"])
def update_grade(gid):
    data    = request.get_json(force=True) or {}
    score   = data.get("score")
    remarks = (data.get("remarks") or "").strip()

    try:
        score = float(score)
        if score < 0 or score > 100:
            raise ValueError
    except (ValueError, TypeError):
        return err("score must be 0–100")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT grade_id FROM Grades WHERE grade_id = %s", (gid,))
        if not cur.fetchone():
            return err("Grade record not found", 404)
        cur.execute(
            "UPDATE Grades SET score=%s, remarks=%s, updated_at=NOW() WHERE grade_id=%s",
            (score, remarks or None, gid),
        )
        conn.commit()
        return ok(message="Grade updated successfully")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/grades/<int:gid>", methods=["DELETE"])
def delete_grade(gid):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT grade_id FROM Grades WHERE grade_id = %s", (gid,))
        if not cur.fetchone():
            return err("Grade record not found", 404)
        cur.execute("DELETE FROM Grades WHERE grade_id = %s", (gid,))
        conn.commit()
        return ok(message="Grade deleted successfully")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()

# ===========================================================================
# REPORTS (admin)
# ===========================================================================

@app.route("/api/reports/enrollment-summary")
def report_enrollment_summary():
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM CourseEnrollmentSummary ORDER BY enrolled_count DESC")
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/reports/student-course-details")
def report_student_course_details():
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM StudentCourseDetails ORDER BY student_name")
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/reports/top-students")
def report_top_students():
    try:
        limit = int(request.args.get("limit", 10))
    except ValueError:
        limit = 10

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT s.student_id, s.full_name, s.department,
                   ROUND(AVG(g.score), 2) AS avg_score,
                   ROUND(
                       SUM(
                           CASE
                               WHEN g.score >= 90 THEN 4.0
                               WHEN g.score >= 80 THEN 3.0
                               WHEN g.score >= 70 THEN 2.0
                               WHEN g.score >= 60 THEN 1.0
                               ELSE 0.0
                           END * c.credits
                       ) / NULLIF(SUM(c.credits), 0),
                       2
                   ) AS weighted_gpa,
                   SUM(c.credits) AS total_credits,
                   COUNT(g.grade_id) AS graded_courses
            FROM Students s
            JOIN Enrollments e ON s.student_id    = e.student_id
            JOIN Courses c     ON e.course_id     = c.course_id
            JOIN Grades g      ON e.enrollment_id = g.enrollment_id
            GROUP BY s.student_id, s.full_name, s.department
            ORDER BY weighted_gpa DESC, avg_score DESC
            LIMIT %s
            """,
            (limit,),
        )
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/audit-logs")
def list_audit_logs():
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT log_id, table_name, action_type, record_id,
                   old_value, new_value, changed_at
            FROM AuditLog
            ORDER BY log_id DESC
            LIMIT 200
            """
        )
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/reports/department-stats")
def report_department_stats():
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT s.department,
                   COUNT(DISTINCT s.student_id)      AS student_count,
                   COUNT(DISTINCT c.course_id)       AS course_count,
                   COUNT(DISTINCT e.enrollment_id)   AS total_enrollments,
                   ROUND(AVG(g.score), 2)            AS avg_score
            FROM Students s
            LEFT JOIN Enrollments e ON s.student_id  = e.student_id
            LEFT JOIN Courses c     ON e.course_id   = c.course_id
            LEFT JOIN Grades g      ON e.enrollment_id = g.enrollment_id
            GROUP BY s.department
            ORDER BY student_count DESC
            """
        )
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/reports/students-without-enrollments")
def report_unenrolled_students():
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT s.student_id, s.full_name, s.email,
                   s.department, s.year_of_study, s.created_at
            FROM Students s
            WHERE NOT EXISTS (
                SELECT 1 FROM Enrollments e
                WHERE e.student_id = s.student_id AND e.status = 'Active'
            )
            ORDER BY s.student_id
            """
        )
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()

# ===========================================================================
# USERS — managed by admin
# ===========================================================================

@app.route("/api/users", methods=["GET"])
def list_users():
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT user_id, username, role, linked_id, created_at FROM Users ORDER BY user_id"
        )
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/users", methods=["POST"])
def add_user():
    data      = request.get_json(force=True) or {}
    username  = (data.get("username") or "").strip()
    password  = (data.get("password") or "").strip()
    role      = (data.get("role") or "").strip()
    linked_id = data.get("linked_id") or None

    if not username: return err("username is required")
    if not password: return err("password is required")
    if len(password) < 6: return err("password must be at least 6 characters")
    if role not in ("admin", "student", "faculty"):
        return err("role must be admin, student, or faculty")
    if linked_id is not None:
        try:
            linked_id = int(linked_id)
        except (ValueError, TypeError):
            return err("linked_id must be an integer")

    pw_hash = generate_password_hash(password)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT user_id FROM Users WHERE username = %s", (username,))
        if cur.fetchone():
            return err(f"Username '{username}' is already taken", 409)
        cur.execute(
            "INSERT INTO Users (username, password_hash, role, linked_id) VALUES (%s,%s,%s,%s)",
            (username, pw_hash, role, linked_id),
        )
        conn.commit()
        new_id = cur.lastrowid
        cur.execute(
            "SELECT user_id, username, role, linked_id, created_at FROM Users WHERE user_id = %s",
            (new_id,),
        )
        return ok(cur.fetchone(), "User created successfully", 201)
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/users/<int:uid>", methods=["DELETE"])
def delete_user(uid):
    if uid == session.get("user_id"):
        return err("You cannot delete your own account", 400)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT user_id FROM Users WHERE user_id = %s", (uid,))
        if not cur.fetchone():
            return err("User not found", 404)
        cur.execute("DELETE FROM Users WHERE user_id = %s", (uid,))
        conn.commit()
        return ok(message="User deleted successfully")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/users/<int:uid>/reset-password", methods=["PUT"])
def reset_password(uid):
    data     = request.get_json(force=True) or {}
    password = (data.get("password") or "").strip()
    if len(password) < 6:
        return err("New password must be at least 6 characters")
    pw_hash = generate_password_hash(password)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT user_id FROM Users WHERE user_id = %s", (uid,))
        if not cur.fetchone():
            return err("User not found", 404)
        cur.execute("UPDATE Users SET password_hash=%s WHERE user_id=%s", (pw_hash, uid))
        conn.commit()
        return ok(message="Password reset successfully")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()

# ===========================================================================
# STUDENT PORTAL APIs  (session role == 'student')
# ===========================================================================

def _get_linked_student_id() -> int | None:
    sid = session.get("linked_id")
    if sid:
        return sid
    # Auto-link if user was created without linked_id
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        uname = (session.get("username") or "").strip()
        cur.execute(
            "SELECT student_id FROM Students WHERE LOWER(full_name) LIKE %s OR LOWER(email) LIKE %s LIMIT 1",
            (f"%{uname.lower().replace('.', ' ')}%", f"%{uname.lower()}%"),
        )
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT student_id FROM Students ORDER BY student_id LIMIT 1")
            row = cur.fetchone()
        if row:
            sid = row["student_id"]
            session["linked_id"] = sid
            if session.get("user_id"):
                cur.execute("UPDATE Users SET linked_id = %s WHERE user_id = %s", (sid, session["user_id"]))
                conn.commit()
            return sid
    except MySQLError:
        pass
    finally:
        cur.close()
        conn.close()
    return None


def _score_to_gp(score) -> float | None:
    if score is None:
        return None
    s = float(score)
    if s >= 90: return 4.0
    if s >= 80: return 3.0
    if s >= 70: return 2.0
    if s >= 60: return 1.0
    return 0.0


@app.route("/api/student/dashboard")
def student_dashboard():
    sid = _get_linked_student_id()
    if not sid:
        return err("No student record linked to this account", 400)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM Students WHERE student_id = %s", (sid,))
        profile = cur.fetchone()
        if not profile:
            return err("Student record not found", 404)

        cur.execute(
            "SELECT COUNT(*) AS cnt FROM Enrollments WHERE student_id = %s AND status = 'Active'",
            (sid,),
        )
        active_enrollments = cur.fetchone()["cnt"]

        cur.execute(
            "SELECT COUNT(*) AS cnt FROM Enrollments WHERE student_id = %s AND status = 'Completed'",
            (sid,),
        )
        completed = cur.fetchone()["cnt"]

        cur.execute(
            """
            SELECT AVG(g.score) AS avg_score,
                   ROUND(
                       SUM(
                           CASE
                               WHEN g.score >= 90 THEN 4.0
                               WHEN g.score >= 80 THEN 3.0
                               WHEN g.score >= 70 THEN 2.0
                               WHEN g.score >= 60 THEN 1.0
                               ELSE 0.0
                           END * c.credits
                       ) / NULLIF(SUM(c.credits), 0),
                       2
                   ) AS weighted_gpa,
                   SUM(c.credits) AS graded_credits
            FROM Grades g
            JOIN Enrollments e ON g.enrollment_id = e.enrollment_id
            JOIN Courses c     ON e.course_id     = c.course_id
            WHERE e.student_id = %s
            """,
            (sid,),
        )
        row = cur.fetchone()
        avg_score    = round(float(row["avg_score"]), 2) if row["avg_score"] is not None else None
        weighted_gpa = round(float(row["weighted_gpa"]), 2) if row["weighted_gpa"] is not None else None

        overall_att_pct = None
        try:
            cur.execute(
                """
                SELECT COUNT(*) AS total_sessions,
                       SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) AS attended
                FROM Attendance a
                JOIN Enrollments e ON a.enrollment_id = e.enrollment_id
                WHERE e.student_id = %s
                """,
                (sid,),
            )
            att = cur.fetchone()
            if att and att["total_sessions"]:
                overall_att_pct = round((float(att["attended"] or 0) / float(att["total_sessions"])) * 100, 1)
        except MySQLError:
            pass

        return ok({
            "profile":            profile,
            "active_enrollments": active_enrollments,
            "completed_courses":  completed,
            "avg_score":          avg_score,
            "weighted_gpa":       weighted_gpa,
            "graded_credits":     int(row["graded_credits"] or 0),
            "overall_attendance": overall_att_pct,
        })
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/student/my-enrollments")
def student_my_enrollments():
    sid = _get_linked_student_id()
    if not sid:
        return err("No student record linked to this account", 400)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                """
                SELECT e.enrollment_id, e.course_id, e.enrollment_date, e.status,
                       c.course_code, c.course_name, c.credits, c.department,
                       f.full_name AS faculty_name,
                       COUNT(a.attendance_id) AS total_sessions,
                       SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) AS attended_sessions,
                       ROUND(
                           SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) * 100.0
                           / NULLIF(COUNT(a.attendance_id), 0),
                           1
                       ) AS attendance_pct
                FROM Enrollments e
                JOIN Courses c      ON e.course_id      = c.course_id
                LEFT JOIN Faculty f ON c.faculty_id     = f.faculty_id
                LEFT JOIN Attendance a ON a.enrollment_id = e.enrollment_id
                WHERE e.student_id = %s
                GROUP BY e.enrollment_id
                ORDER BY e.enrollment_date DESC
                """,
                (sid,),
            )
        except MySQLError:
            cur.execute(
                """
                SELECT e.enrollment_id, e.course_id, e.enrollment_date, e.status,
                       c.course_code, c.course_name, c.credits, c.department,
                       f.full_name AS faculty_name,
                       0 AS total_sessions, 0 AS attended_sessions, NULL AS attendance_pct
                FROM Enrollments e
                JOIN Courses c  ON e.course_id  = c.course_id
                LEFT JOIN Faculty f ON c.faculty_id = f.faculty_id
                WHERE e.student_id = %s
                ORDER BY e.enrollment_date DESC
                """,
                (sid,),
            )
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/student/my-grades")
def student_my_grades():
    sid = _get_linked_student_id()
    if not sid:
        return err("No student record linked to this account", 400)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT c.course_code, c.course_name, c.credits, c.department,
                   e.status AS enrollment_status,
                   g.score, g.remarks, g.updated_at,
                   CASE
                       WHEN g.score IS NULL THEN NULL
                       WHEN g.score >= 90 THEN 4.0
                       WHEN g.score >= 80 THEN 3.0
                       WHEN g.score >= 70 THEN 2.0
                       WHEN g.score >= 60 THEN 1.0
                       ELSE 0.0
                   END AS grade_points
            FROM Enrollments e
            JOIN Courses c  ON e.course_id       = c.course_id
            LEFT JOIN Grades g ON e.enrollment_id = g.enrollment_id
            WHERE e.student_id = %s
            ORDER BY c.course_name
            """,
            (sid,),
        )
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/student/catalog")
def student_catalog():
    """Return all university courses with seat counts and the student's current enrollment state."""
    sid = _get_linked_student_id()
    if not sid:
        return err("No student record linked to this account", 400)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT c.course_id, c.course_code, c.course_name,
                   c.credits, c.department, c.capacity,
                   f.full_name AS faculty_name,
                   COUNT(e_all.enrollment_id) AS enrolled_count,
                   MAX(CASE WHEN e_me.student_id = %s THEN e_me.enrollment_id ELSE NULL END) AS my_enrollment_id,
                   MAX(CASE WHEN e_me.student_id = %s THEN e_me.status ELSE NULL END) AS my_status
            FROM Courses c
            LEFT JOIN Faculty f ON c.faculty_id = f.faculty_id
            LEFT JOIN Enrollments e_all ON e_all.course_id = c.course_id AND e_all.status = 'Active'
            LEFT JOIN Enrollments e_me  ON e_me.course_id  = c.course_id AND e_me.student_id = %s
            GROUP BY c.course_id
            ORDER BY c.course_code
            """,
            (sid, sid, sid),
        )
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/student/enroll", methods=["POST"])
def student_self_enroll():
    """Transaction-safe self-service enrollment for a logged-in student."""
    sid = _get_linked_student_id()
    if not sid:
        return err("No student record linked to this account", 400)

    data      = request.get_json(force=True) or {}
    course_id = data.get("course_id")
    if not course_id:
        return err("course_id is required")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        # Lock the course row for capacity check
        cur.execute("SELECT course_id, course_name, capacity FROM Courses WHERE course_id = %s FOR UPDATE", (course_id,))
        course = cur.fetchone()
        if not course:
            conn.rollback()
            return err("Course not found", 404)

        cur.execute(
            "SELECT COUNT(*) AS cnt FROM Enrollments WHERE course_id = %s AND status = 'Active'",
            (course_id,),
        )
        active_count = cur.fetchone()["cnt"]
        if active_count >= course["capacity"]:
            conn.rollback()
            return err(f"Course is full ({active_count}/{course['capacity']})", 409)

        # Check existing enrollment for this student + course
        cur.execute(
            "SELECT enrollment_id, status FROM Enrollments WHERE student_id = %s AND course_id = %s ORDER BY enrollment_id DESC LIMIT 1",
            (sid, course_id),
        )
        existing = cur.fetchone()
        if existing:
            if existing["status"] == "Active":
                conn.rollback()
                return err("You are already enrolled in this course", 409)
            if existing["status"] == "Completed":
                conn.rollback()
                return err("You have already completed this course", 409)
            # Re-activate a previously Dropped enrollment
            cur.execute(
                "UPDATE Enrollments SET status = 'Active', enrollment_date = %s WHERE enrollment_id = %s",
                (date.today().isoformat(), existing["enrollment_id"]),
            )
            conn.commit()
            return ok({"enrollment_id": existing["enrollment_id"]}, f"Re-enrolled in {course['course_name']}!")

        cur.execute(
            "INSERT INTO Enrollments (student_id, course_id, enrollment_date, status) VALUES (%s, %s, %s, 'Active')",
            (sid, course_id, date.today().isoformat()),
        )
        conn.commit()
        return ok({"enrollment_id": cur.lastrowid}, f"Enrolled in {course['course_name']}!", 201)
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/student/drop/<int:eid>", methods=["PUT"])
def student_self_drop(eid):
    """Allow a student to drop their own Active enrollment."""
    sid = _get_linked_student_id()
    if not sid:
        return err("No student record linked to this account", 400)

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT enrollment_id, status FROM Enrollments WHERE enrollment_id = %s AND student_id = %s",
            (eid, sid),
        )
        row = cur.fetchone()
        if not row:
            return err("Enrollment not found", 404)
        if row["status"] != "Active":
            return err(f"Cannot drop an enrollment with status '{row['status']}'", 400)

        cur.execute(
            "UPDATE Enrollments SET status = 'Dropped' WHERE enrollment_id = %s",
            (eid,),
        )
        conn.commit()
        return ok(message="Course dropped successfully")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/student/my-attendance")
def student_my_attendance():
    """Return per-course attendance summary and individual session records for the student."""
    sid = _get_linked_student_id()
    if not sid:
        return err("No student record linked to this account", 400)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT e.enrollment_id, c.course_code, c.course_name,
                   COUNT(a.attendance_id) AS total_sessions,
                   SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) AS present_count,
                   SUM(CASE WHEN a.status = 'Late'    THEN 1 ELSE 0 END) AS late_count,
                   SUM(CASE WHEN a.status = 'Absent'  THEN 1 ELSE 0 END) AS absent_count,
                   ROUND(
                       SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) * 100.0
                       / NULLIF(COUNT(a.attendance_id), 0),
                       1
                   ) AS attendance_pct
            FROM Enrollments e
            JOIN Courses c ON e.course_id = c.course_id
            LEFT JOIN Attendance a ON a.enrollment_id = e.enrollment_id
            WHERE e.student_id = %s AND e.status IN ('Active', 'Completed')
            GROUP BY e.enrollment_id, c.course_code, c.course_name
            ORDER BY c.course_code
            """,
            (sid,),
        )
        summary = cur.fetchall()

        cur.execute(
            """
            SELECT a.attendance_id, a.session_date, a.status, a.remarks,
                   c.course_code, c.course_name
            FROM Attendance a
            JOIN Enrollments e ON a.enrollment_id = e.enrollment_id
            JOIN Courses c     ON e.course_id     = c.course_id
            WHERE e.student_id = %s
            ORDER BY a.session_date DESC, c.course_code
            LIMIT 100
            """,
            (sid,),
        )
        records = cur.fetchall()
        return ok({"summary": summary, "records": records})
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()

# ===========================================================================
# FACULTY PORTAL APIs  (session role == 'faculty')
# ===========================================================================

def _get_linked_faculty_id() -> int | None:
    fid = session.get("linked_id")
    if fid:
        return fid
    # Auto-link if faculty user was created without linked_id
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        uname = (session.get("username") or "").strip()
        cur.execute(
            "SELECT faculty_id FROM Faculty WHERE LOWER(full_name) LIKE %s OR LOWER(email) LIKE %s LIMIT 1",
            (f"%{uname.lower().replace('.', ' ')}%", f"%{uname.lower()}%"),
        )
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT faculty_id FROM Faculty ORDER BY faculty_id LIMIT 1")
            row = cur.fetchone()
        if row:
            fid = row["faculty_id"]
            session["linked_id"] = fid
            if session.get("user_id"):
                cur.execute("UPDATE Users SET linked_id = %s WHERE user_id = %s", (fid, session["user_id"]))
                conn.commit()
            return fid
    except MySQLError:
        pass
    finally:
        cur.close()
        conn.close()
    return None


@app.route("/api/faculty/dashboard")
def faculty_dashboard():
    fid = _get_linked_faculty_id()
    if not fid:
        return err("No faculty record linked to this account", 400)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM Faculty WHERE faculty_id = %s", (fid,))
        profile = cur.fetchone()
        if not profile:
            return err("Faculty record not found", 404)

        cur.execute(
            "SELECT COUNT(*) AS cnt FROM Courses WHERE faculty_id = %s", (fid,)
        )
        course_count = cur.fetchone()["cnt"]

        cur.execute(
            """
            SELECT COUNT(DISTINCT e.student_id) AS cnt
            FROM Enrollments e
            JOIN Courses c ON e.course_id = c.course_id
            WHERE c.faculty_id = %s AND e.status = 'Active'
            """,
            (fid,),
        )
        student_count = cur.fetchone()["cnt"]

        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM Grades g
            JOIN Enrollments e ON g.enrollment_id = e.enrollment_id
            JOIN Courses c     ON e.course_id      = c.course_id
            WHERE c.faculty_id = %s
            """,
            (fid,),
        )
        graded_count = cur.fetchone()["cnt"]

        return ok({
            "profile":       profile,
            "course_count":  course_count,
            "student_count": student_count,
            "graded_count":  graded_count,
        })
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/faculty/my-courses")
def faculty_my_courses():
    fid = _get_linked_faculty_id()
    if not fid:
        return err("No faculty record linked to this account", 400)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT c.course_id, c.course_code, c.course_name,
                   c.credits, c.department, c.capacity,
                   COUNT(e.enrollment_id) AS enrolled_count
            FROM Courses c
            LEFT JOIN Enrollments e ON e.course_id = c.course_id AND e.status = 'Active'
            WHERE c.faculty_id = %s
            GROUP BY c.course_id
            ORDER BY c.course_code
            """,
            (fid,),
        )
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/faculty/course/<int:cid>/students")
def faculty_course_students(cid):
    fid = _get_linked_faculty_id()
    if not fid:
        return err("No faculty record linked to this account", 400)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        # Verify this course belongs to this faculty
        cur.execute(
            "SELECT course_id FROM Courses WHERE course_id = %s AND faculty_id = %s",
            (cid, fid),
        )
        if not cur.fetchone():
            return err("Course not found or not assigned to you", 403)

        cur.execute(
            """
            SELECT e.enrollment_id, e.enrollment_date, e.status,
                   s.student_id, s.full_name AS student_name,
                   s.email, s.department, s.year_of_study,
                   g.grade_id, g.score, g.remarks, g.updated_at
            FROM Enrollments e
            JOIN Students s ON e.student_id     = s.student_id
            LEFT JOIN Grades g ON e.enrollment_id = g.enrollment_id
            WHERE e.course_id = %s
            ORDER BY s.full_name
            """,
            (cid,),
        )
        return ok(cur.fetchall())
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/faculty/grade", methods=["POST"])
def faculty_add_grade():
    fid  = _get_linked_faculty_id()
    data = request.get_json(force=True) or {}
    enrollment_id = data.get("enrollment_id")
    score         = data.get("score")
    remarks       = (data.get("remarks") or "").strip()

    if not fid:            return err("No faculty record linked to this account", 400)
    if not enrollment_id:  return err("enrollment_id is required")
    try:
        score = float(score)
        if score < 0 or score > 100:
            raise ValueError
    except (ValueError, TypeError):
        return err("score must be 0–100")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        # Verify the enrollment is in a course assigned to this faculty
        cur.execute(
            """
            SELECT e.enrollment_id FROM Enrollments e
            JOIN Courses c ON e.course_id = c.course_id
            WHERE e.enrollment_id = %s AND c.faculty_id = %s
            """,
            (enrollment_id, fid),
        )
        if not cur.fetchone():
            return err("Enrollment not found or not in your course", 403)

        cur.execute("SELECT grade_id FROM Grades WHERE enrollment_id = %s", (enrollment_id,))
        if cur.fetchone():
            return err("Grade already exists. Use PUT to update.", 409)

        cur.execute(
            "INSERT INTO Grades (enrollment_id, score, remarks) VALUES (%s,%s,%s)",
            (enrollment_id, score, remarks or None),
        )
        conn.commit()
        return ok(message="Grade saved successfully", status=201)
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/faculty/grade/<int:gid>", methods=["PUT"])
def faculty_update_grade(gid):
    fid  = _get_linked_faculty_id()
    data = request.get_json(force=True) or {}
    score   = data.get("score")
    remarks = (data.get("remarks") or "").strip()

    if not fid: return err("No faculty record linked to this account", 400)
    try:
        score = float(score)
        if score < 0 or score > 100:
            raise ValueError
    except (ValueError, TypeError):
        return err("score must be 0–100")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        # Verify the grade belongs to a course assigned to this faculty
        cur.execute(
            """
            SELECT g.grade_id FROM Grades g
            JOIN Enrollments e ON g.enrollment_id = e.enrollment_id
            JOIN Courses c     ON e.course_id      = c.course_id
            WHERE g.grade_id = %s AND c.faculty_id = %s
            """,
            (gid, fid),
        )
        if not cur.fetchone():
            return err("Grade not found or not in your course", 403)

        cur.execute(
            "UPDATE Grades SET score=%s, remarks=%s, updated_at=NOW() WHERE grade_id=%s",
            (score, remarks or None, gid),
        )
        conn.commit()
        return ok(message="Grade updated successfully")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/faculty/course/<int:cid>/attendance")
def faculty_course_attendance(cid):
    """Get enrolled students for a course along with their attendance on a specific date and overall %."""
    fid          = _get_linked_faculty_id()
    session_date = (request.args.get("date") or date.today().isoformat()).strip()
    if not fid:
        return err("No faculty record linked to this account", 400)

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT course_id FROM Courses WHERE course_id = %s AND faculty_id = %s",
            (cid, fid),
        )
        if not cur.fetchone():
            return err("Course not found or not assigned to you", 403)

        cur.execute(
            """
            SELECT e.enrollment_id, s.student_id, s.full_name AS student_name, s.email,
                   a_day.status AS date_status, a_day.remarks AS date_remarks,
                   COUNT(a_all.attendance_id) AS total_sessions,
                   SUM(CASE WHEN a_all.status IN ('Present', 'Late') THEN 1 ELSE 0 END) AS attended_sessions,
                   ROUND(
                       SUM(CASE WHEN a_all.status IN ('Present', 'Late') THEN 1 ELSE 0 END) * 100.0
                       / NULLIF(COUNT(a_all.attendance_id), 0),
                       1
                   ) AS attendance_pct
            FROM Enrollments e
            JOIN Students s ON e.student_id = s.student_id
            LEFT JOIN Attendance a_day
                   ON a_day.enrollment_id = e.enrollment_id AND a_day.session_date = %s
            LEFT JOIN Attendance a_all
                   ON a_all.enrollment_id = e.enrollment_id
            WHERE e.course_id = %s AND e.status = 'Active'
            GROUP BY e.enrollment_id, s.student_id, s.full_name, s.email,
                     a_day.status, a_day.remarks
            ORDER BY s.full_name
            """,
            (session_date, cid),
        )
        return ok({"session_date": session_date, "students": cur.fetchall()})
    except MySQLError as e:
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/api/faculty/attendance", methods=["POST"])
def faculty_save_attendance():
    """Save or update daily attendance for a list of enrollments in a faculty's course."""
    fid  = _get_linked_faculty_id()
    data = request.get_json(force=True) or {}
    course_id    = data.get("course_id")
    session_date = (data.get("session_date") or date.today().isoformat()).strip()
    records      = data.get("records") or []

    if not fid:       return err("No faculty record linked to this account", 400)
    if not course_id: return err("course_id is required")
    if not records:   return err("No attendance records provided")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT course_id FROM Courses WHERE course_id = %s AND faculty_id = %s",
            (course_id, fid),
        )
        if not cur.fetchone():
            return err("Course not found or not assigned to you", 403)

        saved = 0
        for rec in records:
            eid     = rec.get("enrollment_id")
            status  = (rec.get("status") or "Present").strip()
            remarks = (rec.get("remarks") or "").strip() or None
            if status not in ("Present", "Absent", "Late"):
                conn.rollback()
                return err(f"Invalid attendance status: {status}")

            # Verify enrollment belongs to this course
            cur.execute(
                "SELECT enrollment_id FROM Enrollments WHERE enrollment_id = %s AND course_id = %s",
                (eid, course_id),
            )
            if not cur.fetchone():
                continue

            cur.execute(
                """
                INSERT INTO Attendance (enrollment_id, session_date, status, remarks)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE status = VALUES(status), remarks = VALUES(remarks)
                """,
                (eid, session_date, status, remarks),
            )
            saved += 1

        conn.commit()

        # Sync nested attendance session document to MongoDB (NoSQL)
        try:
            cur.execute("SELECT course_code, course_name FROM Courses WHERE course_id = %s", (course_id,))
            c_info = cur.fetchone() or {}
            mongo_db.sync_attendance_session_doc(
                course_id=int(course_id),
                course_code=c_info.get("course_code", ""),
                course_name=c_info.get("course_name", ""),
                session_date=session_date,
                faculty_id=fid,
                records=records,
            )
        except Exception:
            pass

        return ok(message=f"Attendance saved for {saved} student(s) on {session_date} (MySQL + MongoDB synced)")
    except MySQLError as e:
        conn.rollback()
        return err(str(e), 500)
    finally:
        cur.close()
        conn.close()


# ===========================================================================
# MONGODB (NoSQL) ENDPOINTS — Admin, Faculty & Student Portals
# ===========================================================================

@app.route("/api/nosql/overview")
def admin_nosql_overview():
    """Return MongoDB status, collection counts, announcements, course reviews, and sample documents."""
    status = mongo_db.get_mongo_status()
    announcements = mongo_db.list_announcements()
    feedback = mongo_db.list_course_feedback()
    att_sessions = mongo_db.list_attendance_session_docs(limit=10)
    transcripts = [
        mongo_db._clean_doc(d)
        for d in mongo_db.get_mongo_db()["student_transcripts"].find({})
    ]
    return ok({
        "status": status,
        "announcements": announcements,
        "feedback": feedback,
        "attendance_sessions": att_sessions,
        "transcripts": transcripts,
    })


@app.route("/api/nosql/announcements/<ann_id>", methods=["DELETE"])
def admin_delete_announcement(ann_id):
    mongo_db.delete_announcement(ann_id)
    return ok(message="Announcement removed from MongoDB")


@app.route("/api/faculty/nosql/feed")
def faculty_nosql_feed():
    """Return announcements and student course feedback for courses taught by this faculty."""
    fid = _get_linked_faculty_id()
    if not fid:
        return err("No faculty record linked to this account", 400)

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT course_id, course_code, course_name FROM Courses WHERE faculty_id = %s", (fid,))
        courses = cur.fetchall()
        c_ids = [c["course_id"] for c in courses]
    finally:
        cur.close()
        conn.close()

    announcements = mongo_db.list_announcements(c_ids)
    feedback = mongo_db.list_course_feedback(c_ids)
    return ok({
        "courses": courses,
        "announcements": announcements,
        "feedback": feedback,
    })


@app.route("/api/faculty/nosql/announcements", methods=["POST"])
def faculty_post_announcement():
    """Post a new course announcement document into MongoDB."""
    fid = _get_linked_faculty_id()
    if not fid:
        return err("No faculty record linked to this account", 400)

    data = request.get_json(force=True) or {}
    course_id = data.get("course_id")
    title = (data.get("title") or "").strip()
    message = (data.get("message") or "").strip()
    priority = (data.get("priority") or "Normal").strip()
    raw_tags = data.get("tags") or []
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]

    if not course_id: return err("course_id is required")
    if not title:     return err("title is required")
    if not message:   return err("message is required")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT c.course_id, c.course_code, c.course_name, f.full_name AS faculty_name
            FROM Courses c
            JOIN Faculty f ON c.faculty_id = f.faculty_id
            WHERE c.course_id = %s AND c.faculty_id = %s
            """,
            (course_id, fid),
        )
        course = cur.fetchone()
        if not course:
            return err("Course not found or not assigned to you", 403)
    finally:
        cur.close()
        conn.close()

    doc = mongo_db.add_announcement(
        course_id=course["course_id"],
        course_code=course["course_code"],
        course_name=course["course_name"],
        faculty_id=fid,
        faculty_name=course["faculty_name"],
        title=title,
        message=message,
        priority=priority,
        tags=tags or ["Announcement"],
    )
    return ok(doc, "Announcement published to MongoDB!", 201)


@app.route("/api/faculty/nosql/announcements/<ann_id>", methods=["DELETE"])
def faculty_delete_announcement(ann_id):
    mongo_db.delete_announcement(ann_id)
    return ok(message="Announcement deleted from MongoDB")


@app.route("/api/student/nosql/feed")
def student_nosql_feed():
    """Return announcements and feedback for courses the logged-in student is enrolled in."""
    sid = _get_linked_student_id()
    if not sid:
        return err("No student record linked to this account", 400)

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT DISTINCT c.course_id, c.course_code, c.course_name
            FROM Enrollments e
            JOIN Courses c ON e.course_id = c.course_id
            WHERE e.student_id = %s AND e.status IN ('Active', 'Completed')
            ORDER BY c.course_code
            """,
            (sid,),
        )
        my_courses = cur.fetchall()
        c_ids = [c["course_id"] for c in my_courses]
    finally:
        cur.close()
        conn.close()

    announcements = mongo_db.list_announcements(c_ids)
    feedback = mongo_db.list_course_feedback(c_ids)
    return ok({
        "my_courses": my_courses,
        "announcements": announcements,
        "feedback": feedback,
    })


@app.route("/api/student/nosql/feedback", methods=["POST"])
def student_post_feedback():
    """Submit or update a student course rating & review in MongoDB."""
    sid = _get_linked_student_id()
    if not sid:
        return err("No student record linked to this account", 400)

    data = request.get_json(force=True) or {}
    course_id = data.get("course_id")
    rating = data.get("rating")
    difficulty = (data.get("difficulty") or "Moderate").strip()
    comment = (data.get("comment") or "").strip()
    raw_tags = data.get("tags") or []
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]

    if not course_id: return err("course_id is required")
    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError
    except (ValueError, TypeError):
        return err("rating must be between 1 and 5")
    if not comment:
        return err("Please enter a short review comment")

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT full_name FROM Students WHERE student_id = %s", (sid,))
        stu = cur.fetchone()
        if not stu:
            return err("Student record not found", 404)

        cur.execute(
            """
            SELECT c.course_id, c.course_code, c.course_name
            FROM Enrollments e
            JOIN Courses c ON e.course_id = c.course_id
            WHERE e.student_id = %s AND c.course_id = %s
            LIMIT 1
            """,
            (sid, course_id),
        )
        course = cur.fetchone()
        if not course:
            return err("You can only review courses you are enrolled in", 403)
    finally:
        cur.close()
        conn.close()

    doc = mongo_db.upsert_course_feedback(
        course_id=course["course_id"],
        course_code=course["course_code"],
        course_name=course["course_name"],
        student_id=sid,
        student_name=stu["full_name"],
        rating=rating,
        difficulty=difficulty,
        tags=tags or ["Well Structured"],
        comment=comment,
    )
    return ok(doc, "Course feedback saved to MongoDB!", 201)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=debug)
