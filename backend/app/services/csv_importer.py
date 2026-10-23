import csv
import io
from collections import Counter
from pydantic import ValidationError
from app.schemas.auth_schema import RegisterSchema

def parse_and_validate_csv(file_stream, valid_grade_names: set[str] | None = None) -> dict:
    """
    Pure parser & validator for bulk user CSV import.
    Accepts optional valid_grade_names set to validate student grade_level values without performing DB calls.

    Returns:
        {
            "valid_rows": [...],  # List of validated row dicts ready for user creation
            "errors": [...]      # List of {"row_number": N, "error": "msg"}
        }
    """
    try:
        if hasattr(file_stream, "read"):
            content = file_stream.read()
            if isinstance(content, bytes):
                text = content.decode("utf-8-sig", errors="replace")
            else:
                text = str(content)
        elif isinstance(file_stream, bytes):
            text = file_stream.decode("utf-8-sig", errors="replace")
        else:
            text = str(file_stream)
    except Exception as err:
        return {
            "valid_rows": [],
            "errors": [{"row_number": 1, "error": f"Failed to read CSV file: {str(err)}"}]
        }

    try:
        stream = io.StringIO(text)
        reader = csv.DictReader(stream)
        
        # Verify header structure
        if not reader.fieldnames or "email" not in [f.strip().lower() for f in reader.fieldnames if f]:
            return {
                "valid_rows": [],
                "errors": [{"row_number": 1, "error": "Invalid CSV structure: missing required 'email' header column"}]
            }
    except Exception as err:
        return {
            "valid_rows": [],
            "errors": [{"row_number": 1, "error": f"Malformed CSV content: {str(err)}"}]
        }

    rows_with_nums = []
    email_counts = Counter()

    # Read rows (row numbers start at 2 since line 1 is the header)
    try:
        for idx, row in enumerate(reader, start=2):
            cleaned_row = {}
            if row:
                for k, v in row.items():
                    if k is not None:
                        key = k.strip()
                        val = v.strip() if isinstance(v, str) else v
                        cleaned_row[key] = val

            raw_email = (cleaned_row.get("email") or "").strip().lower()
            if raw_email:
                email_counts[raw_email] += 1

            rows_with_nums.append((idx, cleaned_row, raw_email))
    except Exception as err:
        return {
            "valid_rows": [],
            "errors": [{"row_number": 1, "error": f"Failed parsing CSV rows: {str(err)}"}]
        }

    valid_rows = []
    errors = []

    for row_num, raw_dict, raw_email in rows_with_nums:
        # Check duplicate email within the CSV file itself
        if raw_email and email_counts[raw_email] > 1:
            errors.append({
                "row_number": row_num,
                "error": f"Duplicate email '{raw_email}' within CSV file"
            })
            continue

        # Prepare payload for Pydantic validation (convert None/empty values safely)
        schema_payload = {
            "email": (raw_dict.get("email") or "").strip(),
            "password": (raw_dict.get("password") or "").strip(),
            "first_name": (raw_dict.get("first_name") or "").strip(),
            "last_name": (raw_dict.get("last_name") or "").strip(),
            "role": (raw_dict.get("role") or "").strip(),
            "guardian_name": (raw_dict.get("guardian_name") or "").strip() or None,
            "guardian_email": (raw_dict.get("guardian_email") or "").strip() or None,
        }

        try:
            validated = RegisterSchema.model_validate(schema_payload)
            grade_level = (raw_dict.get("grade_level") or "").strip() or None

            # Validate grade_level if set of valid_grade_names is provided
            if valid_grade_names is not None and grade_level is not None:
                if grade_level not in valid_grade_names:
                    errors.append({
                        "row_number": row_num,
                        "error": f"grade_level: Invalid grade level '{grade_level}'. Must be one of: {sorted(list(valid_grade_names))}"
                    })
                    continue

            valid_dict = {
                "row_number": row_num,
                "email": validated.email,
                "password": validated.password,
                "first_name": validated.first_name,
                "last_name": validated.last_name,
                "role": validated.role,
                "grade_level": grade_level,
                "guardian_name": validated.guardian_name,
                "guardian_email": str(validated.guardian_email) if validated.guardian_email else None,
            }
            valid_rows.append(valid_dict)

        except ValidationError as err:
            err_msgs = []
            for e in err.errors():
                loc = "->".join(str(x) for x in e["loc"]) if e["loc"] else "row"
                err_msgs.append(f"{loc}: {e['msg']}")
            errors.append({
                "row_number": row_num,
                "error": " | ".join(err_msgs)
            })

    return {
        "valid_rows": valid_rows,
        "errors": errors
    }
