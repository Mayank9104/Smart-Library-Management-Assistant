from typing import Optional
from langchain_core.tools import tool
from sqlalchemy.orm import Session

from backend.db.vector_store import semantic_catalog_search
from backend.services.analytics_service import get_librarian_analytics_report
from backend.services.library_service import (
    check_resource_availability,
    get_personalized_recommendations,
    get_user_account_summary,
    renew_borrowed_loan,
    reserve_library_resource,
)


def build_library_tools(db: Session, acting_user_id: str, tracker: dict) -> list:
    """
    Create deterministic LangChain @tool functions bound to the current DB session
    and authenticated `acting_user_id`. Automatically tracks invoked tools and cited sources.
    """

    def _record_citations(payload: dict) -> None:
        if "resource_code" in payload and payload["resource_code"]:
            tracker["cited_resources"].add(payload["resource_code"])
        for item in payload.get("results", []):
            if "resource_code" in item:
                tracker["cited_resources"].add(item["resource_code"])
        for item in payload.get("recommendations", []):
            if "resource_code" in item:
                tracker["cited_resources"].add(item["resource_code"])
        for item in payload.get("borrowed_items", []):
            if "resource_code" in item:
                tracker["cited_resources"].add(item["resource_code"])

    @tool
    def semantic_search_tool(
        query: str,
        difficulty_level: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> dict:
        """
        Search authorized books, research papers, e-books, and dissertations using semantic search.
        Returns ranked results with resource_code citations or 'not_found' if absent.
        """
        tracker["tools_used"].append("semantic_search_tool")
        res = semantic_catalog_search(
            db=db,
            query=query,
            difficulty_level=difficulty_level,
            resource_type=resource_type,
        )
        if res.get("status") == "not_found":
            tracker["outcome"] = "not_found"
        _record_citations(res)
        return res

    @tool
    def check_availability_tool(resource_identifier: str) -> dict:
        """
        Check real-time availability, branch, shelf_location, and waitlist count
        for a specific book or resource by title or resource_code (e.g., 'BK-002').
        """
        tracker["tools_used"].append("check_availability_tool")
        res = check_resource_availability(db=db, identifier=resource_identifier)
        if res.get("status") == "not_found":
            tracker["outcome"] = "not_found"
        _record_citations(res)
        return res

    @tool
    def reserve_resource_tool(resource_identifier: str) -> dict:
        """
        Place an authorized hold or waitlist reservation on a library resource
        for the currently authenticated user. Returns a confirmation and trace_id.
        """
        tracker["tools_used"].append("reserve_resource_tool")
        res = reserve_library_resource(
            db=db,
            acting_user_id=acting_user_id,
            resource_identifier=resource_identifier,
        )
        if res.get("status") == "not_found":
            tracker["outcome"] = "not_found"
        _record_citations(res)
        return res

    @tool
    def renew_loan_tool(resource_identifier: str) -> dict:
        """
        Renew a borrowed book or resource for the currently authenticated user.
        """
        tracker["tools_used"].append("renew_loan_tool")
        res = renew_borrowed_loan(
            db=db,
            acting_user_id=acting_user_id,
            resource_identifier=resource_identifier,
        )
        if res.get("status") in ("denied", "not_found"):
            tracker["outcome"] = res.get("status")
        _record_citations(res)
        return res

    @tool
    def account_summary_tool(target_user_id: Optional[str] = None) -> dict:
        """
        Retrieve borrowed items, due dates, renewability, and fines.
        Enforces strict privacy: students/faculty can only view their own account.
        """
        tracker["tools_used"].append("account_summary_tool")
        res = get_user_account_summary(
            db=db,
            acting_user_id=acting_user_id,
            target_user_id=target_user_id or acting_user_id,
        )
        if res.get("status") == "access_denied":
            tracker["outcome"] = "denied"
        _record_citations(res)
        return res

    @tool
    def recommendation_tool(
        topic: Optional[str] = None,
        difficulty_level: Optional[str] = None,
    ) -> dict:
        """
        Generate personalized, explainable resource recommendations aligned with the
        authenticated user's course department, research interests, and availability.
        """
        tracker["tools_used"].append("recommendation_tool")
        res = get_personalized_recommendations(
            db=db,
            user_id=acting_user_id,
            topic_override=topic,
            difficulty_level=difficulty_level,
        )
        _record_citations(res)
        return res

    @tool
    def librarian_analytics_tool() -> dict:
        """
        Retrieve circulation analytics, longest waitlists, subject utilization,
        and overdue trends for library planning.
        """
        tracker["tools_used"].append("librarian_analytics_tool")
        return get_librarian_analytics_report(db=db)

    return [
        semantic_search_tool,
        check_availability_tool,
        reserve_resource_tool,
        renew_loan_tool,
        account_summary_tool,
        recommendation_tool,
        librarian_analytics_tool,
    ]
