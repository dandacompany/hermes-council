# council

[![ci](https://github.com/dandacompany/hermes-council/actions/workflows/ci.yml/badge.svg)](https://github.com/dandacompany/hermes-council/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**칸반 기반 다중 프로필 회의**를 진행하는 Hermes 플러그인. 명명된 사회자와 패널 프로필이 격리된 보드에서 안건을 토론하고, 자기전파 카드로 스스로 진행한 뒤, 요약·결론 보고서·회의록 전문 3종을 만들어 준다.

흔한 "멀티 에이전트" 도구는 프롬프트 하나를 뿌리고 답을 이어 붙인다. `council`은 실제 회의를 돌린다 — 모든 발화자가 먼저 전체 기록을 읽고, 사회자가 다음 발언자와 수렴 시점을 판단하며, 회의록이 파일 하나에 실시간으로 쌓인다.

## 동작 원리

`council`은 의도적으로 얇다. `council_start`는 모드별 프로토콜을 본문에 담은 **킥오프 카드 1장**만 씨앗으로 만들고, 이후엔 칸반 워커가 다음 카드를 스스로 생성하며 게이트웨이 디스패처가 자동 실행한다. `~/.hermes/.council/<slug>/transcript.md`가 유일한 공식 기록이며, 카드는 프로토콜만 운반한다(회의록은 안 담음).

- **sequential** — 사회자 ↔ 패널 핑퐁. 각 발화자가 이전 대화를 모두 전달받는다(현실 회의처럼).
- **parallel** — 사회자가 패널을 동시에 디스패치(그 라운드엔 서로 못 봄)한 뒤, 전원 카드에 의존하는 종합 카드로 수렴.
- **max_turns** — 패널 발언(sequential) 또는 라운드(parallel) 상한.
- **allow_early_stop** — 사회자가 상한 전 수렴 허용. `council_stop`은 즉시 종합을 강제.

## 설치

**옵션 A — clone + copy(개발)**

```bash
git clone https://github.com/dandacompany/hermes-council
cp -R hermes-council ~/.hermes/plugins/council   # 레포 루트가 곧 플러그인
hermes -p <profile> plugins enable council               # opt-in은 프로필별
```

> 플러그인 디스커버리는 심링크를 따르지 않는다 — `council/`을 실디렉토리로 복사할 것. 활성화는 프로필별(bare hermes는 활성 프로필 사용). 패널 워커 프로필엔 플러그인 불필요.

**옵션 B — 플러그인 설치**

```bash
hermes plugins install dandacompany/hermes-council --enable
```

**확인**

```bash
hermes plugins list | grep council
hermes tools list  | grep council
hermes council --help
```

## 도구

핸들러는 Hermes 계약 `handle(args: dict, **kwargs) -> str`(JSON 문자열)를 따른다.

| 도구              | 역할                                                                                                                                      |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `council_start`   | 회의 씨앗 생성(topic, panel, moderator, mode, max_turns, allow_early_stop). slug/board/kickoff id 반환. `dry_run`은 디스패치 없이 계획만. |
| `council_status`  | 카드 상태, 회의록 섹션 수, FINAL 도달 여부, blocked 카드 복구 힌트.                                                                       |
| `council_collect` | 회의록을 `summary.md` / `report.md` / `transcript.export.md`로 분리. `out_dir` 지정 시 복사.                                              |
| `council_stop`    | 사회자에게 즉시 종합·종료를 지시하는 카드 주입.                                                                                           |

`council_start`·`council_status`는 `warnings`도 반환한다 — 프리플라이트(게이트웨이 미실행, manual 승인 모드로 인한 백그라운드 타임아웃 위험)와 회의록 린트(헤더 형식 오류, SUMMARY/FINAL 누락·중복). 막힌 회의는 `council_resume(slug)`로 복구한다.

이 외에 `/council` 슬래시 커맨드(목록/상태), `hermes council {start|run|status|list|collect|stop|resume|doctor}` CLI, 번들 `council` 스킬(운영 플레이북)이 등록된다.

### 더 풍부한 회의

- **브리프·역할** — `--brief <파일|텍스트>`로 안건 참고자료 첨부(`<slug>/brief.md`에 저장, 모든 워커가 읽음), `--role name="관점"`(반복)으로 패널별 지정 관점.
- **결정 로그** — 사회자 FINAL 카드가 `## [DECISIONS]`(결정·액션·미결)도 기록 → `council_collect`가 `decisions.md`로 분리.
- **멀티라운드 parallel** — `--mode parallel --max-turns N`은 N개 라운드; 매 라운드 패널 동시 발언 후 사회자가 종합하고 다음 라운드로.
- **doctor** — `hermes council doctor`가 플러그인 활성·게이트웨이 실행·kanban 도달·레지스트리 쓰기를 점검.
- **폭주 안전장치** — 회의마다 카드 상한을 두어, `council_status`가 `runaway`를 보고하고 `council run`은 사회자가 `max_turns`를 넘기면 강제 종합.
- **회의 중 개입** — `hermes council say <slug> "<지침>"`으로 종료 없이 사회자에게 지침 주입(다음 판단에 반영).
- **하우스키핑** — `council archive <slug>`(되돌림), `council rm <slug> --yes`(삭제), `council gc --days N`(오래된 archived 정리), `council list --all`.
- **재부착** — `council run --attach <slug>`는 진행 중(또는 오케스트레이터가 죽은) 회의에 재부착해 완주 대기·수집한다. 회의는 게이트웨이가 카드를 굴리므로 `run` 프로세스가 죽어도 살아남는다.
- **산출물 포맷** — `council collect --format md|json|html|all`은 구조화 `<slug>.json`(파싱된 발언+파트)과 자립형 `<slug>.html`도 생성한다.
- **HITL(사람 개입)** — `--hitl`은 사회자가 종료 전 `결정 요청` 게이트를 열고 대기하게 한다. `council status`가 `pending_decision`으로 표면화, `council decide <slug> "<선택>"`으로 응답·재개. `council vote <slug> "<질문>" A B`는 선택지 게이트를 연다. `council run`은 사람 게이트에서 자동 재개하지 않고 멈춘다. (패널끼리 투표는 `--mode parallel` + "A/B/C 투표" 브리프로.)

### 원샷 실행

`hermes council run`은 시작→완주 대기(막힌 카드 자동 재개)→자동 수집→완료 배너까지 한 명령으로:

```bash
hermes council run --topic "Q3 로드맵" --panel "mia,noah" --moderator sophie \
  --mode sequential --max-turns 3 --out ~/Downloads --timeout 1800
```

## 산출물

모두 `~/.hermes/.council/` 아래에 저장된다:

```
~/.hermes/.council/
  index.json                 # 전체 회의 목록
  <slug>/
    meta.json                # 설정 + 상태
    transcript.md            # 진행 중 회의록
    summary.md               # collect: 임원 요약
    report.md                # collect: 결론 보고서
    transcript.export.md     # collect: 헤더+TOC 붙인 전문
```

## 보안

- 회의는 **실존 프로필 워커**를 **격리 보드**(`council-<slug>`)에서 실행하므로 각 프로필의 도구·승인 모드를 그대로 상속한다 — 패널 프로필 권한을 그에 맞게 설정할 것.
- 플러그인은 시크릿을 다루지 않으며 로컬 `hermes` CLI로만 셸아웃한다.
- `council_start`는 존재하지 않는 프로필을 거부하고, `dry_run`으로 디스패치 전 카드 계획을 검토할 수 있다.

## Attribution

Hermes Agent 칸반 시스템(`kanban_create` fan-out + 게이트웨이 디스패처) 위에 구축. MIT 라이선스 — `LICENSE` 참조.

---

**Dante Labs** · [YouTube @dante-labs](https://youtube.com/@dante-labs) · datapod.k@gmail.com · [Discord](https://discord.com/invite/rXyy5e9ujs) · [Buy Me a Coffee](https://buymeacoffee.com/dante.labs)
