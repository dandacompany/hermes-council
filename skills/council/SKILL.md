---
name: council
description: Run a kanban-based multi-profile meeting with council_start/status/collect/stop — sequential or parallel, then emit summary/report/transcript.
---

# council — 칸반 회의 운영 플레이북

명명된 사회자·패널 프로필이 격리된 칸반 보드에서 안건을 토론하고, 자기전파 카드로 자동 진행한 뒤 요약·결론보고서·전문을 만든다.

## 언제 쓰나

사용자가 "여러 프로필로 회의를 열어줘", "패널 토론 붙여줘", "이 주제로 위원회 돌려줘" 같은 요청을 할 때.

## 진행 절차

1. **시작** — `council_start(topic, panel[], moderator, mode, max_turns, allow_early_stop)`.
   - `mode="sequential"`: 사회자↔패널 핑퐁(현실 회의처럼 각 발화자가 이전 대화를 모두 받음).
   - `mode="parallel"`: 패널이 동시에 발언(같은 턴엔 서로 못 봄) → 사회자 종합. 라운드는 `max_turns`.
   - 프로필은 실존해야 한다(`hermes profile list`). 반환의 `warnings`(게이트웨이 미실행·manual 승인 모드)를 사용자에게 전달하라.
2. **관찰** — `council_status(slug)`를 주기적으로. `sections`·`final_reached`로 진행 파악, `warnings`(회의록 형식 문제)와 `blocked`(막힌 카드)를 확인. 대시보드의 `council-<slug>` 보드에서도 카드가 보인다.
3. **막힘 복구** — `blocked`가 있으면 `council_resume(slug)`로 재개(파일 도구 사용을 상기시키고 재디스패치). 원인은 대개 프로필의 manual 승인 모드다.
4. **조기 종료(선택)** — `council_stop(slug, reason)`으로 사회자에게 즉시 종합을 지시.
5. **수집** — `final_reached`가 참이면 `council_collect(slug, out_dir?)`로 3종 산출물 생성.

**원샷(사람용):** CLI `hermes council run …`은 시작→완주 대기→자동 수집(막힌 카드 자동 재개, 폭주 시 강제 종합)까지 한 번에. 에이전트는 블로킹을 피해 start→status→collect로 나눠 쓴다.

## 사람 개입 (HITL)

- `council_start(..., hitl=True)`이면 사회자가 FINAL 직전에 `결정 요청` 게이트를 열고 멈춘다.
- `council_status`의 `pending_decision`이 있으면 사람 응답 대기 — `council_decide(slug, choice)`로 응답하면 재개된다.
- `council_vote(slug, question, options)`로 언제든 사람 투표 게이트를 열 수 있다.
- `council run`은 사람 게이트를 만나면 자동 재개하지 않고 멈춘다 → `decide` 후 `run --attach`로 이어간다.
- 패널끼리 투표는 `--mode parallel` + "각자 A/B/C 투표하고 이유" 브리프로.

## 조율·정리

- **회의 중 지침** — 종료하지 않고 방향을 틀려면 `council_say(slug, note)`. 다음 사회자 카드가 그 지침을 읽고 반영한다.
- **폭주 감지** — `council_status`의 `runaway`가 참이면 사회자가 max_turns를 넘긴 것 — `council_stop(slug)`으로 강제 종합.
- **정리** — 끝난 회의는 `council_archive(slug)`(되돌림 가능). CLI로 `council rm <slug> --yes`(삭제), `council gc --days N`(오래된 archived 정리), `council list --all`.

## 산출물

`~/.hermes/.council/<slug>/`에 `summary.md`(요약), `report.md`(결론 보고서), `transcript.export.md`(전문). `out_dir` 지정 시 그 폴더에도 `<slug>-summary.md` 등으로 복사.

## 팁

- 진행이 멈춘 듯하면 `council_status`의 `blocked` 카드와 복구 명령을 확인.
- 회의는 게이트웨이 디스패처가 자동 실행한다(수동 개입 불필요). 첫 카드만 council_start가 디스패치한다.
- 큰 회의는 `max_turns`를 늘리고, 빠른 데모는 3 이하로.
