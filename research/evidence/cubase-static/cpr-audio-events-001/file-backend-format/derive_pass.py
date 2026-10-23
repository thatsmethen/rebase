"""Create new bounded derivatives; never execute the qualified target."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s

directory = HERE / ('pass' + sys.argv[1])
assert directory.is_dir() and not list(directory.iterdir()), 'Pass must be empty'
entries = [int(x, 16) for x in sys.argv[2:]]
assert entries and len(entries) == len(set(entries))
rows = s.derive(entries, directory)
print([(r['entry'], r['length']) for r in rows])
