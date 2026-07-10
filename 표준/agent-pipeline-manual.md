# 🧩 agent-pipeline 템플릿 사용 매뉴얼

> **한 줄 요약** — `templates.zip`는 **계획→점검→구현→검증→최종테스트** 5단계 개발 프로세스를 서브에이전트 5개로 굳혀, 어느 Claude Code 프로젝트에나 **복사·치환만으로 심는** 정적 템플릿이다. 별도 오케스트레이터/런타임 코드 없이 게이트 로직이 각 에이전트 프롬프트에 문서로 박혀 있다.

## 핵심 아이디어 3가지

1. **게이트 방식** — 각 단계는 이전 단계 산출물의 판정이 통과일 때만 진행한다.
2. **문서 릴레이** — 단계 간 인계는 대화 맥락이 아니라 **파일**(PLAN/REVIEW/VERIFY/FINAL + CHANGELOG)로 한다.
3. **Codex가 실제 판정자** — 2·4단계(점검/검증)는 서브에이전트가 오케스트레이터일 뿐, 결함 판정 기준은 `codex exec` 결과다.

---

## 1. 패키지 구성

```
templates/agent-pipeline/
├─ README.md                     ← 적용법 + 치환 목록 (원본 안내서)
├─ CLAUDE.snippet.md             ← 대상 프로젝트 CLAUDE.md 에 붙일 정책 조각
├─ settings.local.template.json  ← .claude/settings.local.json 권한(Codex 실행 허용)
└─ agents/                       ← 대상 프로젝트의 .claude/agents/ 로 복사
   ├─ plan-writer.md      (1/5, Opus)         계획 수립
   ├─ plan-reviewer.md    (2/5, Opus + Codex) 계획 점검
   ├─ implementer.md      (3/5, Sonnet)       구현
   ├─ impl-verifier.md    (4/5, Opus + Codex) 구현 검증
   └─ final-tester.md     (5/5, Sonnet)       최종 테스트
```

---

## 2. 파이프라인 개요

```
① 계획 수립  → ② 계획 점검  → ③ 구현      → ④ 구현 검증  → ⑤ 최종 테스트
 plan-writer    plan-reviewer  implementer   impl-verifier  final-tester
 (Opus)         (Opus+Codex)   (Sonnet)      (Opus+Codex)   (Sonnet)
 PLAN_*.md      *_REVIEW.md    코드+CHANGELOG *_VERIFY_*.md  *_FINAL_*.md
                APPROVE/REVISE               PASS/FAIL      DONE/BLOCKED
```

| 단계 | 에이전트 | 모델 | 산출물(게이트) | 통과 조건 |
|---|---|---|---|---|
| 1 계획 수립 | plan-writer | Opus | `PLAN_<주제>.md` | — |
| 2 계획 점검 | plan-reviewer | Opus + **Codex** | `*_REVIEW.md` | **APPROVE** |
| 3 구현 | implementer | Sonnet | 코드 + CHANGELOG | 컴파일·회귀 PASS |
| 4 구현 검증 | impl-verifier | Opus + **Codex** | `*_VERIFY_*.md` | **PASS** |
| 5 최종 테스트 | final-tester | Sonnet | `*_FINAL_*.md` | **DONE** |

> ⚠️ **게이트 규칙** — 통과(APPROVE/PASS/DONE)가 아니면 다음 단계는 **작업하지 않고 종료**한다. 되돌림 흐름: REVISE→1로 / FAIL→3으로 / BLOCKED→3으로.

---

## 3. 적용 절차 (5스텝)

1. **에이전트 복사** — `agents/*.md` 5개를 대상 프로젝트의 `.claude/agents/` 로 복사.
2. **정책 삽입** — `CLAUDE.snippet.md` 내용을 대상 `CLAUDE.md` 에 붙임(작업 원칙 + 안전 제약 + 프로세스 표 + 변경 기록).
3. **권한 병합** — `settings.local.template.json` 을 참고해 `.claude/settings.local.json` 에 Codex 실행 허용 룰 추가.
4. **토큰 치환** — 아래 치환 표대로 모든 복사본에서 찾기·바꾸기.
5. **Codex 확인** — Codex CLI 설치 + 로그인 여부 확인(2·4단계 전제). 없으면 폴백으로 돌지만 판정 품질이 떨어진다.

---

## 4. 치환 표 (모든 파일 공통 — 찾기·바꾸기)

