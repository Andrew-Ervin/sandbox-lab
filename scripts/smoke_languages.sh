#!/bin/bash
# Run inside a persistent test workspace. No host execution of generated code.
set -euo pipefail
export NO_PROXY=localhost,127.0.0.1,.svc,.cluster.local
export JULIA_NUM_PRECOMPILE_TASKS=1
mkdir -p /home/sandbox/project/language-policy-smoke
cd /home/sandbox/project/language-policy-smoke
printf '#include <stdio.h>\nint main(){puts("C:42");}\n' > hello.c
gcc hello.c -o hello-c && ./hello-c
printf '#include <iostream>\nint main(){std::cout << "C++:42\\n";}\n' > hello.cpp
g++ hello.cpp -o hello-cpp && ./hello-cpp
uv venv python-env
uv pip install --python python-env/bin/python humanize==4.13.0
python-env/bin/python -c 'import humanize; print("Python:" + humanize.intcomma(42000))'
mkdir -p js && cd js
npm init -y >/dev/null
npm install --ignore-scripts --save-exact clsx@2.1.1
node -e 'console.log("JS:" + require("clsx")("package", "policy"))'
cd ..
printf 'package main\nimport "fmt"\nfunc main(){fmt.Println("Go:42")}\n' > main.go
go run main.go
mkdir -p rust/src
printf '[package]\nname="language_policy_smoke"\nversion="0.1.0"\nedition="2021"\n[dependencies]\nserde_json="=1.0.143"\n' > rust/Cargo.toml
printf 'fn main(){println!("Rust:{}",serde_json::json!(42));}\n' > rust/src/main.rs
cargo run --quiet --manifest-path rust/Cargo.toml
test -d dotnet || dotnet new console -o dotnet --no-restore >/dev/null
cd dotnet
dotnet add package Newtonsoft.Json --version 13.0.3 >/dev/null
printf 'System.Console.WriteLine("C#:" + Newtonsoft.Json.JsonConvert.SerializeObject(42));\n' > Program.cs
dotnet run --no-restore
cd ..
julia --heap-size-hint=1G --startup-file=no -e 'println("Julia:", sum([20,22]))'
sh -c 'printf "Shell:42\n"'
python - <<'PY'
import urllib.request,urllib.error
base='http://package-proxy.lab-control.svc.cluster.local:3128'
for name,path in [('Go dependency','/go/github.com/google/uuid/@v/v1.6.0.info'),('Julia registry','/julia/registries')]:
 try:
  r=urllib.request.urlopen(base+path,timeout=45);assert r.status==200;print(name+': aged content available')
 except urllib.error.HTTPError as e:
  assert e.code==403;print(name+': policy quarantine is enforced; no exception was created')
PY
printf 'All language execution and approved package checks passed.\n'
