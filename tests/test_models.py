from receipt_bot.models import Category, ExpenseRow


def test_category_coerce():
    assert Category.coerce("food") == Category.FOOD
    assert Category.coerce("Travel") == Category.TRAVEL


def test_over_500_false():
    row = ExpenseRow(
        telegram_user_id=1,
        telegram_username="u",
        receipt_file_id="f",
        vendor="Starbucks",
        expense_date="2026-08-01",
        currency="USD",
        total=12.5,
        tax=1.0,
        category=Category.FOOD,
        notes="latte",
        confidence=0.9,
        needs_review=False,
        message_id=99,
        threshold=500,
    )
    assert row.over_500 is False
    assert len(row.to_excel_row()) == 15


def test_over_500_true():
    row = ExpenseRow(
        telegram_user_id=1,
        telegram_username="u",
        receipt_file_id="f",
        vendor="X",
        expense_date="2026-08-01",
        currency="USD",
        total=500.01,
        tax=0,
        category=Category.TRAVEL,
        notes="",
        confidence=0.8,
        needs_review=False,
        message_id=1,
        threshold=500,
    )
    assert row.over_500 is True
