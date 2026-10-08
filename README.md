# NCAIFinal 개발 허브 (공개본)

개인 프로젝트 NCAIFinal의 개발 허브(게임 위키) 정적 공개본입니다.
원본 저장소는 비공개라 공개본에서는 GitHub 이슈·PR·커밋·보드 링크를 빼고 허브 안 이슈 카드와 패치 내역으로 잇습니다.

- 보기: https://saltlake00.github.io/ncaifinal-hub/
- 출처: 레이아웃(그룹 사이드바·검색·히어로·표지 카드)과 도감 구조(엔티티 → 버전 탭 → 변형 비교)는 Stefan(@stefan_3d_ai)의 [Mr. Mak Workspace](https://github.com/witnesstodark/mr-mak-workspace)(MIT License)를 참고해 옮겼습니다. 디자인은 새로 만들었습니다.
- 갱신: `python export.py` → 결과 확인 → 파일 단위로 커밋·push
  - 마지막에 index.html을 검사해 비공개 저장소 주소·이메일·로컬 경로·브랜치명이 남아 있으면 종료 코드 1로 멈춥니다(본문 속 이슈·PR 주소는 `#번호`로 바꾸고 나머지는 가림 글자로 바꿉니다).
  - 패치 내역은 항상 원본의 `origin/main` 기준입니다. `--ref`로 병합 전 브랜치를 내보내도 브랜치 커밋이 섞이지 않습니다.
- 미리보기 썸네일: 내보낼 때마다 Edge 헤드리스로 첫 화면(1280×800)을 찍어 너비 640 webp로 `preview.webp`에 덮어씁니다. 주소는 https://saltlake00.github.io/ncaifinal-hub/preview.webp 로 고정이고 블로그 카드가 이 주소를 씁니다. `index.html`에는 같은 이미지를 가리키는 `og:` 태그가 들어갑니다. Edge가 없으면 경고만 하고 이전 파일을 둡니다.
- 이미지는 긴 변 1280px webp로 줄여 `img/`에 둡니다. 남이 그린 원본 그림(`원화-*`)과 외부 게임 의상을 참고한 폐기 시안(`export.py`의 `EXCLUDE`·`HIDE_VERSIONS`)은 넣지 않습니다.

## 다른 PC에서

```bash
git clone https://github.com/saltlake00/ncaifinal-hub.git ~/Documents/GitHub/ncaifinal-hub
cd ~/Documents/GitHub/ncaifinal-hub
pip install pillow
python export.py                                    # NCAIFinal 위치를 자동으로 찾는다
python export.py --repo E:/UnityProject/NCAIFinal   # 못 찾으면 직접 지정
```

- 필요한 것: NCAIFinal 저장소 클론(비공개, 읽기 권한), 로그인된 `gh`(보드 읽기), Python + Pillow.
- `.src/`(ref에서 꺼낸 원본, 약 340MB)는 git에서 뺐다. 첫 실행 때 만들어진다.
