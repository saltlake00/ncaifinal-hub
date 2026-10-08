"""NCAIFinal 개발 허브 공개본 내보내기.

비공개 저장소(KDNA-Gwangju-1/NCAIFinal)의 git ref(기본 origin/main)에서 허브 생성기와 자료를 꺼내
허브 데이터를 만든 뒤, 이미지를 줄여 img/에 복사하고 로컬 문서 링크를 빼서 이 폴더의 index.html로 쓴다.
GitHub Pages가 이 폴더를 그대로 서빙한다. 작업 공간이 어느 브랜치에 있든 결과는 ref 기준이다.

    python export.py                          # origin/main 기준, gh로 보드를 새로 읽는다
    python export.py --ref origin/<브랜치>    # 병합 전 브랜치로 미리 보기
    python export.py --repo <경로>            # 원본 저장소 (기본: 환경 변수 NCAIFINAL_REPO,
                                              #  없으면 ~/Documents/UnityProject/NCAIFinal·E:/UnityProject/NCAIFinal 중 있는 것)

push는 하지 않는다. 결과를 보고 사람이 커밋·push한다.
비공개 저장소로 가는 링크(이슈·PR·커밋·보드)는 지우고, 문자열 속 이메일·로컬 경로·브랜치명은 가린다.
마지막에 index.html을 검사해 남은 것이 있으면 종료 코드 1로 멈춘다.
첫 화면을 Edge 헤드리스로 찍어 preview.webp(고정 주소, 블로그 카드용)로 덮어쓰고 <head>에 og 태그를 넣는다.
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
import tempfile
import urllib.parse

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(HERE, "img")
SRC_DIR = os.path.join(HERE, ".src")  # ref에서 꺼낸 원본 (git 제외)
# 원본 저장소: 환경 변수 NCAIFINAL_REPO > PC마다 다른 기본 위치 중 있는 것
REPO_CANDIDATES = [os.environ.get("NCAIFINAL_REPO", ""),
                   os.path.join(os.path.expanduser("~"), "Documents", "UnityProject", "NCAIFinal"),
                   r"E:\UnityProject\NCAIFinal"]
DEFAULT_REPO = next((p for p in REPO_CANDIDATES if p and os.path.isdir(os.path.join(p, ".git"))), None)
PATHS = ["Tools/dev-hub", "Docs", ".wf/issues", "Assets/Data"]  # 허브가 읽는 경로
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")
MAX_SIDE = 1280
QUALITY = 80
# 공개본에 넣지 않는 이미지
# - 남이 그린 원본 그림 (예: 원화-칠보산도-….jpg)
# - 외부 게임 의상을 참고한 폐기 시안 (체른풍 T포즈 v1~v6, 2026-10-07 사용자 요청)
EXCLUDE = re.compile(r"(^|/)원화-|체른풍-Tpose/v[1-6]-")
# 공개본에서 빼는 도감 버전 (이름 앞부분). 연속된 묶음은 이미지 없는 탭 하나로 바꾸고,
# 뒤 탭 번호는 설계 버전(v7…)에 맞춘다 (number_by_design)
HIDE_VERSIONS = ("체른풍 T포즈", "로아풍·검사풍", "호평 디자인 조사", "유료 아바타 기준", "키트 아바타 기준")
PRIVATE = re.compile(r"^https?://github\.com/(?:orgs/)?KDNA-Gwangju-1\b")  # 원본 조직(비공개). 공개본에서는 404
SITE = "https://saltlake00.github.io/ncaifinal-hub/"
PREVIEW = "preview.webp"  # 고정 이름: 블로그 TIL 맨 위 카드가 SITE + PREVIEW를 하드코딩한다
EDGES = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
         r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
# 공개본 문자열에서 가리는 것: (패턴, 바꿀 글자). 이미지 경로(src·cover)에는 쓰지 않는다
SCRUB = [
    (re.compile(r"https://github\.com/KDNA-Gwangju-1/NCAIFinal/(?:issues|pull)/(\d+)\S*"), r"#\1"),
    (re.compile(r"https?://github\.com/(?:orgs/)?KDNA-Gwangju-1\S*"), "(비공개 저장소)"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "(메일 가림)"),
    (re.compile(r"(?<![\w/])[A-Za-z]:[\\/](?:내 드라이브[\\/])?[^\s`'\")\]]*"), "(로컬 경로)"),
    (re.compile(r"/c/Users/[^\s`'\")\]]*"), "(로컬 경로)"),
    (re.compile(r"\b(?:feat|fix|chore|docs|tool|refactor|codex|claude)/[\w.-]+"), "(브랜치)"),
]
# 최종 검사: 비공개 조직 이름, 이메일, 로컬 경로(JSON 이스케이프·URL 인코딩 포함), 브랜치명
AUDIT = re.compile(r"KDNA-Gwangju-1|[\w.+-]+(?:@|%40)[\w-]+\.[a-z]{2,}|(?<![\w/])[A-Za-z]:(?:\\\\|/|%2F)"
                   r"|/c/Users/|\b(?:feat|fix|chore|docs|tool|refactor|codex|claude)/[\w.-]+")
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
    return number_by_design(out)


VER_SUFFIX = re.compile(r"\s*·\s*v(\d+)(?:[–-]v?(\d+))?$")  # 이름 끝 설계 버전 "· v7", "· v8–v9"


def number_by_design(versions):
    """탭 번호를 이름 끝 설계 버전에 맞춘다. 폐기 묶음은 다음 설계 버전 앞 번호까지 차지하고(V3–6 → V7),
    번호와 같아진 설계 버전 꼬리표는 이름에서 뺀다. 맞출 수 없으면 그대로 둔다."""
    no = 1
    for n, v in enumerate(versions):
        nxt = VER_SUFFIX.search(versions[n + 1].get("name") or "") if n + 1 < len(versions) else None
        m = VER_SUFFIX.search(v.get("name") or "")
        if v.get("closed") and nxt and int(nxt.group(1)) > no:
            v["span"] = int(nxt.group(1)) - no
        elif m and int(m.group(1)) == no:
            v["name"] = v["name"][:m.start()]
            v["span"] = int(m.group(2) or m.group(1)) - no + 1
        no += v.get("span", 1)
    return versions


def scrub(s):
    for pat, rep in SCRUB:
        s = pat.sub(rep, s)
    return s


def audit(html):
    """공개하면 안 되는 문자열을 찾는다. (위치, 앞뒤 글자) 목록."""
    return [(m.start(), html[max(0, m.start() - 40):m.end() + 20].replace("\n", " "))
            for m in AUDIT.finditer(html)]


def og_tags(html, model):
    """<head>에 공유 미리보기(og) 태그를 넣는다."""
    done = sum(i["status"] == "완료" for i in model["issues"])
    desc = (f"Unity 1인 개발 마법 보스 러쉬의 개발 허브. 이슈 {len(model['issues'])}개 중 {done}개 완료, "
            f"패치 {len(model.get('patches', []))}건, 내보낸 날 {model['fetched'][:10]}.")
    tags = "".join(f'<meta property="{k}" content="{v}">\n' for k, v in [
        ("og:type", "website"), ("og:title", "NCAIFinal 개발 허브"), ("og:description", desc),
        ("og:image", SITE + PREVIEW), ("og:image:width", "640"), ("og:image:height", "400"), ("og:url", SITE)])
    tags += f'<meta name="twitter:card" content="summary_large_image">\n<meta name="description" content="{desc}">\n'
    return html.replace("</title>\n", "</title>\n" + tags, 1)


def preview(index):
    """index.html 첫 화면을 Edge 헤드리스로 찍어 preview.webp로 덮어쓴다. 실패하면 경고만 한다."""
    edge = next((p for p in EDGES if os.path.isfile(p)), None)
    if not edge:
        return "경고: Edge가 없어 preview를 만들지 못했다(이전 파일을 둔다)"
    prof = tempfile.mkdtemp(prefix="hub-preview-")  # 사용자 Edge 프로필과 분리. 경로에 한글이 없게 임시 폴더에 찍는다
    tmp = os.path.join(prof, "shot.png")
    url = "file:///" + index.replace("\\", "/")
    size = 0
    for _ in range(3):  # 새 프로필 첫 실행은 빈 화면(수 KB)이 찍힐 때가 있다
        if os.path.exists(tmp):
            os.remove(tmp)
        try:
            subprocess.run([edge, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                            "--no-default-browser-check", f"--user-data-dir={prof}", "--window-size=1280,800",
                            "--virtual-time-budget=8000", f"--screenshot={tmp}", url],
                           capture_output=True, timeout=120)  # stderr의 fallback_task_provider ERROR는 정상
        except (OSError, subprocess.TimeoutExpired) as e:
            return f"경고: preview 캡처 실패: {e}"
        size = os.path.getsize(tmp) if os.path.isfile(tmp) else 0
        if size > 30000:
            break
    else:
        shutil.rmtree(prof, ignore_errors=True)
        return f"경고: preview가 빈 화면으로 찍혔다({size} bytes, 이전 파일을 둔다)"
    im = Image.open(tmp).convert("RGB")
    im = im.resize((640, round(im.height * 640 / im.width)), Image.LANCZOS)
    im.save(os.path.join(HERE, PREVIEW), "WEBP", quality=80, method=6)
    im.close()
    shutil.rmtree(prof, ignore_errors=True)
    return f"preview: {PREVIEW} {im.width}x{im.height} {os.path.getsize(os.path.join(HERE, PREVIEW)) / 1e3:.0f}KB"


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
                elif isinstance(x, str) and PRIVATE.match(x):
                    x = None  # 이슈·PR·커밋·보드 링크. 템플릿은 없으면 링크 없이 그린다
                else:
                    x = self.walk(x)
                out[k] = x
            return out
        if isinstance(v, list):
            return [y for y in (self.walk(x) for x in v) if y is not None]
        if isinstance(v, str):
            return scrub(v)
        return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO, help="원본 저장소")
    ap.add_argument("--ref", default="origin/main", help="내보낼 git ref")
    ap.add_argument("--offline", action="store_true", help="gh 호출 없이 직전 cache.json 사용")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not a.repo:
        sys.exit("NCAIFinal 저장소를 찾지 못했다. --repo <경로> 또는 환경 변수 NCAIFINAL_REPO로 알려 준다.")

    git(a.repo, "fetch", "-q", "origin")
    sha = extract(a.repo, a.ref)
    hub = load_hub(SRC_DIR)
    # .src는 git archive라 이력이 없어 원본 저장소에서 읽는다. 패치 내역은 main에 들어간 것만이라
    # --ref로 병합 전 브랜치를 미리 볼 때도 origin/main 기준이다(브랜치 커밋이 직접 커밋으로 섞이지 않게)
    hub.GIT_DIR, hub.IMG_REF, hub.MAIN_REF = a.repo, sha, git(a.repo, "rev-parse", "origin/main", text=True).strip()
    os.makedirs(hub.OUT_DIR, exist_ok=True)
    if a.offline:
        data = json.load(io.open(hub.CACHE, encoding="utf-8"))
    else:
        data = hub.fetch()
        with io.open(hub.CACHE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    model = hub.build(data)
    model["labMissing"] = []
    model["public"] = True
    for ents in model["lab"].values():
        for e in ents:
            e["versions"] = close_hidden(e.get("versions", []))

    os.makedirs(IMG_DIR, exist_ok=True)
    ex = Exporter(hub)
    model = ex.walk(model)

    tpl = io.open(os.path.join(SRC_DIR, "Tools", "dev-hub", "template.html"), encoding="utf-8").read()
    payload = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    html = og_tags(tpl.replace("/*__DATA__*/null", payload), model)
    index = os.path.join(HERE, "index.html")
    with io.open(index, "w", encoding="utf-8") as f:
        f.write(html)

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
    hits = audit(html)
    if hits:
        print(f"검사 실패: 공개하면 안 되는 문자열 {len(hits)}곳. 커밋하지 않는다.")
        for pos, ctx in hits[:30]:
            print(f"  {pos}: …{ctx}…")
        sys.exit(1)
    print("검사: 비공개 주소·이메일·로컬 경로·브랜치명 없음")
    print(preview(index))


if __name__ == "__main__":
    main()
