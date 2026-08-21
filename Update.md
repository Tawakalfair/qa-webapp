# PRD: Database Query Verification & Automated Evidence Engine

---

## 1. Document Control & Overview

| Attribute | Details |
| :--- | :--- |
| **Document Title** | Database Query Verification & Automated Evidence Engine |
| **Version** | v1.0.0 |
| **Author** | QA Automation Engineering Team |
| **Status** | Approved / Ready for Implementation |
| **Target Release** | Next Sprint |

### Executive Summary
This feature enhances QA Automata by automating database verification against Oracle database environments. It allows automated test scenarios to execute SQL queries via Oracle TNS aliases before and after UI mutations, automatically compare data state changes (*Before vs. After*), highlight mutated fields in red, and embed structured evidence directly into the main sheet of the exported Unit Test (UT) document.

---

## 2. Problem Statement & Objectives

### Current Pain Points
* **Manual Verification Overhead**: QA engineers currently pause automated tests or execute manual steps in Oracle SQL Developer, copy-pasting tables or capturing manual screenshots.
* **Audit & Traceability Limits**: Visual screen-only evidence is insufficient for backend/data integrity audits.
* **Document Bloat & Unreadable Images**: Taking screenshots of queries with wide column counts (up to 100 columns) leads to unreadable, compressed images in Excel.

### Core Objectives
* **Zero-Touch DB Verification**: Run database queries directly within test scenarios using standard Oracle TNS profiles.
* **Automated Diff Highlighting**: Instantly detect modified cells between *Before* and *After* states and highlight changed data in red.
* **Inline Native Excel Tables**: Embed data directly into the active/main sheet of the Excel UT matrix, bypassing image distortion for large datasets (capped at 100 rows).

---

## 3. Scope & User Stories

### User Story 1: Database Connection Configuration
> *As a QA Engineer, I want to configure Oracle database profiles (TNS Alias, Username, Password) manually in the system settings so that my test steps can securely connect to different database schemas.*

### User Story 2: Step-Level Database Verification
> *As a QA Engineer, I want to define `DB_QUERY_BEFORE` and `DB_QUERY_AFTER` steps in my scenario workspace so that the system records the data state prior to and following user actions.*

### User Story 3: Automated Cell-Level Diff Highlighting
> *As a QA Engineer & Auditor, I want data modifications in the "After" query table to be highlighted in red directly on the main UT document sheet so that verification is immediate and audit-compliant.*

---

## 4. Functional Specifications

### 4.1 Database Connection Profile Manager

The system will store database connection profiles manageable per project or globally.

* **Profile Fields**:
  * `Profile Name`: Unique identifier (e.g., `DEV01_OM`, `TESTNN_QC`).
  * `TNS Alias`: Net service name defined in `tnsnames.ora` (e.g., `PCSDB_TESTNN`).
  * `Database Username`: Target Oracle schema user (e.g., `OM_APP`).
  * `Database Password`: Encrypted password string.
  * `Project Association`: Optional linkage to a specific project.

### 4.2 Test Step Engine & Commands

Three new commands will be added to the scenario execution pipeline:

| Command Code | Target Selector | Input Value | Behavior |
| :--- | :--- | :--- | :--- |
| `DB_QUERY_BEFORE` | Connection Profile Name | SQL `SELECT` Statement | Executes query, caches baseline snapshot (up to 100 rows). |
| `DB_QUERY_AFTER` | Connection Profile Name | SQL `SELECT` Statement | Executes query, caches mutated snapshot, and computes diff against `BEFORE`. |
| `DB_QUERY` | Connection Profile Name | SQL `SELECT` Statement | Executes standalone query and records tabular evidence without diffing. |

### 4.3 Execution & Diff Logic Rules

* **Row Limit**: All queries are automatically capped at **100 rows** (`ROWNUM <= 100` enforced at the execution layer) to prevent memory overload and maintain Excel sheet readability.
* **Comparison Strategy**:
  * **Primary Key Matching**: The engine checks the first column as the primary key reference by default. If duplicate keys or aggregate rows exist, it falls back to sequential positional comparison (Row $i$ vs. Row $i$).
  * **Cell-Level Diffing**: Every column value in the *After* record is compared against the corresponding column in the *Before* record.
  * **Mutation Handling**:
    * **UPDATE**: Cells in the *After* record with changed values are flagged as `MODIFIED`.
    * **INSERT**: Entire newly added rows are flagged as `NEW_RECORD`.
    * **DELETE / NO DATA**: Flagged appropriately if zero records are returned.

