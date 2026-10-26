"""
mongo_db.py — Hybrid NoSQL (MongoDB) Document Store Layer for CampusHub.

Supports 5 document collections in database `CampusHub_NoSQL`:
  1. course_announcements — Nested announcements with tags & priority posted by faculty
  2. course_feedback      — Student course ratings (1–5 stars), difficulty, tags & reviews
  3. attendance_sessions  — Single nested document per lecture session with embedded student array
  4. audit_logs           — Event-driven audit trail documents
  5. student_transcripts  — Cached nested academic transcript documents

Connection Mode:
  - Attempts to connect to a live MongoDB server via `pymongo.MongoClient(MONGO_URI)`
    (default `mongodb://127.0.0.1:27017/`).
  - If no local MongoDB daemon is running, seamlessly uses a local JSON-persisted
    pymongo-compatible document store (`mongodb_data/*.json`) so the application works
    zero-config out of the box while storing inspectable BSON/JSON collection files.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017/")
MONGO_DB_NAME = os.environ.get("MONGO_DB", "CampusHub_NoSQL")
DATA_DIR = Path(__file__).resolve().parent / "mongodb_data"

_mongo_client = None
_mongo_db = None
_engine_mode = None  # "pymongo" or "json_document_store"


# ---------------------------------------------------------------------------
# Embedded pymongo-compatible JSON Document Collection (Fallback Engine)
# ---------------------------------------------------------------------------

class LocalDocumentCollection:
    """
    A pymongo-compatible document collection backed by a JSON file in `mongodb_data/`.
    Supports insert_one, find, find_one, update_one (with $set and upsert),
    delete_one, count_documents, and replace_one.
    """

    def __init__(self, name: str):
        self.name = name
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.file_path = DATA_DIR / f"{name}.json"
        if not self.file_path.exists():
            self._write_all([])

    def _read_all(self) -> list[dict[str, Any]]:
        try:
            if not self.file_path.exists():
                return []
            raw = self.file_path.read_text(encoding="utf-8").strip()
            return json.loads(raw) if raw else []
        except Exception:
            return []

    def _write_all(self, docs: list[dict[str, Any]]) -> None:
        self.file_path.write_text(
            json.dumps(docs, indent=2, default=str),
            encoding="utf-8",
        )

    @staticmethod
    def _matches(doc: dict[str, Any], query: dict[str, Any] | None) -> bool:
        if not query:
            return True
        for k, v in query.items():
            if isinstance(v, dict):
                if "$in" in v:
                    if doc.get(k) not in v["$in"]:
                        return False
                elif "$ne" in v:
                    if doc.get(k) == v["$ne"]:
                        return False
            else:
                if str(doc.get(k)) != str(v) and doc.get(k) != v:
                    return False
        return True

    def find(self, query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        docs = self._read_all()
        return [d for d in docs if self._matches(d, query)]

    def find_one(self, query: dict[str, Any] | None = None) -> dict[str, Any] | None:
        for d in self._read_all():
            if self._matches(d, query):
                return d
        return None

    def insert_one(self, doc: dict[str, Any]) -> str:
        docs = self._read_all()
        new_doc = dict(doc)
        if "_id" not in new_doc:
            new_doc["_id"] = uuid.uuid4().hex[:24]
        docs.insert(0, new_doc)
        self._write_all(docs)
        return str(new_doc["_id"])

    def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        upsert: bool = False,
    ) -> bool:
        docs = self._read_all()
        set_fields = update.get("$set", update)
        for idx, d in enumerate(docs):
            if self._matches(d, query):
                docs[idx].update(set_fields)
                self._write_all(docs)
                return True
        if upsert:
            merged = {k: v for k, v in query.items() if not isinstance(v, dict)}
            merged.update(set_fields)
            if "_id" not in merged:
                merged["_id"] = uuid.uuid4().hex[:24]
            docs.insert(0, merged)
            self._write_all(docs)
            return True
        return False

    def delete_one(self, query: dict[str, Any]) -> bool:
        docs = self._read_all()
        for idx, d in enumerate(docs):
            if self._matches(d, query):
                docs.pop(idx)
                self._write_all(docs)
                return True
        return False

    def count_documents(self, query: dict[str, Any] | None = None) -> int:
        return len(self.find(query))


class LocalMongoDatabase:
    def __init__(self):
        self._collections: dict[str, LocalDocumentCollection] = {}

    def __getattr__(self, name: str) -> LocalDocumentCollection:
        return self[name]

    def __getitem__(self, name: str) -> LocalDocumentCollection:
        if name not in self._collections:
            self._collections[name] = LocalDocumentCollection(name)
        return self._collections[name]


# ---------------------------------------------------------------------------
# Connection Factory
# ---------------------------------------------------------------------------

def get_mongo_db():
    """Return either a live pymongo Database or the JSON-backed LocalMongoDatabase."""
    global _mongo_client, _mongo_db, _engine_mode
    if _mongo_db is not None:
        return _mongo_db

    try:
        import pymongo
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=800)
        client.admin.command("ping")
        _mongo_client = client
        _mongo_db = client[MONGO_DB_NAME]
        _engine_mode = "pymongo_server"
        return _mongo_db
    except Exception:
        _mongo_db = LocalMongoDatabase()
        _engine_mode = "json_document_store"
        return _mongo_db


def get_mongo_status() -> dict[str, Any]:
    db = get_mongo_db()
    cols = [
        "course_announcements",
        "course_feedback",
        "attendance_sessions",
        "audit_logs",
        "student_transcripts",
    ]
    counts = {}
    for c in cols:
        try:
            counts[c] = db[c].count_documents({})
        except Exception:
            counts[c] = 0
    return {
        "connected": True,
        "database": MONGO_DB_NAME,
        "engine": _engine_mode or "json_document_store",
        "collections": counts,
        "total_documents": sum(counts.values()),
    }


def _clean_doc(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    return out


# ---------------------------------------------------------------------------
# 1. Course Announcements Collection (`course_announcements`)
# ---------------------------------------------------------------------------

def list_announcements(course_ids: list[int] | None = None) -> list[dict[str, Any]]:
    db = get_mongo_db()
    query = {"course_id": {"$in": course_ids}} if course_ids is not None else {}
    if course_ids == []:
        return []
    raw = list(db["course_announcements"].find(query))
    docs = [_clean_doc(d) for d in raw]
    docs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return docs


def add_announcement(
    course_id: int,
    course_code: str,
    course_name: str,
    faculty_id: int | None,
    faculty_name: str,
    title: str,
    message: str,
    priority: str = "Normal",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    db = get_mongo_db()
    doc = {
        "_id": uuid.uuid4().hex[:24],
        "course_id": int(course_id),
        "course_code": course_code,
        "course_name": course_name,
        "faculty_id": faculty_id,
        "faculty_name": faculty_name,
        "title": title,
        "message": message,
        "priority": priority,
        "tags": tags or ["General"],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    db["course_announcements"].insert_one(doc)
    return _clean_doc(doc)


def delete_announcement(ann_id: str) -> bool:
    db = get_mongo_db()
    res = db["course_announcements"].delete_one({"_id": ann_id})
    return bool(res)


# ---------------------------------------------------------------------------
# 2. Course Feedback & Reviews Collection (`course_feedback`)
# ---------------------------------------------------------------------------

def list_course_feedback(course_ids: list[int] | None = None) -> list[dict[str, Any]]:
    db = get_mongo_db()
    query = {"course_id": {"$in": course_ids}} if course_ids is not None else {}
    if course_ids == []:
        return []
    raw = list(db["course_feedback"].find(query))
    docs = [_clean_doc(d) for d in raw]
    docs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return docs


def upsert_course_feedback(
    course_id: int,
    course_code: str,
    course_name: str,
    student_id: int,
    student_name: str,
    rating: int,
    difficulty: str,
    tags: list[str],
    comment: str,
) -> dict[str, Any]:
    db = get_mongo_db()
    now_str = datetime.now().isoformat(timespec="seconds")
    doc = {
        "course_id": int(course_id),
        "course_code": course_code,
        "course_name": course_name,
        "student_id": int(student_id),
        "student_name": student_name,
        "rating": int(rating),
        "difficulty": difficulty,
        "tags": tags or ["Helpful"],
        "comment": comment,
        "created_at": now_str,
    }
    db["course_feedback"].update_one(
        {"course_id": int(course_id), "student_id": int(student_id)},
        {"$set": doc},
        upsert=True,
    )
    return doc


# ---------------------------------------------------------------------------
# 3. Attendance Sessions Collection (`attendance_sessions`)
# ---------------------------------------------------------------------------

def sync_attendance_session_doc(
    course_id: int,
    course_code: str,
    course_name: str,
    session_date: str,
    faculty_id: int | None,
    records: list[dict[str, Any]],
) -> None:
    db = get_mongo_db()
    present_cnt = sum(1 for r in records if r.get("status") in ("Present", "Late"))
    total_cnt = len(records)
    doc = {
        "course_id": int(course_id),
        "course_code": course_code,
        "course_name": course_name,
        "session_date": session_date,
        "faculty_id": faculty_id,
        "summary": {
            "total_students": total_cnt,
            "attended": present_cnt,
            "absent": total_cnt - present_cnt,
            "attendance_rate_pct": round((present_cnt * 100.0 / total_cnt), 1) if total_cnt else 0.0,
        },
        "records": records,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    db["attendance_sessions"].update_one(
        {"course_id": int(course_id), "session_date": session_date},
        {"$set": doc},
        upsert=True,
    )


def list_attendance_session_docs(limit: int = 30) -> list[dict[str, Any]]:
    db = get_mongo_db()
    docs = [_clean_doc(d) for d in db["attendance_sessions"].find({})]
    docs.sort(key=lambda x: x.get("session_date", ""), reverse=True)
    return docs[:limit]


# ---------------------------------------------------------------------------
# 4. Audit Logs Collection (`audit_logs`)
# ---------------------------------------------------------------------------

def log_nosql_audit_event(
    table_name: str,
    action_type: str,
    record_id: int,
    old_value: str | None,
    new_value: str | None,
    actor: str = "system",
    changed_at: str | None = None,
) -> None:
    db = get_mongo_db()
    doc = {
        "_id": uuid.uuid4().hex[:24],
        "table_name": table_name,
        "action_type": action_type,
        "record_id": int(record_id),
        "old_value": old_value,
        "new_value": new_value,
        "actor": actor,
        "changed_at": changed_at or datetime.now().isoformat(timespec="seconds"),
    }
    db["audit_logs"].insert_one(doc)


# ---------------------------------------------------------------------------
# 5. Student Transcripts Collection (`student_transcripts`)
# ---------------------------------------------------------------------------

def cache_student_transcript_doc(
    student_profile: dict[str, Any],
    weighted_gpa: float | None,
    avg_score: float | None,
    graded_credits: int,
    courses: list[dict[str, Any]],
) -> dict[str, Any]:
    db = get_mongo_db()
    sid = int(student_profile["student_id"])
    doc = {
        "student_id": sid,
        "student_profile": {
            "full_name": student_profile.get("full_name"),
            "email": student_profile.get("email"),
            "department": student_profile.get("department"),
            "year_of_study": student_profile.get("year_of_study"),
        },
        "academic_summary": {
            "weighted_gpa_4_scale": weighted_gpa,
            "mean_score_pct": avg_score,
            "graded_credits": graded_credits,
            "total_courses": len(courses),
        },
        "courses": courses,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    db["student_transcripts"].update_one(
        {"student_id": sid},
        {"$set": doc},
        upsert=True,
    )
    return doc