| 토큰 | 의미 | 예시(assignees) |
|---|---|---|
| `{{PROJECT_NAME}}` | 프로젝트 이름 | `assignees` |
| `{{PROJECT_ROOT}}` | 저장소 절대 경로(Codex `-C`) | `C:\Users\...\assignees` |
| `{{ARCH_DOCS}}` | 참조 설계/명세 문서명(쉼표 구분) | `SETUP_PROMPT.md` |
| `{{PYTHON}}` | 실행 인터프리터 | `.venv\Scripts\python.exe` |
| `{{COMPILE_CMD}}` | 컴파일/빌드 점검 명령 | `... -m py_compile <파일들>` |
| `{{TEST_CMD}}` | 오프라인 회귀 테스트 명령 | `... -m tests.test_rules` |
| `{{ENTRYPOINT}}` | 최종 e2e 진입점 | `... main.py report --key <KEY>` |
| `{{CODEX_BIN}}` | Codex 실행 파일 경로 | `$env:LOCALAPPDATA\Programs\OpenAI\Codex\bin\codex.exe` |
| `{{SAFETY_RULES}}` | 프로젝트 고유 안전 제약 | ↓ 4-1 |

### 4-1. `{{SAFETY_RULES}}` — 프로젝트 고유 "금지" 목록

전 에이전트에 공통 삽입되는 안전 제약. **프로젝트의 위험 지점에 맞게 반드시 다시 쓴다.**

- **assignees 예시**

```
- 실제 외부 쓰기(예: Jira --apply, 댓글/담당자/필드 변경) 금지 — 드라이런까지만.
- 원본 데이터 저장소(예: JIRA2 vector_db)에 쓰기 금지.
- reference/ 등 참고 전용 디렉터리 임포트 금지(로직 발췌·이식만).
- 의존성 버전 고정 유지, .env 변경 시 .env.example 동반 갱신, PII 마스킹 왕복 유지.
```

- **일반 프로젝트 예** — "프로덕션 DB/배포 명령 실행 금지", "비밀키·토큰 커밋 금지", "마이그레이션 자동 적용 금지".

---

## 5. 단계별 에이전트 상세

### ① plan-writer (1/5, Opus) — 계획 수립

- **임무**: 요청 기능/개편에 대한 **자기완결적** 계획 문서 작성(이 문서만 읽고 점검·구현 가능해야 함, 대화 맥락 의존 금지).
- **절차**: CLAUDE.md·참조문서·CHANGELOG·기존 PLAN 을 먼저 읽음 → 소스 조사로 "현재 코드 상태" 사실 기반 작성 → `PLAN_<주제>.md` 저장.
- **PLAN 필수 포함**: 5단계 프로세스 표(상태 "계획 단계 — 구현 금지"), 배경/목표, 현재 코드 상태, 상세 설계(모듈·데이터 계약·흐름), Phase 분할·파일 목록, 테스트·수용 기준, 안전 규칙, **"계획 점검 시 확인 요청 사항"**(점검자가 답할 미결 질문).
- **금지**: 코드 작성/수정, 외부 접근, 기존 PLAN 무단 삭제.

### ② plan-reviewer (2/5, Opus + Codex) — 계획 점검

- **구조**: 에이전트는 **오케스트레이터**, 실제 점검 수행자는 **Codex CLI**. Codex 실패 시에만 자체 점검(폴백).
- **점검 관점**: 사실 대조(계획의 "현재 코드 상태"가 실제 소스와 일치?), 정합성(아키텍처 원칙 충돌), 완결성(구현 가능 여부·엣지케이스·실패 경로), 위험(데이터 손상·롤백), 테스트(검증 가능성), 안전 규칙 위반, "확인 요청 사항" 각각에 명시적 답변.
- **산출물**: `<PLAN>_REVIEW.md` — 판정 **APPROVE/REVISE** + 결함 목록(심각도순, 파일:절) + 확인 요청 답변.
- **금지**: 소스/계획 문서 수정.

### ③ implementer (3/5, Sonnet) — 구현

- **착수 게이트**: PLAN + `*_REVIEW.md` 를 읽고 **판정이 APPROVE 가 아니면 구현하지 않고 종료**. 지시받은 **Phase 범위만** 구현(선구현 금지).
- **규칙**: 계획 설계 준수, 임의 변경 금지(편차는 보고서 명시, 중대하면 중단·보고), 새 결정적 로직엔 오프라인 테스트 추가.
- **완료 전 자체 검증(필수)**: 컴파일 통과 → 회귀 전체 PASS → 해당 Phase 오프라인 수용 기준 충족.
- **마무리**: CHANGELOG 맨 위에 변경 기록 추가.

### ④ impl-verifier (4/5, Opus + Codex) — 구현 검증

- **구조**: Codex 가 코드 리뷰 기본 수행자, 에이전트는 구동·정리 + **테스트 직접 실행**. **구현자 보고를 신뢰하지 않는다.**
- **절차**: 변경 파일 목록 확정 → Codex 코드 리뷰(계획 대비 대조 + **scope creep 도 결함**) → **직접 실행 검증**(컴파일·회귀 재확인·오프라인 수용 기준 재현) → 안전 규칙 감사.
- **철칙**: **테스트가 실패하면 Codex 가 PASS 여도 최종 판정은 FAIL.** 안전 규칙 위반 = 즉시 FAIL.
- **산출물**: `<PLAN>_VERIFY_<phase>.md` — 판정 **PASS/FAIL** + 결함(파일:줄, 확인됨/미재현) + 테스트 로그 요약.
- **금지**: 소스 수정(결함은 보고만 — 수정은 implementer 몫).

