"""Offline scientific baseline checks. Run inside the built image as uid 1000."""
import json,subprocess,sys,time
CHECKS = {
 'statistics_doe': "from pydoe import ff2n; import numpy as np; import statsmodels.api as sm; x=ff2n(3); assert x.shape==(8,3); fit=sm.OLS(np.arange(8),sm.add_constant(x)).fit(); assert len(fit.params)==4; import pingouin,scikit_posthocs,reliability,lifelines,arch",
 'bayesian': "import pymc as pm,arviz,emcee; import numpy as np; m=pm.Model();\nwith m:\n x=pm.Normal('x',0,1)\n assert np.isfinite(m.compile_logp()(m.initial_point()))",
 'milp': "from scipy.optimize import milp,Bounds; r=milp(c=[-1.],integrality=[1],bounds=Bounds([0],[3])); assert r.success and abs(r.x[0]-3)<1e-8; import highspy,cvxpy,pyomo.environ,pulp; from ortools.sat.python import cp_model; m=cp_model.CpModel();x=m.new_int_var(0,3,'x');m.maximize(x);s=cp_model.CpSolver();s.parameters.num_search_workers=1;assert s.solve(m)==cp_model.OPTIMAL and s.value(x)==3",
 'ml': "import numpy as np; from sklearn.ensemble import RandomForestRegressor; m=RandomForestRegressor(n_estimators=2,n_jobs=1).fit([[0],[1],[2]],[0,1,2]);assert len(m.predict([[1]]))==1;import xgboost,lightgbm,shap,optuna,imblearn",
 'chemistry': "from rdkit import Chem; assert Chem.MolFromSmiles('CCO').GetNumAtoms()==3; from chemicals import MW; assert MW('7732-18-5')>18; from thermo import Chemical; assert Chemical('water').MW>18; import chempy,periodictable",
 'materials': "from ase.build import bulk; assert len(bulk('Cu','fcc'))==1;from pymatgen.core import Lattice,Structure; s=Structure(Lattice.cubic(3),['Fe'],[[0,0,0]]);assert len(s)==1;import matminer,spglib;from pycalphad import Database;assert Database() is not None",
 'files': "import polars as pl,pandas,pyarrow,openpyxl,xlsxwriter,xlrd,h5py,netCDF4,xarray;assert pl.DataFrame({'a':[1,2]}).select(pl.col('a').sum()).item()==3;import plotly,matplotlib,seaborn,skimage,PIL,sympy,pint,uncertainties,lmfit,SALib,simpy,networkx",
}
CHECKS.update({
 'documents': "import tempfile; from pathlib import Path; from docx import Document; from pptx import Presentation; from reportlab.pdfgen import canvas; from pypdf import PdfReader; import pdfplumber,pypdfium2,docxtpl,mammoth,odf,python_calamine,pyxlsb; d=Path(tempfile.mkdtemp()); w=Document();w.add_paragraph('Lab report');w.save(d/'a.docx');assert Document(d/'a.docx').paragraphs[0].text=='Lab report'; p=Presentation();p.slides.add_slide(p.slide_layouts[6]);p.save(d/'a.pptx');assert len(Presentation(d/'a.pptx').slides)==1;c=canvas.Canvas(str(d/'a.pdf'));c.drawString(30,100,'Lab report');c.save();assert 'Lab report' in PdfReader(d/'a.pdf').pages[0].extract_text()",
 'productivity': "import qrcode,zxingcpp,barcode,cairosvg,duckdb,rapidfuzz,icalendar,vobject,py7zr; im=qrcode.make('sandbox-lab').convert('RGB');assert zxingcpp.read_barcode(im).text=='sandbox-lab';assert duckdb.sql('select sum(x) from (values (1),(2)) t(x)').fetchone()[0]==3;assert cairosvg.svg2png(bytestring=b'<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"10\" height=\"10\"/>').startswith(b'\\x89PNG')",
 'engineering_physics': "from CoolProp.CoolProp import PropsSI;assert 990<PropsSI('D','T',300,'P',101325,'Water')<1000;import fluids,ht,cantera,skfem,meshio,control,ruptures,pywt;g=cantera.Solution('gri30.yaml');assert g.n_species>0;from fipy import Grid1D,CellVariable,DiffusionTerm;mesh=Grid1D(nx=10,dx=1.);v=CellVariable(mesh=mesh,value=0.);v.constrain(0.,mesh.facesLeft);v.constrain(1.,mesh.facesRight);DiffusionTerm().solve(var=v);assert abs(float(v.value.mean())-0.5)<1e-6;from qutip import basis;assert abs(basis(2,0).norm()-1)<1e-9",
})
failed=[]
for name,code in CHECKS.items():
 start=time.monotonic();p=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=120)
 print(json.dumps({'check':name,'seconds':round(time.monotonic()-start,2),'ok':p.returncode==0,'error':p.stderr[-3000:] if p.returncode else ''}),flush=True)
 if p.returncode:failed.append(name)
if failed:raise SystemExit(', '.join(failed))
