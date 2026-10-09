import io
from datetime import date

import pytest

from app.models.enums import CategoryKind
from app.repositories.transactions import duplicate_key
from app.services.importer.csv_import import (
    CategoryRef,
    CsvFormatError,
    parse_amount,
    parse_date,
    preview_csv,
)
from app.services.ml.categorizer import categorize

PREVIEW = "/api/transactions/import/preview"
COMMIT = "/api/transactions/import"
TODAY = date(2026, 10, 8)

CATS = [
    CategoryRef(1, "Groceries", CategoryKind.ESSENTIAL),
    CategoryRef(2, "Food & Dining", CategoryKind.DISCRETIONARY),
    CategoryRef(3, "Other", CategoryKind.DISCRETIONARY),
    CategoryRef(4, "Salary", CategoryKind.INCOME),
    CategoryRef(5, "Other Income", CategoryKind.INCOME),
    CategoryRef(6, "Transport", CategoryKind.ESSENTIAL),
    CategoryRef(7, "Shopping", CategoryKind.DISCRETIONARY),
]


def _preview(text: str, existing: set | None = None) -> dict:
    return preview_csv(
        text.encode(),
        CATS,
        lambda d, m, t: categorize(d, m, t),
        existing or set(),
        duplicate_key,
        today=TODAY,
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-09-01", date(2026, 9, 1)),
        ("01/09/2026", date(2026, 9, 1)),  # Indian day-first
        ("01-09-2026", date(2026, 9, 1)),
        ("01-Sep-2026", date(2026, 9, 1)),
        ("01.09.2026", date(2026, 9, 1)),
        ("01-09-26", date(2026, 9, 1)),
        ("01-Sep-26", date(2026, 9, 1)),
        ("2026-09-01 10:22:00", date(2026, 9, 1)),  # time part ignored
        ("2026-09-01T10:22:00", date(2026, 9, 1)),
        ("01/09/2026 10:22", date(2026, 9, 1)),
        ("2026/13/45", None),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1,30,000", 130000),
        ("₹ 2,500.50", 2500.5),
        ("-450", -450),
        ("(300)", -300),
        ("abc", None),
        ("1,250.00 Dr", -1250),
        ("50,000.00 CR", 50000),
        ("nan", None),  # would put NaN into the JSON response
        ("inf", None),
        ("1e400", None),
    ],
)
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def test_valid_rows_with_types_and_categories():
    out = _preview(
        "date,description,amount,type,category\n"
        "2026-09-01,DMART,1200,expense,Groceries\n"
        "2026-09-01,SALARY ACME,95000,income,\n"
    )
    rows = out["rows"]
    assert [r["status"] for r in rows] == ["ok", "ok"]
    assert rows[0]["transaction"]["category_id"] == 1
    assert rows[0]["transaction"]["category_source"] == "import"
    assert rows[1]["category_name"] == "Salary"
    assert rows[1]["transaction"]["category_source"] == "rule"
    assert out["summary"] == {
        "total": 2, "ok": 2, "warning": 0, "duplicate": 0, "error": 0, "importable": 2
    }  # fmt: skip


def test_row_level_errors_do_not_block_good_rows():
    out = _preview(
        "date,description,amount,type\n"
        "2026-09-01,GOOD,100,expense\n"
        ",NO DATE,100,expense\n"
        "31/02/2026,BAD DATE,100,expense\n"
        "2026-09-01,BAD AMOUNT,12abc,expense\n"
        "2026-09-01,,100,expense\n"
        "2026-12-25,FUTURE,100,expense\n"
        "2026-09-01,ZERO,0,expense\n"
        "2026-09-01,BAD TYPE,100,refund\n"
    )
    rows = out["rows"]
    assert rows[0]["status"] == "ok"
    assert all(r["status"] == "error" and r["errors"] for r in rows[1:])
    assert [r["row"] for r in rows] == list(range(2, 10))  # file line numbers
    assert out["summary"]["importable"] == 1


def test_bank_debit_credit_format_with_aliases():
    out = _preview(
        "Txn Date,Narration,Withdrawal Amt,Deposit Amt\n"
        '05/09/2026,UPI/9921/UBER TRIP,"1,250.00",\n'
        '06/09/2026,NEFT SAL ACME,,"95,000.00"\n'
        "07/09/2026,BOTH,10,20\n"
    )
    first, second, third = out["rows"]
    assert first["transaction"]["type"] == "expense" and first["transaction"]["amount"] == 1250
    assert first["category_name"] == "Transport"
    assert second["transaction"]["type"] == "income" and second["category_name"] == "Salary"
    assert third["status"] == "error"


def test_real_bank_export_quirks():
    """Account info above the header, ';' delimiter, 0.00 / '-' in the unused column."""
    out = _preview(
        "Account Number;0012345678\n"
        "Statement From;01/09/2026 To 30/09/2026\n"
        "\n"
        "Txn Date;Narration;Withdrawal Amt;Deposit Amt;Balance\n"
        "05/09/2026;UPI/9921/UBER TRIP;1,250.00;0.00;48,750.00\n"
        "06/09/2026;NEFT SAL ACME;-;95,000.00;1,43,750.00\n"
        "07/09/2026;HUGE;200000000000;0.00;0\n"
    )
    first, second, third = out["rows"]
    assert first["row"] == 5 and first["transaction"]["amount"] == 1250
    assert first["transaction"]["type"] == "expense"
    assert second["transaction"]["type"] == "income" and second["transaction"]["amount"] == 95000
    assert third["errors"] == ["Amount is too large."]  # caught here, not at commit


