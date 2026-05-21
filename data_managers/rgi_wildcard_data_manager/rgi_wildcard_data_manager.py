import argparse
import gzip
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


def find_card_json(root):
    """Locate card.json in root or one level deep."""
    candidate = os.path.join(root, 'card.json')
    if os.path.exists(candidate):
        return candidate
    for entry in os.listdir(root):
        candidate = os.path.join(root, entry, 'card.json')
        if os.path.exists(candidate):
            return candidate
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True,
                        help='Path to Galaxy data manager output JSON')
    parser.add_argument('--wildcard-url', required=True, dest='wildcard_url',
                        help='URL to card-variants.tar.bz2')
    parser.add_argument('--version', required=True,
                        help='WildCARD version string, e.g. 4.0.0')
    parser.add_argument('--card-url', required=True, dest='card_url',
                        help='URL to card-data.tar.bz2 (provides card.json for rgi wildcard_annotation)')
    parser.add_argument('--data-path', required=True, dest='data_path',
                        help='Galaxy data manager data path')
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Download and extract CARD archive to get card.json
        card_archive = os.path.join(tmpdir, 'card-data.tar.bz2')
        print(f'Downloading CARD data from {args.card_url}', file=sys.stderr)
        download(args.card_url, card_archive)

        print('Extracting CARD archive...', file=sys.stderr)
        card_extract_dir = os.path.join(tmpdir, 'card')
        os.makedirs(card_extract_dir)
        with tarfile.open(card_archive, 'r:bz2') as tf:
            try:
                tf.extractall(card_extract_dir, filter='data')
            except TypeError:
                tf.extractall(card_extract_dir)

        card_json_path = find_card_json(card_extract_dir)
        if card_json_path is None:
            print('ERROR: card.json not found in CARD archive', file=sys.stderr)
            sys.exit(1)
        print(f'Found card.json at {card_json_path}', file=sys.stderr)

        # Download and extract WildCARD archive
        wildcard_archive = os.path.join(tmpdir, 'card-variants.tar.bz2')
        print(f'Downloading WildCARD data from {args.wildcard_url}', file=sys.stderr)
        download(args.wildcard_url, wildcard_archive)

        print('Extracting WildCARD archive...', file=sys.stderr)
        extract_dir = os.path.join(tmpdir, 'wildcard')
        os.makedirs(extract_dir)
        with tarfile.open(wildcard_archive, 'r:bz2') as tf:
            try:
                tf.extractall(extract_dir, filter='data')
            except TypeError:
                tf.extractall(extract_dir)

        # All files in the archive are gzip-compressed (.fasta.gz, .txt.gz).
        # rgi wildcard_annotation matches filenames without .gz and opens them as
        # plain text, so decompress everything before calling rgi.
        print('Decompressing archive files...', file=sys.stderr)
        for gz_path in sorted(os.listdir(extract_dir)):
            if not gz_path.endswith('.gz'):
                continue
            gz_full = os.path.join(extract_dir, gz_path)
            plain_full = gz_full[:-3]  # strip .gz
            with gzip.open(gz_full, 'rb') as f_in, open(plain_full, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
            os.remove(gz_full)

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
                '--card_json', card_json_path,
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
