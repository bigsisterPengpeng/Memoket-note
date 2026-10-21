# Shared contracts

`contracts.json` contains synthetic completion criteria, action preconditions, criterion splitting and saved beat-label cases. The frontend runner (`frontend/scripts/check-contracts.mts`) and backend runner (`backend/tests/test_shared_contracts.py`) both execute these cases.

`beat-label-cases.json` also exercises saved English and legacy status labels in plan tests. Multilingual input examples test compatibility; generated harness instructions and default UI remain English.

Add failures and valid counterexamples together. Keep expected results independent of the implementation. Never add real notes or meeting records.
