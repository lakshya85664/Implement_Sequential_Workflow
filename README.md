# Implement Sequential Workflow

## Project Overview
This project implements and evaluates a sequential employee-onboarding workflow. It coordinates four dependent activities: creating an employee account, assigning equipment, scheduling orientation, and notifying the manager. Each step follows the successful completion of its prerequisite.

## Assessment Tasks
1. **Workflow contract and state model:** defines workflow structure, task dependencies, states, and event evidence.
2. **Sequential orchestration:** executes onboarding activities in order and passes context between steps.
3. **Failure, retry, and replay safety:** classifies failures, records bounded retry decisions, and demonstrates idempotency.
4. **Integration boundary and observability:** uses injectable adapters and records structured traces, metrics, correlation IDs, and redacted sensitive fields.
5. **Operator runbook and evidence report:** documents startup, monitoring, troubleshooting, recovery, and evidence inventory.

## Workflow Sequence
| Order | Activity | Service |
|---|---|---|
| 1 | Create employee account | Identity |
| 2 | Assign equipment | IT |
| 3 | Schedule orientation | HR |
| 4 | Notify manager | Notification |

## Project Structure
```text
Implement_Sequential_Workflow/
├── sequential_workflow.py
├── orchestrator.py
├── reliability.py
├── adapters.py
├── runbook.py
├── tests/
│   ├── test_workflow_contract.py
│   ├── test_sequential_workflow.py
│   ├── test_failure_recovery.py
│   ├── test_integration_observability.py
│   └── test_operator_runbook.py
├── outputs/
├── traces/
├── reports/
├── requirements.txt
├── .gitignore
└── README.md
```

## Environment
- Python 3.13.9
- pytest 9.2.0
- Windows CMD and `.venv`

## Setup
```cmd
cd /d E:\Tayana_Projects\Workflow_Orchestration\Implement_Sequential_Workflow
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run Demonstrations
```cmd
python sequential_workflow.py
python orchestrator.py
python reliability.py
python adapters.py
python runbook.py
```

## Run Tests
```cmd
python -m pytest tests\test_workflow_contract.py -v
python -m pytest tests\test_sequential_workflow.py -v
python -m pytest tests\test_failure_recovery.py -v
python -m pytest tests\test_integration_observability.py -v
python -m pytest tests\test_operator_runbook.py -v
python -m pytest -v
```

## Verified Results
| Task | Tests passed |
|---|---:|
| Task 1 — Workflow contract and state model | 10 |
| Task 2 — Sequential workflow orchestration | 10 |
| Task 3 — Failure, retry, and replay safety | 14 |
| Task 4 — Integration boundary and observability | 11 |
| Task 5 — Operator runbook and evidence report | 8 |
| **Total** | **53** |

Final full-suite verification: **53 passed in 0.35s**.

Task 5 evidence inventory: six expected files, six existing files, and six valid JSON files. Evidence complete: `True`.

## Evidence and Reports
- `outputs/` contains task-level JSON results.
- `traces/` contains retry and observability traces.
- `reports/evidence_report.json` inventories expected evidence.
- `reports/OPERATOR_RUNBOOK.md` contains operational instructions.
- `outputs/task5_operator_report.json` contains the final generated report.

## Design Notes and Limitations
The service adapters are simulated implementations. They demonstrate an injectable integration boundary and do not make live calls to identity, IT, HR, or notification providers. Production use requires provider-specific adapters, authentication, secure secret management, durable state, and operational alerting.

The retry demonstration records bounded backoff decisions; it is not a production scheduler and does not forcibly interrupt a blocked synchronous request. Local JSON evidence demonstrates trace and report formats, not a distributed observability platform.

## Reflection
Completing this assessment helped me understand how a multi-step business process can be designed as a dependable workflow rather than a collection of unrelated function calls. I started by defining a workflow contract and state model, which made task ownership, dependencies, and execution states explicit. Building the orchestrator then showed me why sequence and context handoff matter: later activities must receive the outputs they depend on, and a workflow should not advance when a prerequisite has failed.

The reliability exercises were especially useful. I implemented failure classification, bounded retry decisions, and replay protection. The idempotency demonstration showed how repeating an operation can cause duplicate side effects unless the operation is designed to recognize a replay. I also learned that transient, permanent, timeout, and malformed-response failures need different handling rather than one generic retry rule.

The integration and observability task introduced a cleaner boundary between workflow logic and external services. Injectable adapters make service implementations replaceable, while structured traces, correlation IDs, metrics, and sensitive-field redaction make execution easier to inspect. Finally, the operator runbook and evidence report connected implementation work to operational responsibilities: an engineer must be able to diagnose failures, decide whether replay is safe, and verify that evidence is complete.

Across the five tasks, I strengthened my understanding of orchestration, testing, error handling, interface design, and operational documentation. The final suite completed with 53 passing tests. The project uses simulated adapters, so a future improvement would be to integrate real provider APIs with secure credentials, durable workflow state, and production-grade monitoring.
