#!/usr/bin/env python3
"""Record bounded static HDF5/SOFA metadata and decoded numeric-array hashes.

Requires existing h5py/numpy installations. Does not infer runtime use, validate
the complete SOFA convention, execute target code, or follow external data.
"""
import argparse
import hashlib
import json
import pathlib
import platform

import h5py
import numpy as np


def digest(data):
    return hashlib.sha256(data).hexdigest()


def value(item):
    if isinstance(item, h5py.Empty):
        return {'hdf5_empty_dtype': str(item.dtype)}
    if isinstance(item, bytes):
        try:
            return item.decode('utf-8')
        except UnicodeDecodeError:
            return {'invalid_utf8_bytes_hex': item.hex()}
    if hasattr(item, 'tolist'):
        return value(item.tolist())
    if isinstance(item, (list, tuple)):
        return [value(x) for x in item]
    return item


def inspect(path):
    report = {'scope': __doc__, 'path': str(path.resolve()),
              'file_bytes': path.stat().st_size, 'file_sha256': digest(path.read_bytes()),
              'reader': {'python': platform.python_version(), 'h5py': h5py.__version__,
                         'hdf5': h5py.version.hdf5_version, 'numpy': np.__version__},
              'datasets': []}
    with h5py.File(path, 'r') as handle:
        report['root_attributes'] = {k: value(v) for k, v in handle.attrs.items()}
        for name in handle:
            if not isinstance(handle.get(name, getlink=True), h5py.HardLink):
                raise ValueError('nonlocal HDF5 link unsupported')
            dataset = handle[name]
            if not isinstance(dataset, h5py.Dataset):
                raise ValueError('nested group unsupported by this bounded reader')
            if dataset.is_virtual or dataset.external:
                raise ValueError('external or virtual dataset unsupported')
            if dataset.size * dataset.dtype.itemsize > 32 * 1024 * 1024:
                raise ValueError('dataset exceeds 32 MiB bound')
            properties = dataset.id.get_create_plist()
            filters = []
            for index in range(properties.get_nfilters()):
                fid, flags, args, filtername = properties.get_filter(index)
                if fid not in (1, 2, 3):
                    raise ValueError(f'unsupported HDF5 filter {fid}')
                filters.append({'id': fid, 'flags': flags, 'arguments': list(args), 'name': value(filtername)})
            array = dataset[()]
            if not np.issubdtype(array.dtype, np.number) or not np.isfinite(array).all():
                raise ValueError('only finite numeric datasets supported')
            canonical = np.asarray(array, dtype='<f8', order='C')
            record = {'name': name, 'shape': list(dataset.shape), 'dtype': str(dataset.dtype),
                      'attributes': {k: value(v) for k, v in dataset.attrs.items()
                                     if k not in ('DIMENSION_LIST', 'REFERENCE_LIST')},
                      'dimension_scale_paths': [[scale.name for scale in dim.values()] for dim in dataset.dims],
                      'filters': filters, 'all_values_finite': True,
                      'decoded_float64_le_c_order_sha256': digest(canonical.tobytes(order='C'))}
            if array.size:
                record.update({'minimum': float(array.min()), 'maximum': float(array.max())})
            if array.size <= 16:
                record['values'] = value(array)
            report['datasets'].append(record)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=pathlib.Path)
    parser.add_argument('--output', required=True, type=pathlib.Path)
    args = parser.parse_args()
    report = inspect(args.path)
    source = pathlib.Path(__file__).read_bytes()
    report['reader_sha256'] = digest(source)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'reader-snapshot.py').write_bytes(source)
    (args.output / 'inspection.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'file_sha256': report['file_sha256'], 'datasets': len(report['datasets']),
                      'output': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()
