"""NCAIFinal 개발 허브 공개본 내보내기.

비공개 저장소(KDNA-Gwangju-1/NCAIFinal)의 git ref(기본 origin/main)에서 허브 생성기와 자료를 꺼내
허브 데이터를 만든 뒤, 이미지를 줄여 img/에 복사하고 로컬 문서 링크를 빼서 이 폴더의 index.html로 쓴다.
GitHub Pages가 이 폴더를 그대로 서빙한다. 작업 공간이 어느 브랜치에 있든 결과는 ref 기준이다.

    python export.py                          # origin/main 기준, gh로 보드를 새로 읽는다
    python export.py --ref origin/<브랜치>    # 병합 전 브랜치로 미리 보기
    python export.py --repo <경로>            # 원본 저장소 (기본: 메인 NCAIFinal)

push는 하지 않는다. 결과를 보고 사람이 커밋·push한다.
공개본 규칙과 이유는 원본 Tools/dev-hub/README.md "도감 정리 원칙"에 있다.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.parse

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(HERE, "img")
SRC_DIR = os.path.join(HERE, ".src")  # ref에서 꺼낸 원본 (git 제외)
DEFAULT_REPO = os.path.join(os.path.expanduser("~"), "Documents", "UnityProject", "NCAIFinal")
PATHS = ["Tools/dev-hub", "Docs", ".wf/issues", "Assets/Data"]  # 허브가 읽는 경로
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")
MAX_SIDE = 1280
QUALITY = 80
# 공개본에 넣지 않는 이미지
# - 남이 그린 원본 그림 (예: 원화-칠보산도-….jpg)
# - 외부 게임 의상을 참고한 폐기 시안 (체른풍 T포즈 v1~v6, 2026-10-07 사용자 요청)
EXCLUDE = re.compile(r"(^|/)원화-|체른풍-Tpose/v[1-6]-")
# 공개본에서 빼는 도감 버전 (이름 앞부분). 연속된 묶음은 이미지 없는 탭 하나로 바꿔 번호를 잇는다
HIDE_VERSIONS = ("체른풍 T포즈", "로아풍·검사풍", "호평 디자인 조사", "유료 아바타 기준", "키트 아바타 기준")
CLOSED_NAME = "폐기 시안"
CLOSED_SUMMARY = "외부 게임 의상을 참고해 만든 시안들이다. 채택하지 않았고 공개본에서는 뺐다."


def git(repo, *args, **kw):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, **kw).stdout


def extract(repo, ref):
    """ref의 허브 관련 경로를 .src/에 꺼낸다. 같은 커밋이면 다시 꺼내지 않는다."""
    sha = git(repo, "rev-parse", ref, text=True).strip()
    stamp = os.path.join(SRC_DIR, ".commit")
    if os.path.isfile(stamp) and open(stamp).read().strip() == sha:
        return sha
    shutil.rmtree(SRC_DIR, ignore_errors=True)
    os.makedirs(SRC_DIR)
    data = git(repo, "archive", "--format=tar", sha, "--", *PATHS)
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        tf.extractall(SRC_DIR, filter="data")
    with open(stamp, "w") as f:
        f.write(sha)
    return sha


def load_hub(src):
    path = os.path.join(src, "Tools", "dev-hub", "build_hub.py")
    spec = importlib.util.spec_from_file_location("build_hub", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def close_hidden(versions):
    """HIDE_VERSIONS 버전을 빼고, 연속된 묶음 자리에 이미지 없는 탭 하나를 둔다."""
    out, run = [], []
    for v in versions + [None]:
        if v is not None and (v.get("name") or "").startswith(HIDE_VERSIONS):
            run.append(v)
            continue
        if run:
            out.append({"name": CLOSED_NAME, "date": run[0].get("date", ""), "summary": CLOSED_SUMMARY,
                        "review": "", "why": "", "next": "", "issues": [], "items": [], "missing": 0,
                        "prompts": [], "span": sum(x.get("span", 1) for x in run), "closed": True})
            run = []
        if v is not None:
            out.append(v)
    return out


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
            stem = os.path.splitext(os.path.basename(path))[0]  # 화면 설명에 파일 이름이 보이므로 남긴다
            name = f"{stem}-{hashlib.sha1(data).hexdigest()[:8]}.webp"
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
    ap.add_argument("--repo", default=DEFAULT_REPO, help="원본 저장소")
    ap.add_argument("--ref", default="origin/main", help="내보낼 git ref")
    ap.add_argument("--offline", action="store_true", help="gh 호출 없이 직전 cache.json 사용")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    git(a.repo, "fetch", "-q", "origin")
    sha = extract(a.repo, a.ref)
    hub = load_hub(SRC_DIR)
    os.makedirs(hub.OUT_DIR, exist_ok=True)
    if a.offline:
        data = json.load(io.open(hub.CACHE, encoding="utf-8"))
    else:
        data = hub.fetch()
        with io.open(hub.CACHE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    model = hub.build(data)
    model["labMissing"] = []
    for ents in model["lab"].values():
        for e in ents:
            e["versions"] = close_hidden(e.get("versions", []))

    os.makedirs(IMG_DIR, exist_ok=True)
    ex = Exporter(hub)
    model = ex.walk(model)

    tpl = io.open(os.path.join(SRC_DIR, "Tools", "dev-hub", "template.html"), encoding="utf-8").read()
    payload = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    with io.open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as f:
        f.write(tpl.replace("/*__DATA__*/null", payload))

    removed = 0
    for name in os.listdir(IMG_DIR):  # 이번에 안 쓴 이미지는 지운다 (이력에는 남는다)
        if name not in ex.used:
            os.remove(os.path.join(IMG_DIR, name))
            removed += 1
    size = sum(os.path.getsize(os.path.join(IMG_DIR, n)) for n in ex.used)
    print(f"생성: index.html ({a.ref} {sha[:7]}, 이슈 {len(model['issues'])}, "
          f"이미지 {len(ex.used)}장 {size / 1e6:.1f}MB, 지운 이미지 {removed})")
    for why, rel in ex.skipped:
        print(f"  건너뜀({why}): {rel}")


if __name__ == "__main__":
    main()
