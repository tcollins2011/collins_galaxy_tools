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


def get_archive(url, dest):
    if url.startswith(('http://', 'https://', 'ftp://')):
        urllib.request.urlretrieve(url, dest)
    else:
        shutil.copy2(url, dest)


def find_card_json(root):
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
    parser.add_argument('output_file',
                        help='Galaxy data manager output JSON file')
    parser.add_argument('--wildcard-url', required=True, dest='wildcard_url',
                        help='URL or local path to card-variants.tar.bz2')
    parser.add_argument('--version', required=True,
                        help='WildCARD version string, e.g. 4.0.0')
    parser.add_argument('--card-url', required=True, dest='card_url',
                        help='URL or local path to card-data.tar.bz2')
    args = parser.parse_args()

    params = json.load(open(args.output_file))
    target_directory = params['output_data'][0]['extra_files_path']
    os.makedirs(target_directory, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        card_archive = os.path.join(tmpdir, 'card-data.tar.bz2')
        wildcard_archive = os.path.join(tmpdir, 'card-variants.tar.bz2')

        print(f'Fetching CARD data from {args.card_url}', file=sys.stderr)
        get_archive(args.card_url, card_archive)
        print(f'Fetching WildCARD data from {args.wildcard_url}', file=sys.stderr)
        get_archive(args.wildcard_url, wildcard_archive)

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

        print('Extracting WildCARD archive...', file=sys.stderr)
        extract_dir = os.path.join(tmpdir, 'wildcard')
        os.makedirs(extract_dir)
        with tarfile.open(wildcard_archive, 'r:bz2') as tf:
            try:
                tf.extractall(extract_dir, filter='data')
            except TypeError:
                tf.extractall(extract_dir)

        print('Decompressing archive files...', file=sys.stderr)
        for gz_path in sorted(os.listdir(extract_dir)):
            if not gz_path.endswith('.gz'):
                continue
            gz_full = os.path.join(extract_dir, gz_path)
            plain_full = gz_full[:-3]
            with gzip.open(gz_full, 'rb') as f_in, open(plain_full, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
            os.remove(gz_full)

        index_src = os.path.join(extract_dir, 'index-for-model-sequences.txt')
        if not os.path.exists(index_src):
            print('ERROR: index-for-model-sequences.txt not found in archive',
                  file=sys.stderr)
            sys.exit(1)

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

        annotation_dst = os.path.join(target_directory, f'wildcard_database_v{args.version}.fasta')
        annotation_all_dst = os.path.join(target_directory, f'wildcard_database_v{args.version}_all.fasta')
        index_dst = os.path.join(target_directory, 'index-for-model-sequences.txt')

        shutil.copy2(annotation_src, annotation_dst)
        shutil.copy2(annotation_all_src, annotation_all_dst)
        shutil.copy2(index_src, index_dst)
        print(f'Database stored at {target_directory}', file=sys.stderr)

    data_manager_dict = {
        'data_tables': {
            'rgi_wildcard': [{
                'value': 'wildcard_{}'.format(args.version.replace('.', '_')),
                'name': f'WildCARD {args.version}',
                'wildcard_annotation': annotation_dst,
                'wildcard_annotation_all_models': annotation_all_dst,
                'wildcard_index': index_dst,
                'wildcard_version': args.version,
            }]
        }
    }
    with open(args.output_file, 'w') as f:
        json.dump(data_manager_dict, f, sort_keys=True)
    print('Done.', file=sys.stderr)


if __name__ == '__main__':
    main()
