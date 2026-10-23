import io
import pytest
from app.services.csv_importer import parse_and_validate_csv

def test_parse_and_validate_csv_valid():
    csv_data = (
        "email,password,first_name,last_name,role,grade_level,guardian_name,guardian_email\n"
        "t1@test.com,password123,Teacher,One,teacher,,,\n"
        "s1@test.com,password123,Student,One,student,Grade 10,Parent One,p1@test.com\n"
    )
    result = parse_and_validate_csv(io.StringIO(csv_data))
    assert len(result["valid_rows"]) == 2
    assert len(result["errors"]) == 0

    row_t1 = result["valid_rows"][0]
    assert row_t1["email"] == "t1@test.com"
    assert row_t1["role"] == "teacher"
    assert row_t1["row_number"] == 2

    row_s1 = result["valid_rows"][1]
    assert row_s1["email"] == "s1@test.com"
    assert row_s1["role"] == "student"
    assert row_s1["grade_level"] == "Grade 10"
    assert row_s1["guardian_name"] == "Parent One"
    assert row_s1["row_number"] == 3


def test_parse_and_validate_csv_validation_errors():
    csv_data = (
        "email,password,first_name,last_name,role,grade_level,guardian_name,guardian_email\n"
        "bademail,password123,Bad,Email,teacher,,,\n"
        "s2@test.com,password123,Student,Two,student,Grade 10,,\n"  # Missing guardian fields
    )
    result = parse_and_validate_csv(io.StringIO(csv_data))
    assert len(result["valid_rows"]) == 0
    assert len(result["errors"]) == 2
    assert result["errors"][0]["row_number"] == 2
    assert result["errors"][1]["row_number"] == 3


def test_parse_and_validate_csv_duplicate_email_in_file():
    csv_data = (
        "email,password,first_name,last_name,role,grade_level,guardian_name,guardian_email\n"
        "dup@test.com,password123,Dup,One,teacher,,,\n"
        "dup@test.com,password123,Dup,Two,teacher,,,\n"
        "valid@test.com,password123,Valid,User,teacher,,,\n"
    )
    result = parse_and_validate_csv(io.StringIO(csv_data))
    assert len(result["valid_rows"]) == 1
    assert result["valid_rows"][0]["email"] == "valid@test.com"
    assert len(result["errors"]) == 2
    err_rows = [e["row_number"] for e in result["errors"]]
    assert 2 in err_rows
    assert 3 in err_rows
    assert "Duplicate email" in result["errors"][0]["error"]


def test_parse_and_validate_csv_grade_level_validation():
    valid_grades = {"Grade 10", "Grade 11"}
    csv_data = (
        "email,password,first_name,last_name,role,grade_level,guardian_name,guardian_email\n"
        "good_grade@test.com,password123,Good,Grade,student,Grade 10,Parent One,p1@test.com\n"
        "typo_grade@test.com,password123,Typo,Grade,student,Grade10,Parent Two,p2@test.com\n"
    )
    result = parse_and_validate_csv(io.StringIO(csv_data), valid_grade_names=valid_grades)
    assert len(result["valid_rows"]) == 1
    assert result["valid_rows"][0]["email"] == "good_grade@test.com"
    assert len(result["errors"]) == 1
    assert result["errors"][0]["row_number"] == 3
    assert "Invalid grade level 'Grade10'" in result["errors"][0]["error"]


def test_parse_and_validate_csv_none_value_safety():
    result = parse_and_validate_csv("email,password,first_name,last_name,role\n,")
    assert isinstance(result["errors"], list)


def test_parse_and_validate_csv_binary_file_safety():
    # Simulate a raw binary file (e.g., JPEG image bytes)
    binary_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00\x48\x00\x48\x00\x00"
    result = parse_and_validate_csv(io.BytesIO(binary_bytes))
    assert len(result["valid_rows"]) == 0
    assert len(result["errors"]) == 1
    assert "missing required 'email' header column" in result["errors"][0]["error"].lower()
