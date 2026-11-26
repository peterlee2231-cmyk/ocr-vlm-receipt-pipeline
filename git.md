# GitHub 업로드 가이드 — 여러 클라우드 공통

어느 클라우드에서든 git만 있으면 이 순서대로 하면 됩니다. 토큰 값은 파일에 기록하지 않고, 필요할 때 직접 붙여넣는다.

## 내 계정 정보

- 계정: `peterlee2231-cmyk`
- 출장 도우미 프로젝트 저장소: https://github.com/peterlee2231-cmyk/travel-assistant-chatbot (Private)

## 토큰 준비 (최초 1회)

1. GitHub → Settings → Developer settings → **Personal access tokens → Tokens (classic)** → Generate new token (classic)
2. 스코프는 **`repo`** 하나면 충분 (저장소 생성 + 푸시 모두 가능)
3. Expiration은 30~90일 권장 — 만료되면 재발급 후 각 클라우드에서 1회 재입력
4. fine-grained 토큰을 쓰려면 저장소 생성용으로 **Administration(쓰기)** 권한이 별도로 필요 (classic `repo` 스코프가 가장 편함)

## 클라우드마다 딱 1회 설정

```bash
git config --global user.name  "peterlee2231-cmyk"
git config --global user.email "peterlee2231-cmyk@users.noreply.github.com"
git config --global credential.helper store
```

`credential.helper store` 이후 첫 push에서만 Username(계정명)·Password(토큰)를 입력하면 저장되고, 그 뒤로는 무입력.

## 새 실습 프로젝트 올리기 (git + curl만 있으면 가능)

```bash
cd ~/프로젝트폴더
git init -b main
git add -A && git commit -m "실습 내용 첫 커밋"

# 저장소 자동 생성 — NAME과 토큰만 바꾸기
curl -s -X POST https://api.github.com/user/repos \
  -H "Authorization: Bearer ghp_토큰" \
  -d '{"name":"프로젝트명","private":true}'

git remote add origin https://github.com/peterlee2231-cmyk/프로젝트명.git
git push -u origin main
```

시크릿(.env, API 키)이 있는 프로젝트는 커밋 전에 `.gitignore`를 먼저 만들 것:

```gitignore
.env
__pycache__/
```

## gh CLI를 쓸 수 있는 클라우드 (GitHub Codespaces 등)

```bash
gh auth login        # 또는: export GH_TOKEN=ghp_토큰
gh repo create 프로젝트명 --private --source=. --push
```

init·commit·remote·push를 한 명령이 전부 처리한다.

## 이미 올려둔 프로젝트를 다른 클라우드에서 이어서 하기

```bash
# private 저장소 클론 — 토큰을 URL에 붙임
git clone https://ghp_토큰@github.com/peterlee2231-cmyk/프로젝트명.git

# 작업 후
git add -A && git commit -m "수정 내용" && git push
```

## 위키 문서 (wiki/)

이 프로젝트의 LLM 활용 지식 위키는 `wiki/` 폴더로 **저장소 안에 함께 버전 관리된다**(GitHub Wiki 탭이 아니다). 별도 업로드 절차는 없다 — 코드와 같은 커밋·푸시 흐름을 따른다.

```bash
# 위키를 고쳤거나 새 페이지를 만든 뒤 — 일반 파일과 동일하게
git add wiki/
git commit -m "wiki: 페이지 추가/수정 내용"
git push
```

- **GitHub 웹에서 보기**: 저장소 페이지 → `wiki/` 폴더 → 마크다운이 렌더링되어 바로 읽힌다. `wiki/Home.md`가 목차(인덱스)다.
- **여러 클라우드에서 이어서 작업할 때**: 시작 전 `git pull`로 최신 위키를 받아 둘 것 — 위키는 코드보다 고침이 잦다.
- **코드와 위키의 동기화**: 코드를 고친 커밋에서 위키의 라인 참조(`src/app.py:109` 형식)가 밀리지 않았는지 확인한다. 유지보수 규칙은 `wiki/Home.md`에 정리돼 있다.
- **git 없는 클라우드로 옮길 때**: 저장소 루트의 `wiki.md`(위키 단일 파일 번들)를 복사하거나 채팅에 통째로 붙여넣는다 — 파일 하나에 위키 전체가 들어있다. `wiki/` 폴더를 고치면 번들도 같은 커밋에서 재생성해 둘을 동기화한다.

## 주의사항

- **여러 클라우드에서 같은 저장소 작업**: 시작 전 `git pull`, 마칠 때 `push`를 습관화 — 충돌 방지.
- **토큰을 URL에 직접 넣으면** `.git/config`나 셸 기록에 남을 수 있다. 가능하면 `credential.helper store` 방식을 쓰고, URL 방식은 클론 등 어쩔 수 없을 때만.
- **대화형 입력이 안 되는 샌드박스**(채팅 기반 클라우드)에서는 push 대상 URL에 토큰을 포함시켜야 한다:
  `git push https://계정명:ghp_토큰@github.com/peterlee2231-cmyk/프로젝트명.git main`
- **토큰 노출 시**(채팅에 붙여넣은 경우 포함) 쓸모를 다하면 rotate(재발급+폐기)하는 것이 안전.
- 저장소 생성 403 오류가 나면 토큰 권한 부족(`repo` 스코프 누락 또는 fine-grained의 Administration 누락)이 원인이다.
