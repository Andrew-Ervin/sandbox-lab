# Scientific Python baseline

The quick, project, headless AI and GUI images inherit the same CPU package layer.
The reviewed direct inventory is `sandbox/python/requirements.in`; the full transitive,
hash-pinned resolution is `requirements.lock` in that directory. Packages are loaded
on demand, not imported into every run. User code cannot modify the image layer.

| Area | Included tools |
|---|---|
| Data and files | polars, pandas, NumPy, Arrow, xarray, HDF5/netCDF, Excel read/write |
| Numerical and visualization | SciPy, SymPy, Plotly/Kaleido, matplotlib, seaborn, scikit-image, Pillow |
| Statistics / industrial analysis | statsmodels, patsy, pingouin, scikit-posthocs, PyDOE, SALib, reliability, lifelines, arch, lmfit |
| Bayesian | PyMC, ArviZ, emcee |
| Machine learning | scikit-learn, imbalanced-learn, XGBoost, LightGBM, Optuna, SHAP |
| Operations research | SciPy MILP, HiGHS, OR-Tools CP-SAT, CVXPY, Pyomo, PuLP, SimPy, NetworkX |
| Chemistry | RDKit, chemicals, thermo, chempy, periodictable, Pint, uncertainties |
| Materials | ASE, pymatgen, matminer, spglib, pycalphad |

This supports factorial/response-surface DOE, regression and mixed models, hypothesis
and post-hoc tests, survival/reliability fits, sensitivity analysis, probabilistic models,
optimization, chemical descriptors, thermophysical properties and materials features.
It is not full feature parity with R or JMP. Validate statistical assumptions and solver
termination; installed packages do not guarantee the scientific validity of an analysis.
Pyomo/PuLP model problems; HiGHS and OR-Tools supply usable bundled solvers. Commercial
solvers need separate installation/licensing. HiGHS is pinned to 1.12.0 to match
OR-Tools 9.15's native ABI; upgrading either independently can break imports. External databases still require approved
access; installing an API client grants no network permission or credential.

## Quick versus project

Quick retains its 30-second wall-time, 25 CPU-second and 768 MiB memory bounds. Use it
for small calculations, charts and modest scientific jobs. Large MCMC chains, big MILPs,
training, quantum chemistry and atomistic simulations need a project with appropriate
resources. No GPU, CUDA, DFT engine, VASP license, external potential/model weights or
complete deep-learning stack is implied by this baseline. Those require explicit project
setup and, when applicable, dedicated compute. PyMC's compiled cache and plotting caches
are ephemeral. Project venvs remain project-specific; use `uv venv --system-site-packages`
when intentionally inheriting the baseline, or declare a fully isolated uv project.

Quick has no network/package installation at runtime. A genuinely missing dependency
can justify project execution for an actual computation, never for an explanatory question.

## Azure comparison

Microsoft documents NumPy, pandas and scikit-learn as examples, and instructs users to
query their running pool for its actual inventory. No complete immutable list is published
there. We cover those named packages; exact parity with your pool remains unverified.
Export this from your Azure session, then compare it with this image's inventory:

```python
import importlib.metadata as m
print(sorted((d.metadata['Name'], d.version) for d in m.distributions()))
```

Source: https://learn.microsoft.com/en-us/azure/container-apps/sessions-code-interpreter#preinstalled-packages

## Updating and testing

Use uv to compile the inventory with an absolute cutoff at least five days before the
build date, retaining hashes. The current cutoff is 2026-09-02. Update the matching build
cutoff in `sandbox/Dockerfile` too; it covers source-build dependencies. Build native
extensions in the separate compiler stage. Never loosen runtime package/network policy.

```sh
uv pip compile sandbox/python/requirements.in --python-version 3.12 --universal \
  --exclude-newer 2026-09-02 --generate-hashes -o sandbox/python/requirements.lock
docker build --target quick -t sandbox-lab/quick:science -f sandbox/Dockerfile .
# Run sandbox/python/smoke.py inside that image with network disabled.
```

Rebuild all four targets and load them into kind (or publish versioned images to ACR).
Recycle only unused warm pods. Running workspaces keep their current image until a
normal restart; do not destroy their files to update dependencies. Linux arm64 is the
local target; the universal lock also resolves platform markers, but amd64 execution
must be tested in CI before claiming Windows/Linux-host portability.

Package documentation: https://pydoe.github.io/pydoe/ · https://www.pymc.io/projects/docs/en/latest/installation.html · https://pymatgen.org/ · https://ergo-code.github.io/HiGHS/dev/interfaces/python/

## Business files and engineering expansion

The shared baseline also includes:

- Word and presentations: python-docx, docxtpl, mammoth and python-pptx.
- PDF creation, extraction and rasterization: ReportLab, pypdf, pdfplumber and
  pypdfium2. CairoSVG renders SVG to PNG/PDF using the bundled Cairo library.
- Excel/OpenDocument: openpyxl, XlsxWriter, xlrd, python-calamine, pyxlsb and odfpy.
  These are file libraries, not Excel calculation engines or Office macro runtimes.
- QR/barcodes: qrcode, python-barcode and zxing-cpp (generation and decoding).
- Local SQL/text/calendar/archive workflows: DuckDB, RapidFuzz, Markdown, Jinja2,
  BeautifulSoup/lxml, YAML, encoding detection, icalendar, vobject and py7zr.
- Chemical/transport engineering: fluids, ht, CoolProp and Cantera for fluid flow,
  heat transfer, thermophysical properties and reaction kinetics.
- Computational physics: FiPy finite volumes, scikit-fem finite elements, meshio
  mesh interchange, QuTiP quantum systems, and python-control dynamic systems.
- Process monitoring: ruptures change-point detection and PyWavelets supplement
  existing SciPy/statsmodels/DOE/reliability tools. SPC rules and capability indices
  still need an explicit method, subgroup definition and validated assumptions;
  this is not a claim of turnkey JMP or validated industrial SPC parity.

OneNote: exported HTML/PDF and embedded images can be processed offline. Native
`.one` notebook read/write and live notebook sync are not provided. Microsoft Graph
is the supported integration route for OneNote HTML pages, and belongs behind an
approved MCP/Graph integration with user identity and approval policy, not direct
sandbox credentials. No network access is added by these packages.

OCR engines/language data, LibreOffice rendering, OpenFOAM, FEniCS/PETSc/MPI,
GPU frameworks, licensed solvers and large DFT engines remain project-specific.
FiPy enables modest PDE work; installing it does not make the quick environment a
production CFD cluster. Large meshes, reaction networks and quantum simulations
need project resources. Archive extraction must constrain paths and expanded size;
never execute document macros or treat embedded instructions as trusted.

Microsoft SRE lists ReportLab, python-docx and python-pptx among its preinstalled
packages; these gaps are now included. We deliberately do not add its browser
capability. Its 700+ inventory is not a verified inventory of every standard pool.

References:
- https://sre.azure.com/docs/capabilities/code-interpreter#preinstalled-packages
- https://learn.microsoft.com/en-us/graph/integrate-with-onenote
- https://pages.nist.gov/fipy/en/stable/
- https://coolprop.org/coolprop/wrappers/Python/index.html

XGBoost uses the official `xgboost-cpu` distribution (still imported as `xgboost`)
so the CPU image does not carry unused CUDA/NCCL dependencies.