### 4.4 Excel UT Document Export Engine (`openpyxl`)

All database query evidence will be embedded **inline directly within the main sheet** of the generated Excel Unit Test matrix:

* **Presentation Logic (Hybrid Approach)**:
  * **Standard Single-Row / Narrow Queries ($\le 8$ columns, 1 row)**: Retains option for GUI Mockup screenshot insertion.
  * **Multi-Row / Wide Queries ($> 8$ columns or $> 1$ row)**: Automatically rendered as a **native Excel table** directly below the test case block.
* **Excel Table Styling Specifications**:
  * **Header Row**: Background `#E2E8F0` (Slate Gray), Bold font, Centered alignment, Thin gray borders.
  * **Data Cells**: Monospace font (`Consolas` or `Segoe UI`, 9.5 pt), Thin border on all sides (`border_style="thin"`).
  * **Unchanged Data**: Standard text color `#1E293B`, white background.
  * **Modified Data (*After* table)**:
    * Background Fill: Light Red `#FEE2E2`
    * Font Color: Dark Red `#991B1B` (Bold)
  * **Column Width**: Auto-fitted based on maximum character length per column (with a max-width clamp of 45 characters to avoid stretching).

---

## 5. System Architecture & Data Flow

```text
  [Scenario Step: DB_QUERY_BEFORE]
                 │
                 ▼
  [python-oracledb (Thin Mode)] ────► Reads local `tnsnames.ora` & Decrypts Credentials
                 │
                 ▼
  [Fetch Data (Max 100 Rows)] ──────► Cached in Run Execution State (JSON Payload)
                 │
  [Web UI Execution: Click/Type] ───► Target Application Mutates State
                 │
                 ▼
  [Scenario Step: DB_QUERY_AFTER]
                 │
                 ▼
  [python-oracledb (Thin Mode)] ────► Fetches Post-Action Data State
                 │
                 ▼
  [In-Memory Diff Engine] ──────────► Identifies Modified Rows/Columns
                 │
                 ▼
  [Export UT Matrix Document] ──────► `openpyxl` Renders Inline Native Table with Red Highlights


  6. Non-Functional Requirements
  
  Execution Performance: In-memory diffing and query execution must not add more than $50\text{ ms}$ overhead per scenario run.
  
  Security: Database passwords must be stored using symmetric encryption (e.g., Fernet / AES-256) and never logged in plain text in terminal outputs or client responses.
  
  Driver Independence: Oracle connectivity will utilize python-oracledb in Thin Mode, removing requirements for Oracle Instant Client binaries on the host system.
  
  Stability: Query failures (e.g., invalid SQL syntax, connection timeout) will gracefully record error messages in the test run log without terminating the entire test suite.
  
  Scenario	System Behavior
  Query Returns 0 Rows	    Displays No data found in an inline styled Excel cell with a gray background.
  Query Exceeds 100 Rows	Truncates at row 100 and appends an informational footer: [Displaying 100 of N rows].
  Schema/Table Not Found	Marks step as FAILED, captures the Oracle ORA-xxxxx error code, and writes the error message to the UT document.
  Column Count Mismatch	    If queries in BEFORE and AFTER return different column sets, the diff engine matches shared column names and flags unshared columns.
  

  8. Acceptance Criteria
  
  [ ] Database Connection Profile UI is accessible in settings, allowing manual CRUD operations for TNS-based credentials.
  
  [ ] Steps with DB_QUERY_BEFORE, DB_QUERY_AFTER, and DB_QUERY execute successfully against configured Oracle environments.
  
  [ ] Multi-row query results up to 100 rows are captured and written into native Excel cells on the main sheet with full borders.
  
  [ ] Modified cells in the After data table are styled with #FEE2E2 red background fill and bold #991B1B red text.
  
  [ ] No noticeable performance degradation occurs during dashboard navigation or scenario execution.
  