### ⑤ final-tester (5/5, Sonnet) — 최종 테스트

- **착수 게이트**: PLAN + `*_VERIFY_*.md` 를 읽고 **판정이 PASS 가 아니면 종료**.
- **절차**: 실데이터 수용 기준 실행(외부 조회·LLM·검색 등 **읽기**는 실제 실행) → **외부 쓰기는 드라이런까지만**(`--apply` 등 실제 반영 절대 금지) → e2e 스모크(회귀 1회 + 진입점 단건 → 산출물 표본 검사) → 성능·안정성 관찰.
- **산출물**: `<PLAN>_FINAL_<phase>.md` — 판정 **DONE/BLOCKED**. DONE 이면 CHANGELOG 해당 Phase 기록에 "최종 테스트 통과(날짜)" 한 줄 추가.

---

## 6. Codex 연동 (2·4단계 핵심)

**정규 호출** — 지시문을 파일로 저장 후 stdin 파이프(셸 특수문자·인코딩 깨짐 방지):

```powershell
Get-Content <지시문파일> -Raw -Encoding UTF8 |
  & "{{CODEX_BIN}}" exec `
    --skip-git-repo-check `
    -C "{{PROJECT_ROOT}}" `
    --sandbox danger-full-access `
    -
```

**플래그 사유**

- `--skip-git-repo-check` — git repo 아닐 수 있음
- `-C "{{PROJECT_ROOT}}"` — 작업 루트 고정
- `--sandbox danger-full-access` — Windows 비대화형에서 elevated 샌드박스가 UAC 승격 실패로 무응답→exit255 되므로 Codex 자체 샌드박스를 끄고 격리는 Claude Code 승인 게이트에 위임
- 끝의 `-` — stdin 입력
- `--ask-for-approval` **넣지 않음** — `codex exec` 는 기본이 비대화형(`approval: never`), 넣으면 무효 인자로 에러

**지시문 필수 포함**: ① 역할 지시("너는 비판적 검토자/리뷰어다, 결함을 찾아라, 칭찬 불필요, 심각도순+근거") ② 대상/참조 문서 절대경로 ③ 점검·검증 관점 전체 ④ 요구 출력 형식(판정 + 결함 목록).

> ⚠️ **불변 원칙** — 판정·결함 목록은 Codex 결과가 기준(임의 삭제 금지). Codex 실패(미설치/인증/오류) 시 그 사실을 보고서 맨 위에 명시하고 에이전트가 직접 점검(폴백). 단, **테스트 실행(회귀·컴파일)은 Codex 와 무관하게 에이전트가 항상 직접 수행.**

---

## 7. 주의사항 / 커스터마이징

- **모델 ID**: frontmatter `model:`(opus-4-8 / sonnet-5)은 필요 시 조정. 점검·검증(2·4)은 강한 모델, 구현·테스트(3·5)는 빠른 모델 권장.
- **danger-full-access 차단**: Claude Code auto 모드 분류기가 "Create Unsafe Agents"로 차단할 수 있음 → `settings.local.json` 의 allow 룰 필요(또는 auto 모드 밖 실행). **JSON 경로 백슬래시는 `\\` 로 이스케이프.**
- **비파이썬 프로젝트**: `{{PYTHON}}`/`{{COMPILE_CMD}}`/`{{TEST_CMD}}`/`{{ENTRYPOINT}}` 를 해당 스택으로 교체 — 예: `npm test` / `tsc --noEmit` / `npm run dev` / `go test ./...`.
- **호출법**: 대상 프로젝트에서 자연어로 지시 — 예) `"plan-reviewer 서브에이전트로 PLAN_X.md 점검해줘"`.

---

## 8. 빠른 시작 체크리스트

- [ ] `agents/*.md` 5개 → 대상 `.claude/agents/` 복사
- [ ] `CLAUDE.snippet.md` → 대상 `CLAUDE.md` 에 붙임
- [ ] `settings.local.template.json` → `.claude/settings.local.json` 권한 병합 (백슬래시 `\\` 이스케이프)
- [ ] 9개 `{{TOKEN}}` 전체 찾기·바꾸기 (특히 `{{SAFETY_RULES}}` 는 프로젝트 맞춤 재작성)
- [ ] `codex --version` / `codex login status` 확인
- [ ] 시운전: "plan-writer 로 PLAN_테스트.md 작성해줘" → REVIEW → 구현 → VERIFY → FINAL 순 게이트 확인

---

# 📦 원본 템플릿 소스 8종 (복사용)

