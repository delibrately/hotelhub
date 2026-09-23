"""Export the public retreat pages for static hosting, without accessing the database."""
import argparse
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotelmanagement.settings')
import django

django.setup()
from django.test import RequestFactory
from main.retreat import ROOMS, retreat_home, retreat_room


def export(output, base):
    base = '/' + base.strip('/') + '/' if base.strip('/') else '/'
    output.mkdir(parents=True, exist_ok=True)
    request = RequestFactory().get('/stay/')
    pages = [('index.html', retreat_home(request))]
    pages += [(f'rooms/{room["slug"]}/index.html', retreat_room(request, room['slug'])) for room in ROOMS]
    for relative, response in pages:
        html = response.content.decode('utf-8')
        html = html.replace('/static/retreat/', base + 'assets/')
        html = html.replace('/stay/rooms/', base + 'rooms/').replace('/stay/', base)
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding='utf-8')
    shutil.copytree(ROOT / 'main/static/retreat', output / 'assets', dirs_exist_ok=True)
    (output / '.nojekyll').touch()
    print(f'Exported {len(pages)} pages to {output} (base: {base})')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / '.pages-build')
    parser.add_argument('--base', default='/hotelhub/')
    args = parser.parse_args()
    export(args.output.resolve(), args.base)
