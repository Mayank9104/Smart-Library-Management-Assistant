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

# Sidebar User & Role Configuration
with st.sidebar:
    st.header("👤 Active User Context")
    user_options = {
        "Abhinav Gangwar (Student - Data Science)": "STU001",
        "Priya Nair (Researcher - AI)": "STU002",
        "Dr. Rajesh Verma (Faculty - CS)": "FAC001",
        "Meera Krishnan (Librarian)": "LIB001",
    }
    selected_user_label = st.selectbox("Authenticate As:", list(user_options.keys()))
    current_user_id = user_options[selected_user_label]

    st.divider()
    st.markdown("### 🛠️ Hackathon Controls")
    if st.button("🔄 Reset & Seed Database"):
        try:
            resp = requests.post(f"{BACKEND_URL}/api/v1/seed", timeout=5)
            if resp.status_code == 200:
                st.success("Database seeded successfully!")
            else:
                st.error(f"Error {resp.status_code}")
        except Exception as e:
            st.error(f"Connection failed: {e}")

    st.markdown("---")
    st.caption("HCLTech Future Ready AI Engineer Hackathon Prototype")

# Main Title Header
st.title("📚 AI-Powered Smart Library Management Assistant")
st.caption("Intelligent Discovery, Research Assistance, Circulation Control & Analytics")

# Multi-Tab Layout
tab1, tab2, tab3, tab4 = st.tabs([
    "💬 AI Assistant Chat",
    "🔍 Catalog & Discovery",
    "📋 Account & Circulation",
    "📊 Librarian Analytics",
])

# --- TAB 1: AI Assistant Chat ---
with tab1:
    st.header("Conversational Library Assistant")
    st.markdown(
        "Ask questions about books, papers, reserves, renewals, or policies. "
        "Grounded in verified catalog tools with zero hallucinations."
    )

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("trace_id"):
                st.caption(f"Trace ID: `{msg['trace_id']}` | Tools: {', '.join(msg.get('tools_used', []))}")

    if prompt := st.chat_input("e.g., Recommend beginner resources for learning generative AI that are available"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing intent and querying library systems..."):
                try:
                    payload = {"user_id": current_user_id, "message": prompt}
                    res = requests.post(f"{BACKEND_URL}/api/v1/chat", json=payload, timeout=15)
                    if res.status_code == 200:
                        data = res.json()
                        answer = data["answer"]
                        trace_id = data["trace_id"]
                        tools = data["tools_used"]
                        cited = data["cited_resources"]

                        st.markdown(answer)
                        st.caption(f"Trace ID: `{trace_id}` | Tools invoked: `{', '.join(tools) or 'None'}`")
                        if cited:
                            st.info(f"📚 **Cited Resources:** {', '.join(cited)}")

                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": answer,
                            "trace_id": trace_id,
                            "tools_used": tools,
                        })
                    else:
                        st.error(f"Backend error {res.status_code}: {res.text}")
                except Exception as err:
                    st.error(f"Failed to reach FastAPI backend: {err}")

# --- TAB 2: Catalog & Discovery ---
with tab2:
    st.header("Semantic & Metadata Catalog Search")
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        search_query = st.text_input("Search books, journals, papers, dissertations:", "Artificial Intelligence")
    with col2:
        diff_filter = st.selectbox("Difficulty", ["All", "beginner", "intermediate", "advanced"])
    with col3:
        type_filter = st.selectbox("Type", ["All", "book", "paper", "ebook", "dissertation"])

    if st.button("Search Catalog", type="primary"):
        params = {"q": search_query}
        if diff_filter != "All":
            params["difficulty"] = diff_filter
        if type_filter != "All":
            params["resource_type"] = type_filter

        try:
            resp = requests.get(f"{BACKEND_URL}/api/v1/catalog/search", params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    st.success(f"Found {data['count']} matching resources.")
                    for item in data["results"]:
                        with st.expander(f"[{item['resource_code']}] {item['title']} ({item['resource_type'].upper()})"):
                            st.write(f"**Authors:** {item['authors']}")
                            st.write(f"**Subject:** {item['subject']} | **Level:** {item['difficulty_level'].title()}")
                            st.write(f"**Location:** {item['branch']} — Shelf `{item['shelf_location']}`")
                            st.write(f"**Availability:** {item['available_copies']} of {item['total_copies']} copies available")
                            if item.get("digital_url"):
                                st.markdown(f"🔗 [Access Digital Resource]({item['digital_url']})")
                            st.caption(item.get("description", ""))
                else:
                    st.warning("No authorized resources found matching your query (`not_found`).")
            else:
                st.error(f"Error {resp.status_code}")
        except Exception as e:
            st.error(f"Connection error: {e}")

# --- TAB 3: Account & Circulation ---
with tab3:
    st.header("Circulation, Loans & Privacy Controls")
    st.markdown("Test authorized account access, renewals, holds, and **privacy refusal guardrails**.")

    col_a, col_b = st.columns(2)
    with col_a:
        inspect_user_id = st.text_input("Target User ID to Inspect:", current_user_id)
    with col_b:
        st.markdown("<br>", unsafe_allow_html=True)
        inspect_btn = st.button("View Account Summary")

    if inspect_btn or current_user_id:
        try:
            # We use the chat assistant endpoint to test account lookup & privacy enforcement cleanly
            payload = {
                "user_id": current_user_id,
                "message": f"What items have I borrowed? Show account summary for {inspect_user_id}",
            }
            resp = requests.post(f"{BACKEND_URL}/api/v1/chat", json=payload, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                st.markdown(data["answer"])
                st.caption(f"Trace ID: `{data['trace_id']}` | Outcome: `{data['outcome']}`")
            else:
                st.error(f"Error {resp.status_code}")
        except Exception as e:
            st.error(f"Connection error: {e}")

# --- TAB 4: Librarian Analytics Dashboard ---
with tab4:
    st.header("Librarian Circulation & Demand Analytics")
    st.markdown("Data-driven insights for catalog acquisitions, waitlists, and overdue management.")

    if st.button("Load Analytics Dashboard"):
        try:
            resp = requests.get(f"{BACKEND_URL}/api/v1/analytics", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                kpis = data.get("kpis", {})

                # KPI Metrics Row
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Catalog Titles", kpis.get("total_catalog_titles", 0))
                m2.metric("Active Loans", kpis.get("total_active_loans", 0))
                m3.metric("Overdue Loans", kpis.get("overdue_loans_count", 0), delta_color="inverse")
                m4.metric("Waitlist Requests", kpis.get("active_waitlist_requests", 0))

                st.divider()
                st.subheader("📌 Longest Waitlists & High-Demand Titles")
                waitlists = data.get("longest_waitlists", [])
                if waitlists:
                    for w in waitlists:
                        st.warning(
                            f"**[{w['resource_code']}] {w['title']}** — Waitlist Count: **{w['waitlist_count']}** "
                            f"(Available: {w['available_copies']}/{w['total_copies']})"
                        )
                else:
                    st.info("No active waitlists found.")

                st.subheader("📚 Subject Utilization & Demand")
                subjects = data.get("subject_demand", [])
                if subjects:
                    st.dataframe(subjects, use_container_width=True)

                st.subheader("⚠️ Overdue Items & Fines")
                overdues = data.get("overdue_items", [])
                if overdues:
                    st.dataframe(overdues, use_container_width=True)
                else:
                    st.success("Zero overdue items currently in circulation!")
            else:
                st.error(f"Failed to load analytics: {resp.status_code}")
        except Exception as e:
            st.error(f"Connection error: {e}")