> 아래 코드블록을 그대로 복사해 대상 프로젝트에 파일로 저장하면 된다. `{{TOKEN}}` 은 위 §4 치환 표대로 바꾼다.

## `README.md`

````
# 서브에이전트 5단계 게이트 파이프라인 — 이식용 템플릿

다른 Claude Code 프로젝트에 **계획→점검→구현→검증→최종테스트** 5단계 서브에이전트
파이프라인을 그대로 심기 위한 정적 템플릿이다. 파일을 복사하고 `{{PLACEHOLDER}}` 토큰만
치환하면 동작한다. 별도 오케스트레이터/런타임 코드는 없다 — 연동(게이트) 로직은 각
에이전트 프롬프트 안에 문서로 박혀 있다.

## 1) 구성

```
templates/agent-pipeline/
	README.md                        ← (이 파일) 적용법 + 치환 목록
	agents/                          ← 대상 프로젝트의 .claude/agents/ 로 복사
		plan-writer.md      (1/5, Opus)
		plan-reviewer.md    (2/5, Opus + Codex)
		implementer.md      (3/5, Sonnet)
		impl-verifier.md    (4/5, Opus + Codex)
		final-tester.md     (5/5, Sonnet)
	CLAUDE.snippet.md                ← 대상 프로젝트 CLAUDE.md 에 붙일 정책 조각
	settings.local.template.json     ← 대상 프로젝트 .claude/settings.local.json 권한
```

## 2) 파이프라인 개요

```
① 계획 수립     → ② 계획 점검     → ③ 구현        → ④ 구현 검증     → ⑤ 최종 테스트
	plan-writer      plan-reviewer     implementer     impl-verifier     final-tester
	PLAN_*.md        *_REVIEW.md       코드+CHANGELOG  *_VERIFY_*.md     FINAL_*.md
		APPROVE/REVISE                    PASS/FAIL         DONE/BLOCKED
```

- **게이트**: 각 단계는 착수 전 이전 단계 산출물의 판정을 확인하고, 통과(APPROVE/PASS/DONE)
  가 아니면 작업하지 않고 종료한다. REVISE/FAIL/BLOCKED 면 앞 단계로 되돌아가 보완→재검증.
- **문서 릴레이**: 인계는 대화 맥락이 아니라 파일(PLAN/REVIEW/VERIFY/FINAL + CHANGELOG)로 한다.
- **Codex 가 실제 판정자**: 2·4단계(점검/검증)는 서브에이전트가 오케스트레이터일 뿐이고,
  결함 판정 기준은 `codex exec` 결과다. Codex 실행 실패 시에만 에이전트가 직접 점검(폴백).
  단, **테스트 실행(회귀·컴파일)은 Codex 와 무관하게 검증 에이전트가 항상 직접 수행**한다.

## 3) 적용 절차

1. `agents/*.md` 5개를 대상 프로젝트의 `.claude/agents/` 로 복사한다.
2. `CLAUDE.snippet.md` 내용을 대상 프로젝트 `CLAUDE.md` 에 붙인다(§작업 원칙 + §프로세스 표).
3. `settings.local.template.json` 을 참고해 `.claude/settings.local.json` 의 codex 실행
   허용 룰을 추가한다.
4. 아래 **치환 표**의 토큰을 모든 복사본에서 찾기·바꾸기 한다.
5. Codex CLI 설치 + 로그인 여부를 확인한다(2·4단계 전제). 없으면 폴백으로도 돌아가지만
   판정 품질이 떨어진다.

## 4) 치환 표 (모든 파일 공통 — 찾기·바꾸기)

| 토큰 | 의미 | 예시(assignees) |
|---|---|---|
| `{{PROJECT_NAME}}` | 프로젝트 이름 | `assignees` |
| `{{PROJECT_ROOT}}` | 저장소 절대 경로(Codex `-C`) | `C:\Users\MZC02-CHOHD\Documents\assignees` |
| `{{ARCH_DOCS}}` | 참조 설계/명세 문서명(쉼표 구분) | `SETUP_PROMPT.md` |
| `{{PYTHON}}` | 실행 인터프리터 | `.venv\Scripts\python.exe` |
| `{{COMPILE_CMD}}` | 컴파일/빌드 점검 명령 | `.venv\Scripts\python.exe -m py_compile <파일들>` |
| `{{TEST_CMD}}` | 오프라인 회귀 테스트 명령 | `.venv\Scripts\python.exe -m tests.test_rules` |
| `{{ENTRYPOINT}}` | 최종 e2e 진입점 | `.venv\Scripts\python.exe main.py report --key <KEY>` |
| `{{CODEX_BIN}}` | Codex 실행 파일 경로 | `$env:LOCALAPPDATA\Programs\OpenAI\Codex\bin\codex.exe` |
| `{{SAFETY_RULES}}` | 프로젝트 고유 안전 제약(아래 참고) | ↓ |

