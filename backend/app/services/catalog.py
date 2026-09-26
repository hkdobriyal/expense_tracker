"""Default category tree created for every new user (they can edit or add their own)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Category

EXPENSE_CATEGORIES: list[tuple[str, str, str, list[str]]] = [
    ("Food", "#f7b267", "utensils", ["Groceries", "Restaurants", "Food delivery", "Coffee & snacks"]),
    ("Transport", "#70d6ff", "car", ["Fuel", "Cab & auto", "Metro & bus", "Train", "Flights", "Parking & tolls"]),
    ("Housing", "#b29bff", "home", ["Rent", "Maintenance", "Home repairs", "Furnishing"]),
    ("Bills & utilities", "#8ae6ff", "zap", ["Electricity", "Water", "Gas", "Internet", "Mobile recharge", "DTH & cable"]),
    ("Shopping", "#ff8fab", "shopping-bag", ["Clothing", "Electronics", "Household", "Online shopping"]),
    ("Health", "#7ef0c2", "heart-pulse", ["Pharmacy", "Doctor & hospital", "Health insurance", "Fitness"]),
    ("Entertainment", "#ffd8a8", "clapperboard", ["Movies & events", "Streaming", "Games", "Hobbies"]),
    ("Education", "#95d5b2", "graduation-cap", ["Tuition & fees", "Courses", "Books"]),
    ("Personal & family", "#c8b6ff", "users", ["Personal care", "Gifts & donations", "Childcare", "Pets", "Household help"]),
    ("Travel", "#a8dadc", "plane", ["Hotels", "Holidays", "Visa & forex"]),
    ("Finance", "#ff9d66", "landmark", ["Bank charges", "Loan EMI", "Credit card interest", "Taxes", "Life insurance"]),
    ("Other", "#8a94a6", "circle", []),
]

INCOME_CATEGORIES: list[tuple[str, str, str]] = [
    ("Salary", "#7ef0c2", "briefcase"),
    ("Freelance & business", "#8ae6ff", "laptop"),
    ("Interest", "#b29bff", "percent"),
    ("Dividends & capital gains", "#ffd8a8", "trending-up"),
    ("Rental income", "#70d6ff", "building"),
    ("Refunds & cashback", "#95d5b2", "rotate-ccw"),
    ("Gifts received", "#ff8fab", "gift"),
    ("Other income", "#8a94a6", "plus-circle"),
]


def seed_default_categories(db: Session, user_id: int) -> None:
    for name, color, icon, children in EXPENSE_CATEGORIES:
        parent = Category(user_id=user_id, name=name, kind="expense", color=color, icon=icon)
        db.add(parent)
        db.flush()
        for child in children:
            db.add(Category(user_id=user_id, name=child, kind="expense", color=color, icon=icon, parent_id=parent.id))
    for name, color, icon in INCOME_CATEGORIES:
        db.add(Category(user_id=user_id, name=name, kind="income", color=color, icon=icon))
    db.flush()


# Keyword → "Parent/Child" hints used to categorise statement/SMS narrations when
# no user rule matches. Deliberately small and India-specific; user rules win.
KEYWORD_HINTS: list[tuple[str, str]] = [
    ("swiggy", "Food/Food delivery"), ("zomato", "Food/Food delivery"), ("eatsure", "Food/Food delivery"),
    ("zepto", "Food/Groceries"), ("blinkit", "Food/Groceries"), ("instamart", "Food/Groceries"), ("bigbasket", "Food/Groceries"),
    ("dmart", "Food/Groceries"), ("reliance fresh", "Food/Groceries"), ("country delight", "Food/Groceries"),
    ("starbucks", "Food/Coffee & snacks"), ("chai point", "Food/Coffee & snacks"), ("cafe coffee day", "Food/Coffee & snacks"),
    ("mcdonald", "Food/Restaurants"), ("domino", "Food/Restaurants"), ("kfc", "Food/Restaurants"), ("burger king", "Food/Restaurants"),
    ("uber", "Transport/Cab & auto"), ("ola ", "Transport/Cab & auto"), ("rapido", "Transport/Cab & auto"),
    ("irctc", "Transport/Train"), ("indigo", "Transport/Flights"), ("air india", "Transport/Flights"), ("metro", "Transport/Metro & bus"),
    ("fastag", "Transport/Parking & tolls"), ("hpcl", "Transport/Fuel"), ("iocl", "Transport/Fuel"), ("bpcl", "Transport/Fuel"),
    ("petrol", "Transport/Fuel"), ("amazon", "Shopping/Online shopping"), ("flipkart", "Shopping/Online shopping"),
    ("myntra", "Shopping/Clothing"), ("ajio", "Shopping/Clothing"), ("nykaa", "Personal & family/Personal care"),
    ("croma", "Shopping/Electronics"), ("reliance digital", "Shopping/Electronics"),
    ("netflix", "Entertainment/Streaming"), ("spotify", "Entertainment/Streaming"), ("hotstar", "Entertainment/Streaming"),
    ("prime video", "Entertainment/Streaming"), ("youtube", "Entertainment/Streaming"), ("bookmyshow", "Entertainment/Movies & events"),
    ("pvr", "Entertainment/Movies & events"), ("apollo", "Health/Pharmacy"), ("pharmeasy", "Health/Pharmacy"), ("1mg", "Health/Pharmacy"),
    ("netmeds", "Health/Pharmacy"), ("cult.fit", "Health/Fitness"), ("practo", "Health/Doctor & hospital"),
    ("bescom", "Bills & utilities/Electricity"), ("tneb", "Bills & utilities/Electricity"), ("mahadiscom", "Bills & utilities/Electricity"),
    ("tata power", "Bills & utilities/Electricity"), ("electricity", "Bills & utilities/Electricity"),
    ("airtel", "Bills & utilities/Mobile recharge"), ("jio", "Bills & utilities/Mobile recharge"), ("broadband", "Bills & utilities/Internet"),
    ("act fibernet", "Bills & utilities/Internet"), ("igl", "Bills & utilities/Gas"), ("tata play", "Bills & utilities/DTH & cable"),
    ("rent", "Housing/Rent"), ("maintenance", "Housing/Maintenance"), ("udemy", "Education/Courses"), ("coursera", "Education/Courses"),
    ("emi", "Finance/Loan EMI"), ("lic", "Finance/Life insurance"), ("salary", "Salary"), ("payroll", "Salary"),
    ("interest", "Interest"), ("dividend", "Dividends & capital gains"), ("cashback", "Refunds & cashback"), ("refund", "Refunds & cashback"),
]
