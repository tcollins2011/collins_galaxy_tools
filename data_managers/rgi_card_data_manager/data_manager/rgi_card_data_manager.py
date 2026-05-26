import argparse
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
    parser.add_argument('--url', required=True,
                        help='URL or local path to card-data.tar.bz2')
    args = parser.parse_args()

    params = json.load(open(args.output_file))
    target_directory = params['output_data'][0]['extra_files_path']
    os.makedirs(target_directory, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        archive = os.path.join(tmpdir, 'card-data.tar.bz2')
        print(f'Fetching CARD data from {args.url}', file=sys.stderr)
        get_archive(args.url, archive)

        print('Extracting archive...', file=sys.stderr)
        with tarfile.open(archive, 'r:bz2') as tf:
            try:
                tf.extractall(tmpdir, filter='data')
            except TypeError:
                tf.extractall(tmpdir)

        card_json_src = find_card_json(tmpdir)
        if card_json_src is None:
            print('ERROR: card.json not found in archive', file=sys.stderr)
            sys.exit(1)

        with open(card_json_src) as f:
            card_data = json.load(f)
        version = card_data['_version']
        print(f'CARD version: {version}', file=sys.stderr)

        work_dir = os.path.join(tmpdir, 'annotation')
        os.makedirs(work_dir)
        shutil.copy2(card_json_src, os.path.join(work_dir, 'card.json'))

        print('Running rgi card_annotation...', file=sys.stderr)
        subprocess.run(
            ['rgi', 'card_annotation', '-i', 'card.json'],
            cwd=work_dir,
            check=True,
        )

        annotation_src = os.path.join(work_dir, f'card_database_v{version}.fasta')
        annotation_all_src = os.path.join(work_dir, f'card_database_v{version}_all.fasta')
        for path in (annotation_src, annotation_all_src):
            if not os.path.exists(path):
                print(f'ERROR: expected output not found: {path}', file=sys.stderr)
                sys.exit(1)

        card_json_dst = os.path.join(target_directory, 'card.json')
        annotation_dst = os.path.join(target_directory, 'card_annotation.fasta')
        annotation_all_dst = os.path.join(target_directory, 'card_annotation_all.fasta')

        shutil.copy2(card_json_src, card_json_dst)
        shutil.copy2(annotation_src, annotation_dst)
        shutil.copy2(annotation_all_src, annotation_all_dst)
        print(f'Database stored at {target_directory}', file=sys.stderr)

    data_manager_dict = {
        'data_tables': {
            'rgi_card': [{
                'value': 'card_{}'.format(version.replace('.', '_')),
                'name': f'CARD {version}',
                'card_json': target_directory,
                'card_annotation': '',
                'card_annotation_all_models': '',
                'card_version': version,
            }]
        }
    }
    with open(args.output_file, 'w') as f:
        json.dump(data_manager_dict, f, sort_keys=True)
    print('Done.', file=sys.stderr)


if __name__ == '__main__':
    main()
