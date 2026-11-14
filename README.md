# UBDTCE Secure E-Voting System

A web-based college election management system developed for **University B.D.T. College of Engineering (UBDTCE), Davanagere, Karnataka, India**.

The application provides a centralized platform for managing college-level and department-level elections, student accounts, candidates, voter eligibility, and voting activities.

## Features

- Role-based access for Principal, HOD, and Students.
- Principal dashboard for college-level administration.
- HOD dashboard for department-level management.
- Student registration and email-based account activation.
- Student login using USN and password.
- Administrator login using email and password.
- Branch and student management.
- College-level and department-level election management.
- Candidate registration and management.
- Election duration configuration.
- Voter eligibility management.
- Digital voting functionality.
- Election information and result management.
- Audit event recording and hash-based verification design.

## Technology Stack

| Technology | Purpose |
|---|---|
| React.js | Frontend development |
| Vite | Frontend tooling |
| CSS | User interface styling |
| Python | Backend programming |
| Flask | Backend API |
| PostgreSQL | Database |
| Psycopg 3 | Direct PostgreSQL connectivity |
| Flask-CORS | Cross-origin communication |
| Flask-Limiter | API rate limiting |
| python-dotenv | Environment configuration |
| Git | Version control |

**Database:** PostgreSQL is accessed directly using Psycopg 3. No SQLAlchemy or ORM is used.

## Project Structure

```text
UBDTCE_SECURE_EVOTING/
│
├── backend/
│   ├── app.py
│   ├── requirements.txt
│   └── ...
│
├── frontend/
│   ├── public/
│   ├── src/
│   ├── package.json
│   └── vite.config.js
│
├── docs/
│
├── README.md
└── .gitignore
```

## Prerequisites

Install the following software:

- Python 3
- Node.js and npm
- PostgreSQL
- Git
- Visual Studio Code (recommended)

## Installation and Setup

### 1. Clone the Repository

```bash
git clone YOUR_REPOSITORY_URL
cd UBDTCE_SECURE_EVOTING
```

Replace `YOUR_REPOSITORY_URL` with the actual GitHub repository URL.

### 2. Backend Setup

Navigate to the backend directory:

```bash
cd backend
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate the virtual environment on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

### 3. Database Configuration

Start the PostgreSQL service.

Create the project database if it does not already exist:

```sql
CREATE DATABASE ubdtce_evoting;
```

Configure the database connection according to the environment variables used by the backend.

Apply the project's database schema before starting the application.

### 4. Environment Configuration

Create a `.env` file at the repository root. Both `backend/app.py` and the
independent activation-email worker load this exact file; host-supplied
environment variables take precedence.

Example configuration:

```env
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=ubdtce_evoting
DB_USER=your_database_user
DB_PASSWORD=your_database_password

SMTP_HOST=smtp.example.edu
SMTP_PORT=587
SMTP_EMAIL=sender@example.edu
SMTP_USERNAME=sender@example.edu
SMTP_APP_PASSWORD=your_smtp_app_password
SMTP_FROM_EMAIL=sender@example.edu
SMTP_USE_SSL=false
SMTP_USE_STARTTLS=true
EMAIL_TEST_MODE=false
STUDENT_ACTIVATION_URL=https://portal.example.edu/student-activate
```

For implicit TLS (commonly port 465), set `SMTP_USE_SSL=true` and
`SMTP_USE_STARTTLS=false`. Use the exact environment variable names required
by the backend source code. `EMAIL_TEST_MODE=true` deliberately suppresses SMTP
delivery and must never be used for a real invitation campaign.

**Never upload actual passwords, email app passwords, database credentials, or secret keys to GitHub.**

## Running the Application

The frontend and backend must run in separate terminals.

### Start the Backend

From the `backend` directory:

```bash
..\.venv\Scripts\python.exe app.py
```

Backend local address:

```text
http://127.0.0.1:5000
```

### Start the activation-email worker

The Flask API only queues invitations. Run the following command in a third
terminal from the `backend` directory to deliver them; it must remain supervised
by a service manager or scheduled-task wrapper in production:

```powershell
..\.venv\Scripts\python.exe email_worker.py --watch --limit 25 --interval-seconds 30
```

The worker reports SMTP-accepted messages as `sent`; `queued` and `pending`
mean delivery has not yet been confirmed. Do not run it for real students until
the sender configuration and an authorized test mailbox have been verified.

### Start the Frontend

Open a second terminal at the project root:

```bash
cd frontend
```

Install frontend dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

Open the local URL displayed in the terminal by Vite.

## Database Modules

The PostgreSQL database stores information related to:

- User accounts and credentials
- Student information
- Branches and HOD assignments
- Email verification and account activation
- Password reset tokens
- Elections and eligible branches
- Candidates
- Ballots
- Voter eligibility and participation
- Audit events

## Security

Security mechanisms used or planned in the application include:

- Password hashing
- Session-based authentication
- Role-based authorization
- Email-based account activation
- Password recovery
- Login rate limiting
- Backend input validation
- Hash-linked audit event records

## Development Guidelines

- Keep frontend and backend responsibilities separate.
- Use Psycopg 3 for PostgreSQL database operations.
- Do not introduce SQLAlchemy or ORM-based database access.
- Validate important operations on the backend.
- Enforce role-based authorization on protected routes.
- Do not expose sensitive information in frontend code.
- Test changes before committing them.
- Do not commit `.env`, `.venv`, or `node_modules`.

## Scalability and Performance

The long-term design target is to support up to **10 million users**.

This is a target, not a verified capacity claim. Achieving it requires extensive load testing, stress testing, concurrent voting tests, database optimization, and performance evaluation.

See [OPERATIONS.md](OPERATIONS.md) for the production topology, safe migration
order, email outbox behavior, privacy model, measurable workload assumptions,
testing progression, and known limitations.

## Project Status

**Project:** UBDTCE Secure E-Voting System

**Institution:** University B.D.T. College of Engineering, Davanagere

**Status:** In Development

---

**UBDTCE Secure E-Voting System**  
*Digitalizing college elections through a centralized and user-friendly platform.*
