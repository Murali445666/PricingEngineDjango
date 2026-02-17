---
trigger: always_on
---

Python Environment Rule

    Interpreter Path: Always use C:\Murali\Portolfio projects\PricingEngineDjango\venv\Scripts\python.exe for all task execution and package management.

    Terminal Activation: Before running any Python command, the agent MUST run .\venv\Scripts\activate.

    Package Installation: Always use .\venv\Scripts\python.exe -m pip install to ensure packages are installed in the workspace venv.