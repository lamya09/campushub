-- ============================================================================
-- CampusHub — Complete RDBMS (MySQL 8.0) Schema, Views, Triggers & Seed Script
-- ============================================================================

CREATE DATABASE IF NOT EXISTS CampusHub;
USE CampusHub;

-- 1. Students Table
CREATE TABLE IF NOT EXISTS Students (
    student_id    INT AUTO_INCREMENT PRIMARY KEY,
    full_name     VARCHAR(100) NOT NULL,
    email         VARCHAR(120) NOT NULL UNIQUE,
    department    VARCHAR(80)  NOT NULL,
    year_of_study INT          NOT NULL CHECK (year_of_study BETWEEN 1 AND 6),
    created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- 2. Faculty Table
CREATE TABLE IF NOT EXISTS Faculty (
    faculty_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name  VARCHAR(100) NOT NULL,
    email      VARCHAR(120) NOT NULL UNIQUE,
    department VARCHAR(80)  NOT NULL
);

-- 3. Courses Table
CREATE TABLE IF NOT EXISTS Courses (
    course_id   INT AUTO_INCREMENT PRIMARY KEY,
    course_code VARCHAR(20)  NOT NULL UNIQUE,
    course_name VARCHAR(120) NOT NULL,
    credits     INT          NOT NULL CHECK (credits > 0),
    department  VARCHAR(80)  NOT NULL,
    faculty_id  INT          DEFAULT NULL,
    capacity    INT          NOT NULL DEFAULT 30 CHECK (capacity > 0),
    FOREIGN KEY (faculty_id) REFERENCES Faculty(faculty_id) ON DELETE SET NULL
);

-- 4. Enrollments Table
CREATE TABLE IF NOT EXISTS Enrollments (
    enrollment_id   INT AUTO_INCREMENT PRIMARY KEY,
    student_id      INT  NOT NULL,
    course_id       INT  NOT NULL,
    enrollment_date DATE NOT NULL,
    status          ENUM('Active', 'Dropped', 'Completed') NOT NULL DEFAULT 'Active',
    FOREIGN KEY (student_id) REFERENCES Students(student_id) ON DELETE CASCADE,
    FOREIGN KEY (course_id)  REFERENCES Courses(course_id)   ON DELETE CASCADE
);

-- 5. Grades Table
CREATE TABLE IF NOT EXISTS Grades (
    grade_id      INT AUTO_INCREMENT PRIMARY KEY,
    enrollment_id INT           NOT NULL UNIQUE,
    score         DECIMAL(5, 2) NOT NULL CHECK (score BETWEEN 0 AND 100),
    remarks       VARCHAR(255)  DEFAULT NULL,
    updated_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (enrollment_id) REFERENCES Enrollments(enrollment_id) ON DELETE CASCADE
);

-- 6. Attendance Table
CREATE TABLE IF NOT EXISTS Attendance (
    attendance_id INT AUTO_INCREMENT PRIMARY KEY,
    enrollment_id INT  NOT NULL,
    session_date  DATE NOT NULL,
    status        ENUM('Present', 'Absent', 'Late') NOT NULL DEFAULT 'Present',
    remarks       VARCHAR(255) DEFAULT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_enrollment_date (enrollment_id, session_date),
    FOREIGN KEY (enrollment_id) REFERENCES Enrollments(enrollment_id) ON DELETE CASCADE
);

-- 7. Users Table (Role-Based Access Control)
CREATE TABLE IF NOT EXISTS Users (
    user_id       INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM('admin', 'student', 'faculty') NOT NULL,
    linked_id     INT DEFAULT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. AuditLog Table (Populated automatically via MySQL Triggers)
CREATE TABLE IF NOT EXISTS AuditLog (
    log_id      INT AUTO_INCREMENT PRIMARY KEY,
    table_name  VARCHAR(50) NOT NULL,
    action_type ENUM('INSERT', 'UPDATE', 'DELETE') NOT NULL,
    record_id   INT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    changed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- SQL VIEWS
-- ============================================================================

CREATE OR REPLACE VIEW CourseEnrollmentSummary AS
SELECT 
    c.course_id,
    c.course_code,
    c.course_name,
    c.department,
    c.capacity,
    f.full_name AS faculty_name,
    COUNT(e.enrollment_id) AS enrolled_count
FROM Courses c
LEFT JOIN Faculty f ON c.faculty_id = f.faculty_id
LEFT JOIN Enrollments e ON c.course_id = e.course_id AND e.status = 'Active'
GROUP BY c.course_id, c.course_code, c.course_name, c.department, c.capacity, f.full_name;

CREATE OR REPLACE VIEW StudentCourseDetails AS
SELECT 
    s.student_id,
    s.full_name AS student_name,
    s.department AS student_department,
    s.year_of_study,
    c.course_code,
    c.course_name,
    c.department AS course_department,
    e.enrollment_date,
    e.status AS enrollment_status,
    g.score,
    g.remarks
FROM Students s
JOIN Enrollments e ON s.student_id = e.student_id
JOIN Courses c ON e.course_id = c.course_id
LEFT JOIN Grades g ON e.enrollment_id = g.enrollment_id;

-- ============================================================================
-- MYSQL TRIGGERS (Automated Audit Logging)
-- ============================================================================

DROP TRIGGER IF EXISTS trg_grades_after_update;
DROP TRIGGER IF EXISTS trg_grades_after_delete;
DROP TRIGGER IF EXISTS trg_enrollments_after_update;
DROP TRIGGER IF EXISTS trg_enrollments_after_delete;

DELIMITER $$

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
END$$

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
END$$

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
END$$

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
END$$

DELIMITER ;
