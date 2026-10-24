import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="Smart Library Management Assistant",
    page_icon="📚",
    layout="wide",
)

# Initialize session state for authentication
if "auth_token" not in st.session_state:
    st.session_state.auth_token = None
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None
if "messages" not in st.session_state:
    st.session_state.messages = []


def get_auth_headers() -> dict:
    """Return Bearer token headers if signed in."""
    if st.session_state.auth_token:
        return {"Authorization": f"Bearer {st.session_state.auth_token}"}
    return {}


# --- SIDEBAR: Authentication (Sign In / Sign Up / Demo Quick Login) ---
with st.sidebar:
    st.header("🔐 Library Authentication")

    if st.session_state.auth_user:
        u = st.session_state.auth_user
        st.success(f"Signed in as **{u['name']}**")
        st.markdown(
            f"- **User ID:** `{u['user_id']}`\n"
            f"- **Role:** `{u['role'].upper()}`\n"
            f"- **Dept:** {u['department']}"
        )
        if st.button("🚪 Sign Out", use_container_width=True):
            st.session_state.auth_token = None
            st.session_state.auth_user = None
            st.session_state.messages = []
            st.rerun()
    else:
        auth_mode = st.radio(
            "Account Access:",
            ["Sign In", "Create Account (Sign Up)", "Quick Demo Login"],
            horizontal=False,
        )

        if auth_mode == "Sign In":
            with st.form("signin_form"):
                identifier = st.text_input("User ID or Email", placeholder="e.g., STU001 or LIB001")
                password = st.text_input("Password", type="password", value="pass123", help="Default demo password: pass123")
                submit_signin = st.form_submit_button("Sign In", type="primary", use_container_width=True)
                if submit_signin:
                    try:
                        resp = requests.post(
                            f"{BACKEND_URL}/api/v1/auth/signin",
                            json={"identifier": identifier, "password": password},
                            timeout=5,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            st.session_state.auth_token = data["access_token"]
                            st.session_state.auth_user = data["user"]
                            st.rerun()
                        else:
                            st.error(resp.json().get("detail", "Sign in failed."))
                    except Exception as e:
                        st.error(f"Backend unreachable: {e}")

        elif auth_mode == "Create Account (Sign Up)":
            with st.form("signup_form"):
                new_uid = st.text_input("Choose User ID", placeholder="e.g., STU009")
                new_name = st.text_input("Full Name", placeholder="e.g., Abhinav Gangwar")
                new_email = st.text_input("University Email", placeholder="e.g., abhinav@mnit.ac.in")
                new_pass = st.text_input("Password", type="password", placeholder="Min 4 characters")
                new_role = st.selectbox("Role", ["student", "researcher", "faculty", "librarian"])
                new_dept = st.text_input("Department", value="Computer Science")
                new_interests = st.text_input("Research / Course Interests", value="Generative AI, Python, Machine Learning")
                submit_signup = st.form_submit_button("Create Account & Sign In", type="primary", use_container_width=True)

                if submit_signup:
                    if not new_uid or not new_name or not new_email or len(new_pass) < 4:
                        st.warning("Please fill all fields (password min 4 chars).")
                    else:
                        try:
                            resp = requests.post(
                                f"{BACKEND_URL}/api/v1/auth/signup",
                                json={
                                    "user_id": new_uid,
                                    "name": new_name,
                                    "email": new_email,
                                    "password": new_pass,
                                    "role": new_role,
                                    "department": new_dept,
                                    "interests": new_interests,
                                },
                                timeout=5,
                            )
                            if resp.status_code == 200:
                                data = resp.json()
                                st.session_state.auth_token = data["access_token"]
                                st.session_state.auth_user = data["user"]
                                st.success(data["message"])
                                st.rerun()
                            else:
                                st.error(resp.json().get("detail", "Registration failed."))
                        except Exception as e:
                            st.error(f"Backend error: {e}")

        else:
            st.caption("Instant 1-click login for Hackathon Judges:")
            demo_accounts = {
                "STU001 — Abhinav Gangwar (Student)": "STU001",
                "STU002 — Priya Nair (Researcher)": "STU002",
                "FAC001 — Dr. Rajesh Verma (Faculty)": "FAC001",
                "LIB001 — Meera Krishnan (Librarian Admin)": "LIB001",
            }
            chosen = st.selectbox("Select Demo Persona:", list(demo_accounts.keys()))
            if st.button("⚡ Sign In as Persona", type="primary", use_container_width=True):
                uid = demo_accounts[chosen]
                try:
                    resp = requests.post(
                        f"{BACKEND_URL}/api/v1/auth/signin",
                        json={"identifier": uid, "password": "pass123"},
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        st.session_state.auth_token = data["access_token"]
                        st.session_state.auth_user = data["user"]
                        st.rerun()
                except Exception as e:
                    st.error(f"Connection failed: {e}")

    st.divider()
    st.markdown("### 🛠️ Hackathon Controls")
    if st.button("🔄 Reset & Seed Database", use_container_width=True):
        try:
            resp = requests.post(f"{BACKEND_URL}/api/v1/seed", timeout=5)
            if resp.status_code == 200:
                st.success("Database seeded!")
            else:
                st.error(f"Error {resp.status_code}")
        except Exception as e:
            st.error(f"Connection failed: {e}")


# Main Header
st.title("📚 AI-Powered Smart Library Management Assistant")
st.caption("Intelligent Discovery, Research Assistance, Role-Based Circulation Control & Librarian Analytics")

if not st.session_state.auth_user:
    st.info("👈 Please **Sign In** or **Create an Account (Sign Up)** in the left sidebar to access the Smart Library portal.")
    st.stop()

current_user = st.session_state.auth_user
current_user_id = current_user["user_id"]
is_librarian = current_user["role"].lower() == "librarian"

# Navigation Tabs (Librarian gets Admin Controls & Analytics)
tab_labels = [
    "💬 AI Assistant Chat",
    "🔍 Catalog & Reserve",
    "📋 My Account & Circulation",
    "📊 Librarian Analytics & Admin",
]
tab1, tab2, tab3, tab4 = st.tabs(tab_labels)

# --- TAB 1: AI Assistant Chat ---
with tab1:
    st.header("Conversational Library Assistant")
    st.markdown(
        f"Authenticated as **{current_user['name']} (`{current_user_id}` — {current_user['role'].upper()})**. "
        "Ask about books, papers, reservations, renewals, or recommendations."
    )

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("trace_id"):
                st.caption(f"Trace ID: `{msg['trace_id']}` | Tools: `{', '.join(msg.get('tools_used', []))}`")

    if prompt := st.chat_input("e.g., Reserve BK-002 for me, or Recommend beginner resources for generative AI"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Executing deterministic library tools..."):
                try:
                    payload = {"user_id": current_user_id, "message": prompt}
                    res = requests.post(
                        f"{BACKEND_URL}/api/v1/chat",
                        json=payload,
                        headers=get_auth_headers(),
                        timeout=15,
                    )
                    if res.status_code == 200:
                        data = res.json()
                        st.markdown(data["answer"])
                        st.caption(
                            f"Trace ID: `{data['trace_id']}` | Outcome: `{data['outcome']}` | "
                            f"Tools: `{', '.join(data['tools_used']) or 'None'}`"
                        )
                        if data.get("cited_resources"):
                            st.info(f"📚 **Cited Resources:** {', '.join(data['cited_resources'])}")

                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": data["answer"],
                            "trace_id": data["trace_id"],
                            "tools_used": data["tools_used"],
                        })
                    else:
                        st.error(f"Error {res.status_code}: {res.text}")
                except Exception as err:
                    st.error(f"Failed to reach FastAPI backend: {err}")

# --- TAB 2: Catalog & Direct Reservation ---
with tab2:
    st.header("Semantic Catalog Search & Instant Reservation")
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        search_query = st.text_input("Search books, journals, papers, dissertations:", "Artificial Intelligence")
    with col2:
        diff_filter = st.selectbox("Difficulty", ["All", "beginner", "intermediate", "advanced"])
    with col3:
        type_filter = st.selectbox("Type", ["All", "book", "paper", "ebook", "dissertation"])

    if st.button("🔍 Search Catalog", type="primary"):
        params = {"q": search_query}
        if diff_filter != "All":
            params["difficulty"] = diff_filter
        if type_filter != "All":
            params["resource_type"] = type_filter

        try:
            resp = requests.get(f"{BACKEND_URL}/api/v1/catalog/search", params=params, timeout=5)
            if resp.status_code == 200:
                st.session_state["last_search_results"] = resp.json()
        except Exception as e:
            st.error(f"Search error: {e}")

    search_data = st.session_state.get("last_search_results")
    if search_data:
        if search_data.get("status") == "success":
            st.success(f"Found {search_data['count']} grounded catalog resources.")
            for item in search_data["results"]:
                code = item["resource_code"]
                with st.expander(f"[{code}] {item['title']} ({item['resource_type'].upper()}) — {item['available_copies']}/{item['total_copies']} Available", expanded=True):
                    c_info, c_act = st.columns([3, 1])
                    with c_info:
                        st.write(f"**Authors:** {item['authors']}")
                        st.write(f"**Subject:** {item['subject']} | **Level:** `{item['difficulty_level'].title()}`")
                        st.write(f"**Location:** {item['branch']} — Shelf `{item['shelf_location']}`")
                        st.caption(item.get("description", ""))
                    with c_act:
                        if st.button(f"📌 Reserve {code}", key=f"res_btn_{code}", use_container_width=True):
                            r_resp = requests.post(
                                f"{BACKEND_URL}/api/v1/circulation/reserve",
                                json={"user_id": current_user_id, "resource_code": code},
                                headers=get_auth_headers(),
                                timeout=5,
                            )
                            r_data = r_resp.json()
                            if r_data.get("status") == "success":
                                st.success(r_data.get("message", "Reserved! Check My Account tab."))
                            else:
                                st.warning(r_data.get("message", str(r_data)))
        else:
            st.warning("No matching resources found in authorized library sources (`not_found`).")

# --- TAB 3: My Account & Circulation (Persisted Loans, Reservations & Privacy Check) ---
with tab3:
    st.header("📋 Account Summary, Active Loans & Saved Reservations")

    col_left, col_right = st.columns([2, 1])
    with col_left:
        inspect_user_id = st.text_input(
            "Inspect Account User ID (Change to another ID like STU002 to test Privacy Refusal Guardrail):",
            value=current_user_id,
        )
    with col_right:
        st.markdown("#### Quick Reserve by Resource Code")
        quick_code = st.text_input("Resource Code (e.g., BK-002, BK-003)", placeholder="BK-002")
        if st.button("📌 Reserve Resource Now", type="primary", use_container_width=True):
            if quick_code.strip():
                r_resp = requests.post(
                    f"{BACKEND_URL}/api/v1/circulation/reserve",
                    json={"user_id": current_user_id, "resource_code": quick_code.strip().upper()},
                    headers=get_auth_headers(),
                    timeout=5,
                )
                r_data = r_resp.json()
                if r_data.get("status") == "success":
                    st.success(r_data.get("message", "Reservation saved!"))
                else:
                    st.warning(r_data.get("message", "Could not complete reservation."))

    st.divider()

    # Fetch live structured account summary from backend
    try:
        acc_resp = requests.get(
            f"{BACKEND_URL}/api/v1/account/{inspect_user_id.strip().upper()}",
            headers=get_auth_headers(),
            timeout=5,
        )
        if acc_resp.status_code == 200:
            acc_data = acc_resp.json()
            if acc_data.get("status") == "privacy_refusal":
                st.error(f"🛡️ **Privacy Guardrail Triggered (`privacy_refusal`):** {acc_data.get('message')}")
            elif acc_data.get("status") == "success":
                u_info = acc_data.get("user", {})
                k1, k2, k3 = st.columns(3)
                k1.metric("Account Holder", f"{u_info.get('name', inspect_user_id)} ({inspect_user_id})")
                k2.metric("Active Borrowed Loans", len(acc_data.get("active_loans", [])))
                k3.metric("Saved Reservations / Holds", len(acc_data.get("active_reservations", [])))

                st.subheader("📖 Active Borrowed Items")
                loans = acc_data.get("active_loans", [])
                if loans:
                    for loan in loans:
                        l_col1, l_col2 = st.columns([4, 1])
                        with l_col1:
                            st.markdown(
                                f"**[{loan['resource_code']}] {loan['title']}** — "
                                f"Due: `{loan['due_date']}` | Status: `{loan['status'].upper()}` | "
                                f"Renewals used: `{loan['renewals_used']}` | Fine: `${loan.get('fine_amount', 0.0):.2f}`"
                            )
                        with l_col2:
                            if st.button(f"🔄 Renew {loan['resource_code']}", key=f"renew_{loan['resource_code']}"):
                                ren_resp = requests.post(
                                    f"{BACKEND_URL}/api/v1/circulation/renew",
                                    json={"user_id": inspect_user_id, "resource_code": loan["resource_code"]},
                                    headers=get_auth_headers(),
                                    timeout=5,
                                )
                                ren_data = ren_resp.json()
                                if ren_data.get("status") == "success":
                                    st.success(ren_data.get("message", "Loan renewed!"))
                                    st.rerun()
                                else:
                                    st.warning(ren_data.get("message", "Renewal denied."))
                else:
                    st.info("No active borrowed items on this account.")

                st.subheader("📌 Active Reservations & Holds")
                reservations = acc_data.get("active_reservations", [])
                if reservations:
                    st.dataframe(reservations, use_container_width=True)
                else:
                    st.info("No active reservations yet. Reserve a book above or in the Catalog tab!")
            else:
                st.warning(acc_data.get("message", "Account not found."))
    except Exception as e:
        st.error(f"Error fetching account summary: {e}")

# --- TAB 4: Librarian Analytics & Admin Controls (Secured by RBAC) ---
with tab4:
    st.header("🛡️ Librarian Analytics & Admin Control Center")

    if not is_librarian:
        st.warning(
            f"🔒 **Restricted Access:** You are signed in as **{current_user['name']}** with role **`{current_user['role'].upper()}`**. "
            "Only users with the **`LIBRARIAN`** role (e.g., `LIB001` or a newly registered librarian account) can access Analytics and Admin Catalog Controls."
        )
    else:
        st.success(f"🔓 **Librarian Admin Mode Active** (`{current_user_id}` — {current_user['name']})")

        admin_sub1, admin_sub2, admin_sub3 = st.tabs([
            "📊 Demand & Waitlist Analytics",
            "➕ Add New Catalog Resource (Live Indexing)",
            "🗂️ Global Circulation & Hold Ledger",
        ])

        with admin_sub1:
            try:
                resp = requests.get(
                    f"{BACKEND_URL}/api/v1/analytics",
                    headers=get_auth_headers(),
                    timeout=5,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    kpis = data.get("kpis", {})
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Catalog Titles", kpis.get("total_catalog_titles", 0))
                    m2.metric("Active Loans", kpis.get("total_active_loans", 0))
                    m3.metric("Overdue Loans", kpis.get("overdue_loans_count", 0))
                    m4.metric("Waitlist Requests", kpis.get("active_waitlist_requests", 0))

                    st.subheader("📌 Longest Waitlists & High-Demand Titles")
                    waitlists = data.get("longest_waitlists", [])
                    if waitlists:
                        st.dataframe(waitlists, use_container_width=True)

                    st.subheader("📚 Subject Utilization & Demand")
                    subjects = data.get("subject_demand", [])
                    if subjects:
                        st.dataframe(subjects, use_container_width=True)

                    st.subheader("⚠️ Overdue Items & Fines")
                    overdues = data.get("overdue_items", [])
                    if overdues:
                        st.dataframe(overdues, use_container_width=True)
            except Exception as e:
                st.error(f"Error loading analytics: {e}")

        with admin_sub2:
            st.subheader("➕ Add New Book / Paper to Catalog (Instant Vector Indexing)")
            with st.form("admin_add_resource_form"):
                c1, c2 = st.columns(2)
                with c1:
                    r_code = st.text_input("Resource Code", placeholder="e.g., BK-050")
                    r_title = st.text_input("Title", placeholder="e.g., Building LLM Powered Applications")
                    r_authors = st.text_input("Authors", placeholder="e.g., Valentina Alto")
                    r_type = st.selectbox("Resource Type", ["book", "ebook", "paper", "dissertation"])
                    r_subject = st.text_input("Subject", value="Artificial Intelligence")
                with c2:
                    r_diff = st.selectbox("Difficulty Level", ["beginner", "intermediate", "advanced"])
                    r_branch = st.text_input("Branch", value="Central Library")
                    r_shelf = st.text_input("Shelf Location", value="AI-310")
                    r_total = st.number_input("Total Copies", min_value=1, value=4)
                    r_avail = st.number_input("Available Copies", min_value=0, value=4)
                r_desc = st.text_area("Description / Abstract", value="Practical guide to grounding LLMs, RAG, and enterprise agents.")
                submit_res = st.form_submit_button("Add Resource & Index Live", type="primary")

                if submit_res:
                    resp = requests.post(
                        f"{BACKEND_URL}/api/v1/admin/resources",
                        json={
                            "resource_code": r_code,
                            "title": r_title,
                            "authors": r_authors,
                            "resource_type": r_type,
                            "subject": r_subject,
                            "difficulty_level": r_diff,
                            "branch": r_branch,
                            "shelf_location": r_shelf,
                            "total_copies": int(r_total),
                            "available_copies": int(r_avail),
                            "description": r_desc,
                        },
                        headers=get_auth_headers(),
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        st.success(resp.json()["message"])
                    else:
                        st.error(resp.json().get("detail", "Failed to add resource."))

        with admin_sub3:
            st.subheader("🗂️ All Active Loans & Reservations Across University")
            circ_resp = requests.get(
                f"{BACKEND_URL}/api/v1/admin/circulation",
                headers=get_auth_headers(),
                timeout=5,
            )
            if circ_resp.status_code == 200:
                c_data = circ_resp.json()
                st.write("**All Active Loans:**")
                st.dataframe(c_data.get("loans", []), use_container_width=True)
                st.write("**All Active Reservations / Holds:**")
                st.dataframe(c_data.get("reservations", []), use_container_width=True)
