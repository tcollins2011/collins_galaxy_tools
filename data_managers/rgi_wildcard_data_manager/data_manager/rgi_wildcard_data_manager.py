import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request


def download(url, dest):
    urllib.request.urlretrieve(url, dest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True,
                        help='Path to Galaxy data manager output JSON')
    parser.add_argument('--url', required=True,
                        help='URL to card-variants.tar.bz2')
    parser.add_argument('--version', required=True,
                        help='WildCARD version string, e.g. 4.0.0')
    parser.add_argument('--card-json', required=True, dest='card_json',
                        help='Path to card.json from an installed CARD database')
    parser.add_argument('--data-path', required=True, dest='data_path',
                        help='Galaxy data manager data path')
    args = parser.parse_args()

    if not os.path.exists(args.card_json):
        print(f'ERROR: card.json not found at {args.card_json}', file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        archive = os.path.join(tmpdir, 'card-variants.tar.bz2')
        print(f'Downloading WildCARD data from {args.url}', file=sys.stderr)
        download(args.url, archive)

        print('Extracting archive...', file=sys.stderr)
        extract_dir = os.path.join(tmpdir, 'wildcard')
        os.makedirs(extract_dir)
        with tarfile.open(archive, 'r:bz2') as tf:
            tf.extractall(extract_dir)

        # index-for-model-sequences.txt ships in the archive
        index_src = os.path.join(extract_dir, 'index-for-model-sequences.txt')
        if not os.path.exists(index_src):
            print('ERROR: index-for-model-sequences.txt not found in archive',
                  file=sys.stderr)
            sys.exit(1)

        # rgi wildcard_annotation writes annotation FASTAs to cwd
        print('Running rgi wildcard_annotation...', file=sys.stderr)
        subprocess.run(
            [
                'rgi', 'wildcard_annotation',
                '--input_directory', extract_dir,
                '--version', args.version,
                '--card_json', args.card_json,
            ],
            cwd=tmpdir,
            check=True,
        )

        annotation_src = os.path.join(tmpdir, f'wildcard_database_v{args.version}.fasta')
        annotation_all_src = os.path.join(tmpdir, f'wildcard_database_v{args.version}_all.fasta')
        for path in (annotation_src, annotation_all_src):
            if not os.path.exists(path):
                print(f'ERROR: expected output not found: {path}', file=sys.stderr)
                sys.exit(1)

        dest_dir = os.path.join(args.data_path, 'rgi_wildcard', args.version)
        os.makedirs(dest_dir, exist_ok=True)

        annotation_dst = os.path.join(dest_dir, f'wildcard_database_v{args.version}.fasta')
        annotation_all_dst = os.path.join(dest_dir, f'wildcard_database_v{args.version}_all.fasta')
        index_dst = os.path.join(dest_dir, 'index-for-model-sequences.txt')

        shutil.copy2(annotation_src, annotation_dst)
        shutil.copy2(annotation_all_src, annotation_all_dst)
        shutil.copy2(index_src, index_dst)
        print(f'Database stored at {dest_dir}', file=sys.stderr)

    value = 'wildcard_{}'.format(args.version.replace('.', '_'))
    name = f'WildCARD {args.version}'
    data_manager_dict = {
        'data_tables': {
            'rgi_wildcard': [{
                'value': value,
                'name': name,
                'wildcard_annotation': annotation_dst,
                'wildcard_annotation_all_models': annotation_all_dst,
                'wildcard_index': index_dst,
                'wildcard_version': args.version,
            }]
        }
    }
    with open(args.out, 'w') as f:
        json.dump(data_manager_dict, f, sort_keys=True)
    print('Done.', file=sys.stderr)


if __name__ == '__main__':
    main()