### `{{SAFETY_RULES}}` — 프로젝트 고유 "금지" 목록

각 에이전트에 공통 삽입되는 안전 제약이다. **프로젝트의 위험 지점에 맞게 다시 쓴다.**
assignees 예시:

```
- 실제 외부 쓰기(예: Jira --apply, 댓글/담당자/필드 변경) 금지 — 드라이런까지만.
- 원본 데이터 저장소(예: JIRA2 vector_db)에 쓰기 금지.
- reference/ 등 참고 전용 디렉터리 임포트 금지(로직 발췌·이식만).
- 의존성 버전 고정 유지, .env 변경 시 .env.example 동반 갱신, PII 마스킹 왕복 유지.
```

일반 프로젝트라면 예: "프로덕션 DB/배포 명령 실행 금지", "비밀키·토큰 커밋 금지",
"마이그레이션 자동 적용 금지" 등으로 교체.

## 5) 주의

- **모델 ID**: 에이전트 frontmatter 의 `model:`(opus-4-8 / sonnet-5)은 필요 시 조정한다.
  점검·검증(2·4)은 강한 모델, 구현·테스트(3·5)는 빠른 모델 조합을 권장.
- **Codex 플래그**: `--sandbox danger-full-access` 는 Claude Code auto 모드 분류기가
  "Create Unsafe Agents" 로 차단할 수 있다. 그때 `settings.local.json` 의 allow 룰이 필요하다.
- **비파이썬 프로젝트**: `{{PYTHON}}`/`{{COMPILE_CMD}}`/`{{TEST_CMD}}`/`{{ENTRYPOINT}}` 를
  해당 스택 명령(`npm test`, `tsc --noEmit`, `go test ./...`, `npm run dev` 등)으로 바꾼다.
- **호출법**: 대상 프로젝트에서 예) "plan-reviewer 서브에이전트로 PLAN_X.md 점검해줘".
````

## `CLAUDE.snippet.md`

````
<!--
  이 조각을 대상 프로젝트의 CLAUDE.md 에 붙인다.
  {{PLACEHOLDER}} 는 README.md 의 치환 표대로 바꾼다.
  이 파일 자체는 붙일 내용의 원본이며, 대상 CLAUDE.md 로 복사한 뒤에는 지워도 된다.
-->

## 작업 원칙 (무조건 준수)
- **소스 작성 전 구성/설계 먼저 제시(2~3안 비교) → 확인 → 구현**: 새 소스(스크립트/모듈/함수)를
  만들 때는 반드시 먼저 **최선의 방안 2~3가지**를 구성(파일 배치·함수 구조·동작 흐름)과
  함께 제시하고, **각 안의 장단점을 정리**해 보여준 뒤, 사용자 확인(방안 선택)을 받고 나서
  실제 코드를 작성한다. 확인 없이 바로 구현하지 않는다.
  - 기존 코드 조회·분석(Read/Grep 등)은 확인 없이 진행 가능.
  - 새 파일 생성, 로직 추가/변경은 확인 후 진행.
  - 방안이 사실상 1개뿐이거나(대안 비교 실익이 없는 단순 수정) 사용자가 이미 방식을
    구체적으로 지정한 경우는 예외 — 그 경우 단일안 설계만 제시하고 확인받는다.

## 상시 안전 제약 (전 단계 공통)
{{SAFETY_RULES}}

## 개발 프로세스 (서브에이전트 — .claude/agents/)
5단계 게이트: 각 단계 산출물의 판정이 통과일 때만 다음 단계 진행.

| 단계 | 에이전트 | 모델 | 산출물(게이트) |
|---|---|---|---|
| 1 계획 수립 | plan-writer | Opus | PLAN_<주제>.md |
| 2 계획 점검 | plan-reviewer | **Codex(기본)** / LLM 폴백 | *_REVIEW.md — APPROVE/REVISE |
| 3 구현 | implementer | Sonnet | 코드 + CHANGELOG (Phase 단위) |
| 4 구현 검증 | impl-verifier | **Codex(기본)** / LLM 폴백 | *_VERIFY_*.md — PASS/FAIL |
| 5 최종 테스트 | final-tester | Sonnet | *_FINAL_*.md — DONE/BLOCKED |

- 점검/검증(2·4)은 에이전트가 Codex CLI(`{{CODEX_BIN}}`)를 구동하는 구조 —
  판정·결함 목록은 `codex exec` 결과가 기준이고, 비판적 검토 지침을 Codex 지시문에
  주입한다. Codex 실행 실패 시에만 에이전트가 직접 점검(폴백, 사유 명기).
  테스트 실행(회귀·컴파일)은 Codex 와 무관하게 에이전트가 항상 직접 수행.