def test_type_inferred_from_sign_is_flagged():
    out = _preview("date,description,amount\n2026-09-01,ZOMATO,-350\n2026-09-02,REFUND,200\n")
    first, second = out["rows"]
    assert first["transaction"]["type"] == "expense" and first["transaction"]["amount"] == 350
    assert second["transaction"]["type"] == "income"
    assert first["status"] == "warning" and "inferred" in first["warnings"][0]


def test_unknown_or_mismatched_category_is_auto_categorized_with_warning():
    out = _preview(
        "date,description,amount,type,category\n"
        "2026-09-01,ZOMATO ORDER,300,expense,Fooood\n"
        "2026-09-01,ZOMATO ORDER 2,300,expense,Salary\n"
    )
    for row in out["rows"]:
        assert row["status"] == "warning"
        assert row["category_name"] == "Food & Dining"
        assert "Auto-categorized as Food & Dining" in row["warnings"][0]


def test_duplicates_within_file_and_against_existing():
    existing = {duplicate_key(date(2026, 9, 1), 500, "expense", "AMAZON PURCHASE")}
    out = _preview(
        "date,description,amount,type\n"
        "2026-09-01,amazon purchase,500.00,expense\n"
        "2026-09-02,BLINKIT,250,expense\n"
        "2026-09-02,BLINKIT,250,expense\n",
        existing,
    )
    assert [r["duplicate_of"] for r in out["rows"]] == ["existing", None, "file"]
    assert out["summary"]["duplicate"] == 2


def test_different_reference_numbers_are_not_duplicates():
    out = _preview(
        "date,description,amount,type\n"
        "2026-09-02,UPI/1111/ZOMATO,250,expense\n"
        "2026-09-02,UPI/2222/ZOMATO,250,expense\n"
    )
    assert [r["duplicate_of"] for r in out["rows"]] == [None, None]


@pytest.mark.parametrize(
    "text,message",
    [
        ("", "empty"),
        ("date,description,amount\n", "no data rows"),
        ("date,amount\n2026-09-01,5\n", "missing"),
        ("description,amount\nX,5\n", "missing"),
        ("date,description\n2026-09-01,X\n", "missing"),
    ],
)
def test_unusable_files(text, message):
    with pytest.raises(CsvFormatError, match=message):
        _preview(text)


# ---------------- API ----------------


def _upload(api, text: str, filename: str = "statement.csv"):
    return api.post(
        PREVIEW,
        data={"file": (io.BytesIO(text.encode()), filename)},
        content_type="multipart/form-data",
    )


def test_preview_then_commit_imports_selected_rows(api):
    preview = _upload(
        api,
        "date,description,amount,type\n2026-09-01,DMART,1200,expense\n2026-09-02,UBER,300,expense\n"
        "bad,ROW,1,expense\n",
    ).get_json()["data"]
    rows = [r["transaction"] for r in preview["rows"] if r["status"] in ("ok", "warning")]
    assert len(rows) == 2

    res = api.post(COMMIT, json={"transactions": rows})
    assert res.status_code == 201 and res.get_json()["data"]["imported"] == 2
    listing = api.get("/api/transactions").get_json()
    assert listing["meta"]["total"] == 2

    # Re-uploading the same file now flags both rows as duplicates of existing data.
    again = _upload(api, "date,description,amount,type\n2026-09-01,DMART,1200,expense\n")
    assert again.get_json()["data"]["rows"][0]["duplicate_of"] == "existing"


def test_preview_rejects_missing_or_non_csv_file(api):
    assert api.post(PREVIEW, data={}, content_type="multipart/form-data").status_code == 400
    assert _upload(api, "x", filename="statement.xlsx").status_code == 400


def test_preview_reports_unusable_file_as_422(api):
    res = _upload(api, "foo,bar\n1,2\n")
    assert res.status_code == 422
    assert res.get_json()["error"]["code"] == "INVALID_CSV"
    assert "date" in res.get_json()["error"]["details"]["missing"]


def test_commit_revalidates_rows(api, category_ids):
    good = {
        "date": "2026-09-01",
        "amount": 100,
        "type": "income",
        "description": "X",
        "category_id": category_ids["Groceries"],  # expense category on an income row
    }
    assert api.post(COMMIT, json={"transactions": [good]}).status_code == 400
    assert api.post(COMMIT, json={"transactions": []}).status_code == 400
    bad_amount = good | {"amount": -1, "category_id": category_ids["Salary"]}
    assert api.post(COMMIT, json={"transactions": [bad_amount]}).status_code == 400
    assert api.get("/api/transactions").get_json()["meta"]["total"] == 0  # nothing partial


def test_upload_over_size_limit_rejected(api):
    res = _upload(api, "date,description,amount\n" + "2026-09-01,X,1\n" * 200_000)  # ~3 MB
    assert res.status_code == 413
    assert res.get_json()["error"]["code"] == "REQUEST_ENTITY_TOO_LARGE"


def test_generated_sample_statement_imports_cleanly(api):
    from app.seed.sample_csv import sample_statement

    text = sample_statement(months=3, today=date(2026, 10, 9))
    assert text.splitlines()[0] == "Txn Date,Narration,Withdrawal Amt,Deposit Amt"
    preview = _upload(api, text).get_json()["data"]
    assert preview["summary"]["error"] == 0
    assert preview["summary"]["total"] == len(text.splitlines()) - 1
    categories = {r["category_name"] for r in preview["rows"]}
    assert {"Salary", "Housing", "Groceries", "Investment"} <= categories


def test_sample_statement_download(api, client):
    res = api.get("/api/transactions/import/sample")
    assert res.status_code == 200 and res.mimetype == "text/csv"
    assert "attachment" in res.headers["Content-Disposition"]
    assert res.get_data(as_text=True).startswith("Txn Date,Narration")
    assert client.get("/api/transactions/import/sample").status_code == 401
