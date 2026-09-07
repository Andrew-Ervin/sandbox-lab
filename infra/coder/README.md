# Sandbox Lab workspace templates

Two separate copies of this template are published by setup:

- `developer`: human-owned GUI workspace in `lab-dev`. VS Code, Ori/Pi, Python, JS/TS, C#/.NET, Julia, Go, Rust, C/C++ and shell. Use it independently of chat.
- `ai-headless`: Coder Agents execution workspace in `lab-agents`. No VS Code or GUI service. Python, Node, .NET, Julia, Go, Rust, GCC/G++, Clang, CMake, shell, polars, Plotly and scikit-learn are preinstalled. Work in `/home/sandbox/project`. Write downloadable results to `artifacts/`. Use port 3000 for web application previews. Install Python packages in a project virtual environment and Node packages in the project. Model credentials live in the Coder control plane.

The code-server app only exists when `gui=true`. The headless template uses the project image, which contains no coding-agent harness. Coder Agents connects through the Coder workspace agent.
