from pathlib import Path

from receipt_bot.models import Category, ExpenseRow
from receipt_bot.sheets.excel_store import ExcelExpenseStore


def test_append_and_sum(tmp_path: Path):
    path = tmp_path / "expenses.xlsx"
    store = ExcelExpenseStore(path)
    store.ensure_workbook()
    row = ExpenseRow(
        telegram_user_id=42,
        telegram_username="shane",
        receipt_file_id="abc",
        vendor="Uber",
        expense_date="2026-07-15",
        currency="USD",
        total=80.0,
        tax=0.0,
        category=Category.TRAVEL,
        notes="airport",
        confidence=0.95,
        needs_review=False,
        message_id=1001,
        threshold=500,
    )
    store.append_expense(row)
    store.append_expense(row)  # idempotent by message id
    assert store.sum_total(user_id=42, category="Travel") == 80.0
    assert store.find_by_message_id(1001) is not None
    recent = store.list_recent(5, user_id=42)
    assert len(recent) == 1
