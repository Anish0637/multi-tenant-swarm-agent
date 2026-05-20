"""
Streamlit UI for Multi-Tenant Swarm Agent System
"""

import streamlit as st
import requests
import json
from datetime import datetime
from typing import Dict, Any

# Page config
st.set_page_config(
    page_title="Multi-Tenant Swarm Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main {
        padding: 0rem 1rem;
    }
    .stTabs [data-baseweb="tab-list"] button {
        font-size: 1.2em;
    }
</style>
""", unsafe_allow_html=True)

# Config
MCP_SERVER_URL = "http://localhost:9000"
TIMEOUT = 10

# Session state
if 'tasks_submitted' not in st.session_state:
    st.session_state.tasks_submitted = []

# Helper functions
def make_request(tool_name: str, parameters: Dict[str, Any], tool_id: str = "req-001") -> Dict:
    """Make a request to the MCP server"""
    try:
        url = f"{MCP_SERVER_URL}/tools/execute"
        payload = {
            "tool_name": tool_name,
            "tool_id": tool_id,
            "parameters": parameters,
            "context": {}
        }
        response = requests.post(url, json=payload, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to MCP Server at {MCP_SERVER_URL}"}
    except requests.exceptions.Timeout:
        return {"error": "Request timeout"}
    except Exception as e:
        return {"error": str(e)}

def check_health() -> bool:
    """Check if MCP server is healthy"""
    try:
        response = requests.get(f"{MCP_SERVER_URL}/health", timeout=5)
        return response.status_code == 200
    except:
        return False

def get_agents() -> list:
    """Get list of available agents"""
    result = make_request("list_agents", {})
    if "error" in result:
        return []
    agents = result.get("result", {}).get("agents", [])
    return agents

def get_agent_status(agent_id: str) -> Dict:
    """Get status of a specific agent"""
    return make_request("get_agent_status", {"agent_id": agent_id})

def submit_task(agent_id: str, task_type: str, payload: Dict) -> Dict:
    """Submit a task to an agent"""
    return make_request(
        "submit_task",
        {
            "agent_id": agent_id,
            "task_type": task_type,
            "payload": payload
        },
        tool_id=f"task-{datetime.now().timestamp()}"
    )

# Header
st.title("🤖 Multi-Tenant Swarm Agent Control Panel")
st.markdown("---")

# Health check
col1, col2, col3 = st.columns([2, 2, 2])
with col1:
    health = check_health()
    status_emoji = "✅" if health else "❌"
    st.metric("Server Status", status_emoji, "Online" if health else "Offline")

with col2:
    st.metric("MCP Server", "Port 9000", "Active" if health else "Inactive")

with col3:
    st.metric("Environment", "Development", "Running")

st.markdown("---")

# Main tabs
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "➕ Submit Task", "👥 Agent Status", "📝 History"])

# TAB 1: Dashboard
with tab1:
    st.subheader("System Overview")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Available Agents")
        agents = get_agents()
        
        if agents:
            for agent in agents:
                with st.expander(f"🔹 {agent.get('name', agent.get('id'))}"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.write(f"**Type:** {agent.get('type')}")
                        st.write(f"**ID:** {agent.get('id')}")
                    with col_b:
                        status = agent.get('status', 'unknown')
                        status_color = "🟢" if status == "healthy" else "🟡" if status == "degraded" else "🔴"
                        st.write(f"**Status:** {status_color} {status}")
        else:
            st.warning("No agents available")
    
    with col2:
        st.subheader("Quick Stats")
        
        # Create metrics
        total_agents = len(agents)
        healthy_agents = sum(1 for a in agents if a.get('status') == 'healthy')
        
        st.metric("Total Agents", total_agents)
        st.metric("Healthy Agents", healthy_agents)
        st.metric("Tasks Submitted", len(st.session_state.tasks_submitted))
        
        # MCP Server Info
        st.divider()
        st.write("**MCP Server Endpoints:**")
        st.code("GET  /health\nGET  /tools\nGET  /tools/{name}\nPOST /tools/execute")

# TAB 2: Submit Task
with tab2:
    st.subheader("Submit Task to Agent")
    
    col1, col2 = st.columns(2)
    
    with col1:
        agent_id = st.selectbox(
            "Select Agent",
            ["hr_agent", "finance_agent", "medical_agent", "supervisor"],
            help="Choose the agent to send the task to"
        )
    
    with col2:
        if agent_id == "hr_agent":
            task_type = st.selectbox("Task Type", ["employee_onboarding", "leave_request", "performance_review"])
        elif agent_id == "finance_agent":
            task_type = st.selectbox(
                "Task Type",
                ["expense_report", "budget_planning", "invoice_processing"])
        elif agent_id == "medical_agent":
            task_type = st.selectbox(
                "Task Type",
                ["appointment_scheduling", "patient_records", "prescription_management"])
        else:
            task_type = st.selectbox("Task Type", ["coordinate_task", "supervise_workflow"])
    
    st.divider()
    
    # Dynamic payload based on agent and task type
    st.subheader("Task Payload")
    
    payload = {}
    
    if agent_id == "hr_agent":
        if task_type == "employee_onboarding":
            col1, col2, col3 = st.columns(3)
            with col1:
                payload["employee_name"] = st.text_input("Employee Name", "John Doe")
            with col2:
                payload["department"] = st.text_input("Department", "Engineering")
            with col3:
                payload["start_date"] = st.date_input("Start Date").isoformat()
            
        elif task_type == "leave_request":
            col1, col2, col3 = st.columns(3)
            with col1:
                payload["employee_id"] = st.text_input("Employee ID", "EMP001")
            with col2:
                payload["leave_type"] = st.selectbox("Leave Type", ["Vacation", "Sick", "Personal"])
            with col3:
                payload["days"] = st.number_input("Number of Days", 1, 30, 5)
        
        elif task_type == "performance_review":
            col1, col2 = st.columns(2)
            with col1:
                payload["employee_id"] = st.text_input("Employee ID", "EMP001")
                payload["rating"] = st.slider("Rating", 1, 5, 4)
            with col2:
                payload["comments"] = st.text_area("Comments", "Great performance")
    
    elif agent_id == "finance_agent":
        if task_type == "expense_report":
            col1, col2, col3 = st.columns(3)
            with col1:
                payload["amount"] = st.number_input("Amount ($)", 0.0, 100000.0, 5000.0)
            with col2:
                payload["category"] = st.selectbox("Category", ["Travel", "Meals", "Office", "Other"])
            with col3:
                payload["date"] = st.date_input("Date").isoformat()
            payload["description"] = st.text_input("Description", "Business trip expenses")
        
        elif task_type == "budget_planning":
            col1, col2, col3 = st.columns(3)
            with col1:
                payload["department"] = st.text_input("Department", "Engineering")
            with col2:
                payload["quarter"] = st.selectbox("Quarter", ["Q1", "Q2", "Q3", "Q4"])
            with col3:
                payload["budget"] = st.number_input("Budget ($)", 0, 1000000, 250000)
        
        elif task_type == "invoice_processing":
            col1, col2, col3 = st.columns(3)
            with col1:
                payload["invoice_id"] = st.text_input("Invoice ID", "INV001")
            with col2:
                payload["vendor"] = st.text_input("Vendor", "Acme Corp")
            with col3:
                payload["amount"] = st.number_input("Amount ($)", 0.0, 500000.0, 10000.0)
    
    elif agent_id == "medical_agent":
        if task_type == "appointment_scheduling":
            col1, col2, col3 = st.columns(3)
            with col1:
                payload["patient_name"] = st.text_input("Patient Name", "Jane Smith")
            with col2:
                payload["date"] = st.date_input("Appointment Date").isoformat()
            with col3:
                payload["doctor"] = st.text_input("Doctor", "Dr. Smith")
            payload["reason"] = st.text_input("Reason", "Regular checkup")
        
        elif task_type == "patient_records":
            col1, col2 = st.columns(2)
            with col1:
                payload["patient_id"] = st.text_input("Patient ID", "PAT001")
            with col2:
                payload["action"] = st.selectbox("Action", ["View", "Update", "Archive"])
        
        elif task_type == "prescription_management":
            col1, col2, col3 = st.columns(3)
            with col1:
                payload["patient_id"] = st.text_input("Patient ID", "PAT001")
            with col2:
                payload["medication"] = st.text_input("Medication", "Aspirin")
            with col3:
                payload["dosage"] = st.text_input("Dosage", "100mg")
    
    # Submit button
    st.divider()
    if st.button("🚀 Submit Task", use_container_width=True, type="primary"):
        with st.spinner("Submitting task..."):
            result = submit_task(agent_id, task_type, payload)
            
            # Store in session
            task_record = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "agent": agent_id,
                "task_type": task_type,
                "status": "submitted",
                "result": result
            }
            st.session_state.tasks_submitted.append(task_record)
            
            # Display result
            if "error" in result:
                st.error(f"Error: {result['error']}")
            else:
                st.success("Task submitted successfully!")
                st.json(result)

# TAB 3: Agent Status
with tab3:
    st.subheader("Agent Status Monitor")
    
    agents_list = ["supervisor", "hr_agent", "finance_agent", "medical_agent"]
    
    # Refresh button
    if st.button("🔄 Refresh Status", use_container_width=True):
        st.rerun()
    
    st.divider()
    
    # Display status for each agent
    cols = st.columns(2)
    for idx, agent_id in enumerate(agents_list):
        with cols[idx % 2]:
            with st.spinner(f"Loading {agent_id}..."):
                status = get_agent_status(agent_id)
                
                with st.expander(f"📋 {agent_id}", expanded=True):
                    if "error" in status:
                        st.error(f"Error: {status['error']}")
                    else:
                        result = status.get("result", {})
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            agent_status = result.get("status", "unknown")
                            status_color = (
                                "🟢" if agent_status == "healthy"
                                else "🟡" if agent_status == "degraded"
                                else "🔴"
                            )
                            st.metric(f"{status_color} Status", agent_status)
                        
                        with col_b:
                            st.metric("Tasks Processed", result.get("tasks_processed", 0))
                        
                        col_c, col_d = st.columns(2)
                        with col_c:
                            uptime = result.get("uptime_seconds", 0)
                            minutes = uptime // 60
                            seconds = uptime % 60
                            st.metric("Uptime", f"{minutes}m {seconds}s")
                        
                        with col_d:
                            st.metric("Agent ID", result.get("agent_id", "N/A"))

# TAB 4: History
with tab4:
    st.subheader("Task Submission History")
    
    if st.session_state.tasks_submitted:
        # Clear history button
        if st.button("🗑️ Clear History", type="secondary"):
            st.session_state.tasks_submitted = []
            st.rerun()
        
        st.divider()
        
        # Display history in reverse order (newest first)
        for idx, task in enumerate(reversed(st.session_state.tasks_submitted)):
            with st.expander(
                f"📌 {task['agent']} - {task['task_type']} ({task['timestamp']})",
                expanded=(idx == 0)
            ):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write(f"**Agent:** {task['agent']}")
                    st.write(f"**Type:** {task['task_type']}")
                
                with col2:
                    status_emoji = "✅" if task['status'] == 'submitted' else "❌"
                    st.write(f"**Status:** {status_emoji} {task['status']}")
                    st.write(f"**Time:** {task['timestamp']}")
                
                with col3:
                    st.write("**Result:**")
                    if "error" in task['result']:
                        st.error(task['result']['error'])
                    else:
                        st.success("Success")
                
                st.divider()
                with st.expander("View Details"):
                    st.json(task['result'])
    else:
        st.info("No tasks submitted yet. Go to the 'Submit Task' tab to get started!")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center'>
    <p>🤖 Multi-Tenant Swarm Agent System | Version 1.0</p>
    <p style='font-size: 0.8em; color: gray;'>
        MCP Server: localhost:9000 | Supervisor: localhost:9001
    </p>
</div>
""", unsafe_allow_html=True)
