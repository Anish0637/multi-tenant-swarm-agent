# Streamlit Multi-Tenant Swarm Agent UI

Interactive web interface for managing your multi-tenant swarm agent system.

## Features

- **📊 Dashboard**: Real-time system overview and agent status
- **➕ Task Submission**: Easy-to-use forms for submitting tasks to agents
- **👥 Agent Monitor**: Real-time status monitoring for all agents
- **📝 History**: Track all submitted tasks and their results

## Requirements

- Python 3.9+
- Streamlit >= 1.28.0
- Requests >= 2.31.0
- Running Docker deployment (MCP Server on port 9000)

## Installation

Install dependencies:

```bash
pip install streamlit requests
```

Or install all project dependencies:

```bash
pip install -r requirements.txt
```

## Running the UI

### From the project root directory:

```bash
streamlit run streamlit_app.py
```

### With custom configuration:

```bash
streamlit run streamlit_app.py --logger.level=debug
```

### Access the UI:

Open your browser to: **http://localhost:8501**

## Usage

### 1. Dashboard Tab
- View system health status
- See all available agents
- Quick statistics

### 2. Submit Task Tab
- Select an agent (HR, Finance, Medical, or Supervisor)
- Choose task type
- Fill in task-specific parameters
- Submit task to agent

### 3. Agent Status Tab
- Real-time status for all agents
- Tasks processed count
- Agent uptime
- Click "Refresh" for latest status

### 4. History Tab
- View all submitted tasks
- See submission timestamps
- View task results
- Clear history when needed

## Task Examples

### HR Agent - Employee Onboarding
```json
{
  "agent_id": "hr_agent",
  "task_type": "employee_onboarding",
  "payload": {
    "employee_name": "John Doe",
    "department": "Engineering",
    "start_date": "2026-06-01"
  }
}
```

### Finance Agent - Expense Report
```json
{
  "agent_id": "finance_agent",
  "task_type": "expense_report",
  "payload": {
    "amount": 5000,
    "category": "Travel",
    "date": "2026-05-20",
    "description": "Business trip expenses"
  }
}
```

### Medical Agent - Appointment Scheduling
```json
{
  "agent_id": "medical_agent",
  "task_type": "appointment_scheduling",
  "payload": {
    "patient_name": "Jane Smith",
    "date": "2026-06-01",
    "doctor": "Dr. Smith",
    "reason": "Regular checkup"
  }
}
```

## Configuration

To change the MCP Server URL, edit `streamlit_app.py`:

```python
MCP_SERVER_URL = "http://localhost:9000"  # Change this if needed
```

## Troubleshooting

### Cannot connect to server
- Ensure Docker containers are running: `docker ps`
- Verify MCP Server is healthy: `curl http://localhost:9000/health`
- Check firewall settings

### Streamlit not starting
- Verify Python 3.9+ is installed: `python --version`
- Reinstall dependencies: `pip install -r requirements.txt --force-reinstall`
- Clear Streamlit cache: `streamlit cache clear`

### Slow performance
- Check agent logs: `docker-compose -f docker/docker-compose.yml logs -f`
- Verify network connectivity
- Increase timeout in `streamlit_app.py` if needed

## Development

To modify the UI:
1. Edit `streamlit_app.py`
2. Streamlit will auto-reload on save
3. Check browser for updates

## Features Coming Soon

- [ ] Real-time task notifications
- [ ] Advanced filtering and search
- [ ] Task result visualization
- [ ] Custom task templates
- [ ] Multi-user support
- [ ] Authentication
- [ ] Role-based access control