- Codex 는 파일 읽기를 시키지 말고 대상 문서/소스 전문을 stdin 프롬프트에 포함해
  `Get-Content <지시문> -Raw -Encoding UTF8 | & "{{CODEX_BIN}}" exec --skip-git-repo-check
  -C "{{PROJECT_ROOT}}" --sandbox danger-full-access -` 로 전달한다(검증된 우회 방식).
- 모든 에이전트: 실제 외부 쓰기 금지(드라이런까지), 원본 데이터 저장소 쓰기 금지.
- 호출 예: "plan-reviewer 서브에이전트로 PLAN_<주제>.md 점검해줘"

## 변경 기록
새 작업을 완료하면 CLAUDE.md 가 아니라 CHANGELOG.md 맨 위에 기록할 것
(CLAUDE.md 는 매 턴 자동 로드되므로 간결하게 유지).
````

## `settings.local.template.json`

````json
{
  "_comment": "대상 프로젝트 .claude/settings.local.json 에 병합. 핵심은 Codex exec 실행 허용 룰. {{CODEX_BIN}} 경로는 백슬래시를 JSON 이스케이프(\\\\)로 넣어야 한다. auto 모드 분류기가 danger-full-access 를 차단할 때 이 allow 룰이 필요하다.",
  "permissions": {
    "allow": [
      "PowerShell(& \"$env:LOCALAPPDATA\\\\Programs\\\\OpenAI\\\\Codex\\\\bin\\\\codex.exe\" exec*)",
      "PowerShell(& \"$env:LOCALAPPDATA\\\\Programs\\\\OpenAI\\\\Codex\\\\bin\\\\codex.exe\" --version)",
      "PowerShell(& \"$env:LOCALAPPDATA\\\\Programs\\\\OpenAI\\\\Codex\\\\bin\\\\codex.exe\" login status)",
      "Bash(codex --version)"
    ]
  }
}
````

## `agents/plan-writer.md` (발췌)

```
   - 진행 프로세스 표(5단계 역할), 상태 표기: **"계획 단계 — 구현 금지"**
   - 배경/목표, 현재 코드 상태, 상세 설계(모듈·데이터 계약·흐름)
   - 구현 단계(Phase 분할, Phase 별 파일 목록)
   - 테스트·수용 기준(오프라인 회귀 + 실데이터 검증 구분)
   - 제약·주의(프로젝트 안전 규칙):
{{SAFETY_RULES}}
   - "계획 점검 시 확인 요청 사항" 목록(점검자가 답해야 할 미결 질문)
4. CLAUDE.md 진행 상황 절에 계획 문서 포인터를 한 줄 추가한다.

## 금지
- 소스 코드 작성/수정 (계획만 작성한다)
- 외부 시스템 접근/쓰기
- 기존 계획 문서를 무단 삭제 (개정 시 문서 안에 개정 이력 남길 것)

## 완료 보고
최종 메시지에 계획 문서 경로, 설계 핵심 결정 3~5개, 점검자에게 넘길 미결 질문 목록을 요약한다.
```

## `agents/plan-reviewer.md` (전문)

````
---
name: plan-reviewer
description: "[2/5 계획 점검] PLAN 문서를 구현 전에 점검한다(Codex 병행). 사용자가 '계획 점검', 'PLAN 리뷰', '계획 검토해줘'를 요청할 때 사용. 소스 수정 금지, 점검 보고서만 작성."
model: claude-opus-4-8
tools: Read, Grep, Glob, Write, Bash, PowerShell
---

너는 {{PROJECT_NAME}} 프로젝트의 **계획 점검 담당(2/5 단계)**의 실행자다.
**점검의 기본 수행자는 Codex CLI 이고, 너는 Codex 를 구동·정리하는 오케스트레이터다.**
Codex 가 실패할 때만 네가 직접 점검한다(폴백).

## 프로세스 위치
계획 수립(plan-writer) → 계획 점검(너/Codex) → 구현(implementer) → 구현 검증(impl-verifier) → 최종 완료 테스트(final-tester)

## 기본 경로: Codex 점검 (필수 선행)
1. 아래 정규 명령으로 실행한다. **점검 지시는 스크래치패드 등 격리 경로에 파일로 저장한
   뒤 stdin 으로 파이프**한다(셸 특수문자·인코딩 깨짐 방지). 정규 호출 형태:

```
Get-Content <지시문파일> -Raw -Encoding UTF8 |
	& "{{CODEX_BIN}}" exec `
		--skip-git-repo-check `
		-C "{{PROJECT_ROOT}}" `
		--sandbox danger-full-access `
		-
```

   - 플래그 사유: `--skip-git-repo-check`(git repo 아닐 수 있음), `-C`(작업 루트 고정),
     `--sandbox danger-full-access`(Windows 비대화형에서 elevated 샌드박스가 UAC 승격
     실패로 무응답→exit255 되므로 Codex 자체 샌드박스를 끄고 격리는 Claude Code 승인
     게이트에 위임), `-Encoding UTF8`(지시문 글자 깨짐 방지), 끝의 `-`(stdin). 참고:
     `codex exec` 는 기본이 비대화형(`approval: never`)이라 `--ask-for-approval` 플래그는
     넣지 않는다(무효 인자로 에러남).
   - **주의**: `danger-full-access` 는 Claude Code auto 모드 분류기가 차단할 수 있다
     ("Create Unsafe Agents"). 차단되면 사용자가 auto 모드 밖에서 실행하거나
     `.claude/settings.json` 에 해당 codex 명령 permission allow-rule 을 추가해야 한다.
     승인/허용이 안 되면 아래 폴백(자체 점검)으로 전환하고 사유를 보고서에 명기한다.
   - 지시문 파일에는 반드시 포함:
     - **역할 지시**: "너는 구현자가 아니라 비판적 검토자다. 계획의 결함을 찾는 것이
       임무이며 칭찬·요약은 불필요하다. 결함은 심각도 높은 순으로, 근거(파일:절)와 함께
       제시하라. 실제 소스와 대조해 계획의 전제가 사실인지 확인하라."
     - 대상 PLAN 문서 절대경로 + 참조 문서(CLAUDE.md, {{ARCH_DOCS}}) 절대경로
       + 소스 대조 대상 경로
     - 아래 '점검 관점' 전체와 계획 문서의 '확인 요청 사항' 목록
     - 요구 출력 형식: 판정(APPROVE/REVISE) + 결함 목록(심각도순) + 확인 요청 사항 답변
2. Codex 출력이 길거나 부족하면 후속 `codex exec` 로 보완 질의한다(동일 플래그 사용).
3. Codex 결과를 보고서로 정리한다 — **판정과 결함 목록은 Codex 결과가 기준**이다.
   네가 Codex 결함 중 명백한 오류(존재하지 않는 파일 지적 등)를 발견하면 해당 항목에
   '실행자 검증 결과' 주석을 달되, 임의로 삭제하지 않는다.

## 폴백 경로: 자체 점검 (Codex 실행 불가 시에만)
Codex 실행이 실패(미설치/인증 만료/오류)하면 그 사실과 오류를 보고서 맨 위에 명시하고,
네가 아래 점검 관점으로 직접 점검해 판정한다.

## 점검 관점 (Codex 지시에 포함, 폴백 시 직접 적용)
- 사실 대조: 계획이 인용한 "현재 코드 상태"가 실제 소스와 일치하는가
  (존재하지 않는 함수/계약 전제 = 결함)
- 정합성: 기존 아키텍처 원칙과 충돌 여부
- 완결성: 구현자가 이 문서만으로 구현 가능한가(계약·엣지케이스·실패 경로 누락)
- 위험: 데이터 손상 가능 지점(기존 DB/파일 덮어쓰기, 동시성), 롤백 가능성
- 테스트: 수용 기준이 검증 가능하게 서술됐는가
- 안전 규칙 위반 여부:
{{SAFETY_RULES}}
- 계획 문서의 "확인 요청 사항" 각각에 명시적으로 답할 것

## 보고서 저장
점검 보고서를 `<PLAN파일명>_REVIEW.md` 로 저장한다. 형식:
- 점검 수행자 명시: Codex(기본) 또는 자체 폴백(사유 포함)
- 판정: **APPROVE**(구현 진행 가능) / **REVISE**(수정 후 재점검 필요) 중 하나
- 결함 목록(심각도 높은 순, 파일:절 참조), 확인 요청 사항 답변, 수정 요구 사항

## 금지
- 소스 코드/계획 문서 수정 (보고서 작성만). 외부 시스템 쓰기.

## 완료 보고
최종 메시지에 판정(APPROVE/REVISE), 핵심 결함 상위 3건, 보고서 경로를 요약한다.
````

## `agents/implementer.md` (발췌)

```
3. 계획의 해당 Phase 수용 기준 중 오프라인 항목 충족 확인

## 마무리
- CHANGELOG.md 맨 위에 변경 기록 추가(설계 채택·파일·검증 결과), CLAUDE.md 는 실행
  방법이 바뀐 경우만 갱신.
- 최종 메시지: 구현 범위(Phase), 신규/변경 파일 목록, 테스트 결과 수치, 계획 대비
  편차(없으면 '없음'), impl-verifier 가 확인해야 할 포인트.
```

## `agents/impl-verifier.md` (발췌)

````
   읽고 Phase 범위의 변경/신규 파일 목록을 확정한다.
2. **[기본 경로] Codex 코드 리뷰 (필수 선행)** — 아래 정규 명령으로 실행.
   **검증 지시는 스크래치패드 등 격리 경로에 파일로 저장한 뒤 stdin 으로 파이프**한다
   (셸 특수문자·인코딩 깨짐 방지). 정규 호출 형태:

```
Get-Content <지시문파일> -Raw -Encoding UTF8 |
	& "{{CODEX_BIN}}" exec `
		--skip-git-repo-check `
		-C "{{PROJECT_ROOT}}" `
		--sandbox danger-full-access `
		-
```

   - 플래그 사유: `--skip-git-repo-check`(git repo 아닐 수 있음), `-C`(작업 루트 고정),
     `--sandbox danger-full-access`(Windows 비대화형에서 elevated 샌드박스가 UAC 승격
     실패로 무응답→exit255 되므로 Codex 자체 샌드박스를 끄고 격리는 Claude Code 승인
     게이트에 위임), `-Encoding UTF8`(지시문 글자 깨짐 방지), 끝의 `-`(stdin). 참고:
     `codex exec` 는 기본이 비대화형이라 `--ask-for-approval` 플래그는 넣지 않는다.
   - **주의**: `danger-full-access` 는 Claude Code auto 모드 분류기가 차단할 수 있다
     ("Create Unsafe Agents"). 차단되면 사용자가 auto 모드 밖에서 실행하거나
     `.claude/settings.json` 에 allow-rule 을 추가해야 한다. 승인/허용이 안 되면 아래
     3·폴백(자체 리뷰)으로 전환하고 사유를 보고서에 명기한다.
   - 검증 지시(지시문 파일)에는 반드시 포함:
     - **역할 지시**: "너는 구현자와 독립된 비판적 코드 리뷰어다. 결함을 찾는 것이
       임무이며 칭찬·요약은 불필요하다. 구현이 계획(설계·데이터 계약·흐름)대로인지
       대조하고, 계획 범위 밖 무단 변경(scope creep)도 결함으로 보고하라. 결함은
       심각도 높은 순으로 파일:줄 근거·재현 방법과 함께 제시하라."
     - 대상 파일 절대경로 목록 + PLAN 문서 절대경로 + 아래 '안전 규칙 감사' 목록 전체
     - 요구 출력 형식: 판정(PASS/FAIL) + 결함 목록(심각도순, 파일:줄, 재현 방법)
   - **판정과 결함 목록은 Codex 결과가 기준**이다. Codex 가 지적한 결함은 가능한 한
     직접 재현해 '확인됨/미재현'을 표기하되, 임의로 삭제하지 않는다.
3. **[폴백] 자체 리뷰 (Codex 실행 불가 시에만)**: Codex 실패(미설치/인증/오류) 사실과
   오류 내용을 보고서 맨 위에 명시하고, 위 역할 지시와 동일한 관점(계획 대비 대조,
   scope creep, 안전 규칙 감사)으로 네가 직접 리뷰해 판정한다.
4. **직접 실행 검증 (Codex 와 무관하게 항상 네가 수행)**:
   - 컴파일: `{{COMPILE_CMD}}`
   - 회귀 테스트 전체 PASS 재확인: `{{TEST_CMD}}`
   - 계획의 수용 기준 중 오프라인 항목을 직접 재현
   - **테스트가 실패하면 Codex 판정이 PASS 여도 최종 판정은 FAIL** 이다.
5. **안전 규칙 감사** (Codex 지시에 포함 + 네가 교차 확인, 위반 = 즉시 FAIL):
{{SAFETY_RULES}}
6. 검증 보고서를 `<PLAN파일명>_VERIFY_<phase>.md` 로 저장한다. 형식:
   - 검증 수행자 명시: Codex(기본)+테스트 직접 실행 / 자체 폴백(사유 포함)
   - 판정: **PASS**(최종 테스트 진행 가능) / **FAIL**(구현 보완 필요)
   - 결함 목록(심각도순, 파일:줄, 확인됨/미재현 표기), 테스트 실행 로그 요약

## 금지
- 소스 코드 수정(발견한 결함은 고치지 말고 보고만 한다 — 수정은 implementer 의 몫)
- 실제 외부 쓰기 실행

## 완료 보고
최종 메시지에 판정(PASS/FAIL), 테스트 수치, 핵심 결함 상위 3건(있으면), 보고서 경로를 요약한다.
````

## `agents/final-tester.md` (발췌)

```
  - 판정: **DONE**(운영 투입 가능) / **BLOCKED**(결함 — implementer 재작업 필요)
  - 실행한 시나리오와 결과, 산출물 경로, 관찰된 이상 징후
- DONE 이면 CHANGELOG.md 맨 위 해당 Phase 기록에 "최종 테스트 통과(날짜)" 한 줄을 추가한다.

## 금지
- 소스 코드 수정(결함 발견 시 BLOCKED 로 보고만)
- 실제 외부 쓰기:
{{SAFETY_RULES}}

## 완료 보고
최종 메시지에 판정(DONE/BLOCKED), 실행 시나리오 수, 핵심 관찰 사항, 보고서 경로를 요약한다.
```
