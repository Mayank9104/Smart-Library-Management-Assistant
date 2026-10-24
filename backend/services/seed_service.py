from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from backend.models import Loan, Reservation, Resource, User


def seed_initial_data(db: Session) -> dict:
    """Idempotently seed the SQLite database with realistic university library data."""
    if db.query(User).count() > 0:
        return {"status": "already_seeded", "users": db.query(User).count(), "resources": db.query(Resource).count()}

    now = datetime.now(timezone.utc)

    # 1. Seed Users (Students, Researcher, Faculty, Librarian)
    users = [
        User(
            user_id="STU001",
            name="Abhinav Gangwar",
            email="abhinav@university.edu",
            role="student",
            department="Data Science",
            interests="python, machine learning, generative ai, data science",
        ),
        User(
            user_id="STU002",
            name="Priya Nair",
            email="priya@university.edu",
            role="researcher",
            department="Artificial Intelligence",
            interests="retrieval-augmented generation, natural language processing, transformers, deep learning",
        ),
        User(
            user_id="FAC001",
            name="Dr. Rajesh Verma",
            email="rverma@university.edu",
            role="faculty",
            department="Computer Science",
            interests="algorithms, distributed systems, artificial intelligence",
        ),
        User(
            user_id="LIB001",
            name="Meera Krishnan",
            email="meera.lib@university.edu",
            role="librarian",
            department="Central Library Operations",
            interests="catalog management, circulation analytics, acquisitions",
        ),
    ]
    db.add_all(users)
    db.flush()

    # 2. Seed Catalog Resources (Books, Papers, E-Books, Dissertations)
    resources = [
        Resource(
            resource_code="BK-001",
            title="Python Crash Course: A Hands-On, Project-Based Introduction to Programming",
            authors="Eric Matthes",
            resource_type="book",
            subject="Python Programming",
            difficulty_level="beginner",
            description="A fast-paced, beginner-friendly introduction to Python programming covering fundamentals, data analysis, and web applications.",
            publication_year=2023,
            branch="Central Library",
            shelf_location="CS-101",
            total_copies=4,
            available_copies=3,
        ),
        Resource(
            resource_code="BK-002",
            title="Artificial Intelligence: A Modern Approach",
            authors="Stuart Russell, Peter Norvig",
            resource_type="book",
            subject="Artificial Intelligence",
            difficulty_level="intermediate",
            description="The authoritative textbook on Artificial Intelligence covering search, knowledge representation, machine learning, and robotics.",
            publication_year=2021,
            branch="Central Library",
            shelf_location="AI-201",
            total_copies=2,
            available_copies=0,  # Currently checked out -> great for testing waitlist & availability!
        ),
        Resource(
            resource_code="BK-003",
            title="Hands-On Machine Learning with Scikit-Learn, Keras, and TensorFlow",
            authors="Aurélien Géron",
            resource_type="book",
            subject="Machine Learning",
            difficulty_level="beginner",
            description="Beginner-friendly practical guide to building intelligent machine learning and deep learning systems using Python.",
            publication_year=2022,
            branch="Central Library",
            shelf_location="DS-104",
            total_copies=3,
            available_copies=2,
        ),
        Resource(
            resource_code="EB-001",
            title="Introduction to Generative AI and Large Language Models",
            authors="Sinan Ozdemir",
            resource_type="ebook",
            subject="Generative AI",
            difficulty_level="beginner",
            description="Accessible e-book covering foundational concepts in Generative AI, prompt engineering, embeddings, and RAG architectures.",
            publication_year=2024,
            branch="Digital Portal",
            shelf_location="ONLINE-EBOOK",
            digital_url="https://library.university.edu/ebooks/EB-001",
            total_copies=10,
            available_copies=10,
        ),
        Resource(
            resource_code="PR-001",
            title="Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            authors="Patrick Lewis, Ethan Perez, Aleksandra Piktus, et al.",
            resource_type="paper",
            subject="Artificial Intelligence",
            difficulty_level="advanced",
            description="Foundational research paper introducing Retrieval-Augmented Generation (RAG) combining parametric memory with non-parametric vector indexes.",
            publication_year=2020,
            branch="University Research Archive",
            shelf_location="REPO-RAG-01",
            digital_url="https://library.university.edu/papers/PR-001",
            total_copies=5,
            available_copies=5,
        ),
        Resource(
            resource_code="PR-002",
            title="Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection",
            authors="Akari Asai, Zeqiu Wu, Yizhong Wang, et al.",
            resource_type="paper",
            subject="Artificial Intelligence",
            difficulty_level="advanced",
            description="Research paper comparing adaptive retrieval and self-reflection tokens to improve factuality and citation accuracy in RAG models.",
            publication_year=2023,
            branch="University Research Archive",
            shelf_location="REPO-RAG-02",
            digital_url="https://library.university.edu/papers/PR-002",
            total_copies=5,
            available_copies=5,
        ),
        Resource(
            resource_code="DS-001",
            title="Practical Statistics for Data Scientists",
            authors="Peter Bruce, Andrew Bruce, Peter Gedeck",
            resource_type="book",
            subject="Data Science",
            difficulty_level="beginner",
            description="Essential statistical concepts, exploratory data analysis, and sampling distributions tailored for Data Science semester courses.",
            publication_year=2020,
            branch="Engineering Branch",
            shelf_location="STAT-302",
            total_copies=3,
            available_copies=2,
        ),
        Resource(
            resource_code="TH-001",
            title="Domain-Specific Vector Search Optimization in Academic Libraries",
            authors="Ananya Deshmukh",
            resource_type="dissertation",
            subject="Data Science",
            difficulty_level="advanced",
            description="Doctoral dissertation evaluating dense passage retrieval, ChromaDB indexing, and hybrid search in university repositories.",
            publication_year=2025,
            branch="University Research Archive",
            shelf_location="THESIS-501",
            digital_url="https://library.university.edu/theses/TH-001",
            total_copies=2,
            available_copies=2,
        ),
    ]
    db.add_all(resources)
    db.flush()

    user_map = {u.user_id: u for u in users}
    res_map = {r.resource_code: r for r in resources}

    # 3. Seed Active & Overdue Loans
    loans = [
        # STU001 has 1 active book due in 3 days (renewable) and 1 overdue book with a fine
        Loan(
            user_id=user_map["STU001"].id,
            resource_id=res_map["BK-003"].id,
            borrowed_at=now - timedelta(days=11),
            due_date=now + timedelta(days=3),
            renewal_count=0,
            max_renewals=2,
            fine_amount=0.0,
            status="borrowed",
        ),
        Loan(
            user_id=user_map["STU001"].id,
            resource_id=res_map["BK-002"].id,
            borrowed_at=now - timedelta(days=20),
            due_date=now - timedelta(days=6),
            renewal_count=2,
            max_renewals=2,
            fine_amount=30.0,  # Overdue fine
            status="overdue",
        ),
        # STU002 holds the second copy of BK-002
        Loan(
            user_id=user_map["STU002"].id,
            resource_id=res_map["BK-002"].id,
            borrowed_at=now - timedelta(days=5),
            due_date=now + timedelta(days=9),
            renewal_count=0,
            max_renewals=2,
            fine_amount=0.0,
            status="borrowed",
        ),
    ]
    db.add_all(loans)

    # 4. Seed Waitlist Reservations (BK-002 has 0 available copies and a waitlist)
    reservations = [
        Reservation(
            user_id=user_map["FAC001"].id,
            resource_id=res_map["BK-002"].id,
            status="active",
            waitlist_position=1,
            trace_id="TRC-SEED-001",
        )
    ]
    db.add_all(reservations)
    db.commit()

    return {
        "status": "seeded",
        "users": len(users),
        "resources": len(resources),
        "loans": len(loans),
        "reservations": len(reservations),
    }
