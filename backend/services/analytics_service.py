import pandas as pd
from sqlalchemy.orm import Session
from backend.models import Loan, Reservation, Resource


def get_librarian_analytics_report(db: Session) -> dict:
    """
    Use Pandas to analyze catalog utilization, longest waitlists,
    overdue trends, and subject demand gaps for librarian decision-making.
    """
    resources = db.query(Resource).all()
    loans = db.query(Loan).all()
    reservations = db.query(Reservation).filter(Reservation.status == "active").all()

    if not resources:
        return {"status": "empty", "message": "No catalog data available for analytics."}

    res_rows = [
        {
            "resource_id": r.id,
            "resource_code": r.resource_code,
            "title": r.title,
            "subject": r.subject,
            "resource_type": r.resource_type,
            "total_copies": r.total_copies,
            "available_copies": r.available_copies,
            "checked_out_copies": max(r.total_copies - r.available_copies, 0),
        }
        for r in resources
    ]
    df_res = pd.DataFrame(res_rows)

    # Waitlist aggregation via Pandas
    if reservations:
        df_wait = pd.DataFrame(
            [{"resource_id": r.resource_id, "waitlist_position": r.waitlist_position} for r in reservations]
        )
        wait_counts = df_wait.groupby("resource_id").size().reset_index(name="waitlist_count")
        df_res = df_res.merge(wait_counts, on="resource_id", how="left")
        df_res["waitlist_count"] = df_res["waitlist_count"].fillna(0).astype(int)
    else:
        df_res["waitlist_count"] = 0

    df_res["utilization_rate"] = (
        (df_res["checked_out_copies"] / df_res["total_copies"].replace(0, 1)) * 100
    ).round(1)

    # 1. Titles with longest waitlists / highest utilization
    longest_waitlists = (
        df_res[df_res["waitlist_count"] > 0]
        .sort_values(by=["waitlist_count", "utilization_rate"], ascending=False)[
            ["resource_code", "title", "subject", "available_copies", "total_copies", "waitlist_count"]
        ]
        .to_dict(orient="records")
    )

    # 2. Subject-level demand & catalog gaps
    subject_summary = (
        df_res.groupby("subject", as_index=False)
        .agg(
            total_titles=("resource_code", "count"),
            total_copies=("total_copies", "sum"),
            available_copies=("available_copies", "sum"),
            active_waitlists=("waitlist_count", "sum"),
            avg_utilization_pct=("utilization_rate", "mean"),
        )
        .sort_values(by="avg_utilization_pct", ascending=False)
    )
    subject_summary["avg_utilization_pct"] = subject_summary["avg_utilization_pct"].round(1)

    # 3. Overdue & circulation metrics
    overdue_loans = []
    total_fines = 0.0
    if loans:
        for ln in loans:
            total_fines += ln.fine_amount
            if ln.status == "overdue":
                overdue_loans.append(
                    {
                        "user_id": ln.user.user_id,
                        "resource_code": ln.resource.resource_code,
                        "title": ln.resource.title,
                        "due_date": ln.due_date.strftime("%Y-%m-%d"),
                        "fine_amount": ln.fine_amount,
                    }
                )

    return {
        "status": "success",
        "kpis": {
            "total_catalog_titles": int(len(df_res)),
            "total_physical_and_digital_copies": int(df_res["total_copies"].sum()),
            "total_active_loans": int(len(loans)),
            "overdue_loans_count": len(overdue_loans),
            "active_waitlist_requests": int(df_res["waitlist_count"].sum()),
            "total_outstanding_fines": round(total_fines, 2),
        },
        "longest_waitlists": longest_waitlists,
        "subject_demand": subject_summary.to_dict(orient="records"),
        "overdue_items": overdue_loans,
    }
