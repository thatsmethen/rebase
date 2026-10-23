"""Reproduce declared original LC_FUNCTION_STARTS intervals into a NEW directory."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'));import source_tools as s
P={1: [4324920288, 4324919856, 4325654132, 4327087256], 2: [4324911376, 4324913600, 4324919504, 4324919596, 4324919636, 4324919696, 4324919724, 4324919972, 4324920712], 3: [4327761244, 4327761708, 4324920808, 4324920916, 4324920952, 4324921160], 4: [4327760308, 4327760524, 4327760796, 4327760956, 4327761048, 4327761136, 4324465108], 5: [4324465816, 4324466052, 4324466488, 4324466644, 4325837912, 4325840968, 4325841124, 4325881192], 6: [4325657140, 4325667672, 4324922092, 4324922756]}
if __name__=='__main__':
 destination=Path(sys.argv[1]);destination.mkdir(exist_ok=False)
 for n,addresses in P.items():s.derive(addresses,destination/f'pass{n}')
