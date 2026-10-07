"""NCAIFinal 개발 허브 공개본 내보내기.

비공개 저장소(KDNA-Gwangju-1/NCAIFinal)의 Tools/dev-hub/build_hub.py로 허브 데이터를 만든 뒤,
이미지를 줄여 img/에 복사하고 로컬 문서 링크를 빼서 이 폴더의 index.html로 쓴다.
GitHub Pages가 이 폴더를 그대로 서빙한다.

    python export.py                 # gh로 보드를 새로 읽어 생성
    python export.py --offline       # 원본 작업 공간의 직전 cache.json으로 생성
    python export.py --src <경로>    # 원본 작업 공간 (기본: 메인 NCAIFinal)

push는 하지 않는다. 결과를 보고 사람이 커밋·push한다.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import urllib.parse

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(HERE, "img")
DEFAULT_SRC = os.path.join(os.path.expanduser("~"), "Documents", "UnityProject", "NCAIFinal")
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")
MAX_SIDE = 1280
QUALITY = 80
# 남이 그린 원본 그림은 공개본에 넣지 않는다 (예: 원화-칠보산도-….jpg)
EXCLUDE = re.compile(r"(^|/)원화-")


def load_hub(src):
    path = os.path.join(src, "Tools", "dev-hub", "build_hub.py")
    spec = importlib.util.spec_from_file_location("build_hub", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Exporter:
    def __init__(self, hub):
        self.hub = hub
        self.used = set()
        self.skipped = []
        self.cache = {}

    def local(self, url):
        return isinstance(url, str) and url.startswith("../")

    def image(self, url):
        """상대 URL 이미지를 img/<해시>.webp로 바꾼다. 못 쓰면 None."""
        if url in self.cache:
            return self.cache[url]
        rel = urllib.parse.unquote(url)
        path = os.path.normpath(os.path.join(self.hub.OUT_DIR, rel))
        out = None
        if EXCLUDE.search(rel.replace("\\", "/")):
            self.skipped.append(("제외", rel))
        elif not os.path.isfile(path) or not path.lower().endswith(IMG_EXT):
            self.skipped.append(("없음", rel))
        else:
            data = open(path, "rb").read()
            name = hashlib.sha1(data).hexdigest()[:16] + ".webp"
            dst = os.path.join(IMG_DIR, name)
            if not os.path.exists(dst):
                im = Image.open(io.BytesIO(data))
                im = im.convert("RGBA" if "A" in im.getbands() or im.mode == "P" else "RGB")
                im.thumbnail((MAX_SIDE, MAX_SIDE))
                im.save(dst, "WEBP", quality=QUALITY, method=6)
            self.used.add(name)
            out = "img/" + name
        self.cache[url] = out
        return out

    def walk(self, v):
        if isinstance(v, dict):
            out = {}
            for k, x in v.items():
                if k in ("src", "cover") and self.local(x):
                    x = self.image(x)
                    if x is None and k == "src":
                        return None  # 이미지 항목 자체를 뺀다
                elif k == "doc" and self.local(x):
                    x = None  # 로컬 문서는 공개본에 없다
                elif k == "docs" and isinstance(x, list):
                    x = [d for d in x if not (isinstance(d, list) and len(d) == 2 and self.local(d[1]))]
                else:
                    x = self.walk(x)
                out[k] = x
            return out
        if isinstance(v, list):
            return [y for y in (self.walk(x) for x in v) if y is not None]
        return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC, help="원본 작업 공간")
    ap.add_argument("--offline", action="store_true", help="gh 호출 없이 원본의 cache.json 사용")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    hub = load_hub(a.src)
    if a.offline:
        data = json.load(io.open(hub.CACHE, encoding="utf-8"))
    else:
        data = hub.fetch()
    model = hub.build(data)
    model["labMissing"] = []

    os.makedirs(IMG_DIR, exist_ok=True)
    ex = Exporter(hub)
    model = ex.walk(model)

    tpl = io.open(os.path.join(a.src, "Tools", "dev-hub", "template.html"), encoding="utf-8").read()
    payload = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    with io.open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as f:
        f.write(tpl.replace("/*__DATA__*/null", payload))

    removed = 0
    for name in os.listdir(IMG_DIR):  # 이번에 안 쓴 이미지는 지운다 (이력에는 남는다)
        if name not in ex.used:
            os.remove(os.path.join(IMG_DIR, name))
            removed += 1
    size = sum(os.path.getsize(os.path.join(IMG_DIR, n)) for n in ex.used)
    print(f"생성: index.html (이슈 {len(model['issues'])}, 이미지 {len(ex.used)}장 {size / 1e6:.1f}MB, 지운 이미지 {removed})")
    for why, rel in ex.skipped:
        print(f"  건너뜀({why}): {rel}")


if __name__ == "__main__":
    main()
